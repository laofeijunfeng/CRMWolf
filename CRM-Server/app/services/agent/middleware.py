"""LangChain middleware adapters for CRM AI Agent."""
from __future__ import annotations

from typing import List

from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry

try:
    from langchain.agents.middleware import HumanInTheLoopMiddleware
except Exception:  # pragma: no cover - optional LangChain runtime surface
    HumanInTheLoopMiddleware = None  # type: ignore[assignment]


def build_langchain_hitl_middleware(registry: AgentToolRegistry = agent_tool_registry) -> List[object]:
    """Create LangChain HITL middleware from the Agent tool registry."""
    if HumanInTheLoopMiddleware is None:
        return []

    interrupt_on = {
        name: {
            "allowed_decisions": ["approve", "edit", "reject"],
        }
        for name, spec in registry.list_specs().items()
        if spec.requires_confirmation
    }
    if not interrupt_on:
        return []
    return [HumanInTheLoopMiddleware(interrupt_on=interrupt_on)]
