"""Published customer-profile projection APIs.

This module is intentionally a read-model boundary.  It never invokes the
Agent on the request path and exposes only public IDs plus a stable envelope.
"""

# ruff: noqa: B008

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_db
from app.core.deps import check_customer_view_permission, get_current_active_user, get_current_user_team
from app.crud.permission import permission_crud
from app.models.customer_profile_projection import (
    CustomerProfileCurrent,
    CustomerProfileProjectionVersion,
    CustomerProfileStatus,
)
from app.schemas.customer_profile import (
    CustomerProfileApiEnvelope,
    CustomerProfileApiError,
    CustomerProfileFreshness,
    CustomerProfileLinks,
    CustomerProfileRefreshRequest,
    CustomerProfileRefreshResponse,
    CustomerProfileResponse,
    CustomerProfileSections,
    CustomerProfileStatusValue,
    CustomerProfileSubresourceResponse,
    CustomerProfileVersionListResponse,
    CustomerProfileVersionSummary,
)
from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service
from app.services.customer_profile_evidence_resolver import customer_profile_evidence_resolver
from app.services.customer_profile_projection_service import customer_profile_projection_service
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User
    from app.services.customer_intelligence_refresh_service import CustomerIntelligenceRefreshScope


T = TypeVar("T")
router = APIRouter(prefix="/v1/customers", tags=["客户档案"])


def _request_id() -> str:
    return f"req_profile_{uuid.uuid4().hex}"


def _profile_status(value: object) -> CustomerProfileStatusValue:
    normalized = str(value)
    if normalized in {"READY", "UPDATING", "STALE", "PARTIAL", "FAILED", "NOT_READY"}:
        return cast("CustomerProfileStatusValue", normalized)
    return "NOT_READY"


def _ok(data: T, *, request_id: str | None = None) -> CustomerProfileApiEnvelope[T]:
    return CustomerProfileApiEnvelope(request_id=request_id or _request_id(), data=data, error=None)


def _raise_profile_error(
    code: str,
    message: str,
    http_status: int,
    *,
    details: dict[str, Any] | None = None,
) -> NoReturn:
    # Keep the error code machine-readable for the API error boundary.
    raise HTTPException(
        status_code=http_status,
        detail=CustomerProfileApiError(code=code, message=message, details=details).model_dump(mode="json"),
    )


@router.get(
    "/{customer_public_id}/profile",
    response_model=CustomerProfileApiEnvelope[CustomerProfileResponse],
    summary="读取客户档案",
)
def get_customer_profile(
    customer_public_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    _require_profile_permission(db, current_user, team_id, "customer_profile:view")
    _, current, version = customer_profile_projection_service.get_current_by_public_id(
        db, team_id=team_id, customer_public_id=str(customer.public_id)
    )
    return _ok(_profile_response(customer_public_id=str(customer.public_id), current=current, version=version))


def _get_profile_subresource(
    customer_public_id: str,
    *,
    section: str,
    cursor: str | None,
    limit: int,
    team_id: int,
    current_user: User,
    db: Session,
    evidence_ref: str | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    section_id: str | None = None,
) -> CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    _require_profile_permission(db, current_user, team_id, "customer_profile:view")
    _, current, version = customer_profile_projection_service.get_current_by_public_id(
        db, team_id=team_id, customer_public_id=str(customer.public_id)
    )
    profile_status = _profile_status(current.profile_status if current else CustomerProfileStatus.NOT_READY)
    items = _list_json(getattr(version, section, None) if version is not None else None)
    if evidence_ref:
        items = [
            item
            for item in items
            if evidence_ref in _string_list(item.get("evidence_refs"))
            or str(item.get("evidence_key") or "") == evidence_ref
        ]
    if from_value:
        items = [item for item in items if str(item.get("occurred_at") or "") >= from_value]
    if to_value:
        items = [item for item in items if str(item.get("occurred_at") or "") <= to_value]
    if section_id:
        items = [item for item in items if str(item.get("section_id") or "") == section_id]
    page, next_cursor, has_more = _paginate(
        items,
        cursor=cursor,
        limit=limit,
        resource=section,
        customer_public_id=customer_public_id,
    )
    data = CustomerProfileSubresourceResponse(
        profile_status=profile_status,
        current_profile_version=str(version.public_id) if version else None,
        items=page,
        next_cursor=next_cursor,
        has_more=has_more,
    )
    return _ok(data)


@router.get(
    "/{customer_public_id}/profile/changes",
    response_model=CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse],
    summary="读取客户档案重要变化",
)
def get_customer_profile_changes(
    customer_public_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    section_id: str | None = Query(default=None),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    _require_profile_permission(db, current_user, team_id, "customer_profile:view")
    _, current, version = customer_profile_projection_service.get_current_by_public_id(
        db, team_id=team_id, customer_public_id=str(customer.public_id)
    )
    profile_status = _profile_status(current.profile_status if current else CustomerProfileStatus.NOT_READY)
    decoded_before = (
        _decode_cursor(cursor, resource="changes", customer_public_id=customer_public_id)
        if cursor
        else None
    )
    items, next_version = customer_profile_projection_service.list_changes(
        db,
        team_id=team_id,
        customer_id=int(customer.id),
        limit=limit,
        before_version=decoded_before,
        from_value=from_value,
        to_value=to_value,
        section_id=section_id,
    )
    next_cursor = (
        _encode_cursor(
            resource="changes",
            customer_public_id=customer_public_id,
            sort_key=str(next_version),
        )
        if next_version is not None
        else None
    )
    return _ok(
        CustomerProfileSubresourceResponse(
            profile_status=profile_status,
            current_profile_version=str(version.public_id) if version else None,
            items=items,
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )
    )


@router.get(
    "/{customer_public_id}/profile/evidence",
    response_model=CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse],
    summary="读取客户档案证据",
)
def get_customer_profile_evidence(
    customer_public_id: str,
    evidence_ref: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    _require_profile_permission(db, current_user, team_id, "customer_profile:view")
    _, current, version = customer_profile_projection_service.get_current_by_public_id(
        db, team_id=team_id, customer_public_id=str(customer.public_id)
    )
    profile_status = _profile_status(current.profile_status if current else CustomerProfileStatus.NOT_READY)
    registry = _list_json(version.evidence_refs_json if version is not None else None)
    if evidence_ref:
        registry = [
            item
            for item in registry
            if evidence_ref in {str(item.get("evidence_key") or ""), str(item.get("evidence_id") or "")}
        ]
    resolved = customer_profile_evidence_resolver.resolve_registry(
        db,
        team_id=team_id,
        customer_id=int(customer.id),
        customer_public_id=str(customer.public_id),
        registry=registry,
    )
    page, next_cursor, has_more = _paginate(
        resolved,
        cursor=cursor,
        limit=limit,
        resource="evidence",
        customer_public_id=customer_public_id,
    )
    return _ok(
        CustomerProfileSubresourceResponse(
            profile_status=profile_status,
            current_profile_version=str(version.public_id) if version else None,
            items=page,
            next_cursor=next_cursor,
            has_more=has_more,
        )
    )


@router.get(
    "/{customer_public_id}/profile/journeys",
    response_model=CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse],
    summary="读取客户档案业务旅程",
)
def get_customer_profile_journeys(
    customer_public_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse]:
    return _get_profile_subresource(
        customer_public_id,
        section="current_journeys_json",
        cursor=cursor,
        limit=limit,
        team_id=team_id,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/{customer_public_id}/profile/follow-ups",
    response_model=CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse],
    summary="读取客户档案已记录后续事项",
)
def get_customer_profile_follow_ups(
    customer_public_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileSubresourceResponse]:
    return _get_profile_subresource(
        customer_public_id,
        section="recorded_follow_ups_json",
        cursor=cursor,
        limit=limit,
        team_id=team_id,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/{customer_public_id}/profile/versions",
    response_model=CustomerProfileApiEnvelope[CustomerProfileVersionListResponse],
    summary="读取客户档案版本",
)
def list_customer_profile_versions(
    customer_public_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    before_version: int | None = Query(default=None, ge=1),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileVersionListResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    _require_profile_permission(db, current_user, team_id, "customer_profile:history")
    decoded_before = (
        _decode_version_cursor(cursor, customer_public_id=customer_public_id)
        if cursor
        else before_version
    )
    rows, next_version = customer_profile_projection_service.list_versions(
        db, team_id=team_id, customer_id=int(customer.id), limit=limit, before_version=decoded_before
    )
    next_cursor = (
        _encode_version_cursor(next_version, customer_public_id=customer_public_id)
        if next_version is not None
        else None
    )
    data = CustomerProfileVersionListResponse(
        items=[_version_summary(row) for row in rows],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )
    return _ok(data)


@router.post(
    "/{customer_public_id}/profile/refresh",
    response_model=CustomerProfileApiEnvelope[CustomerProfileRefreshResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="异步刷新客户档案",
)
async def refresh_customer_profile(
    customer_public_id: str,
    payload: CustomerProfileRefreshRequest | None = None,
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerProfileApiEnvelope[CustomerProfileRefreshResponse]:
    customer = check_customer_view_permission(customer_public_id, team_id, current_user, db)
    _require_profile_permission(db, current_user, team_id, "customer_profile:refresh")
    request_payload = payload or CustomerProfileRefreshRequest()
    if request_payload.expected_current_version is not None:
        _, current, _ = customer_profile_projection_service.get_current_by_public_id(
            db, team_id=team_id, customer_public_id=str(customer.public_id)
        )
        current_version = int(current.last_successful_version or 0) if current else 0
        if current_version != request_payload.expected_current_version:
            _raise_profile_error("PROFILE_PUBLISH_REJECTED_STALE", "档案当前版本已变化, 请重新读取后再刷新", 409)

    scope: CustomerIntelligenceRefreshScope = request_payload.scope
    request = await customer_intelligence_refresh_service.trigger_manual_refresh(
        db, team_id=team_id, customer_id=int(customer.id), actor_id=str(current_user.id), scope=scope
    )
    run = customer_intelligence_refresh_service.run_service.get_by_request_id(
        db, team_id=team_id, request_id=request.request_id
    )
    if run is None:
        _raise_profile_error("PROFILE_REFRESH_IN_PROGRESS", "档案刷新任务未成功登记", 409)
    _, current, current_version_obj = customer_profile_projection_service.get_current_by_public_id(
        db, team_id=team_id, customer_public_id=str(customer.public_id)
    )
    data = CustomerProfileRefreshResponse(
        request_id=request.request_id,
        run_id=int(run.id),
        profile_status=_profile_status(current.profile_status if current else CustomerProfileStatus.UPDATING),
        current_profile_version=str(current_version_obj.public_id) if current_version_obj else None,
        scheduled_at=business_now(),
    )
    return _ok(data, request_id=request.request_id)


def _paginate(
    items: list[dict[str, Any]],
    *,
    cursor: str | None,
    limit: int,
    resource: str,
    customer_public_id: str,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    offset = (
        _decode_cursor(cursor, resource=resource, customer_public_id=customer_public_id)
        if cursor
        else 0
    )
    page = items[offset : offset + limit]
    next_offset = offset + len(page)
    has_more = next_offset < len(items)
    return (
        page,
        (
            _encode_cursor(
                resource=resource,
                customer_public_id=customer_public_id,
                sort_key=str(next_offset),
            )
            if has_more
            else None
        ),
        has_more,
    )


def _encode_cursor(*, resource: str, customer_public_id: str, sort_key: str) -> str:
    payload = {
        "schema_version": "v1",
        "resource": resource,
        "customer_public_id": customer_public_id,
        "sort_key": sort_key,
        "direction": "backward",
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str, *, resource: str, customer_public_id: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if not isinstance(payload, dict):
            raise ValueError
        if (
            payload.get("schema_version") != "v1"
            or payload.get("resource") != resource
            or payload.get("customer_public_id") != customer_public_id
            or payload.get("direction") != "backward"
        ):
            raise ValueError
        sort_key = payload.get("sort_key")
        if not isinstance(sort_key, str) or not sort_key.isdigit():
            raise ValueError
        return int(sort_key)
    except (ValueError, TypeError, UnicodeDecodeError, UnicodeError, binascii.Error, json.JSONDecodeError) as exc:
        _raise_profile_error("PROFILE_CURSOR_INVALID", "分页游标无效或不属于当前客户档案", 400)
        raise AssertionError from exc


def _encode_version_cursor(version: int, *, customer_public_id: str) -> str:
    return _encode_cursor(
        resource="profile_versions",
        customer_public_id=customer_public_id,
        sort_key=str(max(1, version)),
    )


def _decode_version_cursor(cursor: str, *, customer_public_id: str) -> int:
    return _decode_cursor(cursor, resource="profile_versions", customer_public_id=customer_public_id)


def _list_json(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _require_profile_permission(db: Session, user: User, team_id: int, permission_code: str) -> None:
    permission_codes = {
        permission.code for permission in permission_crud.get_user_permissions(db, int(user.id), team_id)
    }
    if permission_code not in permission_codes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少权限: {permission_code}")


def _profile_response(
    *,
    customer_public_id: str,
    current: CustomerProfileCurrent | None,
    version: CustomerProfileProjectionVersion | None,
) -> CustomerProfileResponse:
    profile_status = _profile_status(current.profile_status if current else CustomerProfileStatus.NOT_READY)
    watermark = current.latest_source_watermark_json if current else {}
    watermark = watermark if isinstance(watermark, dict) else {}
    profile_as_of = version.published_at if version else None
    latest_event_at = _datetime_value(
        watermark.get("occurred_at") or watermark.get("latest_activity_at") or watermark.get("latest_journey_at")
    )
    if version is None:
        sections = CustomerProfileSections()
        evidence_refs: list[dict[str, Any]] = []
        version_public_id = None
        version_number = None
    else:
        sections = CustomerProfileSections(
            current_situation=_dict_value(version.current_situation_json),
            current_journeys=_list_value(version.current_journeys_json),
            important_changes=_list_value(version.important_changes_json),
            long_term_context=_dict_value(version.long_term_context_json),
            follow_up_process=_list_value(version.follow_up_process_json),
            recorded_follow_ups=_list_value(version.recorded_follow_ups_json),
        )
        evidence_refs = _list_value(version.evidence_refs_json)
        version_public_id = str(version.public_id)
        version_number = int(version.profile_version)
    return CustomerProfileResponse(
        customer_id=customer_public_id,
        profile_status=profile_status,
        current_profile_version=version_public_id,
        profile_version_number=version_number,
        schema_version=str(version.schema_version) if version else "v2",
        freshness=CustomerProfileFreshness(
            profile_as_of=profile_as_of,
            latest_business_event_at=latest_event_at,
            is_stale=profile_status != CustomerProfileStatus.READY,
            stale_reason=str(current.stale_reason) if current and current.stale_reason else None,
        ),
        sections=sections,
        evidence_refs=evidence_refs,
        links=_profile_links(customer_public_id),
    )


def _profile_links(customer_public_id: str) -> CustomerProfileLinks:
    encoded = quote(customer_public_id, safe="")
    prefix = f"/api/v1/customers/{encoded}/profile"
    return CustomerProfileLinks(
        changes=f"{prefix}/changes",
        evidence=f"{prefix}/evidence",
        journeys=f"{prefix}/journeys",
        follow_ups=f"{prefix}/follow-ups",
        versions=f"{prefix}/versions",
    )


def _version_summary(version: CustomerProfileProjectionVersion) -> CustomerProfileVersionSummary:
    return CustomerProfileVersionSummary(
        public_id=str(version.public_id),
        profile_version=int(version.profile_version),
        schema_version=str(version.schema_version),
        publication_status=str(version.publication_status),
        source_event_key=str(version.source_event_key) if version.source_event_key else None,
        run_id=int(version.run_id) if version.run_id is not None else None,
        graph_version=str(version.graph_version),
        source_watermark=_dict_value(version.source_watermark_json),
        fact_watermark=int(version.fact_watermark),
        journey_watermark=int(version.journey_watermark),
        task_watermark=int(version.task_watermark),
        commitment_watermark=int(version.commitment_watermark),
        generated_at=version.generated_at,
        published_at=version.published_at,
        created_time=version.created_time,
    )


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _datetime_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
