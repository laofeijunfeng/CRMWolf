from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReminderObjectType = Literal[
    "business_journey",
    "opportunity",
    "customer",
    "lead",
    "follow_up_task",
    "approval",
    "payment_plan",
]
ReminderTrigger = Literal["schedule", "change", "date"]


class ReminderCatalogChoice(BaseModel):
    value: str
    label: str


class ReminderCatalogField(BaseModel):
    value: str
    label: str
    operators: list[ReminderCatalogChoice]
    options: list[ReminderCatalogChoice] | None = None


class ReminderCatalogObject(BaseModel):
    object_type: ReminderObjectType
    label: str
    recipients: list[ReminderCatalogChoice]
    fields: list[ReminderCatalogField]


class ReminderRecipientUser(BaseModel):
    id: str
    name: str


class ReminderRuleWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    object_type: ReminderObjectType
    trigger: ReminderTrigger
    version: Literal[1, 2] = 1
    status: str | None = None
    inactive_days: int | None = Field(None, ge=1, le=365)
    date_field: str | None = None
    offset_days: int | None = Field(0, ge=-30, le=30)
    require_no_new_activity: bool = False
    trigger_time: str | None = None
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    recipients: list[str] = Field(..., min_length=1)
    message_title: str | None = Field(None, max_length=100)
    message_template: str = Field(..., min_length=1, max_length=1000)
    channels: list[Literal["in_app", "feishu"]] = Field(..., min_length=1)
    notify_once_per_window: bool = True


class ReminderRuleUpdate(ReminderRuleWrite):
    expected_revision: int = Field(..., ge=1)


class ReminderRuleEnabledUpdate(BaseModel):
    enabled: bool
    expected_revision: int = Field(..., ge=1)


class ReminderRuleView(ReminderRuleWrite):
    id: int
    revision: int
    enabled: bool
    sentence: str
    created_time: datetime
    last_modified_time: datetime


class ReminderRuleRunView(BaseModel):
    id: int
    rule_id: int
    object_type: str
    object_id: int
    message: str
    sent_count: int
    skipped_count: int
    created_time: datetime
