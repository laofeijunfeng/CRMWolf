"""自动化工作流 API：CRMWolf 自有 Workflow DSL 的 CRUD、状态流转、乐观锁与团队隔离。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_team, require_permission
from app.models.user import User
from app.models.workflow import VALID_TRANSITIONS, Workflow, WorkflowStatus
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowDetail,
    WorkflowDslSchema,
    WorkflowStatusLiteral,
    WorkflowStatusUpdate,
    WorkflowSummary,
    WorkflowUpdate,
)
from app.services.workflow_dsl import validate_workflow_dsl

router = APIRouter(prefix="/v1/workflows", tags=["自动化工作流"])


def _status_literal(value: object) -> WorkflowStatusLiteral:
    if value in ("draft", "published", "paused"):
        return value  # noqa: TC003  # mypy narrows via literal membership
    return "draft"


def _serialize_dsl(dsl_value: Any) -> dict[str, Any]:
    """sqlite 下 JSON 列以 Text 存储，读取时容错反序列化；MySQL JSON 直接返回 dict。"""
    if isinstance(dsl_value, dict):
        return dsl_value
    if isinstance(dsl_value, str):
        try:
            parsed = json.loads(dsl_value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="工作流 DSL 数据损坏",
            ) from exc
        if isinstance(parsed, dict):
            return parsed
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="工作流 DSL 数据损坏",
    )


def _dsl_node_count(dsl_value: Any) -> int:
    dsl = _serialize_dsl(dsl_value)
    nodes = dsl.get("nodes")
    return len(nodes) if isinstance(nodes, list) else 0


def _summary(workflow: Workflow) -> WorkflowSummary:
    return WorkflowSummary(
        id=int(workflow.id),
        name=str(workflow.name),
        description=workflow.description if isinstance(workflow.description, str) else None,
        status=_status_literal(workflow.status),
        node_count=_dsl_node_count(workflow.dsl),
        created_time=workflow.created_time,
        last_modified_time=workflow.last_modified_time,
    )


def _detail(workflow: Workflow) -> WorkflowDetail:
    return WorkflowDetail(
        **_summary(workflow).model_dump(),
        dsl=WorkflowDslSchema.model_validate(_serialize_dsl(workflow.dsl)),
        created_by=int(workflow.created_by) if workflow.created_by is not None else None,
    )


def _get_workflow_or_404(db: Session, workflow_id: int, team_id: int) -> Workflow:
    workflow = (
        db.query(Workflow)
        .filter(Workflow.id == workflow_id, Workflow.team_id == team_id)
        .first()
    )
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="工作流不存在或不属于当前团队",
        )
    return workflow


def _ensure_valid_dsl(dsl_payload: dict[str, Any]) -> None:
    errors = validate_workflow_dsl(dsl_payload)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "工作流 DSL 校验失败", "errors": errors},
        )

@router.get("", response_model=list[WorkflowSummary], summary="获取工作流列表", include_in_schema=False)
@router.get("/", response_model=list[WorkflowSummary], summary="获取工作流列表")
def list_workflows(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:read")),
) -> list[WorkflowSummary]:
    workflows = (
        db.query(Workflow)
        .filter(Workflow.team_id == team_id)
        .order_by(Workflow.last_modified_time.desc())
        .all()
    )
    return [_summary(wf) for wf in workflows]


@router.post("", response_model=WorkflowDetail, status_code=status.HTTP_201_CREATED, summary="创建工作流")
def create_workflow(
    payload: WorkflowCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:create")),
) -> WorkflowDetail:
    dsl_payload = payload.dsl.model_dump()
    _ensure_valid_dsl(dsl_payload)
    workflow = Workflow(
        team_id=team_id,
        name=payload.name,
        description=payload.description,
        status=WorkflowStatus.DRAFT,
        dsl=dsl_payload,
        created_by=current_user.id,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return _detail(workflow)


@router.get("/{workflow_id}", response_model=WorkflowDetail, summary="获取工作流详情")
def get_workflow(
    workflow_id: int = Path(..., description="工作流ID"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:read")),
) -> WorkflowDetail:
    workflow = _get_workflow_or_404(db, workflow_id, team_id)
    return _detail(workflow)


@router.put("/{workflow_id}", response_model=WorkflowDetail, summary="更新工作流")
def update_workflow(
    payload: WorkflowUpdate,
    workflow_id: int = Path(..., description="工作流ID"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:edit")),
) -> WorkflowDetail:
    workflow = _get_workflow_or_404(db, workflow_id, team_id)
    if workflow.last_modified_time != payload.expected_last_modified_time:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="工作流已被他人修改，请刷新后重试",
        )
    dsl_payload = payload.dsl.model_dump()
    _ensure_valid_dsl(dsl_payload)
    workflow.name = str(payload.name)
    workflow.description = payload.description
    workflow.dsl = dsl_payload
    db.commit()
    db.refresh(workflow)
    return _detail(workflow)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除工作流(仅草稿)",
    response_model=None,
)
def delete_workflow(
    workflow_id: int = Path(..., description="工作流ID"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:edit")),
) -> None:
    workflow = _get_workflow_or_404(db, workflow_id, team_id)
    if workflow.status != WorkflowStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="仅草稿状态的工作流可以删除",
        )
    db.delete(workflow)
    db.commit()


@router.put("/{workflow_id}/status", response_model=WorkflowDetail, summary="流转工作流状态")
def update_workflow_status(
    payload: WorkflowStatusUpdate,
    workflow_id: int = Path(..., description="工作流ID"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("automation:publish")),
) -> WorkflowDetail:
    workflow = _get_workflow_or_404(db, workflow_id, team_id)
    allowed: set[str] = VALID_TRANSITIONS.get(str(workflow.status)) or set()
    if payload.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不允许从 {workflow.status} 流转到 {payload.status}",
        )
    workflow.status = str(payload.status)
    db.commit()
    db.refresh(workflow)
    return _detail(workflow)

