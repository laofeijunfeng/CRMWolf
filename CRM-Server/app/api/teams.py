from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, get_user_teams
from app.crud.team import team_crud, user_team_crud
from app.crud.role import role_crud
from app.services.permission_service import permission_service
from app.models.user import User
from app.schemas.team import (
    TeamCreate,
    TeamUpdate,
    TeamResponse,
    TeamJoinRequest,
    TeamSwitchRequest,
    TeamInviteRequest,
    AddMemberRequest,
    TeamMemberResponse,
    UserTeamsListResponse
)

router = APIRouter(prefix="/teams", tags=["团队"])


@router.post("/", response_model=TeamResponse, summary="创建团队", description="创建新团队，创建者自动成为团队管理员")
def create_team(
    request: TeamCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """创建团队"""
    # 创建团队
    team = team_crud.create(db, request, owner_id=current_user.id)

    # 创建者自动加入团队并设为当前团队
    team_crud.add_member(db, team.id, current_user.id, set_current=True)

    # 创建者自动获得 TEAM_ADMIN 角色（在该团队内）
    admin_role = role_crud.get_by_code(db, "TEAM_ADMIN")
    if admin_role:
        role_crud.assign_to_user(db, current_user.id, admin_role.id, team.id)
        # 清除用户权限缓存，确保下次获取权限时重新加载
        permission_service.clear_user_permissions_cache(current_user.id, team.id)

    return team


@router.post("/join", response_model=TeamResponse, summary="加入团队", description="通过邀请码加入团队")
def join_team(
    request: TeamJoinRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """通过邀请码加入团队"""
    # 查找团队
    team = team_crud.get_by_code(db, request.code)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="邀请码无效，团队不存在"
        )

    # 检查用户是否已加入该团队
    if team_crud.is_member(db, team.id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已加入该团队"
        )

    # 加入团队
    team_crud.add_member(db, team.id, current_user.id, set_current=True)

    return team


@router.post("/switch", summary="切换当前团队", description="切换用户的当前活跃团队")
def switch_team(
    request: TeamSwitchRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """切换当前团队"""
    # 验证用户属于该团队
    if not team_crud.is_member(db, request.team_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不属于该团队"
        )

    # 切换当前团队
    team_crud.set_current_team(db, current_user.id, request.team_id)

    return {"message": "团队已切换", "team_id": request.team_id}


@router.get("/me", response_model=TeamResponse, summary="获取当前团队", description="获取用户当前活跃团队信息")
def get_current_team(
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取当前活跃团队"""
    team = team_crud.get_by_id(db, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="团队不存在"
        )
    return team


@router.get("/user-teams", response_model=UserTeamsListResponse, summary="获取用户所有团队", description="获取用户所属的所有团队列表")
def get_user_teams_list(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取用户所有团队"""
    teams = team_crud.get_user_teams(db, current_user.id)
    current_team_id = team_crud.get_user_current_team(db, current_user.id)

    return UserTeamsListResponse(
        teams=[TeamResponse.model_validate(t) for t in teams],
        current_team_id=current_team_id
    )


@router.get("/{team_id}", response_model=TeamResponse, summary="获取团队详情", description="获取团队详细信息")
def get_team(
    team_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取团队详情"""
    # 验证用户属于该团队
    if not team_crud.is_member(db, team_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该团队"
        )

    team = team_crud.get_by_id(db, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="团队不存在"
        )

    return team


@router.post("/{team_id}/invite", summary="发送邀请邮件", description="向指定邮箱发送团队邀请邮件")
async def invite_member(
    team_id: int,
    request: TeamInviteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """发送邀请邮件"""
    from app.services.email_service import email_service

    # 验证用户属于该团队
    if not team_crud.is_member(db, team_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权邀请成员"
        )

    # 验证用户是团队管理员（在该团队内）
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_owner = team_crud.is_owner(db, team_id, current_user.id)

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有团队管理员可以邀请成员"
        )

    team = team_crud.get_by_id(db, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="团队不存在"
        )

    # 发送邀请邮件
    success = await email_service.send_team_invite(
        request.email,
        team.name,
        team.code,
        current_user.name
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="邀请邮件发送失败"
        )

    return {"message": "邀请邮件已发送", "email": request.email}


@router.get("/{team_id}/members", response_model=List[TeamMemberResponse], summary="获取团队成员列表", description="获取团队成员列表")
def get_team_members(
    team_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取团队成员列表"""
    # 验证用户属于该团队
    if not team_crud.is_member(db, team_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看团队成员"
        )

    members = team_crud.get_member_info(db, team_id)

    return [
        TeamMemberResponse(
            id=m["id"],
            name=m["name"],
            email=m["email"],
            avatar_url=m["avatar_url"],
            current_team=m["current_team"],
            joined_at=m["joined_at"]
        )
        for m in members
    ]


@router.delete("/{team_id}/members/{user_id}", summary="移除团队成员", description="从团队中移除指定成员")
def remove_member(
    team_id: int,
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """移除团队成员"""
    # 验证用户是团队管理员
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_owner = team_crud.is_owner(db, team_id, current_user.id)

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有团队管理员可以移除成员"
        )

    # 不能移除自己（除非是团队创建者）
    if user_id == current_user.id and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除自己"
        )

    # 移除成员
    success = team_crud.remove_member(db, team_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该用户不在团队中"
        )

    return {"message": "成员已移除"}


@router.put("/{team_id}", response_model=TeamResponse, summary="更新团队信息", description="更新团队名称等信息")
def update_team(
    team_id: int,
    request: TeamUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新团队信息"""
    # 验证用户是团队管理员
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_owner = team_crud.is_owner(db, team_id, current_user.id)

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有团队管理员可以更新团队信息"
        )

    team = team_crud.get_by_id(db, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="团队不存在"
        )

    updated_team = team_crud.update(db, team, request)
    return updated_team


@router.post("/{team_id}/regenerate-code", summary="重置邀请码", description="重新生成团队邀请码")
def regenerate_invite_code(
    team_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """重新生成邀请码"""
    # 验证用户是团队管理员
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_owner = team_crud.is_owner(db, team_id, current_user.id)

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有团队管理员可以重置邀请码"
        )

    new_code = team_crud.regenerate_code(db, team_id)

    return {"message": "邀请码已重置", "code": new_code}


@router.post("/{team_id}/members", summary="直接添加成员", description="将用户直接添加到团队，无需对方同意，默认分配销售成员角色")
def add_member_direct(
    team_id: int,
    request: AddMemberRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """直接添加成员到团队"""
    # 验证操作者是团队管理员或创建者
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_owner = team_crud.is_owner(db, team_id, current_user.id)

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有团队管理员可以添加成员"
        )

    # 检查目标用户是否存在
    from app.crud.user import user_crud
    target_user = user_crud.get_by_id(db, request.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 检查用户是否已在团队中
    if team_crud.is_member(db, team_id, request.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已在本团队中"
        )

    # 添加用户到团队
    team_crud.add_member(db, team_id, request.user_id, set_current=True)

    # 自动分配 SALES_MEMBER 角色
    sales_member_role = role_crud.get_by_code(db, "SALES_MEMBER")
    if sales_member_role:
        # 检查是否已有该角色
        existing_roles = role_crud.get_user_roles(db, request.user_id, team_id)
        role_codes_existing = {r.code for r in existing_roles}
        if "SALES_MEMBER" not in role_codes_existing:
            role_crud.assign_to_user(db, request.user_id, sales_member_role.id, team_id)
            # 清除用户权限缓存
            permission_service.clear_user_permissions_cache(request.user_id, team_id)

    return {"message": "成员已添加", "user_id": request.user_id}