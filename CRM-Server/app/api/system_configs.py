"""
系统配置管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.crud.system_config import system_config_crud
from app.schemas.system_config import NotificationConfigResponse, NotificationConfigUpdate
from app.services.feishu import feishu_service


router = APIRouter(prefix="/v1/system/configs", tags=["系统配置管理"])


@router.get(
    "/notification",
    response_model=NotificationConfigResponse,
    summary="获取通知配置",
    description="""
获取当前团队的通知配置信息。

**功能说明：**
- 返回团队的通知配置详情
- 包含飞书 Webhook 和 API 两种通知方式的配置

**业务场景：**
- 管理员查看通知配置
- 配置审批通知发送方式

**权限要求：**
- 需要 TEAM_ADMIN 角色 **或** approval:flow:edit 权限

**返回字段：**
- id: 配置ID
- team_id: 团队ID
- notification_method: 通知方式（webhook/api）
- feishu_webhook_url: 飞书Webhook地址
- feishu_webhook_enabled: Webhook是否启用
- notification_group_name: 通知群名称
- feishu_app_id: 飞书应用ID（预留）
- feishu_app_secret: 飞书应用密钥（预留）
- feishu_api_enabled: API是否启用（预留）
- created_time: 创建时间
- updated_time: 更新时间
"""
)
def get_notification_config(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # 权限检查：TEAM_ADMIN 或 approval:flow:edit
    from app.crud.role import role_crud
    from app.crud.permission import permission_crud

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    # 检查是否为 TEAM_ADMIN
    if "TEAM_ADMIN" not in role_codes:
        # 检查是否有 approval:flow:edit 权限
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}

        if "approval:flow:edit" not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有权限访问通知配置"
            )

    config = system_config_crud.get_notification_config(db, team_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知配置不存在"
        )

    return config


@router.put(
    "/notification",
    response_model=NotificationConfigResponse,
    summary="更新通知配置",
    description="""
更新团队的通知配置信息。

**功能说明：**
- 更新飞书 Webhook 配置
- 更新飞书 API 配置（预留功能）
- 支持启用/禁用通知

**业务场景：**
- 管理员配置审批通知发送方式
- 设置飞书群聊机器人 Webhook
- 配置通知群名称

**权限要求：**
- 需要 TEAM_ADMIN 角色 **或** approval:flow:edit 权限

**请求体字段：**
- notification_method: 通知方式（webhook/api）
- feishu_webhook_url: 飞书Webhook地址
- feishu_webhook_enabled: Webhook是否启用
- notification_group_name: 通知群名称
- feishu_app_id: 飞书应用ID（预留）
- feishu_app_secret: 飞书应用密钥（预留）
- feishu_api_enabled: API是否启用（预留）

**注意事项：**
- 所有字段均为可选，只更新提供的字段
- Webhook URL 格式：https://open.feishu.cn/open-apis/bot/v2/hook/xxx
- 敏感信息（如 app_secret）会加密存储
"""
)
def update_notification_config(
    config_data: NotificationConfigUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # 权限检查：TEAM_ADMIN 或 approval:flow:edit
    from app.crud.role import role_crud
    from app.crud.permission import permission_crud

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    # 检查是否为 TEAM_ADMIN
    if "TEAM_ADMIN" not in role_codes:
        # 检查是否有 approval:flow:edit 权限
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}

        if "approval:flow:edit" not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有权限更新通知配置（需要 TEAM_ADMIN 角色或 approval:flow:edit 权限）"
            )
    # 准备更新数据（只包含非 None 的字段）
    update_dict: Dict[str, Any] = {}
    if config_data.notification_method is not None:
        update_dict["notification_method"] = config_data.notification_method
    if config_data.feishu_webhook_url is not None:
        update_dict["feishu_webhook_url"] = config_data.feishu_webhook_url
    if config_data.feishu_webhook_enabled is not None:
        update_dict["feishu_webhook_enabled"] = config_data.feishu_webhook_enabled
    if config_data.notification_group_name is not None:
        update_dict["notification_group_name"] = config_data.notification_group_name
    if config_data.feishu_app_id is not None:
        update_dict["feishu_app_id"] = config_data.feishu_app_id
    if config_data.feishu_app_secret is not None:
        update_dict["feishu_app_secret"] = config_data.feishu_app_secret
    if config_data.feishu_api_enabled is not None:
        update_dict["feishu_api_enabled"] = config_data.feishu_api_enabled

    # 更新配置
    try:
        system_config_crud.set_notification_config(db, team_id, update_dict)
        db.commit()

        # 返回更新后的配置
        updated_config = system_config_crud.get_notification_config(db, team_id)
        return updated_config
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新通知配置失败: {str(e)}"
        )


@router.post(
    "/notification/test",
    summary="测试通知发送",
    description="""
发送测试消息到配置的 Webhook URL，验证通知配置是否正确。

**功能说明：**
- 向配置的飞书 Webhook 发送测试消息
- 验证 Webhook URL 是否有效
- 测试消息发送是否成功

**业务场景：**
- 配置 Webhook 后进行测试
- 排查通知发送问题

**权限要求：**
- 需要 TEAM_ADMIN 角色 **或** approval:flow:edit 权限

**返回信息：**
- success: 是否发送成功
- message: 详细信息

**注意事项：**
- 需要先配置 Webhook URL 并启用
- 测试消息会发送到配置的飞书群
"""
)
async def test_notification(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # 权限检查：TEAM_ADMIN 或 approval:flow:edit
    from app.crud.role import role_crud
    from app.crud.permission import permission_crud

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    # 检查是否为 TEAM_ADMIN
    if "TEAM_ADMIN" not in role_codes:
        # 检查是否有 approval:flow:edit 权限
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}

        if "approval:flow:edit" not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有权限测试通知配置（需要 TEAM_ADMIN 角色或 approval:flow:edit 权限）"
            )
    # 获取通知配置
    config = system_config_crud.get_notification_config(db, team_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知配置不存在，请先配置"
        )

    # 检查 Webhook 是否启用
    if not config.feishu_webhook_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook 未启用，请先启用 Webhook 通知"
        )

    # 检查 Webhook URL
    if not config.feishu_webhook_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook URL 未配置，请先配置 Webhook 地址"
        )

    # 发送测试消息
    try:
        success = await feishu_service.send_webhook_message(
            webhook_url=config.feishu_webhook_url,
            title="🔔 通知配置测试",
            content="这是一条测试消息，用于验证通知配置是否正确。\n\n如果您收到此消息，说明通知配置成功！"
        )

        if success:
            return {"success": True, "message": "测试消息发送成功，请检查飞书群是否收到消息"}
        else:
            return {"success": False, "message": "测试消息发送失败，请检查 Webhook URL 是否正确"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发送测试消息失败: {str(e)}"
        )