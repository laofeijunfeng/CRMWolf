"""
AI 助手 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional


class AIAssistantChatRequest(BaseModel):
    """内置 AI 助手聊天请求"""
    content: str = Field(..., min_length=1, max_length=2000, description="用户输入内容")