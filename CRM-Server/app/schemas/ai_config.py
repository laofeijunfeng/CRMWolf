"""
AI 配置 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AIConfigCreate(BaseModel):
    """创建/更新 AI 配置请求"""
    api_host: str = Field(..., min_length=1, max_length=255, description="AI接口基础地址（如 https://api.deepseek.com/v1）")
    api_key: str = Field(..., min_length=1, max_length=255, description="API密钥")
    model_name: str = Field(..., min_length=1, max_length=100, description="模型名称（如 deepseek-chat）")


class AIConfigResponse(BaseModel):
    """AI 配置响应"""
    id: int = Field(..., description="配置ID（固定为1）")
    api_host: str = Field(..., description="AI接口基础地址")
    api_key_masked: str = Field(..., description="掩码后的API密钥")
    model_name: str = Field(..., description="模型名称")
    temperature: float = Field(..., description="温度参数")
    max_tokens: int = Field(..., description="最大tokens")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class AITestRequest(BaseModel):
    """测试 AI 连接请求"""
    test_message: str = Field(..., min_length=1, max_length=500, description="测试消息内容")


class AITestResponse(BaseModel):
    """测试 AI 连接响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="提示信息")
    ai_response: Optional[str] = Field(None, description="AI响应内容（测试结果）")