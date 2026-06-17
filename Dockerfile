# ---- Frontend build ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm install
COPY frontend/ ./
RUN npm run build

# ---- Backend deps ----
FROM python:3.11-slim AS backend-deps

WORKDIR /app

RUN printf '[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/\ntrusted-host = mirrors.aliyun.com\ntimeout = 300\n' > /etc/pip.conf

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 只从 PyTorch CPU 源安装；constraints 必须带 +cpu，否则第二步会从 PyPI 拉回 CUDA 版
ARG TORCH_CPU_VERSION=2.5.1
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch==${TORCH_CPU_VERSION}+cpu"

RUN echo "torch==${TORCH_CPU_VERSION}+cpu" > /tmp/constraints.txt \
    && grep -v '^torch' requirements.txt > /tmp/requirements.no-torch.txt \
    && pip install --no-cache-dir -r /tmp/requirements.no-torch.txt -c /tmp/constraints.txt

# 全部依赖装完后再校验（之前在校验后还 pip install，导致 nvidia 包混入）
RUN if pip list | grep -iE '^nvidia-'; then \
        echo "ERROR: 检测到 CUDA/nvidia 包，镜像构建失败" >&2; \
        pip list | grep -i nvidia; \
        exit 1; \
    fi \
    && python -c "import torch; assert '+cpu' in torch.__version__, torch.__version__; print('torch OK:', torch.__version__)"

# ---- Backend runtime ----
FROM python:3.11-slim

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-deps /usr/local/bin /usr/local/bin

COPY . .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV CHROMA_PERSIST_DIR=/app/data/chroma_db
ENV CORPUS_DIR=/app/data/corpus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD alembic upgrade head && \
    (python scripts/build_index.py 2>/dev/null || true) && \
    uvicorn app.main:app --host 0.0.0.0 --port 8000
