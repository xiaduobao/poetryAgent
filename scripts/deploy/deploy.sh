#!/usr/bin/env bash
# 发布到 ECS：rsync 配置与 data → scp .env.prod → 从 ACR 拉取镜像启动
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"
PROD_ENV="${PROJECT_ROOT}/.env.prod"

WITH_DATA=false
ENV_ONLY=false
PULL_ONLY=false

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/deploy.sh [选项]

镜像在 ACR 构建完成后，用本脚本部署到 ECS（只 pull，不 build）。

选项:
  --with-data   额外同步 data/（语料、向量库、模型、postgres/redis 数据目录）
  --env-only    仅更新远端 .env.prod 并重启容器
  --pull        仅拉取 ACR 最新镜像并重启
  -h, --help    显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-data) WITH_DATA=true; shift ;;
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
    _upload_prod_env
    echo "==> 重启容器..."
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh restart"
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh health" || true
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
    echo "==> rsync 同步 data/..."
    rsync -avz \
        -e "${RSYNC_SSH}" \
        "${PROJECT_ROOT}/data/" \
        "${REMOTE}:${REMOTE_DIR}/data/"
fi

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
