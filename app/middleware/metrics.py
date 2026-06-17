"""HTTP 指标采集中间件。"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:
    from app.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS

    _METRICS = True
except ImportError:
    _METRICS = False


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not _METRICS or request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        route = request.url.path
        for prefix in ("/api/v1/chat/stream", "/api/v1/chat", "/api/v1/rag", "/api/v1/sessions"):
            if route.startswith(prefix):
                route = prefix
                break

        HTTP_REQUESTS.labels(
            method=request.method,
            endpoint=route,
            status=str(response.status_code),
        ).inc()
        HTTP_LATENCY.labels(method=request.method, endpoint=route).observe(elapsed)
        return response
