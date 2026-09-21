"""Tenant-scoped administration for durable customer-enrichment jobs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session  # noqa: TC002 - FastAPI resolves endpoint annotations at runtime

from app.core.database import get_db
from app.core.deps import get_current_user_team, require_permission
from app.crud.customer_enrichment_job import customer_enrichment_job_crud
from app.models.customer import Customer
from app.models.customer_enrichment_job import CustomerEnrichmentJob
from app.models.industry import Industry
from app.schemas.customer import (
    CustomerEnrichmentBackfillPreviewResponse,
    CustomerEnrichmentJobDiagnosticResponse,
    CustomerEnrichmentJobListResponse,
    CustomerEnrichmentReconciliationRequest,
    CustomerEnrichmentReconciliationResponse,
    CustomerEnrichmentRequeueResponse,
)
from app.services.customer_enrichment_contracts import (
    CustomerEnrichmentJobRequest,
    CustomerEnrichmentJobStatus,
)
from app.services.customer_enrichment_job_service import customer_enrichment_job_service
from app.services.customer_enrichment_plan import (
    ACTIVE_CUSTOMER_ENRICHMENT_PLAN,
    CustomerEnrichmentFieldRegistry,
)
from app.services.customer_enrichment_reconciliation_service import (
    customer_enrichment_reconciliation_service,
)
from app.utils.time import business_now

router = APIRouter(prefix="/v1/customers/enrichment", tags=["customer-enrichment"])
_admin = Depends(require_permission("customer:edit:all"))


def list_enrichment_jobs_for_team(
    db: Session,
    *,
    team_id: int,
    status_filter: str | None,
    purpose: str | None,
    skip: int,
    limit: int,
) -> tuple[list[tuple[CustomerEnrichmentJob, Customer]], int]:
    rows = (
        db.query(CustomerEnrichmentJob, Customer)
        .join(
            Customer,
            and_(
                Customer.id == CustomerEnrichmentJob.customer_id,
                Customer.team_id == CustomerEnrichmentJob.team_id,
            ),
        )
        .filter(CustomerEnrichmentJob.team_id == team_id)
    )
    if status_filter:
        rows = rows.filter(CustomerEnrichmentJob.status == status_filter)
    if purpose:
        rows = rows.filter(CustomerEnrichmentJob.purpose == purpose)
    total = rows.count()
    return (
        rows.order_by(CustomerEnrichmentJob.id.desc()).offset(skip).limit(limit).all(),
        total,
    )

def build_backfill_preview(db: Session, *, team_id: int) -> dict[str, int | bool]:
    registry = CustomerEnrichmentFieldRegistry()
    industry_missing = registry.missing_condition("industry")
    active_plan_jobs = db.query(CustomerEnrichmentJob.customer_id).filter(
        CustomerEnrichmentJob.team_id == team_id,
        CustomerEnrichmentJob.plan_version == ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version,
    )
    industry_null = (
        db.query(func.count(Customer.id))
        .filter(Customer.team_id == team_id, industry_missing)
        .scalar()
        or 0
    )
    existing_jobs = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.team_id == team_id,
            industry_missing,
            Customer.id.in_(active_plan_jobs),
        )
        .scalar()
        or 0
    )
    active_industries = {
        str(code)
        for (code,) in db.query(Industry.code).filter(Industry.is_active == 1).all()
    }
    non_missing_values = [
        str(value)
        for (value,) in db.query(Customer.industry)
        .filter(Customer.team_id == team_id, ~industry_missing)
        .all()
    ]
    invalid_non_null = sum(value not in active_industries for value in non_missing_values)
    return {
        "industry_null": int(industry_null),
        "existing_jobs": int(existing_jobs),
        "would_schedule": (
            max(0, int(industry_null) - int(existing_jobs))
            if ACTIVE_CUSTOMER_ENRICHMENT_PLAN.backfill_enabled
            else 0
        ),
        "filled_skip": len(non_missing_values),
        "invalid_non_null": invalid_non_null,
        "other_available": (
            db.query(Industry.id)
            .filter(
                Industry.code == "other",
                Industry.level == 1,
                Industry.is_active == 1,
            )
            .first()
            is not None
        ),
    }


def lock_enrichment_job_and_customer(
    db: Session,
    *,
    team_id: int,
    job_public_id: str,
) -> tuple[CustomerEnrichmentJob, Customer]:
    job = customer_enrichment_job_crud.get_by_public_id(
        db,
        team_id=team_id,
        public_id=job_public_id,
        for_update=True,
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户补全任务不存在")
    customer = (
        db.query(Customer)
        .filter(Customer.team_id == team_id, Customer.id == job.customer_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户不存在")
    return job, customer


@router.get("/jobs", response_model=CustomerEnrichmentJobListResponse)
def list_enrichment_jobs(
    team_id: Annotated[int, Depends(get_current_user_team)],
    current_user: Annotated[object, _admin],
    db: Annotated[Session, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
    purpose: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> CustomerEnrichmentJobListResponse:
    del current_user
    rows, total = list_enrichment_jobs_for_team(
        db,
        team_id=team_id,
        status_filter=status_filter,
        purpose=purpose,
        skip=skip,
        limit=limit,
    )
    return CustomerEnrichmentJobListResponse(
        items=[_job_diagnostic(job, customer) for job, customer in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/backfill-preview", response_model=CustomerEnrichmentBackfillPreviewResponse)
def get_enrichment_backfill_preview(
    team_id: Annotated[int, Depends(get_current_user_team)],
    current_user: Annotated[object, _admin],
    db: Annotated[Session, Depends(get_db)],
) -> CustomerEnrichmentBackfillPreviewResponse:
    del current_user
    return CustomerEnrichmentBackfillPreviewResponse.model_validate(
        build_backfill_preview(db, team_id=team_id)
    )


@router.post(
    "/jobs/{job_public_id}/requeue",
    response_model=CustomerEnrichmentRequeueResponse,
)
def requeue_enrichment_job(
    job_public_id: str,
    team_id: Annotated[int, Depends(get_current_user_team)],
    current_user: Annotated[object, _admin],
    db: Annotated[Session, Depends(get_db)],
) -> CustomerEnrichmentRequeueResponse:
    del current_user
    try:
        job, customer = lock_enrichment_job_and_customer(
            db,
            team_id=team_id,
            job_public_id=job_public_id,
        )
        if str(job.status) != CustomerEnrichmentJobStatus.EXHAUSTED.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅耗尽任务可重新入队")
        if str(job.plan_version) != ACTIVE_CUSTOMER_ENRICHMENT_PLAN.version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅当前补全计划可重新入队")
        if not _requested_fields_missing(customer, job.requested_fields_json or []):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="客户待补全字段已填写")
        requeued = customer_enrichment_job_crud.requeue_exhausted(
            db,
            team_id=team_id,
            public_id=job_public_id,
            available_at=business_now(),
            commit=False,
        )
        if requeued is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务状态已变化")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    customer_enrichment_job_service.kick(
        CustomerEnrichmentJobRequest(team_id=team_id, job_public_id=str(requeued.public_id))
    )
    return CustomerEnrichmentRequeueResponse(
        job_public_id=str(requeued.public_id),
        status=CustomerEnrichmentJobStatus.QUEUED.value,
        requeue_count=int(requeued.requeue_count or 0),
    )


@router.post(
    "/reconciliation/run",
    response_model=CustomerEnrichmentReconciliationResponse,
)
def run_enrichment_reconciliation(
    request: CustomerEnrichmentReconciliationRequest,
    team_id: Annotated[int, Depends(get_current_user_team)],
    current_user: Annotated[object, _admin],
    db: Annotated[Session, Depends(get_db)],
) -> CustomerEnrichmentReconciliationResponse:
    del current_user
    try:
        result = customer_enrichment_reconciliation_service.reconcile_once(
            db,
            team_id=team_id,
            after_orphan_job_id=request.after_orphan_job_id,
            limit=request.limit,
            after_customer_id=request.after_customer_id,
            dry_run=request.dry_run,
        )
        if not request.dry_run:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return CustomerEnrichmentReconciliationResponse.model_validate(result.to_dict())


def _requested_fields_missing(customer: Customer, fields: list[object]) -> bool:
    requested = {str(field) for field in fields}
    active = set(ACTIVE_CUSTOMER_ENRICHMENT_PLAN.fields)
    if not requested or not requested.issubset(active):
        return False
    registry = CustomerEnrichmentFieldRegistry()
    return any(
        registry.is_missing(field, getattr(customer, field, None))
        for field in requested
    )


def _job_diagnostic(
    job: CustomerEnrichmentJob,
    customer: Customer,
) -> CustomerEnrichmentJobDiagnosticResponse:
    return CustomerEnrichmentJobDiagnosticResponse(
        job_public_id=str(job.public_id),
        customer_id=str(customer.public_id),
        purpose=str(job.purpose),
        plan_version=str(job.plan_version),
        requested_fields=[str(item) for item in (job.requested_fields_json or [])],
        status=str(job.status),
        attempt_count=int(job.attempt_count or 0),
        max_attempts=int(job.max_attempts or 0),
        requeue_count=int(job.requeue_count or 0),
        has_profile_refresh_receipt=bool(str(job.profile_refresh_request_id or "").strip()),
        available_at=job.available_at,
        next_attempt_at=job.next_attempt_at,
        first_attempt_finished_at=job.first_attempt_finished_at,
        profile_gate_timed_out_at=job.profile_gate_timed_out_at,
        created_time=job.created_time,
        updated_time=job.updated_time,
    )
