from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import OwnerOption, OwnerListResponse


router = APIRouter(prefix="/api/v1/filter-options", tags=["筛选选项"])


@router.get("/owners", response_model=OwnerListResponse, summary="获取可筛选的负责人列表", description="获取当前登录用户有权限查看的客户负责人列表")
def get_filter_owners(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):

    owners = db.query(
        Customer.owner_id
    ).filter(
        Customer.team_id == team_id,
        Customer.owner_id.isnot(None)
    ).distinct().all()

    # Get user names separately
    owner_options = []
    for owner_id in owners:
        if not owner_id[0]:
            continue

        owner_id_str = owner_id[0]
        user = db.query(User).filter(User.id == int(owner_id_str)).first()
        owner_name = user.name if user else None

        is_me = owner_id_str == str(current_user.id)
        display_name = f"{owner_name}（我）" if is_me else (owner_name or owner_id_str)
        owner_options.append(OwnerOption(id=owner_id_str, name=display_name, is_me=is_me))

    owner_options.sort(key=lambda x: not x.is_me)

    return OwnerListResponse(data=owner_options)
