#!/usr/bin/env bash
# 使用 Python 3.11 创建虚拟环境并安装依赖（避免 3.13 无法装 torch）
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3.11}"
if ! command -v "$PY" &>/dev/null; then
  echo "未找到 $PY，请安装 Python 3.11 或设置 PYTHON=python3.12" >&2
  exit 1
fi

VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$VER" in
  3.11|3.12) ;;
  *)
    echo "需要 Python 3.11 或 3.12，当前 $PY 为 $VER（3.13 无法安装 PyTorch）" >&2
    exit 1
    ;;
esac

PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
EXTRA="${1:-}"

echo "==> Python $VER ($PY)"
rm -rf .venv
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt -i "$PIP_INDEX" --default-timeout=120
if [[ "$EXTRA" == "--eval" ]]; then
  pip install -r requirements-eval.txt -i "$PIP_INDEX" --default-timeout=120
fi
echo "==> 完成。执行: source .venv/bin/activate"
