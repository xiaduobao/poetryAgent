"""Sentry 错误追踪初始化。"""
from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        logger.info("Sentry initialized (env=%s)", settings.app_env)
    except Exception as e:
        logger.warning("Sentry init failed: %s", e)
