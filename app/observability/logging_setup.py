"""日志配置。"""
from __future__ import annotations

import logging
import sys

from app.config import Settings


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if settings.log_json:
        try:
            from pythonjsonlogger.json import JsonFormatter

            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                JsonFormatter(
                    "%(asctime)s %(levelname)s %(name)s %(message)s",
                    rename_fields={"asctime": "timestamp", "levelname": "level"},
                )
            )
            logging.basicConfig(level=level, handlers=[handler], force=True)
            return
        except ImportError:
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
