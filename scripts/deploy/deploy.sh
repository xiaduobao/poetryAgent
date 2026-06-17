#!/usr/bin/env bash
# 本地一键发布到阿里云 ECS：rsync 同步代码 → scp .env → 远程 docker compose build。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"

WITH_DATA=false
ENV_ONLY=false
PULL_ONLY=false

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/deploy.sh [选项]

选项:
  --with-data   额外同步 data/（语料、向量库、模型、postgres/redis 数据目录）
  --env-only    仅更新远端 .env 并重启容器
  --pull        仅拉取 ACR 镜像并重启（需 deploy.env 中 POETRY_AGENT_IMAGE）
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

_write_compose_env() {
    if [[ -n "${POETRY_AGENT_IMAGE:-}" ]]; then
        echo "==> 写入远端镜像地址..."
        ssh "${SSH_OPTS[@]}" "${REMOTE}" "printf 'POETRY_AGENT_IMAGE=%s\n' '${POETRY_AGENT_IMAGE}' > '${REMOTE_DIR}/.compose.env'"
    fi
}

echo "==> 测试 SSH 连接 (${REMOTE})..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "echo connected"

if [[ "${PULL_ONLY}" == true ]]; then
    : "${POETRY_AGENT_IMAGE:?请在 deploy.env 中设置 POETRY_AGENT_IMAGE}"
    _write_compose_env
    echo "==> 远端拉取镜像并重启..."
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh pull-up"
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh health" || true
    echo "==> 完成: http://${ECS_HOST}/"
    exit 0
fi

if [[ "${ENV_ONLY}" == true ]]; then
    if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
        echo "本地 .env 不存在: ${PROJECT_ROOT}/.env" >&2
        exit 1
    fi
    echo "==> 上传 .env..."
    scp "${SCP_OPTS[@]}" "${PROJECT_ROOT}/.env" "${REMOTE}:${REMOTE_DIR}/.env"
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

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    echo "==> 上传 .env..."
    scp "${SCP_OPTS[@]}" "${PROJECT_ROOT}/.env" "${REMOTE}:${REMOTE_DIR}/.env"
else
    echo "警告: 本地无 .env，请确保远端 ${REMOTE_DIR}/.env 已配置" >&2
fi

_write_compose_env

echo "==> 远程启动..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "chmod +x '${REMOTE_DIR}/scripts/deploy/'*.sh && cd '${REMOTE_DIR}' && ./scripts/deploy/remote-compose.sh up"

echo "==> 等待服务就绪..."
for i in $(seq 1 30); do
    if ssh "${SSH_OPTS[@]}" "${REMOTE}" "curl -sf --max-time 5 http://127.0.0.1:8000/api >/dev/null"; then
        echo "==> 部署成功: http://${ECS_HOST}/"
        exit 0
    fi
    sleep 5
done

echo "警告: 健康检查超时，请 SSH 登录查看日志:" >&2
echo "  ssh ${SSH_OPTS[*]} ${REMOTE}" >&2
echo "  cd ${REMOTE_DIR} && ./scripts/deploy/remote-compose.sh logs" >&2
exit 1
