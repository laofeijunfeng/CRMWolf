"""AI OpenAPI 通用 Schema 定义

所有 AI OpenAPI 接口必须使用此模块定义的请求/响应结构。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, validator


# ==================== 通用请求结构 ====================

class AIRequestBase(BaseModel):
    """AI OpenAPI 统一请求基类

    所有 Action 层接口必须继承此类。
    """

    preview: bool = Field(
        default=True,
        description="是否仅预览（True=返回变更计划，不执行；False=执行操作）"
    )
    action_id: Optional[str] = Field(
        default=None,
        description="幂等 ID（执行模式时必填）"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="上下文信息（用于多轮对话实体继承）"
    )

    @validator("action_id")
    def validate_action_id(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """执行模式必须提供 action_id"""
        if not values.get("preview") and not v:
            raise ValueError("action_id required when preview=False")
        return v


# ==================== 通用响应结构 ====================

class FieldChange(BaseModel):
    """字段变更详情"""

    field: str = Field(description="字段名")
    from_value: Optional[Any] = Field(default=None, description="变更前值")
    to_value: Any = Field(description="变更后值")


class ActionPlan(BaseModel):
    """变更计划（Preview 模式返回）"""

    description: str = Field(description="变更描述（人类可读）")
    changes: List[FieldChange] = Field(description="变更详情列表")
    entity_type: Optional[str] = Field(default=None, description="实体类型")
    entity_id: Optional[int] = Field(default=None, description="实体 ID")


class AIResponseBase(BaseModel):
    """AI OpenAPI 统一响应基类

    所有 Action 层接口必须返回此类或其子类。
    """

    action_id: str = Field(description="幂等 ID")
    status: Literal["preview", "completed", "failed", "rejected"] = Field(
        description="操作状态"
    )
    plan: Optional[ActionPlan] = Field(
        default=None,
        description="变更计划（preview 状态时必填）"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="置信度（0.0-1.0）"
    )
    requires_confirmation: bool = Field(
        description="是否需要人工确认"
    )
    message: str = Field(description="操作结果消息")
    error: Optional[str] = Field(default=None, description="错误信息")
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="返回数据（completed 状态时返回实体数据）"
    )


# ==================== 错误响应结构 ====================

class AIErrorResponse(BaseModel):
    """AI OpenAPI 错误响应"""

    action_id: str
    status: Literal["failed", "rejected"]
    message: str
    error: str
    error_code: Optional[str] = Field(default=None, description="错误码")
    missing_fields: Optional[List[str]] = Field(
        default=None,
        description="缺失字段提示"
    )
    suggested_actions: Optional[List[str]] = Field(
        default=None,
        description="推荐下一步动作"
    )


# ==================== Action ID 生成 ====================

import time
import uuid


def generate_action_id() -> str:
    """生成幂等 Action ID

    格式: act_{timestamp}_{random_suffix}
    """
    timestamp = int(time.time() * 1000)
    suffix = uuid.uuid4().hex[:8]
    return f"act_{timestamp}_{suffix}"


# ==================== 导出 ====================

__all__ = [
    "AIRequestBase",
    "AIResponseBase",
    "AIErrorResponse",
    "ActionPlan",
    "FieldChange",
    "generate_action_id",
]