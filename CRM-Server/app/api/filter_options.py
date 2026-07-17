from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.customer import Customer
from app.models.contract import Contract
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.crud.permission import permission_crud
from app.schemas.customer import OwnerOption, OwnerListResponse


router = APIRouter(prefix="/v1/filter-options", tags=["筛选选项"])


@router.get("/owners", response_model=OwnerListResponse, summary="获取可筛选的负责人列表", description="获取当前登录用户有权限查看的负责人列表")
def get_filter_owners(
    resource: str = Query("customer", description="资源类型：customer、lead、opportunity 或 contract"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    resource_config = {
        "customer": (Customer, Customer.owner_id, "customer:view:all"),
        "lead": (Lead, Lead.owner_id, "lead:view:all"),
        "opportunity": (Opportunity, Opportunity.owner_id, "opportunity:view:all"),
        "contract": (Contract, Contract.owner_id, "contract:view:all"),
    }

    if resource not in resource_config:
        raise HTTPException(status_code=400, detail="不支持的负责人筛选资源")

    owner_model, owner_column, view_all_permission = resource_config[resource]
    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, current_user.id, team_id)
    }
    has_view_all = view_all_permission in permission_codes

    owners_query = db.query(owner_column).filter(
        owner_model.team_id == team_id,
        owner_column.isnot(None)
    )
    if not has_view_all:
        owners_query = owners_query.filter(owner_column == str(current_user.id))

    owners = owners_query.distinct().all()
    owner_ids = {owner_id[0] for owner_id in owners if owner_id[0]}
    if not has_view_all:
        owner_ids.add(str(current_user.id))

    # Get user names separately
    owner_options = []
    for owner_id_str in owner_ids:
        user = db.query(User).filter(User.id == int(owner_id_str)).first()
        owner_name = user.name if user else None

        is_me = owner_id_str == str(current_user.id)
        display_name = f"{owner_name}（我）" if is_me else (owner_name or owner_id_str)
        owner_options.append(OwnerOption(id=owner_id_str, name=display_name, is_me=is_me))

    owner_options.sort(key=lambda x: not x.is_me)

    return OwnerListResponse(data=owner_options)
