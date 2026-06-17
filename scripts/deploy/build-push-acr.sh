#!/usr/bin/env bash
# 本地构建镜像并推送到阿里云 ACR（避免在 ECS 上 build）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/build-push-acr.sh [选项]

在本地 Mac 构建 Docker 镜像并 push 到阿里云容器镜像服务（ACR）。

前置：deploy.env 中配置 POETRY_AGENT_IMAGE、ACR_REGISTRY（可选 ACR_USERNAME/ACR_PASSWORD）

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
    echo "请先: cp scripts/deploy/deploy.env.example scripts/deploy/deploy.env" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "${DEPLOY_ENV}"

: "${POETRY_AGENT_IMAGE:?请在 deploy.env 中设置 POETRY_AGENT_IMAGE，例如 registry.cn-hangzhou.aliyuncs.com/your-ns/poetry-agent:latest}"

cd "${PROJECT_ROOT}"

echo "==> 构建镜像: ${POETRY_AGENT_IMAGE}"
# shellcheck disable=SC2086
docker build ${NO_CACHE} -t "${POETRY_AGENT_IMAGE}" .

if [[ -n "${ACR_REGISTRY:-}" ]]; then
    echo "==> 登录 ACR: ${ACR_REGISTRY}"
    if [[ -n "${ACR_USERNAME:-}" && -n "${ACR_PASSWORD:-}" ]]; then
        echo "${ACR_PASSWORD}" | docker login "${ACR_REGISTRY}" -u "${ACR_USERNAME}" --password-stdin
    else
        docker login "${ACR_REGISTRY}"
    fi
fi

echo "==> 推送镜像..."
docker push "${POETRY_AGENT_IMAGE}"

echo ""
echo "==> 完成。ECS 部署："
echo "  ./scripts/deploy/deploy.sh --pull"
echo "  或 SSH 后: cd /opt/poetry-agent && ./scripts/deploy/remote-compose.sh pull-up"
