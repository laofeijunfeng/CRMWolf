"""
线索解析 Schema

用于内部线索和跟进信息解析，不承载独立线索创建 API。
"""
from typing import Optional

from pydantic import BaseModel, Field


class LeadParseRequest(BaseModel):
    """线索解析请求"""

    content: str = Field(..., min_length=1, description="用户输入的自然语言描述")


class LeadParsedInfo(BaseModel):
    """解析出的线索信息"""

    lead_name: Optional[str] = Field(None, description="线索名称")
    source: Optional[str] = Field(None, description="线索来源")
    city: Optional[str] = Field(None, description="所在城市")
    company_scale: Optional[str] = Field(None, description="公司规模")
    contact_name: Optional[str] = Field(None, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, description="联系电话")
    missing_fields: list[str] = Field(default_factory=list, description="缺失的必填字段")


class LeadFollowUpParseInfo(BaseModel):
    """解析出的线索跟进记录信息"""

    content: Optional[str] = Field(None, description="跟进内容（除下一步计划外的其他信息）")
    method: Optional[str] = Field(None, description="跟进方式（电话/微信/拜访/邮件）")
    next_action: Optional[str] = Field(None, description="下一步动作/计划")
    next_follow_time: Optional[str] = Field(None, description="下次跟进时间")


class LeadParseResponse(BaseModel):
    """线索解析响应"""

    lead_info: LeadParsedInfo = Field(..., description="解析出的线索信息")
    follow_up_info: Optional[LeadFollowUpParseInfo] = Field(None, description="解析出的跟进记录信息")
    thinking_process: Optional[str] = Field(None, description="解析思考过程")
