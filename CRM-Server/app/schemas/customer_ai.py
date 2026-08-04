"""AI 客户活动解析 Schema."""
from pydantic import BaseModel, Field
from typing import Optional


class CustomerAIParseRequest(BaseModel):
    """AI 解析客户活动请求"""
    content: str = Field(..., min_length=1, max_length=20000, description="用户输入的自然语言描述")
    customer_id: str = Field(..., description="客户对外 ID")
    customer_name: str = Field(..., description="客户名称")


class CustomerAICreateRequest(BaseModel):
    """AI 创建客户活动请求（用户确认后提交）"""
    customer_id: str = Field(..., description="客户对外 ID")
    customer_name: str = Field(..., description="客户名称")
    content: str = Field(..., description="活动原始内容")
    method: Optional[str] = Field(default=None, description="活动方式（电话/微信/拜访/邮件/线上会议/线下会议）")
    next_action: Optional[str] = Field(default=None, description="下一步动作")
    next_follow_time: Optional[str] = Field(default=None, description="下次跟进时间")
