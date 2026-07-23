"""Runtime execution layer for CRM AI Agent tools."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ValidationError

from app.services.agent.guardrails import AgentToolExecutionPolicy, AgentToolGuardrailError
from app.services.agent.tool_registry import AgentToolRegistry, agent_tool_registry
from app.services.agent.tools.base import AgentToolContext, AgentToolResult


class AgentToolRuntime:
    """Single execution path for all Agent tool calls."""

    def __init__(
        self,
        registry: Optional[AgentToolRegistry] = None,
    ) -> None:
        self.registry = registry or agent_tool_registry

    async def execute(
        self,
        tool_name: str,
        context: AgentToolContext,
        payload: Dict[str, Any],
        *,
        policy: Optional[AgentToolExecutionPolicy] = None,
    ) -> AgentToolResult:
        try:
            return await self.registry.execute(tool_name, context, payload, policy=policy)
        except AgentToolGuardrailError as exc:
            return AgentToolResult(tool_name=tool_name, success=False, error_message=str(exc))
        except KeyError as exc:
            return AgentToolResult(tool_name=tool_name, success=False, error_message=str(exc))
        except ValidationError as exc:
            return AgentToolResult(tool_name=tool_name, success=False, error_message=f"tool 入参无效：{exc}")


agent_tool_runtime = AgentToolRuntime()
