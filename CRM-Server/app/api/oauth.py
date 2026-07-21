from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.core.security import create_access_token, decode_access_token
from app.crud.oauth import oauth_provider_config_crud, user_oauth_account_crud
from app.crud.team import team_crud
from app.crud.user import user_crud
from app.models.user import User
from app.schemas.auth import LoginResponse
from app.schemas.oauth import (
    FeishuCallbackRequest,
    FeishuCallbackResponse,
    InviteLoginOptionsResponse,
    OAuthBindingStatusResponse,
    OAuthLoginUrlResponse,
    OAuthProviderConfigResponse,
    OAuthProviderConfigUpdate,
)
from app.schemas.user import UserResponse
from app.services.feishu_oauth import feishu_oauth_service


router = APIRouter(tags=["第三方登录"])


def _ensure_team_admin(db: Session, user_id: int, team_id: int) -> None:
    from app.crud.role import role_crud

    roles = role_crud.get_user_roles(db, user_id, team_id)
    if not any(role.code == "TEAM_ADMIN" for role in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要团队管理员权限",
        )


def _config_response(config, team_id: int) -> OAuthProviderConfigResponse:
    if config is None:
        return OAuthProviderConfigResponse(team_id=team_id)
    return OAuthProviderConfigResponse(
        id=config.id,
        team_id=config.team_id,
        provider=config.provider,
        app_id=config.app_id,
        redirect_uri=config.redirect_uri,
        enabled=config.enabled,
        app_secret_configured=bool(config.app_secret_encrypted),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _create_state(payload: Dict[str, Any]) -> str:
    return create_access_token(payload, expires_delta=timedelta(minutes=10))


def _decode_state(state: str) -> Dict[str, Any]:
    payload = decode_access_token(state)
    if not payload or payload.get("provider") != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="飞书授权状态无效或已过期")
    return payload


def _get_enabled_feishu_config(db: Session, team_id: int):
    config = oauth_provider_config_crud.get(db, team_id, "feishu")
    if not config or not config.enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前团队未启用飞书登录")
    secret = oauth_provider_config_crud.get_secret(config)
    if not secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="飞书 App Secret 未配置")
    return config, secret


@router.get("/v1/invites/{code}", response_model=InviteLoginOptionsResponse)
def get_invite_login_options(code: str, db: Session = Depends(get_db)):
    team = team_crud.get_by_code(db, code)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请链接不存在或已失效")

    config = oauth_provider_config_crud.get(db, team.id, "feishu")
    return InviteLoginOptionsResponse(
        team_name=team.name,
        code=team.code,
        feishu_login_enabled=bool(config and config.enabled and config.app_id and config.app_secret_encrypted),
    )


@router.get("/v1/oauth/configs/feishu", response_model=OAuthProviderConfigResponse)
def get_feishu_config(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _ensure_team_admin(db, current_user.id, team_id)
    config = oauth_provider_config_crud.get(db, team_id, "feishu")
    return _config_response(config, team_id)


@router.put("/v1/oauth/configs/feishu", response_model=OAuthProviderConfigResponse)
def update_feishu_config(
    data: OAuthProviderConfigUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    _ensure_team_admin(db, current_user.id, team_id)
    existing = oauth_provider_config_crud.get(db, team_id, "feishu")
    if data.enabled and not data.app_secret and not (existing and existing.app_secret_encrypted):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="启用飞书登录前请配置 App Secret")

    config = oauth_provider_config_crud.upsert_feishu(
        db,
        team_id=team_id,
        app_id=data.app_id,
        app_secret=data.app_secret,
        redirect_uri=data.redirect_uri,
        enabled=data.enabled,
    )
    return _config_response(config, team_id)


@router.get("/v1/auth/feishu/login-url", response_model=OAuthLoginUrlResponse)
def get_feishu_login_url(
    invite_code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    team = team_crud.get_by_code(db, invite_code)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请链接不存在或已失效")
    config, _secret = _get_enabled_feishu_config(db, team.id)
    state = _create_state({
        "provider": "feishu",
        "mode": "invite",
        "team_id": team.id,
        "invite_code": team.code,
    })
    return OAuthLoginUrlResponse(
        auth_url=feishu_oauth_service.build_auth_url(config.app_id, config.redirect_uri, state)
    )


@router.get("/v1/auth/feishu/bind-url", response_model=OAuthLoginUrlResponse)
def get_feishu_bind_url(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    config, _secret = _get_enabled_feishu_config(db, team_id)
    state = _create_state({
        "provider": "feishu",
        "mode": "bind",
        "team_id": team_id,
        "user_id": current_user.id,
    })
    return OAuthLoginUrlResponse(
        auth_url=feishu_oauth_service.build_auth_url(config.app_id, config.redirect_uri, state)
    )


@router.get("/v1/auth/oauth/feishu/status", response_model=OAuthBindingStatusResponse)
def get_feishu_binding_status(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    config = oauth_provider_config_crud.get(db, team_id, "feishu")
    account = user_oauth_account_crud.get_by_user(db, team_id, "feishu", current_user.id)
    return OAuthBindingStatusResponse(
        enabled=bool(config and config.enabled and config.app_id and config.app_secret_encrypted),
        bound=bool(account),
        name=account.name if account else None,
        email=account.email if account else None,
        avatar_url=account.avatar_url if account else None,
        updated_at=account.updated_at if account else None,
    )


@router.delete("/v1/auth/oauth/feishu/bind")
def unbind_feishu_account(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    deleted = user_oauth_account_crud.delete_by_user(db, team_id, "feishu", current_user.id)
    return {"message": "飞书账号已解绑" if deleted else "当前未绑定飞书账号"}


@router.post("/v1/auth/feishu/callback", response_model=FeishuCallbackResponse)
async def handle_feishu_callback(
    data: FeishuCallbackRequest,
    db: Session = Depends(get_db),
):
    state = _decode_state(data.state)
    team_id = int(state["team_id"])
    mode = state.get("mode")
    config, secret = _get_enabled_feishu_config(db, team_id)

    try:
        user_access_token = await feishu_oauth_service.exchange_code(
            config.app_id,
            secret,
            data.code,
            config.redirect_uri,
        )
        profile = await feishu_oauth_service.get_user_info(user_access_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not profile.open_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="飞书未返回 Open ID")

    profile_data = profile.model_dump()
    existing_account = user_oauth_account_crud.get_by_open_id(db, team_id, "feishu", profile.open_id)

    if mode == "bind":
        user_id = int(state["user_id"])
        if existing_account and existing_account.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该飞书账号已绑定其他用户")
        user_oauth_account_crud.upsert(db, team_id, "feishu", user_id, profile_data)
        return FeishuCallbackResponse(mode="bind", message="飞书账号绑定成功")

    if mode != "invite":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="飞书授权模式无效")

    team = team_crud.get_by_code(db, state.get("invite_code", ""))
    if not team or team.id != team_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请链接不存在或已失效")

    user = user_crud.get_by_id(db, existing_account.user_id) if existing_account else None
    if user is None:
        email = profile.email or profile.enterprise_email
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="飞书账号未提供邮箱，无法创建 CRM 用户")
        user = user_crud.get_by_email(db, email)
        if user is None:
            user = user_crud.create_from_email(
                db,
                email=email,
                name=profile.name or email,
                mobile=profile.mobile,
            )
            if profile.avatar_url:
                user.avatar_url = profile.avatar_url
                db.commit()
                db.refresh(user)

    user_oauth_account_crud.upsert(db, team_id, "feishu", user.id, profile_data)
    team_crud.add_member(db, team_id, user.id, set_current=False)
    team_crud.set_current_team(db, user.id, team_id)

    access_token = create_access_token(data={"sub": str(user.id)})
    return FeishuCallbackResponse(
        mode="invite",
        message="飞书登录成功",
        login=LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        ),
    )
