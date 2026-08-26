"""Authoritative read-only HTTP seams used by the CRM Query Agent."""

from __future__ import annotations

import logging
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session  # noqa: TC002 - FastAPI resolves endpoint annotations at runtime

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User  # noqa: TC001 - FastAPI resolves endpoint annotations at runtime
from app.services.agent.query.completed_work_contracts import (
    CompletedWorkHTTPError,
    CompletedWorkQueryRequest,
    CompletedWorkQueryResponse,
    map_completed_work_http_error,
)
from app.services.work_summary_service import work_summary_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/agent-query", tags=["CRM Agent Query"])

_COMPLETED_WORK_PUBLIC_FILTER_FIELDS = (
    "window",
    "starts_at",
    "ends_at",
    "starts_on",
    "ends_before",
    "timezone",
    "customer_id",
    "include_tasks",
    "include_activities",
    "include_business_events",
)


def _project_completed_work_filters(filters: object) -> dict[str, object]:
    """Keep internal service inputs out of the frozen HTTP response contract."""

    if not isinstance(filters, dict):
        raise TypeError("completed-work filters must be a mapping")
    return {
        field: filters[field]
        for field in _COMPLETED_WORK_PUBLIC_FILTER_FIELDS
        if field in filters
    }


@router.get("/completed-work", response_model=CompletedWorkQueryResponse)
def get_completed_work(
    team_id: Annotated[int, Depends(get_current_user_team)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    window: str = Query("this_week"),
    customer_id: str | None = Query(None, min_length=1, max_length=64),
    start_at: str | None = Query(None, min_length=1, max_length=64),
    end_at: str | None = Query(None, min_length=1, max_length=64),
    cursor: str | None = Query(None, min_length=1, max_length=2048),
    limit: int = Query(50, ge=1, le=100),
) -> CompletedWorkQueryResponse:
    try:
        request = CompletedWorkQueryRequest.model_validate(
            {
                "window": window,
                "customer_id": customer_id,
                "start_at": start_at,
                "end_at": end_at,
                "cursor": cursor,
                "limit": limit,
            }
        )
    except ValidationError as exc:
        error = map_completed_work_http_error(exc)
        raise HTTPException(status_code=error.status_code, detail=error.model_dump()) from exc

    try:
        result = work_summary_service.list_completed_work(
            db,
            team_id=team_id,
            user_id=cast("int", current_user.id),
            window=request.window,
            customer_public_id=request.customer_id,
            include_tasks=True,
            include_activities=True,
            include_business_events=False,
            start_at=request.start_at,
            end_at=request.end_at,
            cursor=request.cursor,
            limit=request.limit,
        )
    except Exception as exc:
        error = map_completed_work_http_error(exc)
        if error.code == "INTERNAL_ERROR":
            logger.exception("Completed-work domain service failed")
        raise HTTPException(status_code=error.status_code, detail=error.model_dump()) from exc

    try:
        items = result["items"]
        return CompletedWorkQueryResponse.model_validate(
            {
                "items": items,
                "available_total": result["available_total"],
                "returned_count": len(items),
                "truncated": result["truncated"],
                "next_cursor": result["next_cursor"],
                "source_counts": result["source_counts"],
                "source_total_counts": result["source_total_counts"],
                "source_status": result["source_status"],
                "filters": _project_completed_work_filters(result["filters"]),
            }
        )
    except Exception as exc:
        logger.exception("Completed-work domain service returned an invalid response")
        error = CompletedWorkHTTPError(
            code="INTERNAL_ERROR",
            status_code=500,
            detail="completed-work query failed",
        )
        raise HTTPException(status_code=error.status_code, detail=error.model_dump()) from exc
