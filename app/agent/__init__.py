"""Agent 包：延迟加载 graph，避免 import 时拉起重依赖。"""

__all__ = ["get_agent_graph", "run_agent"]


def __getattr__(name: str):
    if name == "get_agent_graph":
        from app.agent.graph import get_agent_graph

        return get_agent_graph
    if name == "run_agent":
        from app.agent.graph import run_agent

        return run_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
