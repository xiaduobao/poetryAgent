FROM python:3.11-slim

WORKDIR /app

# 系统依赖（sentence-transformers 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 预下载模型可选：首次启动会自动下载
ENV PYTHONUNBUFFERED=1
ENV CHROMA_PERSIST_DIR=/app/data/chroma_db
ENV CORPUS_DIR=/app/data/corpus

EXPOSE 8000

# 启动前构建索引（若不存在）
CMD python scripts/build_index.py 2>/dev/null || true; \
    uvicorn app.main:app --host 0.0.0.0 --port 8000
