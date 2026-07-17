from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class OwnerInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")

    class Config:
        from_attributes = True


class LeadBasicInfo(BaseModel):
    id: int = Field(..., description="线索ID")
    lead_name: str = Field(..., description="线索名称")

    class Config:
        from_attributes = True


class LeadFollowUpBase(BaseModel):
    content: str = Field(..., min_length=1, description="跟进内容")
    method: str = Field(..., min_length=1, max_length=50, description="跟进方式")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_action: Optional[str] = Field(None, description="下一步动作内容")

    @field_validator('content')
    @classmethod
    def content_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('跟进内容不能为空')
        return v.strip() if v else v

    @field_validator('method')
    @classmethod
    def method_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('跟进方式不能为空')
        return v.strip() if v else v


class LeadFollowUpCreate(LeadFollowUpBase):
    pass


class LeadFollowUpUpdate(BaseModel):
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")


class LeadFollowUpResponse(BaseModel):
    id: int = Field(..., description="跟进记录ID")
    lead_id: int = Field(..., description="线索ID")
    content: str = Field(..., description="跟进内容")
    method: str = Field(..., description="跟进方式")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_action: Optional[str] = Field(None, description="下一步动作内容")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    creator_info: Optional[OwnerInfo] = Field(None, description="跟进人信息")
    lead_info: Optional[LeadBasicInfo] = Field(None, description="线索基本信息")


class MessageResponse(BaseModel):
    message: str
