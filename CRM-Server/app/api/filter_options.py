from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.crud.role import role_crud
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import OwnerOption, OwnerListResponse


router = APIRouter(prefix="/api/v1/filter-options", tags=["筛选选项"])


@router.get("/owners", response_model=OwnerListResponse, summary="获取可筛选的负责人列表", description="获取当前登录用户有权限查看的客户负责人列表")
def get_filter_owners(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    user_roles = role_crud.get_user_roles(db, current_user.id)
    role_codes = {r.code for r in user_roles}
    is_admin = "SYSTEM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    
    owners = db.query(
        Customer.owner_id,
        User.name
    ).outerjoin(
        User, Customer.owner_id == User.feishu_open_id
    ).filter(
        Customer.owner_id.isnot(None)
    ).distinct().all()
    
    owner_options = []
    for owner_id, owner_name in owners:
        if not owner_id:
            continue
            
        is_me = owner_id == current_user.feishu_open_id
        display_name = f"{owner_name}（我）" if is_me else (owner_name or owner_id)
        owner_options.append(OwnerOption(id=owner_id, name=display_name, is_me=is_me))
    
    owner_options.sort(key=lambda x: not x.is_me)
    
    return OwnerListResponse(data=owner_options)
