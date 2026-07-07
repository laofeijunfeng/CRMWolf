from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class OwnerInfo(BaseModel):
    id: str = Field(..., description="用户飞书Open ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")
    
    class Config:
        from_attributes = True


class CustomerBasicInfo(BaseModel):
    id: int = Field(..., description="客户ID")
    account_name: str = Field(..., description="客户公司名称")
    
    class Config:
        from_attributes = True


class CustomerFollowUpBase(BaseModel):
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


class CustomerFollowUpCreate(CustomerFollowUpBase):
    pass


class CustomerFollowUpUpdate(BaseModel):
    method: Optional[str] = Field(None, min_length=1, max_length=50, description="跟进方式")
    content: Optional[str] = Field(None, min_length=1, description="跟进内容")
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


class CustomerFollowUpResponse(BaseModel):
    id: int = Field(..., description="跟进记录ID")
    customer_id: Optional[int] = Field(None, description="客户ID")
    original_lead_id: Optional[int] = Field(None, description="原始线索ID")
    content: str = Field(..., description="跟进内容")
    method: str = Field(..., description="跟进方式")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_action: Optional[str] = Field(None, description="下一步动作内容")
    creator_id: str = Field(..., description="创建人飞书用户ID")
    created_time: datetime = Field(..., description="创建时间")
    creator_info: Optional[OwnerInfo] = Field(None, description="跟进人信息")
    customer_info: Optional[CustomerBasicInfo] = Field(None, description="客户基本信息")


class MessageResponse(BaseModel):
    message: str
