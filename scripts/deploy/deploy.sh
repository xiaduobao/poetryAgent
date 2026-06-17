#!/usr/bin/env bash
# 发布到 ECS：rsync 配置与 data → scp .env.prod → 从 ACR 拉取镜像启动
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"
PROD_ENV="${PROJECT_ROOT}/.env.prod"

WITH_DATA=false
WITH_MODELS=false
MODELS_ONLY=false
ENV_ONLY=false
PULL_ONLY=false

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/deploy.sh [选项]

镜像在 ACR 构建完成后，用本脚本部署到 ECS（只 pull，不 build）。

选项:
  --with-data     额外同步 data/（语料、向量库、模型；不含 postgres/redis）
  --with-models   额外同步 data/models/（可与 --with-data 合用）
  --models-only   仅同步 models 并重建 poetry-agent（不 rsync 代码、不 pull 镜像）
  --env-only      仅更新远端 .env.prod 并重建 poetry-agent 容器（不 pull 镜像）
  --pull          仅拉取 ACR 最新镜像并重启
  -h, --help      显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-data) WITH_DATA=true; shift ;;
        --with-models) WITH_MODELS=true; shift ;;
        --models-only) MODELS_ONLY=true; shift ;;
        --env-only) ENV_ONLY=true; shift ;;
        --pull) PULL_ONLY=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ ! -f "${DEPLOY_ENV}" ]]; then
    echo "缺少 ${DEPLOY_ENV}" >&2
    echo "请先执行: cp scripts/deploy/deploy.env.example scripts/deploy/deploy.env" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "${DEPLOY_ENV}"

: "${ECS_HOST:?请在 deploy.env 中设置 ECS_HOST}"
: "${ECS_USER:=root}"
: "${ECS_PORT:=22}"
: "${REMOTE_DIR:=/opt/poetry-agent}"
: "${POETRY_AGENT_IMAGE:?请在 deploy.env 中设置 POETRY_AGENT_IMAGE}"

SSH_KEY_EXPANDED="${SSH_KEY/#\~/$HOME}"
SSH_COMMON=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
SSH_OPTS=(-p "${ECS_PORT}" "${SSH_COMMON[@]}")
SCP_OPTS=(-P "${ECS_PORT}" "${SSH_COMMON[@]}")
if [[ -n "${SSH_KEY:-}" ]]; then
    if [[ ! -f "${SSH_KEY_EXPANDED}" ]]; then
        echo "SSH 私钥不存在: ${SSH_KEY_EXPANDED}" >&2
        exit 1
    fi
    SSH_OPTS+=(-i "${SSH_KEY_EXPANDED}")
    SCP_OPTS+=(-i "${SSH_KEY_EXPANDED}")
fi

REMOTE="${ECS_USER}@${ECS_HOST}"
RSYNC_SSH="ssh ${SSH_OPTS[*]}"

# _fix_app_data_permissions() {
#     echo "==> 修正 data/ 目录权限（app=1000, postgres=70, redis=999）..."
#     ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && bash scripts/deploy/fix-data-permissions.sh"
# }

_sync_data() {
    echo "==> rsync 同步 data/（排除 postgres/redis，属主映射为 1000:1000）..."
    rsync -avz \
        --chown=1000:1000 \
        --exclude 'postgres/' \
        --exclude 'redis/' \
        -e "${RSYNC_SSH}" \
        "${PROJECT_ROOT}/data/" \
        "${REMOTE}:${REMOTE_DIR}/data/"
}

_sync_models() {
    if [[ ! -d "${PROJECT_ROOT}/data/models" ]] || [[ -z "$(ls -A "${PROJECT_ROOT}/data/models" 2>/dev/null)" ]]; then
        echo "本地 data/models/ 为空，请先执行: python scripts/download_models.py" >&2
        exit 1
    fi
    echo "==> rsync 同步 data/models/（约数百 MB，请耐心等待）..."
    rsync -avz --progress \
        --chown=1000:1000 \
        -e "${RSYNC_SSH}" \
        "${PROJECT_ROOT}/data/models/" \
        "${REMOTE}:${REMOTE_DIR}/data/models/"
}

_upload_prod_env() {
    if [[ ! -f "${PROD_ENV}" ]]; then
        echo "本地 .env.prod 不存在: ${PROD_ENV}" >&2
        echo "请先执行: cp .env.prod.example .env.prod 并填写生产配置" >&2
        exit 1
    fi
    echo "==> 上传 .env.prod..."
    scp "${SCP_OPTS[@]}" "${PROD_ENV}" "${REMOTE}:${REMOTE_DIR}/.env.prod"
}

_write_compose_env() {
    echo "==> 写入远端镜像地址: ${POETRY_AGENT_IMAGE}"
    ssh "${SSH_OPTS[@]}" "${REMOTE}" \
        "printf 'POETRY_AGENT_IMAGE=%s\n' '${POETRY_AGENT_IMAGE}' > '${REMOTE_DIR}/.compose.env'"
}

_acr_login_remote() {
    if [[ -n "${ACR_USERNAME:-}" && -n "${ACR_PASSWORD:-}" && -n "${ACR_REGISTRY:-}" ]]; then
        echo "==> ECS 登录 ACR (${ACR_REGISTRY})..."
        ssh "${SSH_OPTS[@]}" "${REMOTE}" \
            "echo '${ACR_PASSWORD}' | docker login '${ACR_REGISTRY}' -u '${ACR_USERNAME}' --password-stdin"
    fi
}

_remote_pull_up() {
    _acr_login_remote
    _write_compose_env
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh pull-up"
}

_sync_compose_config() {
    echo "==> 同步 compose 与部署脚本..."
    rsync -avz -e "${RSYNC_SSH}" \
        "${PROJECT_ROOT}/docker-compose.dev.yml" \
        "${PROJECT_ROOT}/docker-compose.prod.yml" \
        "${REMOTE}:${REMOTE_DIR}/"
    rsync -avz -e "${RSYNC_SSH}" \
        "${PROJECT_ROOT}/scripts/deploy/" \
        "${REMOTE}:${REMOTE_DIR}/scripts/deploy/"
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "chmod +x '${REMOTE_DIR}/scripts/deploy/'*.sh"
}

_remote_recreate() {
    _write_compose_env
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh recreate"
    echo "==> 校验容器已重建、环境变量已加载..."
    ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s "${REMOTE_DIR}" <<'EOS'
cd "$1"
set -a
# shellcheck source=/dev/null
[[ -f .compose.env ]] && source .compose.env
set +a
files=(-f docker-compose.prod.yml)
cid=$(docker compose "${files[@]}" ps -q poetry-agent)
echo "    容器 ID: ${cid}"
docker inspect --format '    创建时间: {{.Created}}' "${cid}"
docker exec "${cid}" printenv EMBEDDING_MODEL 2>/dev/null | sed 's/^/    EMBEDDING_MODEL=/'
EOS
}

echo "==> 测试 SSH 连接 (${REMOTE})..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "echo connected"

if [[ "${PULL_ONLY}" == true ]]; then
    echo "==> 拉取 ACR 镜像并重启..."
    _remote_pull_up
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh health" || true
    echo "==> 完成: http://${ECS_HOST}/"
    exit 0
fi

if [[ "${ENV_ONLY}" == true ]]; then
    _sync_compose_config
    _upload_prod_env
    #_fix_app_data_permissions
    echo "==> 重建容器以加载新 .env.prod（force-recreate，非 restart）..."
    _remote_recreate
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh health" || true
    echo "==> 完成: http://${ECS_HOST}/"
    exit 0
fi

if [[ "${MODELS_ONLY}" == true ]]; then
    _sync_models
   # _fix_app_data_permissions
    echo "==> 重建 poetry-agent 以重新挂载 models..."
    _remote_recreate
    ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s "${REMOTE_DIR}" <<'EOS'
cd "$1"
echo "==> ECS 上 models 目录:"
ls -la data/models/
cid=$(docker compose -f docker-compose.prod.yml ps -q poetry-agent)
docker exec "${cid}" ls -la /app/data/models/ 2>/dev/null || true
EOS
    echo "==> 完成: http://${ECS_HOST}/"
    exit 0
fi

echo "==> 创建远程目录 ${REMOTE_DIR}..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "mkdir -p '${REMOTE_DIR}'"

echo "==> rsync 同步项目..."
rsync -avz --delete \
    --exclude-from="${PROJECT_ROOT}/.rsyncignore" \
    -e "${RSYNC_SSH}" \
    "${PROJECT_ROOT}/" \
    "${REMOTE}:${REMOTE_DIR}/"

if [[ "${WITH_DATA}" == true ]]; then
    _sync_data
elif [[ "${WITH_MODELS}" == true ]]; then
    _sync_models
fi

# _fix_app_data_permissions

_upload_prod_env
_remote_pull_up

echo "==> 等待服务就绪..."
for i in $(seq 1 30); do
    if ssh "${SSH_OPTS[@]}" "${REMOTE}" "curl -sf --max-time 5 http://127.0.0.1:8000/api >/dev/null"; then
        echo "==> 部署成功: http://${ECS_HOST}/"
        echo "    镜像: ${POETRY_AGENT_IMAGE}"
        exit 0
    fi
    sleep 5
done

echo "警告: 健康检查超时，请 SSH 登录查看日志:" >&2
echo "  ssh ${SSH_OPTS[*]} ${REMOTE}" >&2
echo "  cd ${REMOTE_DIR} && ./scripts/deploy/remote-compose.sh logs" >&2
exit 1
