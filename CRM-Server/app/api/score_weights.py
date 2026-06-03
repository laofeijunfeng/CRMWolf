"""热力值权重配置 API

提供权重配置的查询、更新、复制操作。

权限：
- score:config:view：查看权重配置
- score:config:edit：编辑权重配置（仅 TEAM_ADMIN 和 SALES_DIRECTOR）
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user_team, get_current_active_user, require_permission
from app.crud.score_weight import score_weight_crud
from app.schemas.score_weight import (
    WeightConfigResponse,
    WeightConfigUpdate,
    WeightConfigList
)

router = APIRouter(prefix="/api/v1/score-weights", tags=["热力值权重配置"])


@router.get("/{module_type}", response_model=WeightConfigList, summary="获取权重配置列表")
def get_weight_configs(
    module_type: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取指定模块的权重配置

    Args:
        module_type: 模块类型（LEAD/CUSTOMER）

    Returns:
        权重配置列表及是否使用系统默认配置
    """
    if module_type not in ['LEAD', 'CUSTOMER']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="module_type 必须为 LEAD 或 CUSTOMER"
        )

    weights = score_weight_crud.get_all_weights(db, team_id, module_type)
    is_system_default = not score_weight_crud.has_team_weights(db, team_id, module_type)

    return {
        "module_type": module_type,
        "weights": weights,
        "is_system_default": is_system_default
    }


@router.put("/{weight_id}", response_model=WeightConfigResponse, summary="更新权重配置")
def update_weight_config(
    weight_id: int,
    update_data: WeightConfigUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("score:config:edit")),
    db: Session = Depends(get_db)
):
    """更新权重配置

    需要权限：score:config:edit

    注意：系统默认配置不可直接编辑，需先复制到团队
    """
    try:
        weight = score_weight_crud.update_weight(
            db,
            weight_id,
            update_data.weight_value,
            update_data.is_enabled,
            update_data.condition_rules,
            str(current_user.id)
        )
        return weight

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/copy-from-system", summary="复制系统默认配置到团队")
def copy_system_weights(
    module_type: str = None,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("score:config:edit")),
    db: Session = Depends(get_db)
):
    """将系统默认权重配置复制到当前团队

    需要权限：score:config:edit

    Args:
        module_type: 模块类型（可选，不传则复制所有）
    """
    if module_type and module_type not in ['LEAD', 'CUSTOMER']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="module_type 必须为 LEAD 或 CUSTOMER"
        )

    # 检查是否已存在团队配置
    if module_type:
        if score_weight_crud.has_team_weights(db, team_id, module_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"团队已有 {module_type} 权重配置，请先删除后再复制"
            )
    else:
        # 复制所有模块
        for mt in ['LEAD', 'CUSTOMER']:
            if score_weight_crud.has_team_weights(db, team_id, mt):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"团队已有 {mt} 权重配置，请先删除后再复制"
                )

    # 复制配置
    new_weights = score_weight_crud.create_team_weights_from_system(
        db, team_id, module_type, str(current_user.id)
    )

    return {
        "message": "权重配置已复制到团队",
        "count": len(new_weights),
        "module_types": [w.module_type for w in new_weights]
    }


@router.delete("/{module_type}", summary="删除团队权重配置")
def delete_team_weights(
    module_type: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("score:config:edit")),
    db: Session = Depends(get_db)
):
    """删除团队的权重配置（恢复使用系统默认）

    需要权限：score:config:edit
    """
    if module_type not in ['LEAD', 'CUSTOMER']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="module_type 必须为 LEAD 或 CUSTOMER"
        )

    if not score_weight_crud.has_team_weights(db, team_id, module_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="团队使用的是系统默认配置，无需删除"
        )

    count = score_weight_crud.delete_team_weights(db, team_id, module_type)

    return {
        "message": f"已删除 {count} 条权重配置，恢复使用系统默认配置",
        "deleted_count": count
    }