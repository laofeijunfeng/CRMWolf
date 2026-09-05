"""Public command execution contracts used by non-Agent write flows."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CommandResource(BaseModel):
    type: str
    public_id: str
    version: int | None = None


class CommandEffect(BaseModel):
    type: str
    public_id: str | None = None
    status: str
    detail: str | None = None


class CommandNextAction(BaseModel):
    id: str
    label: str
    kind: str


class CommandError(BaseModel):
    code: str
    message: str
    field_path: str | None = None


class CommandResult(BaseModel, Generic[T]):
    operation_id: str
    status: str
    data: T | None = None
    resource: CommandResource | None = None
    effects: list[CommandEffect] = Field(default_factory=list)
    next_actions: list[CommandNextAction] = Field(default_factory=list)
    retryable: bool = False
    queryable: bool = True
    error: CommandError | None = None
    correlation_id: str | None = None


class CommandExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operation_id: str
    status: str
    command_type: str
    resource: CommandResource | None = None
    data: Any | None = None
    effects: list[CommandEffect] = Field(default_factory=list)
    next_actions: list[CommandNextAction] = Field(default_factory=list)
    retryable: bool
    queryable: bool = True
    error: CommandError | None = None
    correlation_id: str | None = None
    created_time: datetime
    updated_time: datetime
    completed_time: datetime | None = None
