#!/usr/bin/env bash
# 在 ECS（Ubuntu）上用 Certbot + nginx 插件为域名申请 Let's Encrypt 证书
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ENV="${SCRIPT_DIR}/deploy.env"
NGINX_TEMPLATE="${SCRIPT_DIR}/nginx/poetry-agent.domain.conf"

usage() {
    cat <<'EOF'
用法: ./scripts/deploy/setup-ssl-certbot.sh [选项]

在 ECS 上安装 Certbot，更新 nginx server_name，申请 Let's Encrypt 证书并配置 HTTPS 跳转。

前置：
  1. deploy.env 已配置 ECS_HOST、SSH_KEY、DOMAIN、CERTBOT_EMAIL
  2. 域名 DNS A 记录已指向 ECS 公网 IP（含 www 若启用）
  3. 阿里云安全组已放行 80、443
  4. poetry-agent 已通过 nginx :80 可访问

选项:
  --dry-run    仅检查 DNS / nginx，不申请证书
  -h, --help   显示帮助
EOF
}

DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
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
: "${DOMAIN:?请在 deploy.env 中设置 DOMAIN，例如 cnpoetry.top}"
: "${CERTBOT_EMAIL:?请在 deploy.env 中设置 CERTBOT_EMAIL（Let's Encrypt 通知邮箱）}"

INCLUDE_WWW="${INCLUDE_WWW:-true}"

SSH_KEY_EXPANDED="${SSH_KEY/#\~/$HOME}"
SSH_COMMON=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
SSH_OPTS=(-p "${ECS_PORT}" "${SSH_COMMON[@]}")
SCP_OPTS=(-P "${ECS_PORT}" "${SSH_COMMON[@]}")
if [[ -n "${SSH_KEY:-}" ]]; then
    SSH_OPTS+=(-i "${SSH_KEY_EXPANDED}")
    SCP_OPTS+=(-i "${SSH_KEY_EXPANDED}")
fi

REMOTE="${ECS_USER}@${ECS_HOST}"
WWW_DOMAIN="www.${DOMAIN}"
if [[ "${INCLUDE_WWW}" == true ]]; then
    SERVER_NAMES="${DOMAIN} ${WWW_DOMAIN}"
    CERTBOT_DOMAINS=(-d "${DOMAIN}" -d "${WWW_DOMAIN}")
else
    SERVER_NAMES="${DOMAIN}"
    CERTBOT_DOMAINS=(-d "${DOMAIN}")
fi

TMP_NGINX="$(mktemp)"
trap 'rm -f "${TMP_NGINX}"' EXIT
sed -e "s/__DOMAIN__/${DOMAIN}/g" -e "s/__WWW_DOMAIN__/${WWW_DOMAIN}/g" "${NGINX_TEMPLATE}" > "${TMP_NGINX}"
# 未启用 www 时去掉多余 server_name
if [[ "${INCLUDE_WWW}" != true ]]; then
    sed -i '' "s/ ${WWW_DOMAIN}//" "${TMP_NGINX}" 2>/dev/null || sed -i "s/ ${WWW_DOMAIN}//" "${TMP_NGINX}"
fi

echo "==> 测试 SSH (${REMOTE})..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" "echo connected"

echo "==> 上传 nginx 配置（server_name: ${SERVER_NAMES}）..."
scp "${SCP_OPTS[@]}" "${TMP_NGINX}" "${REMOTE}:/tmp/poetry-agent.conf"

echo "==> 在 ECS 上配置 Certbot..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s -- "${DOMAIN}" "${CERTBOT_EMAIL}" "${DRY_RUN}" "${INCLUDE_WWW}" <<'REMOTE_SSL'
set -euo pipefail
DOMAIN="$1"
CERTBOT_EMAIL="$2"
DRY_RUN="$3"
INCLUDE_WWW="$4"

if ! command -v nginx >/dev/null 2>&1; then
    echo "未安装 nginx，请先运行 ./scripts/deploy/setup-ecs.sh" >&2
    exit 1
fi

apt-get update -y
apt-get install -y certbot python3-certbot-nginx

rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
cp /tmp/poetry-agent.conf /etc/nginx/sites-available/poetry-agent.conf
ln -sf /etc/nginx/sites-available/poetry-agent.conf /etc/nginx/sites-enabled/poetry-agent.conf
nginx -t
systemctl reload nginx

echo "==> 检查 DNS 解析..."
RESOLVED="$(getent ahosts "${DOMAIN}" | awk '{print $1; exit}')"
PUBLIC_IP="$(curl -sf --max-time 5 https://api.ipify.org || curl -sf --max-time 5 http://ifconfig.me/ip || true)"
echo "    ${DOMAIN} -> ${RESOLVED:-未解析}"
echo "    ECS 公网 IP -> ${PUBLIC_IP:-未知}"
if [[ -n "${RESOLVED}" && -n "${PUBLIC_IP}" && "${RESOLVED}" != "${PUBLIC_IP}" ]]; then
    echo "警告: 域名解析 IP 与 ECS 公网 IP 不一致，Certbot 可能失败" >&2
fi

if [[ "${DRY_RUN}" == true ]]; then
    echo "==> dry-run 完成（未申请证书）"
    exit 0
fi

echo "==> 申请证书: ${DOMAIN}"
if [[ "${INCLUDE_WWW}" == true ]]; then
    certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" \
        --non-interactive --agree-tos -m "${CERTBOT_EMAIL}" --redirect
else
    certbot --nginx -d "${DOMAIN}" \
        --non-interactive --agree-tos -m "${CERTBOT_EMAIL}" --redirect
fi

nginx -t
systemctl reload nginx

echo ""
echo "==> HTTPS 已启用"
echo "    https://${DOMAIN}/"
certbot certificates
REMOTE_SSL

echo ""
echo "==> 完成。请在本机 .env.prod 更新 CORS 并发布："
echo "    CORS_ORIGINS=https://${DOMAIN},https://www.${DOMAIN}"
echo "    ./scripts/deploy/deploy.sh --env-only"
echo ""
echo "证书自动续期: systemctl status certbot.timer"
