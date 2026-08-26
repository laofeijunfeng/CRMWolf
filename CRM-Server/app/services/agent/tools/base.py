"""Shared types for CRM AI Agent tools."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services.agent.durable_work_contracts import AgentDurableWorkReceipt

JsonDict = dict[str, object]


@dataclass
class AgentToolContext:
    """Runtime context required for audited API tool calls."""

    db: Session
    team_id: int
    user_id: int
    session_id: int
    authorization: str
    permission_codes: frozenset[str] = frozenset()
    workflow_id: str | None = None
    action_id: str | None = None
    execution_policy: str | None = None
    authorization_source: str | None = None
    hitl_decision: str | None = None
    confirmed_by_user: bool = False
    auto_execute_authorized: bool = False
    allowed_tool_names: list[str] | None = None
    allowed_customer_ids: list[str] | None = None
    source_user_message_id: int | None = None
    deadline_at: float | None = None


@dataclass
class AgentToolResult:
    tool_name: str
    success: bool
    data: object = None
    error_message: str | None = None
    status_code: int | None = None
    tool_call_id: int | None = None
    idempotent_replay: bool = False
    durable_work: tuple[AgentDurableWorkReceipt, ...] = field(default_factory=tuple)

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
            "durable_work": [receipt.model_dump(mode="json") for receipt in self.durable_work],
        }
