from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.models.user import User
from app.schemas.acquisition_source import (
    AcquisitionSourceCreate,
    AcquisitionSourceOption,
    AcquisitionSourceReorderRequest,
    AcquisitionSourceResponse,
    AcquisitionSourceUpdate,
)
from app.services.acquisition_source_service import (
    AcquisitionSourceError,
    count_usage,
    create_custom_source,
    get_by_public_id,
    list_options,
    reorder_sources,
    update_source,
)

router = APIRouter(prefix="/v1/acquisition-sources", tags=["获客来源"])


def _raise_domain_error(exc: AcquisitionSourceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _to_option(row) -> AcquisitionSourceOption:
    return AcquisitionSourceOption.model_validate(row)


def _to_response(row, usage: dict[int, dict[str, int]]) -> AcquisitionSourceResponse:
    counts = usage.get(int(row.id), {"lead_count": 0, "customer_count": 0})
    payload = {
        "public_id": row.public_id,
        "name": row.name,
        "code": row.code,
        "is_system": row.is_system,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
        "lead_count": counts["lead_count"],
        "customer_count": counts["customer_count"],
        "created_time": row.created_time,
        "updated_time": row.updated_time,
    }
    return AcquisitionSourceResponse.model_validate(payload)


@router.get("/options", response_model=list[AcquisitionSourceOption], summary="获取获客来源选项")
def get_acquisition_source_options(
    include_inactive: bool = Query(False, description="筛选场景传 true，表单默认 false"),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return [_to_option(row) for row in list_options(db, team_id, include_inactive=include_inactive)]


@router.get("/", response_model=list[AcquisitionSourceResponse], summary="获取获客来源管理列表")
def get_acquisition_sources(
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("acquisition_source:view")),
):
    rows = list_options(db, team_id, include_inactive=True)
    usage = count_usage(db, team_id, [row.id for row in rows])
    return [_to_response(row, usage) for row in rows]


@router.put("/reorder", response_model=list[AcquisitionSourceResponse], summary="重排获客来源")
def reorder_acquisition_sources(
    request: AcquisitionSourceReorderRequest,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("acquisition_source:update")),
):
    rows = reorder_sources(
        db,
        team_id=team_id,
        items=[item.model_dump() for item in request.items],
        updater_id=str(current_user.id),
    )
    usage = count_usage(db, team_id, [row.id for row in rows])
    return [_to_response(row, usage) for row in rows]


@router.get("/{public_id}", response_model=AcquisitionSourceResponse, summary="获取获客来源详情")
def get_acquisition_source(
    public_id: str,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("acquisition_source:view")),
):
    row = get_by_public_id(db, public_id, team_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="获客来源不存在")
    usage = count_usage(db, team_id, [row.id])
    return _to_response(row, usage)


@router.post("/", response_model=AcquisitionSourceResponse, status_code=status.HTTP_201_CREATED, summary="新增获客来源")
def create_acquisition_source(
    request: AcquisitionSourceCreate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("acquisition_source:create")),
):
    try:
        row = create_custom_source(
            db,
            team_id=team_id,
            name=request.name,
            created_by=str(current_user.id),
            sort_order=request.sort_order,
        )
    except AcquisitionSourceError as exc:
        _raise_domain_error(exc)
    usage = count_usage(db, team_id, [row.id])
    return _to_response(row, usage)


@router.put("/{public_id}", response_model=AcquisitionSourceResponse, summary="更新获客来源")
def update_acquisition_source(
    public_id: str,
    request: AcquisitionSourceUpdate,
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("acquisition_source:update")),
):
    try:
        row = update_source(
            db,
            team_id=team_id,
            public_id=public_id,
            updater_id=str(current_user.id),
            name=request.name,
            is_active=request.is_active,
            sort_order=request.sort_order,
        )
    except AcquisitionSourceError as exc:
        _raise_domain_error(exc)
    usage = count_usage(db, team_id, [row.id])
    return _to_response(row, usage)
