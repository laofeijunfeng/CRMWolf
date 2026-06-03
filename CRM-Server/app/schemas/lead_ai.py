"""
AI 解析线索信息 Schema

用于 AI 智能创建线索功能的请求和响应结构
"""
from pydantic import BaseModel, Field
from typing import Optional


class LeadAIParseRequest(BaseModel):
    """AI 解析线索信息请求"""
    content: str = Field(..., min_length=1, description="用户输入的自然语言描述")


class LeadAIParsedInfo(BaseModel):
    """AI 解析出的线索信息"""
    lead_name: Optional[str] = Field(None, description="线索名称")
    source: Optional[str] = Field(None, description="线索来源")
    city: Optional[str] = Field(None, description="所在城市")
    company_scale: Optional[str] = Field(None, description="公司规模")
    contact_name: Optional[str] = Field(None, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, description="联系电话")

    # 缺失字段提示
    missing_fields: list[str] = Field(default_factory=list, description="缺失的必填字段")


class LeadAIFollowUpInfo(BaseModel):
    """AI 解析出的跟进记录信息"""
    content: Optional[str] = Field(None, description="跟进内容（除下一步计划外的其他信息）")
    method: Optional[str] = Field(None, description="跟进方式（电话/微信/拜访/邮件）")
    next_action: Optional[str] = Field(None, description="下一步动作/计划")
    next_follow_time: Optional[str] = Field(None, description="下次跟进时间（相对时间表达，如'下周三'、'三天后'）")


class LeadAIParseResponse(BaseModel):
    """AI 解析线索信息响应"""
    lead_info: LeadAIParsedInfo = Field(..., description="解析出的线索信息")
    follow_up_info: Optional[LeadAIFollowUpInfo] = Field(None, description="解析出的跟进记录信息")
    thinking_process: Optional[str] = Field(None, description="AI 思考过程")


class LeadAICreateRequest(BaseModel):
    """AI 创建线索请求（用户确认后提交）"""
    lead_name: str = Field(..., description="线索名称")
    source: str = Field(..., description="线索来源")
    city: str = Field(..., description="所在城市")
    contact_name: str = Field(..., description="联系人姓名")
    contact_phone: str = Field(..., description="联系电话")
    company_scale: Optional[str] = Field(None, description="公司规模")
    # 跟进记录相关
    follow_up_content: Optional[str] = Field(None, description="跟进内容")
    next_action: Optional[str] = Field(None, description="下一步动作")
    next_follow_time: Optional[str] = Field(None, description="下次跟进时间")