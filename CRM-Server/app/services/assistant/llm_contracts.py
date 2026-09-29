"""Typed neutral LLM contracts for activity kind and canonical structuring."""

# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from app.services.customer_activity_ai.schemas import FollowUpContent, MeetingContent

ActivityKind = Literal["FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"]


class KindDecision(BaseModel):
    """Closed-world result of the kind classifier."""

    model_config = ConfigDict(extra="forbid")

    kind: ActivityKind | Literal["UNCLEAR"] = "UNCLEAR"
    reason: str = Field(default="", max_length=200)


class StructuredFollowUp(BaseModel):
    """Follow-up structuring output mapped into the task draft."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=20000, description="整理后的跟进正文，保留全部事实点")
    customer_name: str = Field(default="", max_length=500, description="客户名称文本，仅作查找线索")
    next_action: str = Field(default="", max_length=4000, description="下一步动作，忠于原文")
    next_follow_time_text: str = Field(default="", max_length=200, description="原文中的时间表达")
    content_json: FollowUpContent | None = None


class StructuredMeeting(BaseModel):
    """Meeting structuring output mapped into the task draft."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(default="", max_length=500, description="客户名称文本，仅作查找线索")
    meeting_subject: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=20000, description="按发言人整理的关键讨论")
    participants: str = Field(default="", max_length=2000, description="我方与客户方参会角色")
    next_action: str = Field(default="", max_length=4000, description="首要行动项，含负责人与时间")
    next_follow_time_text: str = Field(default="", max_length=200)
    content_json: MeetingContent | None = None


class StructureDraftResult(BaseModel):
    """Normalized structuring result consumed by the coordinator."""

    model_config = ConfigDict(extra="forbid")

    kind_confirmed: ActivityKind
    content: str
    customer_name: str = ""
    next_action: str = ""
    next_follow_time_text: str = ""
    meeting_subject: str = ""
    participants: str = ""
    content_json: dict[str, Any] | None = None
    structuring_model: str = ""
