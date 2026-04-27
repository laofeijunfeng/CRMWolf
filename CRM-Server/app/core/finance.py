from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole


class FinancePermissions:
    INVOICE_APPROVE = "finance:invoice:approve"
    PAYMENT_CONFIRM = "finance:payment:confirm"
    RECEIVABLES_VIEW = "finance:receivables:view"
    REPORTS_VIEW = "finance:reports:view"
    AUDIT_LOGS_VIEW = "finance:audit_logs:view"


class RoleCodes:
    ADMIN = "admin"
    FINANCE = "finance"
    SALES_DIRECTOR = "sales_director"
    SALES_MEMBER = "sales_member"


def has_finance_role(db: Session, user: User) -> bool:
    if not user or not user.id:
        return False
    
    user_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.code.in_([RoleCodes.ADMIN, RoleCodes.FINANCE])
    ).first()
    
    return user_role is not None


def require_finance_role(db: Session, user: User):
    if not has_finance_role(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要财务角色权限"
        )


def can_approve_invoice(db: Session, user: User) -> bool:
    return has_finance_role(db, user)


def can_confirm_payment(db: Session, user: User) -> bool:
    return has_finance_role(db, user)


def can_view_finance_reports(db: Session, user: User) -> bool:
    return has_finance_role(db, user)


def has_admin_role(db: Session, user: User) -> bool:
    if not user or not user.id:
        return False
    
    user_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.code == RoleCodes.ADMIN
    ).first()
    
    return user_role is not None


def has_sales_director_role(db: Session, user: User) -> bool:
    if not user or not user.id:
        return False
    
    user_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.code == RoleCodes.SALES_DIRECTOR
    ).first()
    
    return user_role is not None


def can_approve_any_contract(db: Session, user: User) -> bool:
    """检查用户是否可以审批任何合同（包括自己创建的）"""
    return has_admin_role(db, user) or has_sales_director_role(db, user)


def has_role(db: Session, user: User, role_code: str) -> bool:
    """检查用户是否拥有指定角色"""
    if not user or not user.id:
        return False
    
    user_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.code == role_code
    ).first()
    
    return user_role is not None


def has_any_role(db: Session, user: User, role_codes: list) -> bool:
    """检查用户是否拥有任一指定角色"""
    if not user or not user.id:
        return False
    
    user_roles = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.code.in_(role_codes)
    ).first()
    
    return user_roles is not None
