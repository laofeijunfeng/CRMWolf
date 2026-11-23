"""
AI 创建客户 Schema

用于 AI 智能创建客户功能
"""

from pydantic import BaseModel, Field


class CustomerAICreateParseRequest(BaseModel):
    """AI 解析客户创建信息请求"""
    content: str = Field(..., min_length=1, description="用户输入的自然语言描述")


class CustomerAIParsedInfo(BaseModel):
    """AI 解析出的客户信息"""
    account_name: str | None = Field(None, description="客户公司名称")
    city: str | None = Field(None, description="所在城市")
    company_scale: str | None = Field(None, description="公司规模")
    source: str | None = Field(None, description="客户来源")
    industry_hint: str | None = Field(None, description="行业关键词")
    missing_fields: list[str] = Field(default_factory=list, description="缺失的必填字段")


class CustomerAIContactInfo(BaseModel):
    """AI 解析出的主联系人信息"""
    contact_name: str | None = Field(None, description="联系人姓名")
    contact_phone: str | None = Field(None, description="联系电话")
    contact_position: str | None = Field(None, description="职务")
    contact_gender: str | None = Field(None, description="性别：1=男, 2=女")
    contact_email: str | None = Field(None, description="邮箱")


class CustomerAIFollowUpInfo(BaseModel):
    """AI 解析出的跟进记录信息"""
    content: str | None = Field(None, description="跟进内容")
    next_action: str | None = Field(None, description="下一步动作")
    next_follow_time: str | None = Field(None, description="下次跟进时间")


class CustomerAICreateRequest(BaseModel):
    """AI 创建客户请求（用户确认后提交）"""
    customer_info: CustomerAIParsedInfo = Field(..., description="客户信息")
    contact_info: CustomerAIContactInfo = Field(..., description="主联系人信息")
    follow_up_info: CustomerAIFollowUpInfo | None = Field(None, description="跟进信息（可选）")
