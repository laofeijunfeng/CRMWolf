"""Typed persistence inputs and snapshots for CRM Agent registries."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves this annotation at runtime.
from typing import Literal
from uuid import UUID  # noqa: TC003  # Pydantic resolves this annotation at runtime.

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.services.agent.query.schemas import (  # noqa: TC001  # Pydantic resolves these annotations at runtime.
    CRMQuerySpec,
    CRMResource,
    EntityRef,
)
from app.services.agent.ui.schemas import (  # noqa: TC001  # Pydantic resolves these annotations at runtime.
    AgentUIAction,
    AgentUIBlock,
    AgentUIEnvelope,
    AgentUIMetadata,
)


class AgentPersistenceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AgentResultPage(AgentPersistenceContract):
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    page_size: int = Field(ge=1, le=100)
    range_start: int = Field(ge=0)
    range_end: int = Field(ge=0)
    total: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> AgentResultPage:
        if self.range_end < self.range_start:
            raise ValueError("range_end must be greater than or equal to range_start")
        return self


class AgentQueryResultSetCreate(AgentPersistenceContract):
    public_id: str = Field(min_length=1, max_length=64)
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    source_message_id: int = Field(gt=0)
    parent_result_set_id: str | None = Field(default=None, min_length=1, max_length=64)
    resource: CRMResource
    query: CRMQuerySpec
    ordered_entity_refs: list[EntityRef] = Field(max_length=100)
    page: AgentResultPage
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_resource_and_page(self) -> AgentQueryResultSetCreate:
        if self.query.resource != self.resource:
            raise ValueError("query resource must match result set resource")
        ref_count = len(self.ordered_entity_refs)
        if ref_count == 0:
            if (self.page.range_start, self.page.range_end) != (0, 0):
                raise ValueError("empty result pages must use range 0..0")
        elif self.page.range_start < 1 or self.page.range_end - self.page.range_start + 1 != ref_count:
            raise ValueError("non-empty result pages use a one-based inclusive range matching entity refs")
        return self


class AgentQueryResultSetRecord(AgentPersistenceContract):
    public_id: str = Field(min_length=1, max_length=64)
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    source_message_id: int = Field(gt=0)
    parent_result_set_id: str | None = Field(default=None, min_length=1, max_length=64)
    resource: CRMResource
    query: CRMQuerySpec
    ordered_entity_refs: list[EntityRef] = Field(max_length=100)
    page: AgentResultPage
    row_count: int = Field(ge=0, le=100)
    expires_at: datetime
    created_time: datetime


AgentUIActionType = Literal[
    "open_entity",
    "query_refinement",
    "start_workflow",
    "submit_interaction",
    "retry",
]
AgentUIActionConsumptionMode = Literal["REUSABLE", "ONE_SHOT"]
AgentUIActionStatus = Literal["ACTIVE", "CONSUMING", "CONSUMED", "EXPIRED", "REVOKED"]
AgentUIActionConsumptionOutcome = Literal["ACQUIRED", "REPLAY", "REUSABLE"]


class AgentUIActionRegistration(AgentPersistenceContract):
    public_id: str = Field(min_length=1, max_length=64)
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    message_id: int = Field(gt=0)
    action_type: AgentUIActionType
    target: dict[str, JsonValue]
    consumption_mode: AgentUIActionConsumptionMode
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def require_one_shot_for_side_effect_actions(self) -> AgentUIActionRegistration:
        if self.action_type in {"start_workflow", "submit_interaction"} and self.consumption_mode != "ONE_SHOT":
            raise ValueError(f"{self.action_type} action must be ONE_SHOT")
        return self


class AgentUIActionRecord(AgentPersistenceContract):
    public_id: str = Field(min_length=1, max_length=64)
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    message_id: int = Field(gt=0)
    action_type: AgentUIActionType
    target: dict[str, JsonValue]
    consumption_mode: AgentUIActionConsumptionMode
    status: AgentUIActionStatus
    expires_at: datetime
    consumed_at: datetime | None = None
    consumed_request_id: str | None = Field(default=None, min_length=36, max_length=36)
    result_message_id: int | None = Field(default=None, gt=0)
    lock_version: int = Field(ge=0)
    created_time: datetime
    last_modified_time: datetime


class AgentUIActionConsumption(AgentPersistenceContract):
    outcome: AgentUIActionConsumptionOutcome
    action: AgentUIActionRecord








AgentPersistedMessageRole = Literal["USER", "ASSISTANT", "SYSTEM"]
AgentTurnBeginOutcome = Literal["CREATED", "IN_PROGRESS", "COMPLETED"]
AgentAssistantMessageWriteOutcome = Literal["CREATED", "REPLAY"]


class AgentUIMessageBody(AgentPersistenceContract):
    state: Literal["streaming", "final", "failed"]
    blocks: list[AgentUIBlock] = Field(max_length=30)
    suggested_actions: list[AgentUIAction] = Field(default_factory=list, max_length=10)
    metadata: AgentUIMetadata


class AgentTurnStart(AgentPersistenceContract):
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    client_request_id: UUID = Field(strict=False)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str = Field(min_length=1, max_length=10000)
    ui: AgentUIMessageBody

    @model_validator(mode="after")
    def require_final_user_message(self) -> AgentTurnStart:
        if self.ui.state != "final":
            raise ValueError("persisted user messages must be final")
        return self


class AgentAssistantMessageCreate(AgentPersistenceContract):
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    turn_id: str = Field(min_length=1, max_length=64)
    content: str = Field(max_length=10000)
    ui: AgentUIMessageBody
    diagnostics: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def require_terminal_assistant_message(self) -> AgentAssistantMessageCreate:
        if self.ui.state not in {"final", "failed"}:
            raise ValueError("persisted assistant messages must be final or failed")
        return self


class AgentAssistantProjectionCreate(AgentPersistenceContract):
    """A server-originated assistant message with a stable projection identity."""

    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    projection_key: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=10000)
    ui: AgentUIMessageBody
    diagnostics: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def require_terminal_assistant_message(self) -> AgentAssistantProjectionCreate:
        if self.ui.state not in {"final", "failed"}:
            raise ValueError("persisted assistant projections must be final or failed")
        return self


class AgentPersistedMessageRecord(AgentPersistenceContract):
    id: int = Field(gt=0)
    team_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    role: AgentPersistedMessageRole
    turn_id: str = Field(min_length=1, max_length=64)
    client_request_id: str | None = Field(default=None, min_length=36, max_length=36)
    content: str
    ui: AgentUIEnvelope
    diagnostics: dict[str, JsonValue] | None = None
    created_time: datetime
    last_modified_time: datetime


class AgentTurnBeginResult(AgentPersistenceContract):
    outcome: AgentTurnBeginOutcome
    user_message: AgentPersistedMessageRecord
    assistant_message: AgentPersistedMessageRecord | None = None


class AgentAssistantMessageWriteResult(AgentPersistenceContract):
    outcome: AgentAssistantMessageWriteOutcome
    message: AgentPersistedMessageRecord
