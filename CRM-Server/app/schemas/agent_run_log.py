"""HTTP contracts for the Agent run-log inspector."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

TurnOutcome: TypeAlias = Literal[
    "answered",
    "blocked_unwritten",
    "waiting_confirmation",
    "waiting_input",
    "written",
    "failed",
    "clarified",
]
StepKind: TypeAlias = Literal["model", "code", "interaction", "api", "background"]
StepTone: TypeAlias = Literal["done", "blocked", "skipped"]


class AgentRunLogStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: StepKind
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=2_000)
    tone: StepTone


class AgentRunLogTurnListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1, max_length=64)
    user_id: int = Field(gt=0)
    user_name: str | None = Field(default=None, min_length=1, max_length=100)
    user_text: str = Field(min_length=1, max_length=10_000)
    outcome: TurnOutcome
    summary: str = Field(min_length=1, max_length=500)
    quality_score: int | None = Field(default=None, ge=0, le=100)
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    created_time: datetime


class AgentRunLogTurnDetail(AgentRunLogTurnListItem):
    steps: list[AgentRunLogStep] = Field(min_length=6, max_length=6)
