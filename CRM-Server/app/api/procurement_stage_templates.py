from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission, get_current_user_team
from app.models.user import User
from app.schemas.procurement import (
    ProcurementStageTemplateCreate, ProcurementStageTemplateUpdate,
    ProcurementStageTemplateResponse, StageTemplateChangeLogResponse
)
from app.crud.procurement import procurement_stage_template_crud


router = APIRouter(prefix="/api/v1/procurement-stage-templates", tags=["采购阶段管理"])


@router.get("/", response_model=List[ProcurementStageTemplateResponse], summary="获取阶段模板列表", description="""
获取指定采购方式下的所有阶段模板。

**查询参数：**
- procurement_method_id: 采购方式ID（必填）

**业务规则：**
- 按照sort_order排序返回
- 返回该采购方式下的所有阶段
""")
def get_stage_templates(
    procurement_method_id: int = Query(..., description="采购方式ID（必填）"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    templates = procurement_stage_template_crud.get_by_method(
        db, procurement_method_id, team_id
    )
    return templates


@router.get("/{template_id}", response_model=ProcurementStageTemplateResponse, summary="获取阶段模板详情", description="""
根据ID获取阶段模板的详细信息。

**业务规则：**
- 返回阶段模板的所有字段
- 包含版本信息
""")
def get_stage_template(
    template_id: int = Path(..., description="阶段模板ID（路径参数）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    template = procurement_stage_template_crud.get(db, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"阶段模板 ID {template_id} 不存在"
        )
    return template


@router.post("/", response_model=ProcurementStageTemplateResponse, status_code=status.HTTP_201_CREATED, summary="创建阶段模板", description="""
为指定采购方式创建新的阶段模板。

**业务规则：**
- 阶段编码在同一采购方式下必须唯一
- 每个采购方式只能有一个默认起始阶段
- 创建时会记录变更日志

**权限要求：**
- 需要阶段模板创建权限
""")
def create_stage_template(
    template_in: ProcurementStageTemplateCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement_stage:create"))
):
    try:
        template = procurement_stage_template_crud.create(
            db, template_in, creator_id=str(current_user.id), team_id=team_id
        )
        return template
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{template_id}", response_model=ProcurementStageTemplateResponse, summary="更新阶段模板", description="""
更新阶段模板的信息。

**业务规则：**
- 使用乐观锁机制，需要提供version_lock
- 如果数据已被其他人修改，会返回错误
- 修改会记录变更日志
- 默认起始阶段只能有一个

**权限要求：**
- 需要阶段模板更新权限

**并发处理：**
- 如果返回409错误，表示数据已被其他人修改
- 用户需要重新加载数据后重试
""")
def update_stage_template(
    template_id: int,
    template_in: ProcurementStageTemplateUpdate,
    db: Session = Depends(get_db),
    reason: str = Query(None, description="修改原因（可选）"),
    current_user: User = Depends(require_permission("procurement_stage:update"))
):
    template = procurement_stage_template_crud.get(db, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"阶段模板 ID {template_id} 不存在"
        )
    
    try:
        updated_template = procurement_stage_template_crud.update(
            db, template, template_in, 
            updater_id=str(current_user.id),
            reason=reason
        )
        return updated_template
    except ValueError as e:
        if "version_lock" in str(e) or "重新加载" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="数据已被其他人修改，请刷新后重试"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除阶段模板", description="""
删除指定的阶段模板。

**业务规则：**
- 删除前会检查是否被商机使用
- 如果有活跃商机使用该阶段，不允许删除
- 删除会记录变更日志

**权限要求：**
- 需要阶段模板删除权限
""")
def delete_stage_template(
    template_id: int = Path(..., description="阶段模板ID（路径参数）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement_stage:delete"))
):
    try:
        success = procurement_stage_template_crud.delete(db, template_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"阶段模板 ID {template_id} 不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{template_id}/change-logs", response_model=List[StageTemplateChangeLogResponse], summary="获取阶段模板变更日志", description="""
获取指定阶段模板的所有变更记录。

**业务规则：**
- 按时间倒序返回
- 包含创建、更新、删除等操作
- 记录了变更前后的数据
""")
def get_stage_template_change_logs(
    template_id: int = Path(..., description="阶段模板ID（路径参数）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    logs = procurement_stage_template_crud.get_change_logs(db, template_id)
    return logs
