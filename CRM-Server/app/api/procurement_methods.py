from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.core.deps import get_current_active_user, require_permission, get_current_user_team
from app.models.user import User
from app.schemas.procurement import (
    ProcurementMethodCreate, ProcurementMethodUpdate, ProcurementMethodResponse,
    ProcurementMethodWithStagesResponse, ProcurementStageTemplateResponse,
    ProcurementStageTemplateCreate, ProcurementStageTemplateUpdate,
    BatchUpdateStagesRequest, ProcurementMethodWithStagesUpdate,
    ProcurementMethodOption
)
from app.crud.procurement import procurement_method_crud, procurement_stage_template_crud


router = APIRouter(prefix="/v1/procurement-methods", tags=["采购方式管理"])


@router.get("/options", response_model=list[ProcurementMethodOption], summary="获取采购方式选项", description="""
获取采购方式的下拉选项列表（用于客户创建、商机创建等场景）。

**业务规则：**
- 只返回启用状态的采购方式（is_active=1）
- 按照sort_order排序
- 只返回必要的字段：id、code、name
- 轻量级接口，适合前端下拉选择
""")
def get_procurement_method_options(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    methods, _ = procurement_method_crud.get_multi(
        db, team_id=team_id, skip=0, limit=100, is_active=1
    )
    return methods


@router.get("/", response_model=list[ProcurementMethodResponse], summary="获取采购方式列表", description="""
获取系统中的所有采购方式。

**查询参数：**
- is_active: 可选，筛选启用状态的采购方式（1:启用, 0:停用）
- page: 页码，从1开始
- page_size: 每页数量

**业务规则：**
- 按照sort_order排序返回
- 支持分页查询
""")
def get_procurement_methods(
    is_active: Optional[int] = Query(None, ge=0, le=1, description="启用状态筛选：1=启用, 0=停用（可选）"),
    page: int = Query(1, ge=1, description="页码，从1开始（默认1）"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，最大100（默认20）"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    skip = (page - 1) * page_size
    methods, total = procurement_method_crud.get_multi(
        db, team_id=team_id, skip=skip, limit=page_size, is_active=is_active
    )
    return methods


@router.get("/{method_id}", response_model=ProcurementMethodWithStagesResponse, summary="获取采购方式详情", description="""
根据ID获取采购方式的详细信息，包括其关联的阶段模板列表。

**业务规则：**
- 返回采购方式的基本信息
- 包含该采购方式下的所有阶段模板
- 阶段模板按sort_order排序
""")
def get_procurement_method(
    method_id: int,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    method = procurement_method_crud.get(db, method_id)
    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"采购方式 ID {method_id} 不存在"
        )

    # 获取阶段模板
    stage_templates = procurement_stage_template_crud.get_by_method(db, method_id, team_id)
    
    # 构造响应
    response_dict = {
        **{c.name: getattr(method, c.name) for c in method.__table__.columns},
        "stage_templates": stage_templates
    }
    
    return ProcurementMethodWithStagesResponse(**response_dict)


@router.post("/", response_model=ProcurementMethodResponse, status_code=status.HTTP_201_CREATED, summary="创建采购方式", description="""
创建新的采购方式。

**业务规则：**
- 采购方式编码必须唯一
- 编码必须是大写字母和下划线
- 只能由管理员创建

**权限要求：**
- 需要采购方式创建权限
""")
def create_procurement_method(
    method_in: ProcurementMethodCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement_method:create"))
):
    try:
        method = procurement_method_crud.create(
            db, method_in, creator_id=str(current_user.id), team_id=team_id
        )
        return method
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{method_id}", response_model=ProcurementMethodResponse, summary="更新采购方式", description="""
更新采购方式的基本信息。

**业务规则：**
- 不能修改code字段
- 停用采购方式前，需要检查是否有活跃商机使用该方式
- 使用乐观锁机制防止并发修改冲突

**权限要求：**
- 需要采购方式更新权限
""")
def update_procurement_method(
    method_id: int,
    method_in: ProcurementMethodUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement_method:update"))
):
    method = procurement_method_crud.get(db, method_id)
    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"采购方式 ID {method_id} 不存在"
        )
    
    try:
        updated_method = procurement_method_crud.update(
            db, method, method_in, updater_id=str(current_user.id)
        )
        return updated_method
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{method_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除采购方式", description="""
删除指定的采购方式。

**业务规则：**
- 删除前会检查是否有活跃商机使用该方式
- 如果有活跃商机，不允许删除
- 删除是物理删除

**权限要求：**
- 需要采购方式删除权限
""")
def delete_procurement_method(
    method_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement_method:delete"))
):
    try:
        success = procurement_method_crud.delete(db, method_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"采购方式 ID {method_id} 不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{method_id}/stages", response_model=list[ProcurementStageTemplateResponse], summary="批量更新阶段模板", description="""
批量更新指定采购方式的阶段模板列表。

**业务规则：**
- 根据stage中是否有ID来判断是新增还是更新
- stage.mark_delete=true表示删除该阶段
- 使用事务保证操作的原子性
- 自动检查并处理默认起始阶段
- 支持完全替换某采购方式的所有阶段

**权限要求：**
- 需要阶段模板更新权限

**前端使用场景：**
- 编辑采购方式时，同时编辑阶段列表
- 点击保存时调用此接口一次提交所有阶段变更
""")
def batch_update_stages(
    method_id: int,
    stages_in: BatchUpdateStagesRequest,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("procurement_stage:update"))
):
    from app.schemas.procurement import StageTemplateBatchUpdate, ProcurementStageTemplateCreate, ProcurementStageTemplateUpdate
    
    # 验证采购方式是否存在
    method = procurement_method_crud.get(db, method_id)
    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"采购方式 ID {method_id} 不存在"
        )
    
    try:
        updated_stages = []
        
        for stage_in in stages_in.stages:
            # 处理删除
            if getattr(stage_in, 'mark_delete', False):
                if stage_in.id:
                    procurement_stage_template_crud.delete(db, stage_in.id)
            # 处理更新
            elif stage_in.id:
                # 从数据库获取当前阶段数据，用于获取 version_lock
                existing_stage = procurement_stage_template_crud.get(db, stage_in.id)
                if not existing_stage:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"阶段 ID {stage_in.id} 不存在"
                    )
                
                stage_update = ProcurementStageTemplateUpdate(
                    template_code=stage_in.template_code,
                    stage_name=stage_in.stage_name,
                    win_probability=stage_in.win_probability,
                    sort_order=stage_in.sort_order,
                    is_default_start=stage_in.is_default_start,
                    can_skip=stage_in.can_skip,
                    description=stage_in.description,
                    version_lock=existing_stage.version_lock
                )
                updated_stage = procurement_stage_template_crud.update(
                    db, existing_stage, stage_update, str(current_user.id)
                )
                updated_stages.append(updated_stage)
            # 处理新增
            else:
                stage_create = ProcurementStageTemplateCreate(
                    procurement_method_id=method_id,
                    template_code=stage_in.template_code,
                    stage_name=stage_in.stage_name,
                    win_probability=stage_in.win_probability,
                    sort_order=stage_in.sort_order,
                    is_default_start=stage_in.is_default_start,
                    can_skip=stage_in.can_skip,
                    description=stage_in.description
                )
                new_stage = procurement_stage_template_crud.create(
                    db, stage_create, str(current_user.id), team_id
                )
                updated_stages.append(new_stage)
        
        db.commit()
        
        # 返回更新后的阶段列表
        return procurement_stage_template_crud.get_by_method(db, method_id, team_id)
        
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量更新失败: {str(e)}"
        )


@router.put("/{method_id}/full", response_model=ProcurementMethodWithStagesResponse, summary="完整更新采购方式及阶段", description="""
同时更新采购方式信息和阶段模板列表。

**业务规则：**
- 使用事务保证操作的原子性（要么全部成功，要么全部回滚）
- method为空则只更新阶段，stages为空则只更新采购方式
- 阶段模板支持新增、更新、删除操作
- 自动进行影响评估和冲突检查
- 支持乐观锁机制防止并发修改冲突

**权限要求：**
- 需要采购方式更新权限和阶段模板更新权限

**前端使用场景：**
- 编辑采购方式页面，同时修改采购方式和阶段信息
- 点击保存按钮时调用此接口，一次完成所有操作
- 保证数据一致性，避免部分成功的情况

**参数说明：**
- method: 采购方式更新数据（可选）
- stages: 阶段模板列表（每个阶段包含id字段，有ID=更新，无ID=新增，mark_delete=true=删除）
""")
def full_update_procurement_method(
    method_id: int,
    update_in: ProcurementMethodWithStagesUpdate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    from app.schemas.procurement import StageTemplateBatchUpdate, ProcurementStageTemplateCreate, ProcurementStageTemplateUpdate
    
    # 验证采购方式是否存在
    method = procurement_method_crud.get(db, method_id)
    if not method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"采购方式 ID {method_id} 不存在"
        )
    
    try:
        # 更新采购方式
        if update_in.method:
            procurement_method_crud.update(
                db, method, update_in.method, str(current_user.id)
            )
        
        # 批量更新阶段
        updated_stages = []
        if update_in.stages:
            for stage_in in update_in.stages:
                # 处理删除
                if getattr(stage_in, 'mark_delete', False):
                    if stage_in.id:
                        procurement_stage_template_crud.delete(db, stage_in.id)
                # Handle update
                elif stage_in.id:
                    # 从数据库获取当前阶段数据，用于获取 version_lock
                    existing_stage = procurement_stage_template_crud.get(db, stage_in.id)
                    if not existing_stage:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"阶段 ID {stage_in.id} 不存在"
                        )
                    
                    stage_update = ProcurementStageTemplateUpdate(
                        template_code=stage_in.template_code,
                        stage_name=stage_in.stage_name,
                        win_probability=stage_in.win_probability,
                        sort_order=stage_in.sort_order,
                        is_default_start=stage_in.is_default_start,
                        can_skip=stage_in.can_skip,
                        description=stage_in.description,
                        version_lock=existing_stage.version_lock
                    )
                    updated_stage = procurement_stage_template_crud.update(
                        db, existing_stage, stage_update, str(current_user.id)
                    )
                    updated_stages.append(updated_stage)
                # 处理新增
                else:
                    stage_create = ProcurementStageTemplateCreate(
                        procurement_method_id=method_id,
                        template_code=stage_in.template_code,
                        stage_name=stage_in.stage_name,
                        win_probability=stage_in.win_probability,
                        sort_order=stage_in.sort_order,
                        is_default_start=stage_in.is_default_start,
                        can_skip=stage_in.can_skip,
                        description=stage_in.description
                    )
                    new_stage = procurement_stage_template_crud.create(
                        db, stage_create, str(current_user.id)
                    )
                    updated_stages.append(new_stage)
        
        db.commit()
        
        # 重新查询以确保获取最新数据
        db.refresh(method)
        stage_templates = procurement_stage_template_crud.get_by_method(db, method_id, team_id)
        
        # 构造阶段模板响应列表 - 添加异常处理以便调试
        logger.info(f"开始序列化阶段模板，共 {len(stage_templates)} 个阶段")
        stage_template_responses = []
        for idx, s in enumerate(stage_templates):
            try:
                logger.debug(f"序列化阶段 {idx}: id={s.id}, type={type(s).__name__}")
                stage_resp = ProcurementStageTemplateResponse(
                    id=s.id,
                    procurement_method_id=s.procurement_method_id,
                    template_code=s.template_code,
                    stage_name=s.stage_name,
                    win_probability=s.win_probability,
                    sort_order=s.sort_order,
                    is_default_start=s.is_default_start,
                    can_skip=s.can_skip,
                    description=s.description,
                    version=s.version,
                    version_lock=s.version_lock,
                    created_by=s.created_by,
                    updated_by=s.updated_by,
                    created_time=s.created_time,
                    updated_time=s.updated_time
                )
                stage_template_responses.append(stage_resp)
                logger.debug(f"阶段 {idx} 序列化成功")
            except Exception as e:
                logger.error(f"序列化阶段 {idx} 失败: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"序列化阶段 {idx} 失败: {str(e)} - type: {type(s).__name__}, object: {repr(s)}"
                )
        
        # 构造最终响应
        logger.info(f"开始序列化采购方式对象")
        try:
            return ProcurementMethodWithStagesResponse(
                    id=method.id,
                    code=method.code,
                    name=method.name,
                    description=method.description,
                    is_active=method.is_active,
                    sort_order=method.sort_order,
                    created_by=method.created_by,
                    updated_by=method.updated_by,
                    created_time=method.created_time,
                    updated_time=method.updated_time,
                    stage_templates=stage_template_responses
                )
        except Exception as e:
            logger.error(f"序列化采购方式失败: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"序列化采购方式失败: {str(e)} - type: {type(method).__name__}, object: {repr(method)}"
            )
        
    except ValueError as e:
        db.rollback()
        logger.error(f"业务逻辑错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"更新失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新失败: {str(e)}"
        )
