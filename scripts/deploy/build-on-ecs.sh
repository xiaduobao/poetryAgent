#!/usr/bin/env bash
# 在 ECS 上构建镜像并 push 到 ACR（不在本地 Mac build）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/build-on-ecs.sh [选项]

将代码同步到 ECS，在 ECS 上 docker build，并 push 到 ACR。
适合不在本地打镜像、利用 ECS 与 ACR 同区域网络的场景。

说明：ACR 个人版是镜像仓库，不提供「在 ACR 控制台里 build」；
      本脚本在 ECS 上 build，构建完成后 push 到你的 ACR 地址。

前置：deploy.env 中 POETRY_AGENT_IMAGE、ACR_REGISTRY；ECS 已 docker login ACR（或配置 ACR_USERNAME/ACR_PASSWORD）

选项:
  --no-cache   不使用 Docker 构建缓存
  -h, --help   显示帮助
EOF
}

NO_CACHE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ ! -f "${DEPLOY_ENV}" ]]; then
    echo "缺少 ${DEPLOY_ENV}" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "${DEPLOY_ENV}"

: "${ECS_HOST:?请在 deploy.env 中设置 ECS_HOST}"
: "${ECS_USER:=root}"
: "${ECS_PORT:=22}"
: "${REMOTE_DIR:=/opt/poetry-agent}"
: "${POETRY_AGENT_IMAGE:?请在 deploy.env 中设置 POETRY_AGENT_IMAGE}"
: "${ACR_REGISTRY:?请在 deploy.env 中设置 ACR_REGISTRY}"

SSH_KEY_EXPANDED="${SSH_KEY/#\~/$HOME}"
SSH_COMMON=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
SSH_OPTS=(-p "${ECS_PORT}" "${SSH_COMMON[@]}")
if [[ -n "${SSH_KEY:-}" ]]; then
    SSH_OPTS+=(-i "${SSH_KEY_EXPANDED}")
fi

REMOTE="${ECS_USER}@${ECS_HOST}"
RSYNC_SSH="ssh ${SSH_OPTS[*]}"
BUILD_DIR="${REMOTE_DIR}/build"

echo "==> 测试 SSH (${REMOTE})..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "echo connected"

echo "==> 同步构建上下文到 ECS ${BUILD_DIR}..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "mkdir -p '${BUILD_DIR}'"
rsync -avz --delete \
    --exclude-from="${PROJECT_ROOT}/.rsyncignore" \
    -e "${RSYNC_SSH}" \
    "${PROJECT_ROOT}/" \
    "${REMOTE}:${BUILD_DIR}/"

echo "==> ECS 登录 ACR..."
if [[ -n "${ACR_USERNAME:-}" && -n "${ACR_PASSWORD:-}" ]]; then
    ssh "${SSH_OPTS[@]}" "${REMOTE}" \
        "echo '${ACR_PASSWORD}' | docker login '${ACR_REGISTRY}' -u '${ACR_USERNAME}' --password-stdin"
else
    echo "提示: 未配置 ACR_USERNAME/ACR_PASSWORD，请确保 ECS 已执行过 docker login ${ACR_REGISTRY}"
fi

echo "==> ECS 上构建镜像: ${POETRY_AGENT_IMAGE}"
# shellcheck disable=SC2086
ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s -- "${BUILD_DIR}" "${POETRY_AGENT_IMAGE}" "${NO_CACHE}" <<'REMOTE_BUILD'
set -euo pipefail
BUILD_DIR="$1"
IMAGE="$2"
NO_CACHE="$3"
cd "${BUILD_DIR}"
echo "构建目录: $(pwd)"
if [[ -n "${NO_CACHE}" ]]; then
    docker build --no-cache -t "${IMAGE}" .
else
    docker build -t "${IMAGE}" .
fi
echo "==> push ${IMAGE}"
docker push "${IMAGE}"
REMOTE_BUILD

echo ""
echo "==> 构建并推送完成"
echo "  部署: ./scripts/deploy/deploy.sh --pull"
echo "  镜像: ${POETRY_AGENT_IMAGE}"
