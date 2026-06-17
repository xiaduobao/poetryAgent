#!/usr/bin/env python3
"""
通过 HF 镜像将 Embedding / Rerank 模型下载到 data/models/，供离线使用。

用法：
  python scripts/download_models.py

.env 可填 HuggingFace 模型 ID（BAAI/bge-reranker-base）或本地相对路径
（./data/models/BAAI--bge-reranker-base）；后者若目录不存在会自动推断 repo 并下载到该路径。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 必须在 huggingface_hub 导入前设置镜像
from app.hf_bootstrap import bootstrap_hf_hub_env  # noqa: E402

endpoint = bootstrap_hf_hub_env()
if not endpoint:
    endpoint = "https://hf-mirror.com"
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint
    print("未配置 HF_ENDPOINT，临时使用 https://hf-mirror.com")

print(f"HF_ENDPOINT = {os.environ.get('HF_ENDPOINT')}")

# 取消错误代理（浏览器能上网但 Python 走代理失败时常见）
for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
    if os.environ.get(key):
        print(f"提示: 当前存在 {key}={os.environ[key]!r}，若下载失败可尝试 unset {key}")

# 常见本地目录名 → HuggingFace repo id
_KNOWN_REPO_IDS: dict[str, str] = {
    "bge-small-zh-v1.5": "BAAI/bge-small-zh-v1.5",
    "bge-reranker-base": "BAAI/bge-reranker-base",
    "BAAI--bge-small-zh-v1.5": "BAAI/bge-small-zh-v1.5",
    "BAAI--bge-reranker-base": "BAAI/bge-reranker-base",
}


def _resolve_local_path(name: str) -> Path:
    p = Path(name.strip())
    return p.resolve() if p.is_absolute() else (ROOT / name.strip()).resolve()


def _looks_like_local_path(name: str) -> bool:
    """区分 .env 里的本地路径与 HuggingFace repo id（如 BAAI/bge-reranker-base）。"""
    n = name.strip().replace("\\", "/")
    if n.startswith(("./", "../", "/")):
        return True
    if "data/models" in n or n.startswith("models/"):
        return True
    parts = n.split("/")
    return not (len(parts) == 2 and parts[0] and not parts[0].startswith("."))


def _infer_repo_id(name: str, local_dir: Path) -> str:
    folder = local_dir.name
    if folder in _KNOWN_REPO_IDS:
        return _KNOWN_REPO_IDS[folder]
    if "--" in folder:
        org, rest = folder.split("--", 1)
        return f"{org}/{rest}"
    return f"BAAI/{folder}"


def _env_relative_path(path: Path) -> str:
    try:
        rel = path.relative_to(ROOT)
        return f"./{rel.as_posix()}"
    except ValueError:
        return str(path)


def _test_hub_connectivity() -> None:
    import urllib.request

    url = f"{endpoint.rstrip('/')}/api/models/BAAI/bge-small-zh-v1.5"
    print(f"测试 Python 访问镜像 API: {url}")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            print(f"  状态码: {resp.status}")
    except Exception as e:
        print(f"  失败: {e}")
        print("  浏览器能打开 hf-mirror 但 Python 失败时，多为终端代理/防火墙问题。")


def _download(repo_id: str, local_dir: Path) -> Path:
    from huggingface_hub import snapshot_download

    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n下载 {repo_id} -> {local_dir}")
    return Path(
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
    )


def main() -> int:
    _test_hub_connectivity()

    from app.config import Settings

    settings = Settings()
    models_root = ROOT / "data" / "models"
    models_root.mkdir(parents=True, exist_ok=True)

    # (repo_id, label, local_dir)
    tasks: list[tuple[str, str, Path]] = []
    for attr, label in (("embedding_model", "embedding"), ("rerank_model", "rerank")):
        name = getattr(settings, attr).strip()
        if not name:
            print(f"\n[{label}] 未配置，跳过")
            continue

        if _looks_like_local_path(name):
            resolved = _resolve_local_path(name)
            if resolved.is_dir():
                print(f"\n[{label}] 已是本地目录，跳过: {name} (resolved={resolved})")
                continue
            repo_id = _infer_repo_id(name, resolved)
            print(
                f"\n[{label}] 本地目录不存在，将从 {repo_id!r} 下载到 {resolved}"
            )
            tasks.append((repo_id, label, resolved))
            continue

        if "/" not in name:
            print(f"\n[{label}] 无效模型 ID: {name}")
            continue
        folder = models_root / name.replace("/", "--")
        tasks.append((name, label, folder))

    if not tasks:
        print("\n模型均已为本地路径，无需下载。")
        return 0

    paths: dict[str, Path] = {}
    for repo_id, label, local_dir in tasks:
        try:
            paths[label] = _download(repo_id, local_dir)
        except Exception as e:
            print(f"\n[{label}] 下载失败: {e}")
            print(
                "\n可改用手动下载（见 README），或在本机执行：\n"
                f"  export HF_ENDPOINT={endpoint}\n"
                f"  huggingface-cli download --resume-download {repo_id} "
                f"--local-dir {local_dir}\n"
            )
            return 1

    print("\n" + "=" * 60)
    print("下载完成。请将 .env 改为本地路径后重建索引：\n")
    if "embedding" in paths:
        print(f"EMBEDDING_MODEL={_env_relative_path(paths['embedding'])}")
    if "rerank" in paths:
        print(f"RERANK_MODEL={_env_relative_path(paths['rerank'])}")
    print("\npython scripts/build_index.py")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
