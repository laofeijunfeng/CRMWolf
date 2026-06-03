"""AI OpenAPI 审计日志路由

提供 AI 操作的审计日志查询。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.ai.deps import get_ai_user
from app.core.database import get_db
from app.models.user import User
from app.services.operation_log_service import operation_log_service


router = APIRouter()


# ==================== 请求/响应 Schema ====================

class AILogEntry(BaseModel):
    """AI 审计日志条目"""

    id: int = Field(..., description="日志 ID")
    action_id: Optional[str] = Field(None, description="动作唯一标识")
    event_type: str = Field(..., description="事件类型")
    resource_type: str = Field(..., description="资源类型")
    resource_id: Optional[str] = Field(None, description="资源 ID")
    action_type: Optional[str] = Field(None, description="动作类型")
    content: Dict[str, Any] = Field(default_factory=dict, description="日志内容")
    operator_type: str = Field(..., description="操作者类型")
    operator_id: str = Field(..., description="操作者 ID")
    created_at: datetime = Field(..., description="创建时间")


class AILogListResponse(BaseModel):
    """AI 审计日志列表响应"""

    logs: List[AILogEntry] = Field(default_factory=list, description="日志列表")
    total: int = Field(0, description="总数")
    page: int = Field(1, description="当前页")
    page_size: int = Field(20, description="每页数量")


class AILogStatsResponse(BaseModel):
    """AI 审计统计响应"""

    total_operations: int = Field(0, description="总操作数")
    success_count: int = Field(0, description="成功数")
    failed_count: int = Field(0, description="失败数")
    action_distribution: Dict[str, int] = Field(default_factory=dict, description="动作分布")
    resource_distribution: Dict[str, int] = Field(default_factory=dict, description="资源分布")


# ==================== 审计日志查询 ====================

@router.get("", response_model=AILogListResponse, summary="查询 AI 审计日志")
async def query_ai_logs(
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
    action_id: Optional[str] = Query(None, description="按 action_id 精确匹配"),
    action_type: Optional[str] = Query(None, description="按动作类型筛选"),
    resource_type: Optional[str] = Query(None, description="按资源类型筛选"),
    resource_id: Optional[str] = Query(None, description="按资源 ID 精确匹配"),
    event_type: Optional[str] = Query(None, description="按事件类型筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> AILogListResponse:
    """查询 AI 操作的审计日志

    只返回 source='ai' 的日志（event_type 以 'AI_' 开头）。
    支持多维度筛选。
    """
    from sqlalchemy import and_

    # 构建查询条件
    filters = []

    # 固定筛选：只查 AI 操作（event_type 以 AI_ 开头）
    filters.append(operation_log_service.model.event_type.like("AI_%"))

    # 或者通过 content.source 筛选（作为备用条件）
    # MySQL JSON 查询需要特殊处理，这里主要依赖 event_type

    # 动态筛选
    if action_id:
        # action_id 存储在 content 中
        filters.append(operation_log_service.model.content["action_id"].as_string() == action_id)

    if action_type:
        filters.append(operation_log_service.model.content["action_type"].as_string() == action_type)

    if resource_type:
        filters.append(operation_log_service.model.primary_resource_type == resource_type)

    if resource_id:
        filters.append(operation_log_service.model.primary_resource_id == int(resource_id))

    if event_type:
        filters.append(operation_log_service.model.event_type == event_type)

    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        filters.append(operation_log_service.model.operated_at >= start_datetime)

    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        filters.append(operation_log_service.model.operated_at <= end_datetime)

    # 查询
    query = db.query(operation_log_service.model).filter(and_(*filters))

    # 排序
    query = query.order_by(operation_log_service.model.operated_at.desc())

    # 分页
    total = query.count()
    offset = (page - 1) * page_size
    logs = query.offset(offset).limit(page_size).all()

    # 转换
    log_entries = []
    for log in logs:
        content_dict = log.content if isinstance(log.content, dict) else {}
        log_entries.append(AILogEntry(
            id=log.id,
            action_id=content_dict.get("action_id"),
            event_type=log.event_type,
            resource_type=log.primary_resource_type,
            resource_id=str(log.primary_resource_id),
            action_type=content_dict.get("action_type"),
            content=content_dict,
            operator_type=content_dict.get("operator_type", "ai"),
            operator_id=log.operator_id,
            created_at=log.operated_at,
        ))

    return AILogListResponse(
        logs=log_entries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=AILogStatsResponse, summary="AI 操作统计")
async def get_ai_log_stats(
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
) -> AILogStatsResponse:
    """获取 AI 操作统计

    包含：总操作数、成功/失败数、动作类型分布、资源类型分布。
    """
    from datetime import datetime

    # 构建基础查询
    base_query = db.query(operation_log_service.model).filter(
        operation_log_service.model.event_type.like("AI_%")
    )

    # 时间范围筛选
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        base_query = base_query.filter(operation_log_service.model.operated_at >= start_datetime)

    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        base_query = base_query.filter(operation_log_service.model.operated_at <= end_datetime)

    # 总数
    total_operations = base_query.count()

    # 成功/失败统计（基于 content.status）
    success_count = 0
    failed_count = 0

    for log in base_query.all():
        content = log.content if isinstance(log.content, dict) else {}
        status = content.get("status", "")
        if status in ["completed", "success"]:
            success_count += 1
        elif status in ["failed", "error"]:
            failed_count += 1

    # 动作类型分布
    action_distribution = {}
    for log in base_query.all():
        content = log.content if isinstance(log.content, dict) else {}
        action_type = content.get("action_type", "unknown")
        action_distribution[action_type] = action_distribution.get(action_type, 0) + 1

    # 资源类型分布
    resource_distribution = {}
    for log in base_query.all():
        resource_type = log.primary_resource_type or "unknown"
        resource_distribution[resource_type] = resource_distribution.get(resource_type, 0) + 1

    return AILogStatsResponse(
        total_operations=total_operations,
        success_count=success_count,
        failed_count=failed_count,
        action_distribution=action_distribution,
        resource_distribution=resource_distribution,
    )


@router.get("/{log_id}", response_model=AILogEntry, summary="查询单条日志")
async def get_ai_log_detail(
    log_id: int,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> AILogEntry:
    """查询单条 AI 审计日志详情"""
    log = db.query(operation_log_service.model).filter(
        operation_log_service.model.id == log_id,
        operation_log_service.model.event_type.like("AI_%"),
    ).first()

    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="日志不存在")

    content_dict = log.content if isinstance(log.content, dict) else {}

    return AILogEntry(
        id=log.id,
        action_id=content_dict.get("action_id"),
        event_type=log.event_type,
        resource_type=log.primary_resource_type,
        resource_id=str(log.primary_resource_id),
        action_type=content_dict.get("action_type"),
        content=content_dict,
        operator_type=content_dict.get("operator_type", "ai"),
        operator_id=log.operator_id,
        created_at=log.operated_at,
    )


__all__ = ["router"]