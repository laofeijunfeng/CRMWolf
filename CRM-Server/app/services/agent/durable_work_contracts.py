"""Typed receipts connecting committed CRM writes to Agent UI projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class AgentAsyncOperationBinding:
    """Exact Agent turn that owns a late-bound durable operation projection."""

    team_id: int
    user_id: int
    session_id: int
    source_user_message_id: int | None = None
    source_assistant_message_id: int | None = None


class DurableWorkReceiptModel(BaseModel):
    """Closed-world base for committed durable-work receipts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CustomerActivityDurableWorkReceipt(DurableWorkReceiptModel):
    """Durable work atomically created by one customer-activity write."""

    type: Literal["customer_activity"] = "customer_activity"
    activity_id: int = Field(gt=0)
    post_commit_job_public_id: str = Field(min_length=1, max_length=64)
    customer_intelligence_request_id: str = Field(min_length=1, max_length=160)


AgentDurableWorkReceipt: TypeAlias = Annotated[
    CustomerActivityDurableWorkReceipt,
    Field(discriminator="type"),
]
