from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.core.list_query import optional_request_list_query, run_or_400
from app.crud.customer_member import ACCESS_LEVEL_RANK
from app.crud.permission import permission_crud
from app.models.customer import CustomerMember
from app.schemas.common import PaginatedResponse
from app.schemas.customer import OwnerListResponse
from app.schemas.deal_journey import (
    BusinessJourneyBoardResponse,
    BusinessJourneyListItem,
)
from app.services.business_journey_presenter import board_response, list_items
from app.services.business_journey_query_service import (
    BusinessJourneyQueryRequest,
    JourneyScopeTab,
    business_journey_query_service,
)

router = APIRouter(prefix="/v1/business-journeys", tags=["业务旅程"])
_RELEVANT_PERMISSIONS = frozenset(
    {
        "customer:view:all",
        "customer:view:own",
        "opportunity:view:all",
        "opportunity:view:own",
    }
)
_VIEW_ACCESS_LEVELS = tuple(
    level for level, rank in ACCESS_LEVEL_RANK.items() if rank >= ACCESS_LEVEL_RANK["VIEW"]
)


def _permission_codes(db: Session, *, user_id: int, team_id: int) -> frozenset[str]:
    return frozenset(
        permission.code
        for permission in permission_crud.get_user_permissions(db, user_id, team_id)
    )


def _require_view_access(
    db: Session,
    *,
    user_id: int,
    team_id: int,
    permission_codes: frozenset[str],
) -> None:
    if permission_codes & _RELEVANT_PERMISSIONS:
        return
    has_membership = (
        db.query(CustomerMember.id)
        .filter(
            CustomerMember.team_id == team_id,
            CustomerMember.user_id == str(user_id),
            CustomerMember.is_active.is_(True),
            CustomerMember.access_level.in_(_VIEW_ACCESS_LEVELS),
        )
        .first()
        is not None
    )
    if not has_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="缺少业务旅程查看权限",
        )


def _query_request(
    *,
    team_id: int,
    user_id: int,
    permission_codes: frozenset[str],
    tab: JourneyScopeTab,
    search: str | None,
    filters: str | None,
    sorts: str | None,
) -> BusinessJourneyQueryRequest:
    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    return BusinessJourneyQueryRequest(
        team_id=team_id,
        user_id=user_id,
        permission_codes=permission_codes,
        tab=tab,
        search=search,
        filters=parsed_filters,
        sorts=parsed_sorts,
    )


def _authorized_request(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    tab: JourneyScopeTab,
    search: str | None,
    filters: str | None,
    sorts: str | None,
) -> BusinessJourneyQueryRequest:
    permission_codes = _permission_codes(db, user_id=user_id, team_id=team_id)
    _require_view_access(
        db,
        user_id=user_id,
        team_id=team_id,
        permission_codes=permission_codes,
    )
    return _query_request(
        team_id=team_id,
        user_id=user_id,
        permission_codes=permission_codes,
        tab=tab,
        search=search,
        filters=filters,
        sorts=sorts,
    )


@router.get("", response_model=PaginatedResponse[BusinessJourneyListItem])
def list_business_journeys(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    tab: Literal["all", "active", "completed", "lost"] = Query("all"),
    search: str | None = Query(None),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[BusinessJourneyListItem]:
    request = _authorized_request(
        db,
        team_id=team_id,
        user_id=current_user.id,
        tab=tab,
        search=search,
        filters=filters,
        sorts=sorts,
    )
    rows, total = run_or_400(
        lambda: business_journey_query_service.paginate(
            db,
            request=request,
            skip=skip,
            limit=limit,
        )
    )
    return PaginatedResponse(
        items=list_items(db, rows),
        total=total,
        page=skip // limit + 1,
        page_size=limit,
        total_pages=(total + limit - 1) // limit if total else 0,
    )


@router.get("/board", response_model=BusinessJourneyBoardResponse)
def get_business_journey_board(
    tab: Literal["all", "active", "completed", "lost"] = Query("all"),
    search: str | None = Query(None),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    limit: int = Query(500, ge=1, le=1000),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> BusinessJourneyBoardResponse:
    request = _authorized_request(
        db,
        team_id=team_id,
        user_id=current_user.id,
        tab=tab,
        search=search,
        filters=filters,
        sorts=sorts,
    )
    rows, total, truncated = run_or_400(
        lambda: business_journey_query_service.list_for_board(
            db,
            request=request,
            limit=limit,
        )
    )
    return board_response(
        db,
        team_id=team_id,
        rows=rows,
        total=total,
        truncated=truncated,
    )


@router.get("/owner-options", response_model=OwnerListResponse)
def get_business_journey_owner_options(
    tab: Literal["all", "active", "completed", "lost"] = Query("all"),
    search: str | None = Query(None),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> OwnerListResponse:
    request = _authorized_request(
        db,
        team_id=team_id,
        user_id=current_user.id,
        tab=tab,
        search=search,
        filters=filters,
        sorts=sorts,
    )
    options = run_or_400(
        lambda: business_journey_query_service.owner_options(db, request=request)
    )
    return OwnerListResponse(data=options)
