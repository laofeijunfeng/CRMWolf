"""
AI Skill 配置管理接口

提供 Skill、Action、CRUD 映射、Enum 映射的 CRUD 操作
"""
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Generic, TypeVar, List

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_crud_mapping import ai_crud_mapping_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud
from app.schemas.ai_skill_config import (
    SkillCreate, SkillUpdate, SkillResponse,
    SkillActionCreate, SkillActionUpdate, SkillActionResponse,
    CRUDMappingCreate, CRUDMappingResponse,
    EnumMappingCreate, EnumMappingResponse
)

T = TypeVar("T")


router = APIRouter(prefix="/v1/ai/skills", tags=["AI Skill 配置管理"])


# ============================================================================
# 静态路由（必须在动态路由 /{skill_id} 之前定义）
# ============================================================================

@router.get("/crud-mappings")
async def list_crud_mappings(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取 CRUD 映射列表"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 CRUD 映射")

    mappings, total = ai_crud_mapping_crud.get_multi(db, skip=skip, limit=limit)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": [
                {
                    "id": m.id,
                    "mapping_name": m.mapping_name,
                    "crud_module": m.crud_module,
                    "crud_instance_name": m.crud_instance_name,
                    "model_class": m.model_class,
                    "schema_create_class": m.schema_create_class,
                    "owner_field": m.owner_field,
                    "status_field": m.status_field,
                    "name_field": m.name_field
                }
                for m in mappings
            ],
            "total": total
        },
        "timestamp": int(time.time())
    }


@router.post("/crud-mappings")
async def create_crud_mapping(
    mapping_in: CRUDMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建 CRUD 映射"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限创建 CRUD 映射")

    existing = ai_crud_mapping_crud.get_by_name(db, mapping_in.mapping_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"CRUD 映射已存在: {mapping_in.mapping_name}")

    mapping_data = mapping_in.model_dump()
    mapping = ai_crud_mapping_crud.create(db, mapping_data)

    return {
        "code": 0,
        "message": "CRUD 映射创建成功",
        "data": {
            "id": mapping.id,
            "mapping_name": mapping.mapping_name,
            "crud_module": mapping.crud_module,
            "crud_instance_name": mapping.crud_instance_name
        },
        "timestamp": int(time.time())
    }


@router.get("/enum-mappings")
async def list_enum_mappings(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取 Enum 映射列表"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 Enum 映射")

    enums, total = ai_enum_mapping_crud.get_multi(db, skip=skip, limit=limit)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": [
                {
                    "id": e.id,
                    "enum_name": e.enum_name,
                    "display_name": e.display_name,
                    "enum_class": e.enum_class,
                    "values": e.values
                }
                for e in enums
            ],
            "total": total
        },
        "timestamp": int(time.time())
    }


@router.post("/enum-mappings")
async def create_enum_mapping(
    enum_in: EnumMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建 Enum 映射"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限创建 Enum 映射")

    existing = ai_enum_mapping_crud.get_by_name(db, enum_in.enum_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"Enum 映射已存在: {enum_in.enum_name}")

    enum_data = enum_in.model_dump()
    enum = ai_enum_mapping_crud.create(db, enum_data)

    return {
        "code": 0,
        "message": "Enum 映射创建成功",
        "data": {
            "id": enum.id,
            "enum_name": enum.enum_name,
            "display_name": enum.display_name,
            "values": enum.values
        },
        "timestamp": int(time.time())
    }


@router.get("/handler-types")
async def list_handler_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取支持的 Handler 类型列表"""
    from app.services.permission_service import permission_service
    from app.services.skills.handlers import HandlerFactory

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 Handler 类型")

    handler_types = HandlerFactory.get_supported_handlers()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "handler_types": handler_types
        },
        "timestamp": int(time.time())
    }


# ============================================================================
# Skill 管理（动态路由）
# ============================================================================

@router.get("")
async def list_skills(
    skip: int = 0,
    limit: int = 100,
    module_type: Optional[str] = None,
    is_active: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取 Skill 列表"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 Skill 配置")

    skills, total = ai_skill_crud.get_multi(
        db, skip=skip, limit=limit, module_type=module_type, is_active=is_active
    )

    # 获取每个 Skill 的 Action 数量
    skill_items = []
    for s in skills:
        actions = ai_skill_action_crud.get_by_skill_id(db, s.id)
        skill_items.append({
            "id": s.id,
            "skill_name": s.skill_name,
            "display_name": s.display_name,
            "description": s.description,
            "module_type": s.module_type,
            "is_active": s.is_active,
            "sort_order": s.sort_order,
            "action_count": len(actions),
            "created_time": s.created_time.isoformat() if s.created_time else None,
            "updated_time": s.updated_time.isoformat() if s.updated_time else None
        })

    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": skill_items,
            "total": total
        },
        "timestamp": int(time.time())
    }


@router.post("")
async def create_skill(
    skill_in: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建 Skill"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限创建 Skill")

    # 检查名称是否已存在
    existing = ai_skill_crud.get_by_name(db, skill_in.skill_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"Skill 名称已存在: {skill_in.skill_name}")

    skill_data = skill_in.model_dump()
    skill = ai_skill_crud.create(db, skill_data)

    return {
        "code": 0,
        "message": "Skill 创建成功",
        "data": {
            "id": skill.id,
            "skill_name": skill.skill_name,
            "display_name": skill.display_name,
            "description": skill.description,
            "module_type": skill.module_type,
            "is_active": skill.is_active,
            "sort_order": skill.sort_order
        },
        "timestamp": int(time.time())
    }


@router.get("/{skill_id}")
async def get_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取 Skill 详情"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 Skill 配置")

    skill = ai_skill_crud.get_by_id(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {skill_id}")

    # 获取关联的 Actions
    actions = ai_skill_action_crud.get_by_skill_id(db, skill_id)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": skill.id,
            "skill_name": skill.skill_name,
            "display_name": skill.display_name,
            "description": skill.description,
            "module_type": skill.module_type,
            "is_active": skill.is_active,
            "sort_order": skill.sort_order,
            "actions": [
                {
                    "id": a.id,
                    "action_name": a.action_name,
                    "display_name": a.display_name,
                    "description": a.description,
                    "handler_type": a.handler_type,
                    "required_params": a.required_params,
                    "optional_params": a.optional_params,
                    "permission_code": a.permission_code,
                    "is_active": a.is_active
                }
                for a in actions
            ]
        },
        "timestamp": int(time.time())
    }


@router.put("/{skill_id}")
async def update_skill(
    skill_id: int,
    skill_in: SkillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新 Skill"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限修改 Skill")

    skill = ai_skill_crud.get_by_id(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {skill_id}")

    update_data = skill_in.model_dump(exclude_unset=True)
    skill = ai_skill_crud.update(db, skill_id, update_data)

    return {
        "code": 0,
        "message": "Skill 更新成功",
        "data": {
            "id": skill.id,
            "skill_name": skill.skill_name,
            "display_name": skill.display_name,
            "description": skill.description,
            "module_type": skill.module_type,
            "is_active": skill.is_active
        },
        "timestamp": int(time.time())
    }


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除 Skill（同时删除关联的 Actions）"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限删除 Skill")

    skill = ai_skill_crud.get_by_id(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {skill_id}")

    # 删除关联的 Actions
    action_count = ai_skill_action_crud.delete_by_skill_id(db, skill_id)

    # 删除 Skill
    ai_skill_crud.delete(db, skill_id)

    return {
        "code": 0,
        "message": f"Skill 删除成功，同时删除 {action_count} 个关联 Action",
        "timestamp": int(time.time())
    }


# ============================================================================
# Action 管理
# ============================================================================

@router.get("/{skill_id}/actions")
async def list_actions(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取 Skill 的 Action 列表"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage", "ai:read"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限访问 Skill 配置")

    skill = ai_skill_crud.get_by_id(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {skill_id}")

    actions = ai_skill_action_crud.get_by_skill_id(db, skill_id)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "skill_name": skill.skill_name,
            "items": [
                {
                    "id": a.id,
                    "action_name": a.action_name,
                    "display_name": a.display_name,
                    "description": a.description,
                    "handler_type": a.handler_type,
                    "handler_config": a.handler_config,
                    "required_params": a.required_params,
                    "optional_params": a.optional_params,
                    "permission_code": a.permission_code,
                    "result_template": a.result_template,
                    "is_active": a.is_active,
                    "sort_order": a.sort_order
                }
                for a in actions
            ]
        },
        "timestamp": int(time.time())
    }


@router.post("/{skill_id}/actions")
async def create_action(
    skill_id: int,
    action_in: SkillActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建 Action"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限创建 Action")

    skill = ai_skill_crud.get_by_id(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {skill_id}")

    # 检查 Action 名称是否已存在
    existing = ai_skill_action_crud.get_by_skill_and_action(db, skill_id, action_in.action_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"Action 已存在: {skill.skill_name}.{action_in.action_name}")

    action_data = action_in.model_dump()
    action_data["skill_id"] = skill_id

    action = ai_skill_action_crud.create(db, action_data)

    return {
        "code": 0,
        "message": "Action 创建成功",
        "data": {
            "id": action.id,
            "skill_id": action.skill_id,
            "action_name": action.action_name,
            "display_name": action.display_name,
            "handler_type": action.handler_type
        },
        "timestamp": int(time.time())
    }


@router.put("/{skill_id}/actions/{action_id}")
async def update_action(
    skill_id: int,
    action_id: int,
    action_in: SkillActionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新 Action"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限修改 Action")

    action = ai_skill_action_crud.get_by_id(db, action_id)
    if not action or action.skill_id != skill_id:
        raise HTTPException(status_code=404, detail=f"Action 不存在: {action_id}")

    update_data = action_in.model_dump(exclude_unset=True)
    action = ai_skill_action_crud.update(db, action_id, update_data)

    return {
        "code": 0,
        "message": "Action 更新成功",
        "data": {
            "id": action.id,
            "action_name": action.action_name,
            "handler_type": action.handler_type
        },
        "timestamp": int(time.time())
    }


@router.delete("/{skill_id}/actions/{action_id}")
async def delete_action(
    skill_id: int,
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除 Action"""
    from app.services.permission_service import permission_service

    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限删除 Action")

    action = ai_skill_action_crud.get_by_id(db, action_id)
    if not action or action.skill_id != skill_id:
        raise HTTPException(status_code=404, detail=f"Action 不存在: {action_id}")

    ai_skill_action_crud.delete(db, action_id)

    return {
        "code": 0,
        "message": "Action 删除成功",
        "timestamp": int(time.time())
    }