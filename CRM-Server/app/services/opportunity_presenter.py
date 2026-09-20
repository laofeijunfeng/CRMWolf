from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.crud.customer import customer_crud
from app.crud.deal_journey import deal_journey_crud
from app.models.approval import ApprovalStatus
from app.schemas.customer import ProcurementMethodInfo
from app.schemas.opportunity import CurrentStageSnapshotInfo, OpportunityDetailResponse


def _normalize_approval_value(value) -> Optional[str]:
    if value is None:
        return None
    normalized = str(getattr(value, "value", value)).strip()
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    return normalized.lower()


def _approval_phase_value(opportunity) -> Optional[str]:
    phase = _normalize_approval_value(getattr(opportunity, "approval_phase", None))
    if phase in {
        ApprovalPhase.DRAFT.value,
        ApprovalPhase.PENDING_REVIEW.value,
        ApprovalPhase.APPROVED.value,
        ApprovalPhase.REJECTED.value,
    }:
        return phase
    return phase


def resolve_opportunity_approval_phase(db: Session, opportunity, team_id: Optional[int]) -> str:
    phase = _approval_phase_value(opportunity)
    if phase in {
        ApprovalPhase.PENDING_REVIEW.value,
        ApprovalPhase.APPROVED.value,
        ApprovalPhase.REJECTED.value,
    }:
        return phase

    from app.crud.approval import approval_crud

    approval = approval_crud.get_by_entity(db, BusinessType.OPPORTUNITY, opportunity.id, team_id)
    approval_status = _normalize_approval_value(getattr(approval, "status", None)) if approval else None
    if approval_status == ApprovalStatus.PENDING.lower():
        return ApprovalPhase.PENDING_REVIEW.value
    if approval_status == ApprovalStatus.APPROVED.lower():
        return ApprovalPhase.APPROVED.value
    if approval_status == ApprovalStatus.REJECTED.lower():
        return ApprovalPhase.REJECTED.value

    return phase or ApprovalPhase.DRAFT.value


def customer_public_id(db: Session, customer_id: Optional[int], team_id: Optional[int]) -> Optional[str]:
    if customer_id is None:
        return None
    customer = customer_crud.get_by_id(db, customer_id, team_id)
    return customer.public_id if customer else None


def deal_journey_public_id(
    db: Session,
    journey_id: Optional[int],
    team_id: Optional[int],
    *,
    journey_public_id: Optional[str] = None,
) -> Optional[str]:
    if journey_public_id is not None:
        return journey_public_id
    if journey_id is None or team_id is None:
        return None
    journey = deal_journey_crud.get_by_id(db, int(journey_id), int(team_id))
    return journey.public_id if journey else None


def deal_journey_public_id_map(
    db: Session,
    *,
    team_id: int,
    journey_ids: list[int],
) -> dict[int, str]:
    unique_ids = list(dict.fromkeys(journey_id for journey_id in journey_ids if journey_id is not None))
    if not unique_ids:
        return {}
    journeys = deal_journey_crud.list_by_ids(db, team_id=team_id, journey_ids=unique_ids)
    return {int(journey.id): journey.public_id for journey in journeys}


def customer_info_dict(customer) -> Optional[dict]:
    if not customer:
        return None
    return {
        "id": customer.public_id,
        "public_id": customer.public_id,
        "account_name": customer.account_name,
        "industry": customer.industry,
        "city": customer.city,
        "address": customer.address,
        "company_scale": customer.company_scale,
        "status": customer.status,
        "owner_id": customer.owner_id,
    }


def opportunity_product_payload(opportunity) -> dict:
    product = getattr(opportunity, "product", None)
    modules = list(getattr(opportunity, "selected_modules", []) or [])
    return {
        "product_public_id": getattr(product, "public_id", None),
        "product_name": getattr(product, "name", None),
        "product_module_public_ids": [module.public_id for module in modules],
        "product_modules": [
            {
                "public_id": module.public_id,
                "name": module.name,
                "module_role": module.module_role,
            }
            for module in modules
        ],
    }


def opportunity_response_dict(
    db: Session,
    opportunity,
    team_id: Optional[int],
    *,
    journey_public_id: Optional[str] = None,
    customer_public_id_override: str | None = None,
) -> dict:
    payload = {
        "id": opportunity.public_id,
        "public_id": opportunity.public_id,
        "deal_journey_id": deal_journey_public_id(
            db,
            opportunity.deal_journey_id,
            team_id,
            journey_public_id=journey_public_id,
        ),
        "opportunity_number": opportunity.opportunity_number,
        "opportunity_name": opportunity.opportunity_name,
        "customer_id": customer_public_id_override or customer_public_id(db, opportunity.customer_id, team_id),
        "procurement_method_id": opportunity.procurement_method_id,
        "procurement_method_info": None,
        "total_amount": float(opportunity.total_amount),
        "user_count": opportunity.user_count,
        "unit_price": float(opportunity.unit_price),
        "license_type": opportunity.license_type,
        "subscription_years": opportunity.subscription_years,
        "purchase_type": opportunity.purchase_type,
        "decision_maker_count": opportunity.decision_maker_count,
        "expected_closing_date": opportunity.expected_closing_date,
        "stage_id": opportunity.procurement_stage_id,
        "procurement_stage_id": opportunity.procurement_stage_id,
        "win_probability": opportunity.win_probability,
        "owner_id": opportunity.owner_id,
        "status": opportunity.status,
        "approval_phase": resolve_opportunity_approval_phase(db, opportunity, team_id),
        "loss_reason": opportunity.loss_reason,
        "actual_amount": float(opportunity.actual_amount) if opportunity.actual_amount else None,
        "actual_closing_date": opportunity.actual_closing_date,
        "creator_id": opportunity.creator_id,
        "created_time": opportunity.created_time,
        "last_modified_time": opportunity.last_modified_time,
        "updated_time": opportunity.last_modified_time,
        "version": opportunity.version,
        "current_stage_snapshot": None,
    }
    payload.update(opportunity_product_payload(opportunity))
    return payload


def opportunity_detail_response(
    db: Session,
    opportunity,
    team_id: int,
    *,
    journey_public_id: str | None = None,
    customer=None,
) -> OpportunityDetailResponse:
    if customer is None:
        customer = customer_crud.get_by_id(db, opportunity.customer_id, team_id)
    owner_info = db.execute(
        text("SELECT id, name, avatar_url FROM users WHERE id = :owner_id"),
        {"owner_id": int(opportunity.owner_id)},
    ).first()
    creator_info = db.execute(
        text("SELECT id, name, avatar_url FROM users WHERE id = :creator_id"),
        {"creator_id": int(opportunity.creator_id)},
    ).first()

    current_stage_snapshot = None
    if opportunity.current_stage_snapshot_id:
        snapshot_data = db.execute(
            text(
                """
                SELECT
                    s.id,
                    s.procurement_stage_template_id,
                    s.stage_name,
                    s.win_probability,
                    s.template_sort_order,
                    s.template_code,
                    s.entered_at,
                    s.exited_at,
                    pm.id as procurement_method_id,
                    pm.code as procurement_method_code,
                    pm.name as procurement_method_name,
                    pm.is_active as procurement_method_is_active
                FROM crm_opportunity_stage_snapshots s
                LEFT JOIN crm_procurement_stage_templates pt ON s.procurement_stage_template_id = pt.id
                LEFT JOIN crm_procurement_methods pm ON pt.procurement_method_id = pm.id
                WHERE s.id = :snapshot_id
                """
            ),
            {"snapshot_id": opportunity.current_stage_snapshot_id},
        ).first()
        if snapshot_data:
            procurement_method_dict = (
                {
                    "id": snapshot_data[8],
                    "code": snapshot_data[9],
                    "name": snapshot_data[10],
                    "is_active": snapshot_data[11],
                }
                if snapshot_data[8]
                else None
            )
            current_stage_snapshot = CurrentStageSnapshotInfo(
                id=snapshot_data[0],
                procurement_stage_template_id=snapshot_data[1],
                stage_name=snapshot_data[2],
                win_probability=snapshot_data[3],
                template_sort_order=snapshot_data[4],
                template_code=snapshot_data[5],
                entered_at=snapshot_data[6],
                exited_at=snapshot_data[7],
                procurement_method=(
                    ProcurementMethodInfo(**procurement_method_dict)
                    if procurement_method_dict
                    else None
                ),
            )

    payload = opportunity_response_dict(
        db,
        opportunity,
        team_id,
        journey_public_id=journey_public_id,
        customer_public_id_override=customer.public_id if customer else None,
    )
    payload.update(
        {
            "current_stage_snapshot": current_stage_snapshot,
            "procurement_stages": None,
            "customer_name": customer.account_name if customer else None,
            "customer_info": customer_info_dict(customer),
            "owner_info": (
                {
                    "id": str(owner_info[0]),
                    "name": owner_info[1],
                    "avatar_url": owner_info[2],
                }
                if owner_info
                else None
            ),
            "creator_info": (
                {
                    "id": str(creator_info[0]),
                    "name": creator_info[1],
                    "avatar_url": creator_info[2],
                }
                if creator_info
                else None
            ),
        }
    )
    return OpportunityDetailResponse(**payload)


__all__ = [
    "customer_info_dict",
    "customer_public_id",
    "deal_journey_public_id",
    "deal_journey_public_id_map",
    "opportunity_detail_response",
    "opportunity_product_payload",
    "opportunity_response_dict",
    "resolve_opportunity_approval_phase",
]
