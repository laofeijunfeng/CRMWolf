from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.view_preference import parse_config, view_preference_crud
from app.models.view_preference import ViewPreference, ViewPreferenceScope
from app.schemas.view_preference import (
    ViewPreferenceCustomViewCreateRequest,
    ViewPreferenceCustomViewListResponse,
    ViewPreferenceCustomViewUpdateRequest,
    ViewPreferenceItem,
    ViewPreferenceResponse,
    ViewPreferenceSaveRequest,
)


router = APIRouter(prefix="/v1/view-preferences", tags=["视图偏好"])


def _ensure_can_manage_team_view(db: Session, team_id: int, user_id: int) -> None:
    from app.crud.permission import permission_crud
    from app.crud.role import role_crud
    from app.crud.team import team_crud

    role_codes = {role.code for role in role_crud.get_user_roles(db, user_id, team_id)}
    permission_codes = {permission.code for permission in permission_crud.get_user_permissions(db, user_id, team_id)}
    if team_crud.is_owner(db, team_id, user_id) or "TEAM_ADMIN" in role_codes or "system:config" in permission_codes:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="您没有权限同步团队视图配置",
    )


def _to_item(preference: ViewPreference | None) -> ViewPreferenceItem | None:
    if preference is None:
        return None
    return ViewPreferenceItem(
        id=preference.id,
        team_id=preference.team_id,
        user_id=preference.user_id,
        view_key=preference.view_key,
        scope=preference.scope,
        preference_key=preference.preference_key,
        name=preference.name,
        is_default=bool(preference.is_default),
        sort_order=preference.sort_order,
        config=parse_config(preference.config_json),
        created_by=preference.created_by,
        updated_by=preference.updated_by,
        created_time=preference.created_time,
        updated_time=preference.updated_time,
    )


@router.get("/{view_key}", response_model=ViewPreferenceResponse)
def get_view_preference(
    view_key: str = Path(..., min_length=1, max_length=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    personal = view_preference_crud.get_personal(
        db,
        team_id=team_id,
        view_key=view_key,
        user_id=current_user.id,
    )
    team = view_preference_crud.get_team(db, team_id=team_id, view_key=view_key)
    effective = personal or team

    return ViewPreferenceResponse(
        view_key=view_key,
        personal=_to_item(personal),
        team=_to_item(team),
        effective_scope=effective.scope if effective else None,
        effective_config=parse_config(effective.config_json) if effective else None,
    )


@router.get("/{view_key}/custom-views", response_model=ViewPreferenceCustomViewListResponse)
def list_custom_views(
    view_key: str = Path(..., min_length=1, max_length=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    items = view_preference_crud.list_custom_views(
        db,
        team_id=team_id,
        view_key=view_key,
        user_id=current_user.id,
    )
    return ViewPreferenceCustomViewListResponse(
        view_key=view_key,
        items=[item for item in (_to_item(preference) for preference in items) if item is not None],
    )


@router.post("/{view_key}/custom-views", response_model=ViewPreferenceItem, status_code=status.HTTP_201_CREATED)
def create_custom_view(
    payload: ViewPreferenceCustomViewCreateRequest,
    view_key: str = Path(..., min_length=1, max_length=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    preference = view_preference_crud.create_custom_view(
        db,
        team_id=team_id,
        view_key=view_key,
        user_id=current_user.id,
        config=payload.config,
        actor_id=current_user.id,
    )
    item = _to_item(preference)
    if item is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="自定义视图创建失败")
    return item


@router.patch("/{view_key}/custom-views/{preference_id}", response_model=ViewPreferenceItem)
def update_custom_view(
    payload: ViewPreferenceCustomViewUpdateRequest,
    view_key: str = Path(..., min_length=1, max_length=100),
    preference_id: int = Path(..., ge=1),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    normalized_name = None
    if payload.name is not None:
        normalized_name = payload.name.strip()
        if normalized_name == "":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="视图名称不能为空")

    preference = view_preference_crud.update_custom_view(
        db,
        team_id=team_id,
        view_key=view_key,
        user_id=current_user.id,
        preference_id=preference_id,
        actor_id=current_user.id,
        name=normalized_name,
        config=payload.config,
        sort_order=payload.sort_order,
    )
    if preference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="自定义视图不存在")
    item = _to_item(preference)
    if item is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="自定义视图更新失败")
    return item


@router.delete("/{view_key}/custom-views/{preference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_view(
    view_key: str = Path(..., min_length=1, max_length=100),
    preference_id: int = Path(..., ge=1),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    deleted = view_preference_crud.delete_custom_view(
        db,
        team_id=team_id,
        view_key=view_key,
        user_id=current_user.id,
        preference_id=preference_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="自定义视图不存在")


@router.put("/{view_key}", response_model=ViewPreferenceResponse)
def save_view_preference(
    payload: ViewPreferenceSaveRequest,
    view_key: str = Path(..., min_length=1, max_length=100),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if payload.scope == ViewPreferenceScope.TEAM.value:
        _ensure_can_manage_team_view(db, team_id, current_user.id)

    view_preference_crud.upsert(
        db,
        team_id=team_id,
        user_id=current_user.id,
        view_key=view_key,
        scope=payload.scope,
        config=payload.config,
        actor_id=current_user.id,
        name=payload.name,
        is_default=payload.is_default,
    )
    return get_view_preference(view_key=view_key, team_id=team_id, current_user=current_user, db=db)


@router.delete("/{view_key}", response_model=ViewPreferenceResponse)
def delete_view_preference(
    view_key: str = Path(..., min_length=1, max_length=100),
    scope: ViewPreferenceScope = Query(...),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if scope == ViewPreferenceScope.TEAM:
        _ensure_can_manage_team_view(db, team_id, current_user.id)

    view_preference_crud.delete(
        db,
        team_id=team_id,
        view_key=view_key,
        scope=scope.value,
        user_id=current_user.id,
    )
    return get_view_preference(view_key=view_key, team_id=team_id, current_user=current_user, db=db)
