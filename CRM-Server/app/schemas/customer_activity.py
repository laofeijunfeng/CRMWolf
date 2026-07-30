from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.customer_activity_kinds import ACTIVITY_KIND_META, get_activity_kind_meta, normalize_activity_kind


NEXT_FOLLOW_TIME_SOURCES = {"UI_DEFAULT", "USER", "AI_EXTRACTED", "AGENT", "MIGRATED"}


class OwnerInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")

    class Config:
        from_attributes = True


class CustomerBasicInfo(BaseModel):
    id: int = Field(..., description="客户ID")
    account_name: str = Field(..., description="客户公司名称")

    class Config:
        from_attributes = True


class CustomerActivityKindInfo(BaseModel):
    value: str
    category: str
    label: str
    agent_schema: str
    score_rule: str


class CustomerActivityBase(BaseModel):
    activity_kind: str = Field(..., min_length=1, max_length=50, description="活动分类")
    title: Optional[str] = Field(None, max_length=255, description="活动标题")
    source_content: str = Field(..., min_length=1, description="原始输入内容")
    content_json: Optional[Dict[str, Any]] = Field(None, description="结构化活动内容")
    summary: Optional[str] = Field(None, description="列表摘要")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_follow_time_source: Optional[str] = Field(None, description="下次跟进时间来源")
    next_action: Optional[str] = Field(None, description="下一步动作内容")
    occurred_at: Optional[datetime] = Field(None, description="活动发生时间")

    @field_validator("activity_kind")
    @classmethod
    def activity_kind_must_be_known(cls, value: str) -> str:
        normalized = normalize_activity_kind(value)
        if normalized not in ACTIVITY_KIND_META:
            raise ValueError("未知活动分类")
        return normalized

    @field_validator("source_content")
    @classmethod
    def source_content_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("活动内容不能为空")
        return value.strip()

    @field_validator("next_follow_time_source")
    @classmethod
    def next_follow_time_source_must_be_known(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in NEXT_FOLLOW_TIME_SOURCES:
            raise ValueError("未知下次跟进时间来源")
        return value


class CustomerActivityCreate(CustomerActivityBase):
    pass


class CustomerActivityUpdate(BaseModel):
    activity_kind: Optional[str] = Field(None, min_length=1, max_length=50, description="活动分类")
    title: Optional[str] = Field(None, max_length=255, description="活动标题")
    source_content: Optional[str] = Field(None, min_length=1, description="原始输入内容")
    content_json: Optional[Dict[str, Any]] = Field(None, description="结构化活动内容")
    summary: Optional[str] = Field(None, description="列表摘要")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_follow_time_source: Optional[str] = Field(None, description="下次跟进时间来源")
    next_action: Optional[str] = Field(None, description="下一步动作内容")
    occurred_at: Optional[datetime] = Field(None, description="活动发生时间")

    @field_validator("activity_kind")
    @classmethod
    def activity_kind_must_be_known(cls, value: Optional[str]) -> Optional[str]:
        return normalize_activity_kind(value) if value is not None else value

    @field_validator("source_content")
    @classmethod
    def source_content_must_not_be_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and (not value or not value.strip()):
            raise ValueError("活动内容不能为空")
        return value.strip() if value else value

    @field_validator("next_follow_time_source")
    @classmethod
    def next_follow_time_source_must_be_known(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in NEXT_FOLLOW_TIME_SOURCES:
            raise ValueError("未知下次跟进时间来源")
        return value


class CustomerActivityResponse(BaseModel):
    id: int = Field(..., description="活动ID")
    customer_id: Optional[int] = Field(None, description="客户ID")
    original_lead_id: Optional[int] = Field(None, description="原始线索ID")
    deal_journey_id: Optional[int] = Field(None, description="成交旅程ID")
    activity_kind: str = Field(..., description="活动分类")
    activity_category: str = Field(..., description="活动大类")
    activity_label: str = Field(..., description="活动展示名称")
    title: Optional[str] = Field(None, description="活动标题")
    source_content: str = Field(..., description="原始输入内容")
    content_json: Optional[Dict[str, Any]] = Field(None, description="结构化活动内容")
    summary: Optional[str] = Field(None, description="列表摘要")
    processing_status: str = Field(..., description="整理状态")
    processing_error: Optional[str] = Field(None, description="整理失败原因")
    processed_at: Optional[datetime] = Field(None, description="整理完成时间")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_follow_time_source: Optional[str] = Field(None, description="下次跟进时间来源")
    next_action: Optional[str] = Field(None, description="下一步动作内容")
    occurred_at: datetime = Field(..., description="活动发生时间")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")
    creator_info: Optional[OwnerInfo] = Field(None, description="创建人信息")
    customer_info: Optional[CustomerBasicInfo] = Field(None, description="客户基本信息")
    effectiveness_score: Optional[int] = Field(None, description="AI评估活动有效性得分，满分100")
    effectiveness_is_valid: Optional[bool] = Field(None, description="AI评估是否有效")
    effectiveness_reason: Optional[str] = Field(None, description="AI评估原因摘要")
    effectiveness_detail_json: Optional[str] = Field(None, description="AI评估分项明细JSON")
    effectiveness_status: Optional[str] = Field(None, description="AI评估状态")
    effectiveness_evaluated_time: Optional[datetime] = Field(None, description="AI评估完成时间")
    effectiveness_error_message: Optional[str] = Field(None, description="AI评估失败原因")


class CustomerActivityProcessResponse(BaseModel):
    message: str


class MessageResponse(BaseModel):
    message: str


def kind_infos() -> list[CustomerActivityKindInfo]:
    return [CustomerActivityKindInfo(**get_activity_kind_meta(kind)) for kind in ACTIVITY_KIND_META]
