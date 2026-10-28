"""Typed HTTP contracts shared by assistant transport and presentation."""
# ruff: noqa: RUF001 -- Chinese user-facing copy uses native punctuation.

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.services.assistant.contracts import (  # noqa: TC001 -- Pydantic resolves models at runtime.
    CommittedReceipt,
    TaskDraft,
    TaskStatus,
    TaskWaiting,
    TurnStatus,
)


class AssistantTaskView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str
    status: TaskStatus
    goal: str
    activity_kind: str | None
    draft: TaskDraft
    waiting: TaskWaiting | None
    committed: list[CommittedReceipt]
    budget_steps: int
    budget_max_steps: int
    version: int
    last_modified_time: str | None = None
    processing_turn_id: str | None = None
    processing_turn_status: TurnStatus | None = None
    reprocess_turn_id: str | None = None

    @model_validator(mode="after")
    def match_processing_pointer(self) -> AssistantTaskView:
        if (self.processing_turn_id is None) != (self.processing_turn_status is None):
            raise ValueError("processing turn ID and status must appear together")
        return self

    @field_serializer("committed")
    def serialize_receipts(self, receipts: list[CommittedReceipt]) -> list[dict[str, object]]:
        return [receipt.model_dump(mode="json", exclude_unset=True) for receipt in receipts]


class AssistantTurnEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    event: str
    data: dict[str, object]


class AssistantTurnView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    status: TurnStatus
    lease_version: int = Field(ge=0)
    reprocess_allowed: bool = False
    events: list[AssistantTurnEventView]
    task: AssistantTaskView


class RetryTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_lease_version: int = Field(ge=0)
    after_seq: int = Field(default=0, ge=0)


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000, description="任务目标，来自用户首句")
    client_request_id: str = Field(min_length=8, max_length=128)


class SubmitInputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "submit_field", "confirm", "cancel"]
    text: str | None = Field(default=None, max_length=20000)
    choice: str | None = Field(default=None, max_length=64)
    client_request_id: str = Field(min_length=8, max_length=128)
    action_id: str | None = Field(default=None, max_length=128)
    expected_version: int | None = Field(default=None, ge=0)


class SubmitInputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: AssistantTaskView
    message: str = Field(min_length=1, max_length=2000)
