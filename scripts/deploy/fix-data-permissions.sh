#!/usr/bin/env bash
# 修正 data/ 目录权限，匹配 Docker 容器内用户。
# poetry-agent: uid 1000 | postgres:16-alpine: 70 | redis:7-alpine: 999
# 在 ECS 上执行: sudo ./scripts/deploy/fix-data-permissions.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATA_DIR="${1:-${PROJECT_DIR}/data}"

APP_UID=1000
APP_GID=1000
POSTGRES_UID=70
REDIS_UID=999

if [[ ! -d "${DATA_DIR}" ]]; then
    echo "目录不存在: ${DATA_DIR}" >&2
    exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
    echo "请使用 root 运行（ECS 上: sudo $0）" >&2
    exit 1
fi

echo "==> 修正 app 数据属主 ${APP_UID}:${APP_GID} ..."
for name in authors.json sessions.db corpus chroma_db models; do
    if [[ -e "${DATA_DIR}/${name}" ]]; then
        chown -R "${APP_UID}:${APP_GID}" "${DATA_DIR}/${name}"
    fi
done

shopt -s nullglob
for f in "${DATA_DIR}"/poems_batch*.txt; do
    chown "${APP_UID}:${APP_GID}" "$f"
done

# rsync 可能留下其他顶层文件
for f in "${DATA_DIR}"/*; do
    base="$(basename "$f")"
    [[ "$base" == postgres || "$base" == redis ]] && continue
    if [[ -f "$f" ]]; then
        chown "${APP_UID}:${APP_GID}" "$f"
    elif [[ -d "$f" && "$base" != corpus && "$base" != chroma_db && "$base" != models ]]; then
        chown -R "${APP_UID}:${APP_GID}" "$f"
    fi
done

if [[ -d "${DATA_DIR}/postgres" ]]; then
    echo "==> postgres 目录属主 ${POSTGRES_UID} ..."
    chown -R "${POSTGRES_UID}:${POSTGRES_UID}" "${DATA_DIR}/postgres" \
        || chown -R "${POSTGRES_UID}:root" "${DATA_DIR}/postgres"
    chmod 700 "${DATA_DIR}/postgres"
fi

if [[ -d "${DATA_DIR}/redis" ]]; then
    echo "==> redis 目录属主 ${REDIS_UID} ..."
    chown -R "${REDIS_UID}:${REDIS_UID}" "${DATA_DIR}/redis"
fi

echo "==> 完成:"
ls -la "${DATA_DIR}"
