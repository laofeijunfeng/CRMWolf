from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.security import decode_access_token
from app.crud.user import user_crud
from app.crud.permission import permission_crud
from app.crud.team import team_crud, user_team_crud
from app.models.team import UserTeam

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_crud.get_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user = Depends(get_current_user)
):
    if current_user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    return current_user


async def get_current_user_team(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
) -> int:
    """获取当前用户的活跃 team_id，无团队时抛出错误"""
    user_team = user_team_crud.get_user_current_team(db, current_user.id)

    if not user_team:
        # 检查是否有任何团队
        any_team = db.query(UserTeam).filter(
            UserTeam.user_id == current_user.id
        ).first()

        if not any_team:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="用户未加入团队",
                headers={"X-Error-Code": "NO_TEAM"}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="请先选择一个团队",
                headers={"X-Error-Code": "NO_CURRENT_TEAM"}
            )

    return user_team.team_id


async def get_user_teams(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
) -> List[int]:
    """获取用户所有所属团队的 ID 列表"""
    user_teams = db.query(UserTeam.team_id).filter(
        UserTeam.user_id == current_user.id
    ).all()
    return [ut.team_id for ut in user_teams]


async def get_current_user_team_optional(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
) -> int | None:
    """获取当前用户的活跃 team_id，无团队时返回 None"""
    user_team = user_team_crud.get_user_current_team(db, current_user.id)
    return user_team.team_id if user_team else None


async def check_permission(
    required_permission: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    if required_permission not in permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少权限: {required_permission}"
        )

    return current_user


def require_permission(permission_code: str):
    def permission_checker(
        team_id: int = Depends(get_current_user_team),
        current_user = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}

        if permission_code not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission_code}"
            )

        return current_user

    return permission_checker


def require_role(role_code: str):
    def role_checker(
        current_user = Depends(get_current_active_user),
        team_id: int = Depends(get_current_user_team),
        db: Session = Depends(get_db)
    ):
        from app.crud.role import role_crud
        user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
        role_codes = {r.code for r in user_roles}

        if role_code not in role_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少角色: {role_code}"
            )

        return current_user

    return role_checker


def check_lead_access(
    lead_id: int,
    current_user = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    from app.crud.lead import lead_crud
    from app.crud.role import role_crud

    lead = lead_crud.get_by_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    is_owner = lead.owner_id == str(current_user.id)
    is_creator = lead.creator_id == str(current_user.id)

    if not (is_admin or is_director or is_owner or is_creator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该线索"
        )

    return lead


def check_lead_owner(
    lead_id: int,
    current_user = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    from app.crud.lead import lead_crud
    from app.crud.role import role_crud

    lead = lead_crud.get_by_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    is_owner = lead.owner_id == str(current_user.id)

    if not (is_admin or is_director or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有线索负责人或管理员可以操作"
        )

    return lead


def check_lead_delete_permission(
    lead_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查线索删除权限（基于权限码）

    权限规则：
    - lead:delete:all → 可删除任何线索
    - lead:delete:own → 只能删除自己负责的线索
    """
    from app.crud.lead import lead_crud

    lead = lead_crud.get_by_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部删除权限
    if "lead:delete:all" in permission_codes:
        return lead

    # 检查是否有删除自己线索的权限
    if "lead:delete:own" in permission_codes:
        if lead.owner_id == str(current_user.id):
            return lead
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己负责的线索"
        )

    # 无任何删除权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: lead:delete:own 或 lead:delete:all"
    )


def check_lead_edit_permission(
    lead_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查线索编辑权限（基于权限码）

    权限规则：
    - lead:edit:all → 可编辑任何线索
    - lead:edit:own → 只能编辑自己负责的线索
    """
    from app.crud.lead import lead_crud

    lead = lead_crud.get_by_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部编辑权限
    if "lead:edit:all" in permission_codes:
        return lead

    # 检查是否有编辑自己线索的权限
    if "lead:edit:own" in permission_codes:
        if lead.owner_id == str(current_user.id):
            return lead
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能编辑自己负责的线索"
        )

    # 无任何编辑权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: lead:edit:own 或 lead:edit:all"
    )


def check_customer_delete_permission(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查客户删除权限（基于权限码）

    权限规则：
    - customer:delete:all → 可删除任何客户
    - customer:delete:own → 只能删除自己负责的客户
    """
    from app.crud.customer import customer_crud

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部删除权限
    if "customer:delete:all" in permission_codes:
        return customer

    # 检查是否有删除自己客户的权限
    if "customer:delete:own" in permission_codes:
        if customer.owner_id == str(current_user.id):
            return customer
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己负责的客户"
        )

    # 无任何删除权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: customer:delete:own 或 customer:delete:all"
    )


def check_customer_edit_permission(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查客户编辑权限（基于权限码）

    权限规则：
    - customer:edit:all → 可编辑任何客户
    - customer:edit:own → 只能编辑自己负责的客户
    """
    from app.crud.customer import customer_crud

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部编辑权限
    if "customer:edit:all" in permission_codes:
        return customer

    # 检查是否有编辑自己客户的权限
    if "customer:edit:own" in permission_codes:
        if customer.owner_id == str(current_user.id):
            return customer
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能编辑自己负责的客户"
        )

    # 无任何编辑权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: customer:edit:own 或 customer:edit:all"
    )


def check_opportunity_delete_permission(
    opportunity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查商机删除权限（基于权限码）

    权限规则：
    - opportunity:delete:all → 可删除任何商机
    - opportunity:delete:own → 只能删除自己负责的商机
    """
    from app.crud.opportunity import opportunity_crud

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部删除权限
    if "opportunity:delete:all" in permission_codes:
        return opportunity

    # 检查是否有删除自己商机的权限
    if "opportunity:delete:own" in permission_codes:
        if opportunity.owner_id == str(current_user.id):
            return opportunity
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己负责的商机"
        )

    # 无任何删除权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: opportunity:delete:own 或 opportunity:delete:all"
    )


def check_opportunity_edit_permission(
    opportunity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查商机编辑权限（基于权限码）

    权限规则：
    - opportunity:edit:all → 可编辑任何商机
    - opportunity:edit:own → 只能编辑自己负责的商机
    """
    from app.crud.opportunity import opportunity_crud

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部编辑权限
    if "opportunity:edit:all" in permission_codes:
        return opportunity

    # 检查是否有编辑自己商机的权限
    if "opportunity:edit:own" in permission_codes:
        if opportunity.owner_id == str(current_user.id):
            return opportunity
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能编辑自己负责的商机"
        )

    # 无任何编辑权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: opportunity:edit:own 或 opportunity:edit:all"
    )


def check_contract_delete_permission(
    contract_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查合同删除权限（基于权限码）

    权限规则：
    - contract:delete:all → 可删除任何合同
    - contract:delete:own → 只能删除自己负责的合同
    """
    from app.crud.contract import contract_crud

    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部删除权限
    if "contract:delete:all" in permission_codes:
        return contract

    # 检查是否有删除自己合同的权限
    if "contract:delete:own" in permission_codes:
        if contract.owner_id == str(current_user.id):
            return contract
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己负责的合同"
        )

    # 无任何删除权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: contract:delete:own 或 contract:delete:all"
    )


def check_contract_edit_permission(
    contract_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查合同编辑权限（基于权限码）

    权限规则：
    - contract:edit:all → 可编辑任何合同
    - contract:edit:own → 只能编辑自己负责的合同
    """
    from app.crud.contract import contract_crud

    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    # 获取用户权限
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部编辑权限
    if "contract:edit:all" in permission_codes:
        return contract

    # 检查是否有编辑自己合同的权限
    if "contract:edit:own" in permission_codes:
        if contract.owner_id == str(current_user.id):
            return contract
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能编辑自己负责的合同"
        )

    # 无任何编辑权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: contract:edit:own 或 contract:edit:all"
    )


# ===== View Permission Checkers =====

def check_lead_view_permission(
    lead_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查线索查看权限（基于权限码）

    权限规则：
    - lead:view:all → 可查看任何线索
    - lead:view:own → 只能查看自己负责或创建的线索
    """
    from app.crud.lead import lead_crud

    lead = lead_crud.get_by_id(db, lead_id, team_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="线索不存在"
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部查看权限
    if "lead:view:all" in permission_codes:
        return lead

    # 检查是否有查看自己线索的权限
    if "lead:view:own" in permission_codes:
        if lead.owner_id == str(current_user.id) or lead.creator_id == str(current_user.id):
            return lead
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己负责的线索"
        )

    # 无任何查看权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: lead:view:own 或 lead:view:all"
    )


def check_customer_view_permission(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查客户查看权限（基于权限码）

    权限规则：
    - customer:view:all → 可查看任何客户
    - customer:view:own → 只能查看自己负责的客户
    """
    from app.crud.customer import customer_crud

    customer = customer_crud.get_by_id(db, customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部查看权限
    if "customer:view:all" in permission_codes:
        return customer

    # 检查是否有查看自己客户的权限
    if "customer:view:own" in permission_codes:
        if customer.owner_id == str(current_user.id):
            return customer
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己负责的客户"
        )

    # 无任何查看权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: customer:view:own 或 customer:view:all"
    )


def check_opportunity_view_permission(
    opportunity_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查商机查看权限（基于权限码）

    权限规则：
    - opportunity:view:all → 可查看任何商机
    - opportunity:view:own → 只能查看自己负责的商机
    """
    from app.crud.opportunity import opportunity_crud

    opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商机不存在"
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部查看权限
    if "opportunity:view:all" in permission_codes:
        return opportunity

    # 检查是否有查看自己商机的权限
    if "opportunity:view:own" in permission_codes:
        if opportunity.owner_id == str(current_user.id):
            return opportunity
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己负责的商机"
        )

    # 无任何查看权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: opportunity:view:own 或 opportunity:view:all"
    )


def check_contract_view_permission(
    contract_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查合同查看权限（基于权限码）

    权限规则：
    - contract:view:all → 可查看任何合同
    - contract:view:own → 只能查看自己负责的合同
    """
    from app.crud.contract import contract_crud

    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部查看权限
    if "contract:view:all" in permission_codes:
        return contract

    # 检查是否有查看自己合同的权限
    if "contract:view:own" in permission_codes:
        if contract.owner_id == str(current_user.id):
            return contract
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己负责的合同"
        )

    # 无任何查看权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: contract:view:own 或 contract:view:all"
    )


def check_invoice_view_permission(
    invoice_application_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查发票申请查看权限（基于权限码）

    权限规则：
    - invoice:view:all → 可查看任何发票申请
    - invoice:view:own → 只能查看自己申请的发票申请
    """
    from app.crud.invoice import invoice_application_crud

    application = invoice_application_crud.get_by_id(db, invoice_application_id, team_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="发票申请不存在"
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部查看权限
    if "invoice:view:all" in permission_codes:
        return application

    # 检查是否有查看自己发票申请的权限
    if "invoice:view:own" in permission_codes:
        if application.applicant_id == str(current_user.id):
            return application
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己申请的发票申请"
        )

    # 无任何查看权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: invoice:view:own 或 invoice:view:all"
    )


def check_payment_view_permission(
    payment_plan_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    检查回款计划查看权限（基于权限码）

    权限规则：
    - payment:view:all → 可查看任何回款计划
    - payment:view:own → 只能查看自己负责的回款计划（申请人）
    """
    from app.crud.payment import payment_plan_crud

    plan = payment_plan_crud.get_by_id(db, payment_plan_id, team_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有全部查看权限
    if "payment:view:all" in permission_codes:
        return plan

    # 检查是否有查看自己回款计划的权限
    if "payment:view:own" in permission_codes:
        # 回款计划的负责人通过合同关联
        if plan.contract and plan.contract.owner_id == str(current_user.id):
            return plan
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己负责的回款计划"
        )

    # 无任何查看权限
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少权限: payment:view:own 或 payment:view:all"
    )
