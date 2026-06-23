"""
AI Conversation Schema

用于 AI 对话历史的 Pydantic schema 校验
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


class ExecutionStepType(str, Enum):
    """执行步骤类型枚举"""
    ROUND_START = "ROUND_START"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    ROUND_COMPLETED = "ROUND_COMPLETED"
    REACT_COMPLETE = "REACT_COMPLETE"
    ERROR = "ERROR"


class ExecutionStepSchema(BaseModel):
    """执行步骤 Schema"""
    id: str = Field(..., description="步骤唯一标识")
    type: ExecutionStepType = Field(..., description="步骤类型")
    title: str = Field(..., description="业务化标题")
    description: Optional[str] = Field(None, description="步骤描述")
    timestamp: datetime = Field(..., description="时间戳")
    round: Optional[int] = Field(None, description="轮次编号")
    tool: Optional[str] = Field(None, description="工具名称")
    params: Optional[dict] = Field(None, description="工具参数")
    result: Optional[dict] = Field(None, description="执行结果")
    success: Optional[bool] = Field(None, description="是否成功")
    error: Optional[str] = Field(None, description="错误信息")
    businessParams: Optional[str] = Field(None, description="业务化参数描述")

    class Config:
        from_attributes = True
        use_enum_values = True


class MessageItemSchema(BaseModel):
    """消息项 Schema"""
    role: str = Field(..., description="角色：user 或 assistant")
    content: str = Field(..., description="消息内容")
    timestamp: str = Field(..., description="时间戳")
    execution_steps: Optional[List[ExecutionStepSchema]] = Field(
        None, description="执行步骤列表（仅 assistant 消息）"
    )

    class Config:
        from_attributes = True


class ConversationHistoryItemSchema(BaseModel):
    """对话历史项 Schema"""
    id: int = Field(..., description="对话 ID")
    title: str = Field(..., description="对话标题")
    action_type: Optional[str] = Field(None, description="操作类型")
    entity_type: Optional[str] = Field(None, description="实体类型")
    entity_id: Optional[int] = Field(None, description="实体 ID")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class ConversationDetailSchema(BaseModel):
    """对话详情 Schema"""
    id: int = Field(..., description="对话 ID")
    title: str = Field(..., description="对话标题")
    summary: Optional[str] = Field(None, description="对话摘要")
    action_type: Optional[str] = Field(None, description="操作类型")
    entity_type: Optional[str] = Field(None, description="实体类型")
    entity_id: Optional[int] = Field(None, description="实体 ID")
    messages: List[MessageItemSchema] = Field(..., description="消息列表")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class ConversationGroupSchema(BaseModel):
    """对话分组 Schema"""
    today: List[ConversationHistoryItemSchema] = Field(..., description="今天的对话")
    yesterday: List[ConversationHistoryItemSchema] = Field(..., description="昨天的对话")
    earlier: List[ConversationHistoryItemSchema] = Field(..., description="更早的对话")


class HistoryListResponseSchema(BaseModel):
    """历史列表响应 Schema"""
    groups: ConversationGroupSchema = Field(..., description="分组对话列表")
    total: int = Field(..., description="总数")


class ConversationCreateParamsSchema(BaseModel):
    """创建对话请求参数 Schema"""
    title: str = Field(..., max_length=200, description="对话标题")
    messages: List[MessageItemSchema] = Field(..., description="消息列表")
    action_type: Optional[str] = Field(None, description="操作类型")
    entity_type: Optional[str] = Field(None, description="实体类型")
    entity_id: Optional[int] = Field(None, description="实体 ID")