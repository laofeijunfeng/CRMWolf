from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    get_current_active_user,
    get_current_user_team,
    check_customer_edit_permission,
    check_customer_view_permission,
)
from app.models.user import User
from app.schemas.procurement import MessageResponse
from app.crud.procurement import procurement_method_crud


router = APIRouter(
    prefix="/v1/customers",
    tags=["客户管理"]
)


@router.post("/{customer_id}/set-default-procurement-method", response_model=MessageResponse, summary="设置客户默认采购方式", description="""
为客户设置默认的采购方式。

**业务规则：**
- 客户创建新商机时，会自动使用客户的默认采购方式
- 采购方式必须是系统已启用的方式
- 可以设置为空，表示不限制

**权限要求：**
- 只有客户负责人或管理员可以设置
""")
def set_customer_default_procurement_method(
    customer_id: int,
    procurement_method_id: int,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    customer = check_customer_edit_permission(customer_id, team_id, current_user, db)
    
    # 检查采购方式是否存在
    if procurement_method_id != 0:
        procurement_method = procurement_method_crud.get(db, procurement_method_id)
        if not procurement_method:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"采购方式 {procurement_method_id} 不存在"
            )
        
        if procurement_method.is_active != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只能使用已启用的采购方式"
            )
    
    # 设置默认采购方式
    customer.default_procurement_method_id = procurement_method_id if procurement_method_id != 0 else None
    db.commit()
    
    return MessageResponse(
        message=f"客户默认采购方式设置成功"
    )


@router.get("/{customer_id}/default-procurement-method", summary="获取客户默认采购方式", description="""
获取客户的默认采购方式信息。

**业务规则：**
- 返回采购方式的详细信息
- 如果未设置，返回null
""")
def get_customer_default_procurement_method(
    customer_id: int,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    
    if customer.default_procurement_method_id:
        procurement_method = procurement_method_crud.get(db, customer.default_procurement_method_id)
        return {
            "procurement_method_id": procurement_method.id,
            "code": procurement_method.code,
            "name": procurement_method.name,
            "description": procurement_method.description
        }
    else:
        return {
            "procurement_method_id": None,
            "message": "客户未设置默认采购方式"
        }
