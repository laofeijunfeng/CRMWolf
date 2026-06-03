"""
AI 客户跟进解析 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional


class CustomerAIParseRequest(BaseModel):
    """AI 解析客户跟进请求"""
    content: str = Field(..., min_length=1, max_length=2000, description="用户输入的自然语言描述")
    customer_id: int = Field(..., description="客户 ID")
    customer_name: str = Field(..., description="客户名称")


class CustomerAICreateRequest(BaseModel):
    """AI 创建客户跟进请求（用户确认后提交）"""
    customer_id: int = Field(..., description="客户 ID")
    customer_name: str = Field(..., description="客户名称")
    content: str = Field(..., description="跟进内容")
    method: Optional[str] = Field(default=None, description="跟进方式（电话/微信/拜访/邮件）")
    next_action: Optional[str] = Field(default=None, description="下一步动作")
    next_follow_time: Optional[str] = Field(default=None, description="下次跟进时间")