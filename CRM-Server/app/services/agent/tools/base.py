"""Shared types for CRM AI Agent tools."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


JsonDict = Dict[str, Any]


@dataclass
class AgentToolContext:
    """Runtime context required for audited API tool calls."""

    db: Session
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    task_id: Optional[int] = None
    hitl_decision: Optional[str] = None
    confirmed_by_user: bool = False
    allowed_tool_names: Optional[List[str]] = None
    allowed_customer_ids: Optional[List[int]] = None


@dataclass
class AgentToolResult:
    tool_name: str
    success: bool
    data: Any = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    tool_call_id: Optional[int] = None
    idempotent_replay: bool = False

    def to_event(self) -> JsonDict:
        return {
            "event": "tool_result",
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "error_message": self.error_message,
            "status_code": self.status_code,
            "tool_call_id": self.tool_call_id,
            "idempotent_replay": self.idempotent_replay,
        }
