"""Closed, neutral conversation contracts; never import the legacy graph runtime."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assistant import AssistantTaskView, SubmitInputRequest  # noqa: TC001 -- Pydantic runtime models.
from app.services.agent.semantic_plan import AgentSemanticPlan  # noqa: TC001 -- Pydantic runtime model.
from app.services.agent.ui.schemas import AgentUIEnvelope  # noqa: TC001 -- Pydantic runtime model.
from app.services.assistant.contracts import (  # noqa: TC001 -- Pydantic runtime models.
    AcceptedProposalReceipt,
    EntityCreateReceipt,
)


class ConversationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorrectedParticipants(ConversationModel):
    internal: list[str]
    customer: list[str]


class ActivityCorrection(ConversationModel):
    # The model may name any field it heard; the server decides which ones can change here.
    field: str = Field(min_length=1, max_length=64)
    new_value: str | CorrectedParticipants | None
    quote: str = Field(min_length=1, max_length=2000)


class ConversationDecision(ConversationModel):
    semantic_plan: AgentSemanticPlan
    task_relation: Literal["NEW_TASK", "CONTINUE_TASK", "SWITCH_TASK"]
    route: Literal["QUERY", "WORKFLOW", "CLARIFY"]
    boundary: Literal["NEW", "CONTINUE", "AMBIGUOUS"]
    target_task_public_id: str | None = Field(default=None, max_length=64)
    resume_only: bool = False
    field_answer: bool = False
    confidence: float = Field(ge=0, le=1)
    correction: ActivityCorrection | None = None


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


class ConversationFocusRequest(ConversationModel):
    """Open one of the owner's 「待补充」 drafts as the conversation's current card."""

    task_public_id: str = Field(min_length=1, max_length=64)
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


class ConversationDispositionProjection(ConversationModel):
    task_public_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    item_ids: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list, max_length=100)
    card_role: Literal["NONE", "CURRENT", "FINAL"] = "NONE"
    version: int = Field(default=0, ge=0)


class ConversationProjection(ConversationModel):
    visibility: Literal["VISIBLE", "FALLBACK_RECEIPT", "COVERED"] = "VISIBLE"
    covered_by: str | None = Field(default=None, min_length=1)
    activity_public_id: str | None = Field(default=None, min_length=1)
    disposition: ConversationDispositionProjection | None = None

class ConversationLink(ConversationModel):
    """A server-signed in-app page a reply points at; the Web host owns the actual route."""

    page: Literal["leads", "payments", "invoices", "contracts", "customers", "follow_up_tasks"]
    label: str = Field(min_length=1, max_length=40)
    customer_public_id: str | None = Field(default=None, min_length=1, max_length=64)



class ConversationMessage(ConversationModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    at: str
    task: AssistantTaskView | None = None
    boundary: ConversationBoundary | None = None
    outcome: Literal[
        "activity_written", "failure", "follow_up_disposition", "task_completed", "proposal_unavailable"
    ] | None = None
    ui: AgentUIEnvelope | None = None
    links: list[ConversationLink] = Field(default_factory=list, max_length=4)
    projection: ConversationProjection | None = None
    proposal_receipt: AcceptedProposalReceipt | None = Field(default=None, exclude=True)
    entity_receipt: EntityCreateReceipt | None = Field(default=None, exclude=True)
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


class ConversationRequestStatus(ConversationModel):
    """Read-only answer to "did this client request land?" after a lost response.

    none: the server never stored it. running: it is still being handled.
    not_saved: it stalled before producing a result; resending the same request resumes it.
    saved: it produced its result, which ``conversation`` already shows.
    """

    state: Literal["none", "running", "not_saved", "saved"]
    conversation: ConversationView


class PreparedSubmission(ConversationModel):
    task_public_id: str
    turn_id: str
    input: SubmitInputRequest


class ConversationReply(ConversationModel):
    conversation: ConversationView
    submission: PreparedSubmission | None = None
