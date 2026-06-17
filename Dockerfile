# 供 ACR 控制台「镜像构建」使用
# 基础镜像走阿里云新加坡区域代理（同区域，避免 docker.io 429）
# 路径 library/ 对应 Docker Hub 官方镜像
# ---- Frontend build ----
FROM registry.ap-southeast-1.aliyuncs.com/library/node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm install
COPY frontend/ ./
RUN npm run build

# ---- Backend ----
FROM registry.ap-southeast-1.aliyuncs.com/library/python:3.11-slim

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN printf '[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/\ntrusted-host = mirrors.aliyun.com\ntimeout = 300\n' > /etc/pip.conf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV PYTHONUNBUFFERED=1
ENV CHROMA_PERSIST_DIR=/app/data/chroma_db
ENV CORPUS_DIR=/app/data/corpus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD python scripts/build_index.py 2>/dev/null || true; \
    uvicorn app.main:app --host 0.0.0.0 --port 8000
