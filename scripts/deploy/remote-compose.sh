#!/usr/bin/env bash
# 在 ECS 上管理 Docker Compose（仅 ACR 拉取，不 build）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_DIR}"

if [[ -f "${PROJECT_DIR}/.compose.env" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "${PROJECT_DIR}/.compose.env"
    set +a
fi

: "${POETRY_AGENT_IMAGE:?缺少 POETRY_AGENT_IMAGE，请检查 deploy.env 与 .compose.env}"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)

compose() {
    docker compose "${COMPOSE_FILES[@]}" "$@"
}

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/remote-compose.sh <command>

命令:
  up          从 ACR 拉取镜像并启动
  pull-up     同 up（拉取最新镜像后启动）
  down        停止并移除容器
  restart     重启服务
  logs        查看日志（follow）
  ps          查看容器状态
  health      检查 /api 与 nginx 健康状态
EOF
}

cmd_pull_up() {
    echo "==> 拉取镜像: ${POETRY_AGENT_IMAGE}"
    compose pull poetry-agent
    compose up -d --no-build
}

cmd_down() {
    compose down
}

cmd_restart() {
    compose restart
}

cmd_logs() {
    compose logs -f --tail=100
}

cmd_ps() {
    compose ps
}

cmd_health() {
    local url="http://127.0.0.1:8000/api"
    local nginx_ok=false
    if curl -sf --max-time 10 "${url}" >/dev/null; then
        echo "OK: app ${url}"
    else
        echo "FAIL: app ${url} 不可达" >&2
    fi
    if systemctl is-active nginx >/dev/null 2>&1; then
        nginx_ok=true
        echo "OK: nginx $(systemctl is-active nginx)"
    else
        echo "FAIL: nginx 未运行。请执行: sudo systemctl start nginx" >&2
        echo "      或本地运行: ./scripts/deploy/setup-ecs.sh" >&2
    fi
    if curl -sf --max-time 10 "http://127.0.0.1/" >/dev/null; then
        echo "OK: http://127.0.0.1/ (nginx -> app)"
    else
        echo "FAIL: http://127.0.0.1/ 不可达（检查 nginx 配置与安全组 80 端口）" >&2
    fi
    compose ps
    if curl -sf --max-time 10 "${url}" >/dev/null && [[ "${nginx_ok}" == true ]]; then
        return 0
    fi
    return 1
}

COMMAND="${1:-}"
case "${COMMAND}" in
    up|pull-up) cmd_pull_up ;;
    down) cmd_down ;;
    restart) cmd_restart ;;
    logs) cmd_logs ;;
    ps) cmd_ps ;;
    health) cmd_health ;;
    *)
        usage
        exit 1
        ;;
esac
