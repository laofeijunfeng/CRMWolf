"""Closed, neutral conversation contracts; never import the legacy graph runtime."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assistant import AssistantTaskView, SubmitInputRequest  # noqa: TC001 -- Pydantic runtime models.
from app.services.agent.semantic_plan import AgentSemanticPlan  # noqa: TC001 -- Pydantic runtime model.
from app.services.agent.ui.schemas import AgentUIEnvelope  # noqa: TC001 -- Pydantic runtime model.


class ConversationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationDecision(ConversationModel):
    semantic_plan: AgentSemanticPlan
    task_relation: Literal["NEW_TASK", "CONTINUE_TASK", "SWITCH_TASK"]
    route: Literal["QUERY", "WORKFLOW", "CLARIFY"]
    boundary: Literal["NEW", "CONTINUE", "AMBIGUOUS"]
    target_task_public_id: str | None = Field(default=None, max_length=64)
    resume_only: bool = False
    field_answer: bool = False
    confidence: float = Field(ge=0, le=1)


class ConversationTextRequest(ConversationModel):
    text: str = Field(min_length=1, max_length=20000)
    client_request_id: str = Field(min_length=8, max_length=128)
    expected_version: int = Field(ge=0)


class ConversationChoiceRequest(ConversationModel):
    entry_id: str = Field(min_length=1, max_length=64)
    choice: Literal["CONTINUE", "NEW", "CANCEL"]
    client_request_id: str = Field(min_length=8, max_length=128)
    expected_version: int = Field(ge=0)


class ConversationCommandRequest(ConversationModel):
    task_public_id: str = Field(min_length=1, max_length=64)
    input: SubmitInputRequest
    expected_version: int = Field(ge=0)


class ConversationEntryRetryRequest(ConversationModel):
    expected_version: int = Field(ge=0)


class ConversationKindRequest(ConversationModel):
    task_public_id: str = Field(min_length=1, max_length=64)
    kind: Literal["FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"]
    task_version: int = Field(ge=0)
    expected_version: int = Field(ge=0)
    client_request_id: str = Field(min_length=8, max_length=128)


class ConversationBoundary(ConversationModel):
    entry_id: str
    prompt: str


class ConversationMessage(ConversationModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    at: str
    task: AssistantTaskView | None = None
    boundary: ConversationBoundary | None = None
    outcome: Literal["activity_written", "failure"] | None = None
    ui: AgentUIEnvelope | None = None
    # Read-model inputs. The Web UI uses ui.blocks, not these fields.
    error_code: str | None = Field(default=None, exclude=True)
    retryable: bool | None = Field(default=None, exclude=True)


class ConversationView(ConversationModel):
    public_id: str
    version: int
    focused_task: AssistantTaskView | None
    pending_choice: ConversationBoundary | None
    has_pending_request: bool = False
    messages: list[ConversationMessage]
    older_cursor: int | None = None


class PreparedSubmission(ConversationModel):
    task_public_id: str
    turn_id: str
    input: SubmitInputRequest


class ConversationReply(ConversationModel):
    conversation: ConversationView
    submission: PreparedSubmission | None = None
