"""在导入 huggingface 相关库之前加载 .env 并设置镜像端点。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def bootstrap_hf_hub_env(env_file: Path | None = None) -> str:
    """
    尽早执行：加载 .env，强制设置 HF 镜像环境变量。
    返回当前使用的 endpoint（未配置则为空字符串）。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore

    path = env_file or ROOT_DIR / ".env"
    if load_dotenv and path.exists():
        load_dotenv(path, override=False)

    endpoint = (os.getenv("HF_ENDPOINT") or "").strip().rstrip("/")
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint
        os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint
    return endpoint
