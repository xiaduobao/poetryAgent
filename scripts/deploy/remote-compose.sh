#!/usr/bin/env bash
# 在 ECS 上管理 Docker Compose 服务（由 deploy.sh 调用，也可 SSH 后手动执行）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_DIR}"

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/remote-compose.sh <command>

命令:
  up        构建并启动（docker compose up -d --build）
  down      停止并移除容器
  restart   重启服务
  logs      查看日志（follow）
  ps        查看容器状态
  health    检查 /api 健康状态
EOF
}

cmd_up() {
    docker compose up -d --build
}

cmd_down() {
    echo "提示: 仅停止容器，./data/postgres 与 ./data/redis 数据会保留。"
    echo "      若执行 docker compose down -v 将删除命名卷（当前 compose 已改用绑定目录）。"
    docker compose down
}

cmd_restart() {
    docker compose restart
}

cmd_logs() {
    docker compose logs -f --tail=100
}

cmd_ps() {
    docker compose ps
}

cmd_health() {
    local url="http://127.0.0.1:8000/api"
    if curl -sf --max-time 10 "${url}" >/dev/null; then
        echo "OK: ${url}"
        docker compose ps
        return 0
    fi
    echo "FAIL: ${url} 不可达" >&2
    docker compose ps || true
    return 1
}

COMMAND="${1:-}"
case "${COMMAND}" in
    up) cmd_up ;;
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
