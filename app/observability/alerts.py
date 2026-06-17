"""告警通知（钉钉/飞书 Webhook）。"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_alert(title: str, message: str) -> bool:
    settings = get_settings()
    if not settings.alert_webhook_url:
        return False
    payload = {
        "msgtype": "text",
        "text": {"content": f"[poetryAgent] {title}\n{message}"},
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(settings.alert_webhook_url, json=payload)
            return resp.status_code < 300
    except Exception as e:
        logger.warning("alert webhook failed: %s", e)
        return False
