"""
Web AI 助手 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class WebAssistantRequest(BaseModel):
    """Web AI 助手请求"""
    content: str = Field(..., min_length=1, max_length=2000, description="用户输入内容")
    skill: Optional[str] = Field(default=None, description="确认执行时的 Skill 名称")
    action: Optional[str] = Field(default=None, description="确认执行时的 Action 名称")
    params: Optional[Dict[str, Any]] = Field(default=None, description="确认执行时的参数")