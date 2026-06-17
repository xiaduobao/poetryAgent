#!/usr/bin/env bash
# 一次性初始化阿里云 ECS：安装 Docker、Nginx，并写入反向代理配置。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"
NGINX_CONF="${SCRIPT_DIR}/nginx/poetry-agent.conf"

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

echo "==> 测试 SSH 连接 (${REMOTE})..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "echo connected"

echo "==> 上传 Nginx 配置..."
scp "${SCP_OPTS[@]}" "${NGINX_CONF}" "${REMOTE}:/tmp/poetry-agent.conf"

echo "==> 在 ECS 上安装 Docker 与 Nginx..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s -- "${REMOTE_DIR}" <<'REMOTE_SETUP'
set -euo pipefail
REMOTE_DIR="$1"

detect_os() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        echo "${ID:-unknown}"
    else
        echo "unknown"
    fi
}

OS_ID="$(detect_os)"
echo "检测到系统: ${OS_ID}"

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        echo "Docker 已安装: $(docker --version)"
        return
    fi
    echo "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
}

install_nginx() {
    if command -v nginx >/dev/null 2>&1; then
        echo "Nginx 已安装: $(nginx -v 2>&1)"
    else
        case "${OS_ID}" in
            ubuntu|debian)
                apt-get update -y
                apt-get install -y nginx curl
                ;;
            alinux|centos|rhel|rocky|almalinux|fedora)
                if command -v dnf >/dev/null 2>&1; then
                    dnf install -y nginx curl
                else
                    yum install -y nginx curl
                fi
                ;;
            *)
                echo "未识别的发行版，尝试通用安装..."
                if command -v apt-get >/dev/null 2>&1; then
                    apt-get update -y && apt-get install -y nginx curl
                elif command -v dnf >/dev/null 2>&1; then
                    dnf install -y nginx curl
                elif command -v yum >/dev/null 2>&1; then
                    yum install -y nginx curl
                else
                    echo "无法自动安装 Nginx，请手动安装后重试" >&2
                    exit 1
                fi
                ;;
        esac
    fi
    systemctl enable nginx
    systemctl start nginx || systemctl restart nginx
}

install_docker
install_nginx

if ! docker compose version >/dev/null 2>&1; then
    echo "警告: docker compose 插件不可用，请确认 Docker 版本 >= 20.10" >&2
fi

if [[ "${EUID}" -ne 0 ]] && ! groups | grep -q docker; then
    usermod -aG docker "$(whoami)" || true
    echo "已将 $(whoami) 加入 docker 组，重新登录 SSH 后生效"
fi

mkdir -p "${REMOTE_DIR}"

# Ubuntu 默认站点与 poetry-agent 同时 default_server 会冲突
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

if [[ -d /etc/nginx/sites-available ]]; then
    cp /tmp/poetry-agent.conf /etc/nginx/sites-available/poetry-agent.conf
    ln -sf /etc/nginx/sites-available/poetry-agent.conf /etc/nginx/sites-enabled/poetry-agent.conf
    rm -f /etc/nginx/conf.d/poetry-agent.conf 2>/dev/null || true
elif [[ -d /etc/nginx/conf.d ]]; then
    cp /tmp/poetry-agent.conf /etc/nginx/conf.d/poetry-agent.conf
else
    echo "无法定位 Nginx 配置目录" >&2
    exit 1
fi

nginx -t
systemctl enable nginx
systemctl restart nginx
systemctl is-active nginx

echo ""
echo "ECS 初始化完成。"
echo "请确认阿里云安全组已放行: 22 (SSH)、80 (HTTP)"
echo "应用将通过 Nginx :80 反代到 127.0.0.1:8000"
REMOTE_SETUP

echo ""
echo "==> setup-ecs 完成"
echo "下一步:"
echo "  1. 配置本地 .env.prod（cp .env.prod.example .env.prod，DashScope API Key 等）"
echo "  2. 首次发布: ./scripts/deploy/deploy.sh --with-data"
echo "  3. 访问: http://${ECS_HOST}/"
