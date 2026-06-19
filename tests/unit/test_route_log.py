"""路由日志单元测试。"""
from __future__ import annotations

import logging

from app.agent.route_log import log_route


def test_log_route_emits_agent_route_prefix(caplog):
    caplog.set_level(logging.INFO, logger="app.agent.route_log")
    log_route("intent_classify", source="rule", intent="tool_meter", rule="meter", query="分析格律")
    assert any("[agent-route] intent_classify" in r.message for r in caplog.records)
    assert any("source=rule" in r.message for r in caplog.records)
    assert any("intent=tool_meter" in r.message for r in caplog.records)
