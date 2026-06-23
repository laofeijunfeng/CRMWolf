"""
撤销 API 接口

提供撤销操作的 REST API 接口：
- 单步撤销
- 流程级撤销
- 撤销状态查询
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User
from app.services.workflow.undo_service import undo_service


router = APIRouter(prefix="/workflow", tags=["workflow-undo"])


@router.post("/undo/{operation_id}")
async def undo_operation(
    operation_id: int,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    撤销单步操作

    Args:
        operation_id: 操作ID
        current_user: 当前用户
        team_id: 团队ID
        db: 数据库会话

    Returns:
        撤销结果
    """
    user_id = current_user.id
    result = undo_service.undo_single(db, operation_id, user_id)

    if result.success:
        return {
            "success": True,
            "message": result.message,
            "impact": [
                {
                    "type": i.type,
                    "resource_type": i.resource_type,
                    "resource_id": i.resource_id,
                    "description": i.description
                }
                for i in result.impact
            ]
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=result.reason
        )


@router.post("/undo/workflow/{session_id}")
async def undo_workflow(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    撤销整个流程

    Args:
        session_id: Workflow Session ID
        current_user: 当前用户
        team_id: 团队ID
        db: 数据库会话

    Returns:
        撤销结果（包含撤销的操作数量）
    """
    user_id = current_user.id
    result = undo_service.undo_workflow(db, session_id, user_id)

    if result.success:
        return {
            "success": True,
            "undone_count": result.undone_count,
            "message": result.message,
            "failed_operations": result.failed_operations
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=result.reason
        )


@router.get("/undo/status/{operation_id}")
async def get_undo_status(
    operation_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取撤销状态

    Args:
        operation_id: 操作ID
        db: 数据库会话

    Returns:
        撤销状态信息（是否可撤销、剩余时间、撤销接口）
    """
    return undo_service.get_undo_status(db, operation_id)


@router.get("/undo/recent/{user_id}")
async def get_recent_undoable(
    user_id: int,
    within_seconds: int = 60,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取用户最近的可撤销操作

    Args:
        user_id: 用户ID
        within_seconds: 时间窗口（秒）
        db: 数据库会话

    Returns:
        最近可撤销操作的信息
    """
    from app.crud.operation_log import operation_log_crud

    log = operation_log_crud.get_recent_undoable(db, str(user_id), within_seconds)

    if log:
        return undo_service.get_undo_status(db, log.id)
    else:
        return {"can_undo": False, "reason": "无最近的可撤销操作"}