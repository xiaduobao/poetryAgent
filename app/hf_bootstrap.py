"""在导入 huggingface 相关库之前加载 .env 并设置镜像端点。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _default_env_file() -> Path:
    override = os.getenv("ENV_FILE", "").strip()
    if override:
        return ROOT_DIR / override
    if os.getenv("APP_ENV", "").lower() in ("production", "prod"):
        prod = ROOT_DIR / ".env.prod"
        if prod.exists():
            return prod
    return ROOT_DIR / ".env"


def bootstrap_hf_hub_env(env_file: Path | None = None) -> str:
    """
    尽早执行：加载 .env，强制设置 HF 镜像环境变量。
    返回当前使用的 endpoint（未配置则为空字符串）。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore

    path = env_file or _default_env_file()
    if load_dotenv and path.exists():
        load_dotenv(path, override=False)

    endpoint = (os.getenv("HF_ENDPOINT") or "").strip().rstrip("/")
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint
        os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint
    return endpoint
