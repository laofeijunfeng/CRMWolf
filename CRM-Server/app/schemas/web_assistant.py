"""
Web AI 助手 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal


class EntityContext(BaseModel):
    """实体上下文（JSON 格式传递）"""
    entity_type: Literal["customer", "opportunity", "lead", "contract"] = Field(
        ..., description="实体类型"
    )
    entity_id: int = Field(..., description="实体 ID")
    entity_name: str = Field(..., description="实体名称")


class WebAssistantRequest(BaseModel):
    """Web AI 助手请求"""
    content: str = Field(..., min_length=1, max_length=2000, description="用户输入内容")
    tool: Optional[str] = Field(default=None, description="确认执行时的工具名称")
    params: Optional[Dict[str, Any]] = Field(default=None, description="确认执行时的参数")
    entity_context: Optional[EntityContext] = Field(
        default=None, description="实体上下文（JSON 格式）"
    )