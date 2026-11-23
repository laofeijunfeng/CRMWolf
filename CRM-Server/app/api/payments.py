import logging
from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, case, inspect, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.core.database import SessionLocal, get_db
from app.core.deps import (
    check_contract_edit_permission,
    check_contract_view_permission,
    check_payment_view_permission,
    get_current_active_user,
    get_current_user_team,
    require_permission,
)
from app.core.list_export import (
    PAYMENT_PLANS_LIST_EXPORT_CATALOG,
    PAYMENT_RECORDS_LIST_EXPORT_CATALOG,
    create_list_export_file,
    iter_batches,
    list_export_file_response,
    run_list_export_or_400,
)
from app.core.list_query import optional_request_list_query, run_or_400
from app.crud.approval import approval_crud
from app.crud.customer_member import customer_member_crud
from app.crud.payment import (
    PaymentRecordIdempotencyConflict,
    PaymentRecordIdempotentReplay,
    payment_plan_crud,
    payment_record_crud,
    payment_record_request_body,
    payment_record_request_fingerprint,
    query_pending_approval_me,
)
from app.crud.permission import permission_crud
from app.crud.user import user_crud
from app.models.approval import Approval, ApprovalNode, ApprovalRecord, ApprovalStatus
from app.models.command_execution import CommandExecutionStatus
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus, PaymentRecord
from app.models.user import User
from app.schemas.command import CommandEffect, CommandResource
from app.schemas.list_export import PaymentPlanListExportRequest, PaymentRecordListExportRequest
from app.schemas.payment import (
    ContractPaymentSummary,
    PaginatedResponse,
    PaymentPlanBatchCreate,
    PaymentPlanResponse,
    PaymentPlanStatusSummary,
    PaymentPlanUpdate,
    PaymentRecordCreate,
    PaymentRecordDetailResponse,
    PaymentRecordInfo,
    PaymentRecordListItem,
    PaymentRecordListResponse,
    PaymentRecordResponse,
    PaymentRecordUpdate,
    PaymentReminder,
)
from app.schemas.payment_composition import composition_payload
from app.schemas.payment_record_chart import (
    PaymentRecordChartBucketRecords,
    PaymentRecordChartResponse,
)
from app.services.approval_routing import NODE_TYPE_APPROVAL, current_approver_ids
from app.services.approval_transaction_manager import approval_transaction_manager
from app.services.command_execution_service import (
    CommandAlreadyInProgress,
    CommandIdempotencyConflict,
    CommandOperationConflict,
    command_execution_service,
    request_fingerprint,
)
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeRefreshInput,
    customer_business_object_intelligence_service,
)
from app.services.outbound_notification_job_service import outbound_notification_job_service
from app.services.payment_record_chart_stats import (
    build_payment_record_chart,
    list_chart_bucket_records,
)

if TYPE_CHECKING:
    from app.models.command_execution import CommandExecution
    from app.models.customer import Customer


router = APIRouter(prefix="/v1/payments", tags=["回款管理"])
logger = logging.getLogger(__name__)

_team_dependency = Depends(get_current_user_team)
_user_dependency = Depends(get_current_active_user)
_db_dependency = Depends(get_db)
_create_plan_permission = Depends(require_permission("payment:plan:create"))
_edit_plan_permission = Depends(require_permission("payment:plan:edit"))
_delete_plan_permission = Depends(require_permission("payment:plan:delete"))
_register_payment_permission = Depends(require_permission("payment:register"))
_delete_record_permission = Depends(require_permission("payment:record:delete"))
_submit_payment_permission = Depends(require_permission("payment:submit"))
_due_date_start_query = Query(None, description="计划回款日期起始\uff08YYYY-MM-DD\uff09")
_due_date_end_query = Query(None, description="计划回款日期结束\uff08YYYY-MM-DD\uff09")
_chart_payment_date_start_query = Query(None)
_chart_payment_date_end_query = Query(None)
_chart_created_time_start_query = Query(None)
_chart_created_time_end_query = Query(None)
_payment_date_start_query = Query(None, description="回款日期起始\uff08YYYY-MM-DD\uff09")
_payment_date_end_query = Query(None, description="回款日期结束\uff08YYYY-MM-DD\uff09")
_created_time_start_query = Query(None, description="创建时间起始\uff08YYYY-MM-DD\uff09")
_created_time_end_query = Query(None, description="创建时间结束\uff08YYYY-MM-DD\uff09")


def _payment_record_request_data(record_data: object) -> object:
    """Serialize request data while keeping direct API-call test doubles compatible."""
    if isinstance(record_data, PaymentRecordCreate):
        return payment_record_request_body(record_data)
    model_dump = getattr(record_data, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        if isinstance(payload, dict) and payload.get("composition") is None:
            payload.pop("composition", None)
        return payload
    if hasattr(record_data, "__dict__"):
        return vars(record_data)
    return record_data


def _payment_record_last_modified_time(record: PaymentRecord) -> datetime:
    """Return the public last-modified timestamp for a payment record.

    ``last_modified_time`` is the compatibility name used by the public
    payment schemas, while the ORM stores the value as ``updated_time``.
    Legacy records or lightweight test doubles may not expose ``updated_time``;
    in that case creation time is the stable fallback.
    """
    return getattr(record, "updated_time", None) or record.created_time


def _build_payment_plan_intelligence_change(
    db: Session,
    plan: PaymentPlan,
    *,
    change_type: Literal["created", "updated", "deleted"],
    actor_id: str | None,
) -> CustomerBusinessObjectChangeRefreshInput | None:
    return customer_business_object_intelligence_service.build_change(
        db,
        source_type="payment_plan",
        business_object=plan,
        change_type=change_type,
        actor_id=actor_id,
    )


async def _trigger_payment_plan_intelligence_refresh(
    db: Session,
    change: CustomerBusinessObjectChangeRefreshInput | None,
) -> None:
    del db  # Keep the two-argument refresh hook contract.
    if change is None:
        return
    customer_business_object_intelligence_service.enqueue_change_refresh_after_commit(change)


def _build_payment_record_intelligence_change(
    db: Session,
    record: PaymentRecord,
    *,
    change_type: Literal["created", "updated", "deleted"],
    actor_id: str | None,
) -> CustomerBusinessObjectChangeRefreshInput | None:
    return customer_business_object_intelligence_service.build_change(
        db,
        source_type="payment_record",
        business_object=record,
        change_type=change_type,
        actor_id=actor_id,
    )


async def _trigger_payment_record_intelligence_refresh(
    db: Session,
    change: CustomerBusinessObjectChangeRefreshInput | None,
) -> None:
    del db  # Keep the two-argument refresh hook contract.
    if change is None:
        return
    customer_business_object_intelligence_service.enqueue_change_refresh_after_commit(change)


def _customer_public_id(customer: "Customer | None") -> str | None:
    return customer.public_id if customer else None


def _payment_plan_response(plan: PaymentPlan) -> PaymentPlanResponse:
    contract = plan.contract
    customer = contract.customer if contract and getattr(contract, "customer", None) else None
    opportunity = contract.opportunity if contract and getattr(contract, "opportunity", None) else None
    return PaymentPlanResponse.model_validate({
        "id": plan.id,
        "contract_id": plan.contract_id,
        "plan_number": plan.plan_number,
        "stage_name": plan.stage_name,
        "planned_amount": float(plan.planned_amount),
        "due_date": plan.due_date,
        "notes": plan.notes,
        "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
        "created_time": plan.created_time,
        "last_modified_time": plan.last_modified_time,
        "paid_amount": float(getattr(plan, "paid_amount", 0) or 0),
        "remaining_amount": float(getattr(plan, "remaining_amount", plan.planned_amount) or 0),
        "payment_records": [
            PaymentRecordInfo.model_validate({
                "id": record.id,
                "actual_amount": float(record.actual_amount),
                "actual_payer_name": getattr(record, "actual_payer_name", None),
                "payment_date": record.payment_date,
                "proof_attachment": record.proof_attachment,
                "commission_member_id": record.commission_member_id,
                "commission_member_name": record.commission_member_name,
                "creator_id": record.creator_id,
                "creator_name": record.creator_name,
                "notes": record.notes,
                "confirmation_status": (
                    record.confirmation_status.value
                    if hasattr(record.confirmation_status, "value")
                    else record.confirmation_status
                ),
                "approval_phase": (
                    record.approval_phase.value
                    if hasattr(record.approval_phase, "value")
                    else record.approval_phase
                ),
                "approval_id": record.approval_id,
                "created_time": record.created_time,
            })
            for record in getattr(plan, "payment_records", []) or []
        ],
        "contract_name": contract.contract_name if contract else None,
        "creator_id": contract.creator_id if contract else None,
        "customer_id": _customer_public_id(customer),
        "customer_name": customer.account_name if customer else None,
        "opportunity_id": contract.opportunity_id if contract else None,
        "opportunity_name": opportunity.opportunity_name if opportunity else None,
        "owner_id": opportunity.owner_id if opportunity else (contract.owner_id if contract else None),
        "owner_name": getattr(plan, "owner_name", None),
        "is_invoiced": bool(getattr(plan, "invoice_count", 0)),
        "invoice_count": int(getattr(plan, "invoice_count", 0) or 0),
        "invoiced_amount": float(getattr(plan, "invoiced_amount", 0) or 0),
    })

PAYMENT_PLAN_STATUS_LABELS = {
    "PENDING": "待登记",
    "PARTIAL": "部分回款",
    "COMPLETED": "已登记",
    "OVERDUE": "已逾期",
}
PAYMENT_PLAN_TAB_STATUS = {
    "pending": "PENDING",
    "partial": "PARTIAL",
    "completed": "COMPLETED",
}
PAYMENT_PLAN_TAB_STEMS = {
    "all": "全部计划",
    "pending": "待登记",
    "partial": "部分回款",
    "completed": "已登记",
}
PAYMENT_RECORD_STATUS_LABELS = {
    "PENDING": "待确认",
    "CONFIRMED": "已确认",
    "DISPUTED": "有争议",
}
LICENSE_TYPE_LABELS = {
    "SUBSCRIPTION": "订阅",
    "PERPETUAL": "买断",
}
PURCHASE_TYPE_LABELS = {
    "NEW": "新购",
    "RENEWAL": "续购",
    "EXPANSION": "增购",
}
PAYMENT_RECORD_TAB_APPROVAL_STATUS = {
    "pending_submit": "pending_submit",
    "pending_approval": "pending_approval",
    "rejected": "rejected",
    "confirmed": "approved",
}
PAYMENT_RECORD_TAB_STEMS = {
    "all": "全部记录",
    "pending_submit": "待提交",
    "pending_approval": "审批中",
    "rejected": "已驳回",
    "confirmed": "已确认",
}


def _blank_business_number(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    return cast("str | None", getattr(value, "value", value))


def resolve_payment_scope_user_id(
    db: Session,
    current_user: User,
    team_id: int,
    *,
    me: bool,
    missing_detail: str,
) -> str | None:
    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, current_user.id, team_id)
    }
    has_view_all = "payment:view:all" in permission_codes
    has_view_own = "payment:view:own" in permission_codes
    if not has_view_all and not has_view_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=missing_detail,
        )
    if me or (has_view_own and not has_view_all):
        return str(current_user.id)
    return None


def _payment_view_own_user_id(db: Session, current_user: User, team_id: int) -> str | None:
    return resolve_payment_scope_user_id(
        db,
        current_user,
        team_id,
        me=False,
        missing_detail="没有查看回款数据的权限",
    )


class _PaymentPlanProjection(Protocol):
    owner_name: str | None
    contract_name: str
    creator_id: str
    customer_id: str | None
    customer_name: str | None
    opportunity_id: int | None
    opportunity_name: str | None
    owner_id: str | None

def _attach_payment_plan_owner_names(projection_db: Session, plans: list[PaymentPlan]) -> None:
    from app.models.user import User

    owner_ids: set[int] = set()
    owner_id_by_plan: dict[int, str] = {}
    for plan in plans:
        contract = getattr(plan, "contract", None)
        opportunity = getattr(contract, "opportunity", None) if contract is not None else None
        owner_id = None
        if opportunity is not None and getattr(opportunity, "owner_id", None):
            owner_id = str(opportunity.owner_id)
        elif contract is not None and getattr(contract, "owner_id", None):
            owner_id = str(contract.owner_id)
        if owner_id is None:
            continue
        owner_id_by_plan[plan.id] = owner_id
        if owner_id.isdigit():
            owner_ids.add(int(owner_id))
    owner_name_by_id = {
        str(user.id): user.name
        for user in projection_db.query(User).filter(User.id.in_(owner_ids)).all()
    } if owner_ids else {}
    # Owner names are a presentation-only projection, not mapped columns.
    for plan in plans:
        owner_id = owner_id_by_plan.get(plan.id)
        cast("_PaymentPlanProjection", plan).owner_name = owner_name_by_id.get(owner_id) if owner_id else None


def _payment_plan_export_row(plan: PaymentPlan) -> dict[str, object]:
    contract = getattr(plan, "contract", None)
    customer = getattr(contract, "customer", None) if contract is not None else None
    status_value = _enum_value(plan.status)
    return {
        "plan_number": _blank_business_number(plan.plan_number),
        "stage_name": plan.stage_name,
        "customer_name": customer.account_name if customer is not None else None,
        "contract_name": contract.contract_name if contract is not None else None,
        "plan_amount": float(plan.planned_amount),
        "due_date": plan.due_date,
        "status": PAYMENT_PLAN_STATUS_LABELS.get(status_value, status_value) if status_value is not None else None,
    }


def _iter_payment_plan_export_rows(
    stream: Iterable[PaymentPlan],
    projection_session_factory: Callable[[], Session] = SessionLocal,
) -> Iterator[dict[str, object]]:
    for batch in iter_batches(stream, 500):
        projection_db = projection_session_factory()
        try:
            plans = payment_plan_crud._base_plans_query(projection_db, batch[0].team_id).filter(
                PaymentPlan.id.in_([plan.id for plan in batch])
            ).all()
            plans_by_id = {plan.id: plan for plan in plans}
            for streamed in batch:
                plan = plans_by_id.get(streamed.id)
                if plan is not None:
                    yield _payment_plan_export_row(plan)
        finally:
            projection_db.close()



def _positive_contract_user_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _build_payment_record_list_items(
    projection_db: Session,
    records: list[PaymentRecord],
    team_id: int,
    *,
    include_approval: bool = True,
) -> list[dict[str, object]]:
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.invoice import InvoiceApplication
    from app.models.opportunity import Opportunity
    from app.models.user import User

    if not records:
        return []

    record_ids = [record.id for record in records]
    plan_ids = list({record.payment_plan_id for record in records})
    plans = {
        plan.id: plan
        for plan in projection_db.query(PaymentPlan).filter(
            PaymentPlan.team_id == team_id,
            PaymentPlan.id.in_(plan_ids),
        ).all()
    } if plan_ids else {}
    contract_ids = {plan.contract_id for plan in plans.values() if plan.contract_id}
    contracts = {
        contract.id: contract
        for contract in projection_db.query(Contract).filter(
            Contract.team_id == team_id,
            Contract.id.in_(contract_ids),
        ).all()
    } if contract_ids else {}
    customer_ids = {contract.customer_id for contract in contracts.values() if contract.customer_id}
    customers = {
        customer.id: customer
        for customer in projection_db.query(Customer).filter(
            Customer.team_id == team_id,
            Customer.id.in_(customer_ids),
        ).all()
    } if customer_ids else {}
    opportunity_ids = {
        contract.opportunity_id for contract in contracts.values() if contract.opportunity_id
    }
    opportunities = {
        opportunity.id: opportunity
        for opportunity in projection_db.query(Opportunity).filter(
            Opportunity.team_id == team_id,
            Opportunity.id.in_(opportunity_ids),
        ).all()
    } if opportunity_ids else {}

    record_ids_by_plan: dict[int, list[int]] = {}
    for record in records:
        record_ids_by_plan.setdefault(record.payment_plan_id, []).append(record.id)

    latest_invoice_title_by_record: dict[int, str] = {}
    has_invoice_application_table = (
        inspect(projection_db.bind).has_table(InvoiceApplication.__tablename__)
        if projection_db.bind
        else True
    )
    if record_ids and has_invoice_application_table:
        explicit_record_link = InvoiceApplication.payment_record_id.in_(record_ids)
        plan_level_link = and_(
            InvoiceApplication.payment_record_id.is_(None),
            InvoiceApplication.payment_plan_id.in_(plan_ids),
        )
        invoice_rows = projection_db.query(
            InvoiceApplication.payment_record_id,
            InvoiceApplication.payment_plan_id,
            InvoiceApplication.invoice_title_text,
        ).filter(
            InvoiceApplication.team_id == team_id,
            or_(explicit_record_link, plan_level_link),
        ).order_by(
            case((explicit_record_link, 0), else_=1),
            InvoiceApplication.created_time.desc(),
            InvoiceApplication.id.desc(),
        ).all()
        for payment_record_id, payment_plan_id, invoice_title_text_value in invoice_rows:
            target_record_ids = (
                [payment_record_id]
                if payment_record_id is not None
                else record_ids_by_plan.get(payment_plan_id, [])
            )
            for target_record_id in target_record_ids:
                if target_record_id not in latest_invoice_title_by_record:
                    latest_invoice_title_by_record[target_record_id] = invoice_title_text_value

    owner_id_by_record: dict[int, str] = {}
    for record in records:
        plan = plans.get(record.payment_plan_id)
        contract = contracts.get(plan.contract_id) if plan is not None else None
        opportunity = (
            opportunities.get(contract.opportunity_id)
            if contract is not None and contract.opportunity_id
            else None
        )
        owner_id_value = (
            opportunity.owner_id if opportunity is not None else (
                contract.owner_id if contract is not None else None
            )
        )
        if owner_id_value:
            owner_id_by_record[record.id] = str(owner_id_value)

    numeric_owner_ids = sorted({
        int(owner_id_value)
        for owner_id_value in owner_id_by_record.values()
        if str(owner_id_value).isdigit()
    })
    owner_name_by_id = {
        str(user.id): user.name
        for user in projection_db.query(User).filter(User.id.in_(numeric_owner_ids)).all()
    } if numeric_owner_ids else {}

    approval_ids = {record.approval_id for record in records if record.approval_id}

    # Legacy approval models use Column descriptors without Mapped instance types.
    approvals_by_id = {
        cast("int", approval.id): approval
        for approval in projection_db.query(Approval).filter(
            Approval.id.in_(approval_ids),
            Approval.team_id == team_id,
            Approval.business_type == BusinessType.PAYMENT,
        ).all()
    } if include_approval and approval_ids else {}
    approval_records_by_approval: dict[int, list[ApprovalRecord]] = {}
    if include_approval and approval_ids:
        approval_records = projection_db.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id.in_(approval_ids),
            ApprovalRecord.team_id == team_id,
        ).order_by(ApprovalRecord.created_time, ApprovalRecord.id).all()
        for approval_record in approval_records:
            approval_id = cast("int", approval_record.approval_id)
            approval_records_by_approval.setdefault(approval_id, []).append(approval_record)

    items: list[dict[str, object]] = []
    for record in records:
        plan = plans.get(record.payment_plan_id)
        contract = contracts.get(plan.contract_id) if plan is not None else None
        customer = customers.get(contract.customer_id) if contract is not None else None
        opportunity = (
            opportunities.get(contract.opportunity_id)
            if contract is not None and contract.opportunity_id
            else None
        )
        owner_id = owner_id_by_record.get(record.id)
        item_dict: dict[str, object] = {
            "id": record.id,
            "payment_plan_id": record.payment_plan_id,
            "record_number": record.record_number,
            "actual_amount": float(record.actual_amount),
            "actual_payer_name": getattr(record, "actual_payer_name", None),
            "payment_date": record.payment_date.isoformat() if record.payment_date else None,
            "proof_attachment": getattr(record, "proof_attachment", None),
            "commission_member_id": getattr(record, "commission_member_id", None),
            "commission_member_name": getattr(record, "commission_member_name", None),
            "notes": getattr(record, "notes", None),
            "composition": composition_payload(record),
            "creator_id": getattr(record, "creator_id", None),
            "creator_name": getattr(record, "creator_name", None),
            "approval_phase": _enum_value(getattr(record, "approval_phase", None)),
            "confirmation_status": _enum_value(record.confirmation_status),
            "created_time": record.created_time.isoformat() if record.created_time else None,
            "updated_time": getattr(record, "updated_time", None),
            "last_modified_time": _payment_record_last_modified_time(record).isoformat(),
            "contract_id": plan.contract_id if plan is not None else None,
            "contract_name": contract.contract_name if contract is not None else None,
            "contract_user_count": _positive_contract_user_count(
                contract.user_count if contract is not None else None
            ),
            "stage_name": plan.stage_name if plan is not None else None,
            "customer_id": customer.public_id if customer is not None else None,
            "customer_name": customer.account_name if customer is not None else None,
            "opportunity_id": opportunity.id if opportunity is not None else None,
            "opportunity_name": opportunity.opportunity_name if opportunity is not None else None,
            "license_type": contract.license_type if contract is not None else None,
            "purchase_type": opportunity.purchase_type if opportunity is not None else None,
            "invoice_title_text": latest_invoice_title_by_record.get(record.id),
            "owner_id": owner_id,
            "owner_name": owner_name_by_id.get(owner_id) if owner_id else None,
            "approval_id": record.approval_id,
        }

        if include_approval and record.approval_id:
            approval = approvals_by_id.get(record.approval_id)
            if approval is not None:
                item_dict["approval"] = _payment_approval_info(
                    projection_db, approval, team_id,
                    records=approval_records_by_approval.get(int(approval.id), []),
                )
        items.append(item_dict)
    return items



def _composition_segment(item: dict[str, object], segment: str) -> dict[str, int | float] | None:
    composition = item.get("composition")
    if not isinstance(composition, dict):
        return None
    value = composition.get(segment)
    return value if isinstance(value, dict) else None


def _composition_export_count(item: dict[str, object], segment: str) -> str | None:
    value = _composition_segment(item, segment)
    if value is None or value.get("headcount") is None:
        return None
    return str(int(value["headcount"]))


def _composition_export_amount(item: dict[str, object], segment: str) -> int | float | None:
    value = _composition_segment(item, segment)
    if value is None or value.get("amount") is None:
        return None
    return value["amount"]


def _payment_record_export_row(item: dict[str, object]) -> dict[str, object]:
    created_time = item.get("created_time")
    if isinstance(created_time, str):
        created_time = datetime.fromisoformat(created_time)
    payment_date = item.get("payment_date")
    if isinstance(payment_date, str):
        payment_date = date.fromisoformat(payment_date)
    confirmation_status = _enum_value(item.get("confirmation_status"))
    license_type = _enum_value(item.get("license_type"))
    purchase_type = _enum_value(item.get("purchase_type"))
    return {
        "record_number": _blank_business_number(item.get("record_number")),
        "customer_name": item.get("customer_name"),
        "actual_payer_name": item.get("actual_payer_name"),
        "invoice_title_text": item.get("invoice_title_text"),
        "contract_name": item.get("contract_name"),
        "license_type": LICENSE_TYPE_LABELS.get(license_type, license_type) if license_type is not None else None,
        "purchase_type": PURCHASE_TYPE_LABELS.get(purchase_type, purchase_type) if purchase_type is not None else None,
        "actual_amount": item.get("actual_amount"),
        "renewal_headcount": _composition_export_count(item, "renewal"),
        "renewal_amount": _composition_export_amount(item, "renewal"),
        "expansion_headcount": _composition_export_count(item, "expansion"),
        "expansion_amount": _composition_export_amount(item, "expansion"),
        "owner_name": item.get("owner_name"),
        "commission_member_name": item.get("commission_member_name"),
        "payment_date": payment_date,
        "confirmation_status": (
            PAYMENT_RECORD_STATUS_LABELS.get(confirmation_status, confirmation_status)
            if confirmation_status is not None else None
        ),
        "created_time": created_time,
    }


def _iter_payment_record_export_rows(
    stream: Iterable[PaymentRecord],
    team_id: int,
    projection_session_factory: Callable[[], Session] = SessionLocal,
) -> Iterator[dict[str, object]]:
    for batch in iter_batches(stream, 500):
        projection_db = projection_session_factory()
        try:
            for item in _build_payment_record_list_items(
                projection_db,
                batch,
                team_id,
                include_approval=False,
            ):
                yield _payment_record_export_row(item)
        finally:
            projection_db.close()



def _payment_record_response(
    record: PaymentRecord,
    *,
    operation_id: str | None = None,
    status: str | None = None,
) -> PaymentRecordResponse:
    plan = record.payment_plan
    contract = plan.contract if plan else None
    customer = contract.customer if contract and getattr(contract, "customer", None) else None
    opportunity = contract.opportunity if contract and getattr(contract, "opportunity", None) else None
    return PaymentRecordResponse.model_validate({
        "id": record.id,
        "payment_plan_id": record.payment_plan_id,
        "record_number": record.record_number,
        "actual_amount": float(record.actual_amount),
        "actual_payer_name": getattr(record, "actual_payer_name", None),
        "payment_date": record.payment_date,
        "proof_attachment": record.proof_attachment,
        "notes": record.notes,
        "composition": composition_payload(record),
        "creator_id": record.creator_id,
        "creator_name": record.creator_name,
        "approval_phase": (
            record.approval_phase.value
            if hasattr(record.approval_phase, "value")
            else record.approval_phase
        ),
        "created_time": record.created_time,
        "contract_id": contract.id if contract else None,
        "contract_name": contract.contract_name if contract else None,
        "stage_name": plan.stage_name if plan else None,
        "customer_id": _customer_public_id(customer),
        "customer_name": customer.account_name if customer else None,
        "opportunity_id": opportunity.id if opportunity else None,
        "opportunity_name": opportunity.opportunity_name if opportunity else None,
        "license_type": contract.license_type if contract else None,
        "purchase_type": opportunity.purchase_type if opportunity else None,
        "invoice_title_text": getattr(record, "invoice_title_text", None),
        "owner_id": opportunity.owner_id if opportunity else (contract.owner_id if contract else None),
        "owner_name": getattr(record, "owner_name", None),
        "commission_member_id": record.commission_member_id,
        "commission_member_name": record.commission_member_name,
        "confirmation_status": (
            record.confirmation_status.value
            if hasattr(record.confirmation_status, "value")
            else record.confirmation_status
        ),
        "updated_time": getattr(record, "updated_time", None),
        # PaymentRecord historically exposed last_modified_time while the model
        # uses updated_time. Keep the public response backward-compatible and
        # always provide the required timestamp, including legacy rows.
        "last_modified_time": _payment_record_last_modified_time(record),
        "operation_id": operation_id,
        "status": status,
    })


def _payment_record_from_command_replay(execution: "CommandExecution") -> PaymentRecordResponse:
    """Return a previously committed payment response without replaying writes."""
    payload = command_execution_service.to_response_payload(execution)
    if execution.status == CommandExecutionStatus.SUCCEEDED:
        data = payload.get("data")
        if isinstance(data, dict):
            return PaymentRecordResponse.model_validate(data)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "operation_id": execution.operation_id,
                "message": "操作结果格式异常\uff0c请通过操作编号查询结果",
            },
        )
    if execution.status == CommandExecutionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={
                "operation_id": execution.operation_id,
                "message": "回款登记正在处理中\uff0c请稍候查询结果",
            },
        )
    error = payload.get("error")
    message = error.get("message") if isinstance(error, dict) else "回款登记未成功"
    response_status = (
        status.HTTP_409_CONFLICT
        if execution.status == CommandExecutionStatus.CONFLICT
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(
        status_code=response_status,
        detail={"operation_id": execution.operation_id, "message": message},
    )


def _persist_payment_command_failure(
    db: Session,
    *,
    customer_id: int,
    team_id: int,
    actor_id: str,
    command_type: str,
    resource_type: str,
    resource_public_id: str,
    operation_id: str,
    idempotency_key: str | None,
    fingerprint: str,
    correlation_id: str | None,
    error_code: str,
    error_message: str,
    command_status: str = CommandExecutionStatus.FAILED,
) -> None:
    """Persist a failure after the business transaction has been rolled back."""
    del customer_id  # Command persistence is scoped by team and operation.
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=actor_id,
            command_type=command_type,
            resource_type=resource_type,
            resource_public_id=resource_public_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
        if not replay:
            command_execution_service.fail(
                db,
                execution,
                status=command_status,
                error_code=error_code,
                error_message=error_message,
                retryable=command_status == CommandExecutionStatus.UNKNOWN,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.error("[Payment] 无法持久化回款操作失败结果", exc_info=True)


def _validate_payment_commission_member(
    db: Session,
    team_id: int,
    customer_id: int | None,
    current_user_id: str,
    commission_member_id: str | None,
) -> None:
    if customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="回款计划未关联合同客户\uff0c无法选择提成成员"
        )
    if not commission_member_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择提成协作成员"
        )

    normalized_member_id = str(commission_member_id).strip()
    try:
        normalized_member_pk = int(normalized_member_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="提成协作成员不存在"
        ) from None

    if normalized_member_id == current_user_id:
        return

    user = user_crud.get_by_id(db, normalized_member_pk)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="提成协作成员不存在"
        )

    member = customer_member_crud.get_active_member(
        db,
        team_id=team_id,
        customer_id=customer_id,
        user_id=normalized_member_id,
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="提成协作成员必须是当前客户的团队成员\uff0c或选择你自己"
        )


@router.post(
    "/contracts/{contract_id}/payment-plans",
    response_model=list[PaymentPlanResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建回款计划",
    description="为指定合同创建回款计划\uff0c支持批量创建多个阶段。只有已签署的合同可以创建回款计划\uff0c所有阶段的计划金额之和不能超过合同总金额。返回创建成功的回款计划列表。",
)
async def create_payment_plans(
    contract_id: int,
    plans_data: PaymentPlanBatchCreate,
    team_id: int = _team_dependency,
    current_user: User = _create_plan_permission,
    db: Session = _db_dependency
) -> list[PaymentPlanResponse]:
    contract = check_contract_edit_permission(contract_id, team_id, current_user, db)

    from app.models.contract import ContractStatus
    if contract.status != ContractStatus.SIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有已签署的合同可以创建回款计划\uff0c当前状态: {contract.status}"
        )

    try:
        plans = payment_plan_crud.batch_create(db, contract_id, plans_data.plans, str(current_user.id), team_id)
        for plan in plans:
            await _trigger_payment_plan_intelligence_refresh(
                db,
                _build_payment_plan_intelligence_change(
                    db,
                    plan,
                    change_type="created",
                    actor_id=str(current_user.id),
                ),
            )
        return [_payment_plan_response(plan) for plan in plans]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建回款计划失败: {e!s}"
        ) from e


@router.get(
    "/contracts/{contract_id}/payment-plans",
    response_model=list[PaymentPlanResponse],
    summary="查询合同回款计划",
    description=(
        "获取指定合同下的所有回款计划\uff0c包括计划金额、已回款金额、待回款金额等信息。支持按回款状态筛选\uff08PENDING待回款、OVERDUE已逾期、"
        "PARTIAL部分回款、COMPLETED已登记\uff09。"
    ),
)
def get_payment_plans(
    contract_id: int,
    status: str | None = Query(None, description="回款状态筛选"),
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> list[PaymentPlanResponse]:
    check_contract_view_permission(contract_id, team_id, current_user, db)

    plans = payment_plan_crud.get_by_contract_id(db, contract_id, status)

    contract = plans[0].contract if plans and plans[0].contract else None
    if contract is None:
        from app.models.contract import Contract
        contract = db.query(Contract).filter(Contract.id == contract_id, Contract.team_id == team_id).first()

    if contract:
        customer = None
        opportunity = None
        if contract.customer_id:
            from app.crud.customer import customer_crud
            customer = customer_crud.get_by_id(db, contract.customer_id, team_id)
        if contract.opportunity_id:
            from app.crud.opportunity import opportunity_crud
            opportunity = opportunity_crud.get_by_id(db, contract.opportunity_id, team_id)

        for plan in plans:
            plan.contract = contract
            projection = cast("_PaymentPlanProjection", plan)
            projection.contract_name = contract.contract_name
            projection.creator_id = contract.creator_id
            projection.customer_id = customer.public_id if customer else None
            projection.customer_name = customer.account_name if customer else None
            projection.opportunity_id = contract.opportunity_id
            projection.opportunity_name = opportunity.opportunity_name if opportunity else None
            projection.owner_id = contract.owner_id

    return [_payment_plan_response(plan) for plan in plans]


@router.get(
    "/payment-plans",
    response_model=PaginatedResponse[PaymentPlanResponse],
    summary="查询回款计划列表",
    description="支持按状态、负责人、日期范围等条件筛选并分页查询回款计划。返回计划详情及关联的客户、商机、合同信息。可用于前端表格渲染和数据筛选。",
)
def list_payment_plans(
    plan_status: str | None = Query(
        None, alias="status", description="回款状态筛选\uff1aPENDING, OVERDUE, PARTIAL, COMPLETED"
    ),
    status_exclude: str | None = Query(None, description="排除的回款状态\uff0c多个值用逗号分隔"),
    owner_id: str | None = Query(None, description="负责人飞书ID\uff08合同创建人\uff09"),
    keyword: str | None = Query(None, description="关键词\uff0c支持客户、合同、商机、阶段名称"),
    search: str | None = Query(None, description="统一搜索词\uff0c支持计划编号、阶段、客户全称/简称/别名、合同、商机"),
    me: bool = Query(False, description="是否只查询当前用户的计划"),
    due_date_start: date | None = _due_date_start_query,
    due_date_end: date | None = _due_date_end_query,
    sort: str | None = Query(None, description="多字段排序\uff0c格式\uff1afield:asc,field2:desc"),
    order_by: str | None = Query(None, description="兼容旧版单字段排序"),
    order_dir: str | None = Query(None, description="兼容旧版排序方向\uff08asc/desc\uff09"),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> PaginatedResponse[PaymentPlanResponse]:
    """
    查询回款计划列表\uff08添加权限隔离\uff09

    权限逻辑\uff1a
    - payment:view:all → 可查看所有回款计划
    - payment:view:own → 只能查看自己创建的回款计划\uff08通过合同创建人\uff09
    - 都没有 → 403 Forbidden
    """
    from app.crud.permission import permission_crud

    # 权限检查
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    has_view_all = "payment:view:all" in permission_codes
    has_view_own = "payment:view:own" in permission_codes

    if not has_view_all and not has_view_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有查看回款计划的权限"
        )

    skip = (page - 1) * page_size

    # 数据所有权隔离
    current_user_id = None
    if me or (has_view_own and not has_view_all):
        # 如果只有 view:own 权限,或者用户明确选择只看自己的数据
        current_user_id = str(current_user.id)

    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )

    try:
        plans, total = run_or_400(lambda: payment_plan_crud.list_plans(
            db,
            team_id=team_id,
            skip=skip,
            limit=page_size,
            status=plan_status,
            status_exclude=status_exclude,
            owner_id=owner_id,
            keyword=keyword,
            search=search,
            due_date_start=due_date_start,
            due_date_end=due_date_end,
            sort=sort,
            order_by=order_by,
            order_dir=order_dir,
            current_user_id=current_user_id,
            filters=parsed_filters,
            sorts=parsed_sorts,
        ))

        _attach_payment_plan_owner_names(db, plans)

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return PaginatedResponse[PaymentPlanResponse](
            items=[_payment_plan_response(plan) for plan in plans],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询回款计划失败: {e!s}"
        ) from e


@router.post(
    "/payment-plans/export",
    dependencies=[Depends(require_permission("payment:plan:export"))],
    summary="导出回款计划列表",
    description="按当前筛选条件导出全部匹配回款计划为 Excel",
)
def export_payment_plans(
    request: PaymentPlanListExportRequest,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency,
) -> FileResponse:
    current_user_id = _payment_view_own_user_id(db, current_user, team_id)
    query = run_or_400(lambda: payment_plan_crud.build_list_query(
        db,
        team_id=team_id,
        status=PAYMENT_PLAN_TAB_STATUS.get(request.tab),
        current_user_id=current_user_id,
        search=request.search,
        filters=request.filters,
        sorts=request.sorts,
    ))
    stream = query.enable_eagerloads(False).execution_options(stream_results=True).yield_per(500)
    rows = _iter_payment_plan_export_rows(stream, projection_session_factory=SessionLocal)
    generated = run_list_export_or_400(lambda: create_list_export_file(
        catalog=PAYMENT_PLANS_LIST_EXPORT_CATALOG,
        selected_keys=request.fields,
        rows=rows,
        file_stem=f"回款计划列表-{PAYMENT_PLAN_TAB_STEMS.get(request.tab, '全部计划')}",
    ))
    return list_export_file_response(generated)



@router.get(
    "/payment-plans/badge-counts",
    response_model=None,
    summary="获取回款计划 Badge 数量",
    description=(
        "返回各类待处理数量\uff1apending(未登记)、partial(部分回款)、overdue(逾期)、pending_submit(待提交)、"
        "pending_approval(审批中-团队)、pending_approval_me(审批中-待我审批)"
    ),
)
def get_payment_plan_badge_counts(
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> dict[str, int]:
    """
    获取回款计划 Badge 数量\uff08Task 8.3: 增加 pending_approval_me\uff09

    返回\uff1a
    - pending: 未登记的计划数\uff08status=PENDING 且 payment_records.length=0\uff09
    - partial: 部分回款的计划数\uff08status=PARTIAL\uff09
    - overdue: 逾期计划数\uff08status=OVERDUE\uff09
    - pending_submit: 待提交的记录数\uff08confirmation_status=PENDING 且无关联审批\uff09
    - pending_approval: 审批中的记录数\uff08confirmation_status=PENDING 且审批状态=PENDING\uff09- 团队总数
    - pending_approval_me: 待我审批的数量\uff08与审批中心一致\uff09
    """
    # 1. 未登记的计划数(PENDING 且没有任何回款记录)
    pending_count = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id,
        PaymentPlan.status == PaymentPlanStatus.PENDING,
        ~PaymentPlan.payment_records.any()
    ).count()

    # 2. 部分回款的计划数
    partial_count = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id,
        PaymentPlan.status == PaymentPlanStatus.PARTIAL
    ).count()

    # 3. 逾期计划数
    overdue_count = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id,
        PaymentPlan.status == PaymentPlanStatus.OVERDUE
    ).count()

    # 4. 待提交的记录数(confirmation_status=PENDING 且没有关联审批)
    # 查找没有审批记录的回款记录
    pending_submit_count = db.query(PaymentRecord).filter(
        PaymentRecord.team_id == team_id,
        PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING,
        ~PaymentRecord.id.in_(
            db.query(Approval.business_id).filter(
                Approval.business_type == BusinessType.PAYMENT,
                Approval.team_id == team_id
            )
        )
    ).count()

    # 5. 审批中的记录数(confirmation_status=PENDING 且审批状态=PENDING)- 团队总数
    pending_approval_count = db.query(PaymentRecord).join(
        Approval,
        PaymentRecord.id == Approval.business_id
    ).filter(
        PaymentRecord.team_id == team_id,
        Approval.business_type == BusinessType.PAYMENT,
        Approval.team_id == team_id,
        PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING,
        Approval.status == ApprovalStatus.PENDING
    ).count()

    # 查询冻结参与人中的待我审批数量,避免读取已移除的节点角色字段。
    pending_approval_me_count = query_pending_approval_me(db, team_id, current_user.id)

    return {
        "pending": pending_count,
        "partial": partial_count,
        "overdue": overdue_count,
        "pending_submit": pending_submit_count,
        "pending_approval": pending_approval_count,
        "pending_approval_me": pending_approval_me_count  # Task 8.3: 新增
    }


@router.get(
    "/contracts/{contract_id}/payment-summary",
    response_model=ContractPaymentSummary,
    summary="查询合同回款汇总",
    description="获取指定合同的回款汇总信息\uff0c包括合同金额、已回款金额、回款状态、计划完成情况等",
)
def get_payment_summary(
    contract_id: int,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> ContractPaymentSummary:
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity

    contract = check_contract_view_permission(contract_id, team_id, current_user, db)
    
    plans = payment_plan_crud.get_by_contract_id(db, contract_id)
    
    completed_count = sum(1 for p in plans if p.status == PaymentPlanStatus.COMPLETED)
    overdue_count = sum(1 for p in plans if p.status == PaymentPlanStatus.OVERDUE)
    total_planned = sum(float(p.planned_amount) for p in plans)
    
    customer_id = None
    customer_name = None
    opportunity_id = None
    opportunity_name = None
    
    if contract.customer_id:
        customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
        if customer:
            customer_id = customer.public_id
            customer_name = customer.account_name
    
    if contract.opportunity_id:
        opportunity = db.query(Opportunity).filter(Opportunity.id == contract.opportunity_id).first()
        if opportunity:
            opportunity_id = opportunity.id
            opportunity_name = opportunity.opportunity_name
    
    return ContractPaymentSummary(
        contract_id=contract.id,
        contract_name=contract.contract_name,
        total_amount=float(contract.total_amount),
        total_paid_amount=float(contract.total_paid_amount),
        payment_status=contract.payment_status,
        payment_plans_count=len(plans),
        completed_plans_count=completed_count,
        overdue_plans_count=overdue_count,
        remaining_amount=total_planned - float(contract.total_paid_amount),
        customer_id=customer_id,
        customer_name=customer_name,
        opportunity_id=opportunity_id,
        opportunity_name=opportunity_name
    )



@router.get(
    "/payment-plans/{plan_id}",
    response_model=None,
    summary="查询回款计划详情",
    description="获取指定回款计划的详细信息\uff0c包括计划金额、已回款金额、待回款金额、回款记录列表、关联的合同和客户信息、最新审批信息。",
)
def get_payment_plan_detail(
    plan_id: int,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> dict[str, object]:
    """
    获取回款计划详情\uff08含回款记录 + 审批信息\uff09

    返回\uff08Task 8.2\uff09\uff1a
    - PaymentPlan 基本信息
    - PaymentRecord 列表
    - latest_approval\uff1a最新回款记录的审批信息
    """
    plan = check_payment_view_permission(plan_id, team_id, current_user, db)

    # 从关联对象获取信息(不修改 plan 对象)
    contract_name = None
    creator_id = None
    customer_id = None
    customer_name = None
    opportunity_id = None
    opportunity_name = None

    # 确保 contract 已加载
    if plan.contract:
        contract_name = plan.contract.contract_name
        creator_id = plan.contract.creator_id
        internal_customer_id = plan.contract.customer_id
        opportunity_id = plan.contract.opportunity_id

        # 手动查询 customer(Contract 没有 customer relationship)
        if internal_customer_id:
            from app.crud.customer import customer_crud
            customer = customer_crud.get_by_id(db, internal_customer_id)
            if customer:
                customer_id = customer.public_id
                customer_name = customer.account_name

        # 手动查询 opportunity(Contract 没有 opportunity relationship)
        if opportunity_id:
            from app.crud.opportunity import opportunity_crud
            opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
            if opportunity:
                opportunity_name = opportunity.opportunity_name

    # Task 8.2: 获取最新回款记录的审批信息
    latest_record = None
    latest_approval = None

    if plan.payment_records:
        latest_record = plan.payment_records[-1]  # 最后一条记录

        # 查询该回款记录关联的审批
        approval = db.query(Approval).filter(
            Approval.business_type == BusinessType.PAYMENT,
            Approval.business_id == latest_record.id,
            Approval.team_id == team_id,
        ).order_by(Approval.created_time.desc()).first()

        if approval:
            latest_approval = _payment_approval_info(db, approval, team_id, include_times=True)
            if latest_approval is not None:
                latest_approval.update(
                    submitter_id=approval.submitter_id,
                    submitter_name=approval.submitter_name,
                    created_time=approval.created_time.isoformat(),
                )

    # 构建响应(添加 approval 信息)
    # Task 1.2: Compute invoice fields using model properties
    invoiced_amount = float(plan.invoiced_amount)
    invoice_count = plan.invoice_count
    is_invoiced = invoice_count > 0

    response = {
        "id": plan.id,
        "contract_id": plan.contract_id,
        "stage_name": plan.stage_name,
        "planned_amount": float(plan.planned_amount),
        "due_date": plan.due_date.isoformat(),
        "notes": plan.notes,
        "status": plan.status.value if hasattr(plan.status, 'value') else plan.status,
        "paid_amount": float(plan.paid_amount),
        "remaining_amount": float(plan.remaining_amount),
        "payment_records": [
            {
                "id": r.id,
                "actual_amount": float(r.actual_amount),
                "actual_payer_name": r.actual_payer_name,
                "payment_date": r.payment_date.isoformat(),
                "proof_attachment": r.proof_attachment,
                "commission_member_id": r.commission_member_id,
                "commission_member_name": r.commission_member_name,
                "creator_id": r.creator_id,
                "creator_name": r.creator_name,
                "notes": r.notes,
                "confirmation_status": (
                    r.confirmation_status.value
                    if hasattr(r.confirmation_status, 'value')
                    else r.confirmation_status
                ),
                "approval_phase": r.approval_phase.value if hasattr(r.approval_phase, 'value') else r.approval_phase,
                "approval_id": r.approval_id,
                "created_time": r.created_time.isoformat()
            }
            for r in plan.payment_records
        ],
        "contract_name": contract_name,
        "creator_id": creator_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "opportunity_id": opportunity_id,
        "opportunity_name": opportunity_name,
        "created_time": plan.created_time.isoformat(),
        "last_modified_time": plan.last_modified_time.isoformat(),
        # Task 1.2: Invoice computed fields
        "invoiced_amount": invoiced_amount,
        "invoice_count": invoice_count,
        "is_invoiced": is_invoiced,
        # Task 8.2: 新增审批信息字段
        "latest_record_id": latest_record.id if latest_record else None,
        "latest_approval": latest_approval
    }

    return response


@router.put(
    "/payment-plans/{plan_id}",
    response_model=PaymentPlanResponse,
    summary="修改回款计划",
    description="修改指定的回款计划。已登记的计划或已有回款记录的计划不能修改金额和日期\uff0c只能修改阶段名称和备注。",
)
async def update_payment_plan(
    plan_id: int,
    plan_data: PaymentPlanUpdate,
    team_id: int = _team_dependency,
    current_user: User = _edit_plan_permission,
    db: Session = _db_dependency
) -> PaymentPlanResponse:
    plan = check_payment_view_permission(plan_id, team_id, current_user, db)

    if plan.status in [PaymentPlanStatus.COMPLETED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已登记的回款计划不能修改"
        )

    if plan.payment_records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="存在关联的回款记录\uff0c不能修改金额和日期"
        )

    try:
        updated_plan = payment_plan_crud.update(db, plan, plan_data)
        await _trigger_payment_plan_intelligence_refresh(
            db,
            _build_payment_plan_intelligence_change(
                db,
                updated_plan,
                change_type="updated",
                actor_id=str(current_user.id),
            ),
        )
        # Task 1.2: Computed fields are properties on the model, no need to set them
        return _payment_plan_response(updated_plan)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.delete(
    "/payment-plans/{plan_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除回款计划",
    description="删除指定的回款计划。存在关联回款记录的计划不能删除\uff0c删除后无法恢复。",
)
async def delete_payment_plan(
    plan_id: int,
    team_id: int = _team_dependency,
    current_user: User = _delete_plan_permission,
    db: Session = _db_dependency
) -> None:
    try:
        plan = check_payment_view_permission(plan_id, team_id, current_user, db)
        change = _build_payment_plan_intelligence_change(
            db,
            plan,
            change_type="deleted",
            actor_id=str(current_user.id),
        )
        success = payment_plan_crud.delete(db, plan_id, team_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款计划不存在"
            )
        await _trigger_payment_plan_intelligence_refresh(
            db,
            change,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.post(
    "/payment-plans/{plan_id}/records",
    response_model=PaymentRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="登记回款",
    description="为指定的回款计划登记回款记录。系统会自动校验回款金额\uff0c确保累计回款不超过计划金额。登记后自动更新计划状态和合同回款状态。返回创建成功的回款记录。",
)
async def create_payment_record(
    plan_id: int,
    record_data: PaymentRecordCreate,
    team_id: int = _team_dependency,
    current_user: User = _register_payment_permission,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    operation_id: str | None = Header(None, alias="X-Operation-Id"),
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
    db: Session = _db_dependency,
) -> PaymentRecordResponse:
    """登记回款\uff0c并为结果提供可查询的操作记录。

    回款写入属于财务事实\uff1a业务事务和命令结果在同一个事务中提交。
    因网络超时或刷新导致结果不可见时\uff0c客户端只能查询 operation_id\uff0c不能
    重新创建另一笔回款。
    """
    if not isinstance(idempotency_key, str):
        idempotency_key = None
    if not isinstance(operation_id, str):
        operation_id = None
    elif not operation_id.strip() or len(operation_id.strip()) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operation-Id 必须为 1-64 个字符",
        )
    else:
        operation_id = operation_id.strip()
    if not isinstance(correlation_id, str):
        correlation_id = None
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency-Key 必须为 1-128 个字符",
            )

    plan = check_payment_view_permission(plan_id, team_id, current_user, db)
    contract = plan.contract
    if plan.team_id != team_id or contract is None or contract.team_id != team_id or contract.customer_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回款计划不存在")
    if idempotency_key:
        existing_record = payment_record_crud.get_by_idempotency_key(db, team_id, idempotency_key)
        if existing_record:
            if existing_record.idempotency_fingerprint != payment_record_request_fingerprint(plan_id, record_data):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="幂等键已用于其他回款登记请求\uff0c请勿复用",
                )
            # 兼容在统一命令记录上线前已经落库的回款记录:补写一条
            # 已完成的 command execution,后续统一通过 operation_id 查询。
            fingerprint = request_fingerprint({
                "plan_id": plan_id,
                "record": _payment_record_request_data(record_data),
            })
            # Legacy rows may need a command receipt; fence that write too,
            # without advancing source progress for a replay.
            try:
                execution, replay = command_execution_service.begin(
                    db,
                    team_id=team_id,
                    actor_id=str(current_user.id),
                    command_type="PAYMENT_RECORD_CREATE",
                    resource_type="PAYMENT_RECORD",
                    resource_public_id=str(existing_record.id),
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    correlation_id=correlation_id,
                )
                if replay:
                    return _payment_record_from_command_replay(execution)
                response = _payment_record_response(
                    existing_record,
                    operation_id=cast("str", execution.operation_id),
                    status=CommandExecutionStatus.SUCCEEDED,
                )
                command_execution_service.succeed(
                    db,
                    execution,
                    data=response.model_dump(mode="json"),
                    resource=CommandResource(type="PAYMENT_RECORD", public_id=str(existing_record.id)),
                    correlation_id=correlation_id,
                )
                db.commit()
                return response
            except (CommandIdempotencyConflict, CommandAlreadyInProgress, CommandOperationConflict) as exc:
                db.rollback()
                if isinstance(exc, CommandAlreadyInProgress):
                    raise HTTPException(
                        status_code=status.HTTP_202_ACCEPTED,
                        detail={"operation_id": str(exc), "message": "回款登记正在处理中\uff0c请稍候查询结果"},
                    ) from exc
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    _validate_payment_commission_member(
        db,
        team_id=team_id,
        customer_id=contract.customer_id,
        current_user_id=str(current_user.id),
        commission_member_id=record_data.commission_member_id,
    )

    if plan.status == PaymentPlanStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该回款计划已登记\uff0c无法继续登记回款",
        )

    # CommandExecution.begin flushes a command row. Take the customer fence
    # first so the command, payment-plan/record locks, source progress, and
    # payment fact all follow the publisher's customer-first lock order.

    fingerprint = request_fingerprint({
        "plan_id": plan_id,
        "record": _payment_record_request_data(record_data),
    })
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=str(current_user.id),
            command_type="PAYMENT_RECORD_CREATE",
            resource_type="PAYMENT_PLAN",
            resource_public_id=str(plan_id),
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
        if replay:
            return _payment_record_from_command_replay(execution)
    except CommandIdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommandAlreadyInProgress as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"operation_id": str(exc), "message": "回款登记正在处理中\uff0c请稍候查询结果"},
        ) from exc
    except CommandOperationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        # ``commit=False`` keeps the financial fact, approval, status rollups,
        # and command result inside one transaction.
        record = payment_record_crud.create(
            db,
            plan_id,
            record_data,
            str(current_user.id),
            current_user.name,
            team_id,
            idempotency_key=idempotency_key,
            commit=False,
        )
        # Build the intelligence change before commit: expire_on_commit would
        # otherwise detach the live SQLAlchemy instance used by the builder.
        intelligence_change = _build_payment_record_intelligence_change(
            db,
            record,
            change_type="created",
            actor_id=str(current_user.id),
        )

        notify_request = None
        if record.approval_id:
            approval = approval_crud.get_by_id(db, record.approval_id, team_id)
            if approval is not None:
                try:
                    notify_request = outbound_notification_job_service.enqueue_pending_for_approval(
                        db,
                        approval=approval,
                        team_id=team_id,
                        actor_id=str(current_user.id),
                    )
                except Exception as notify_error:
                    logger.error(
                        "[Payment] 通知入队失败: record_id=%s, approval_id=%s, error=%s",
                        record.id,
                        record.approval_id,
                        notify_error,
                    )

        response = _payment_record_response(
            record,
            operation_id=cast("str", execution.operation_id),
            status=CommandExecutionStatus.SUCCEEDED,
        )
        command_execution_service.succeed(
            db,
            execution,
            data=response.model_dump(mode="json"),
            resource=CommandResource(type="PAYMENT_RECORD", public_id=str(record.id)),
            effects=[CommandEffect(type="PAYMENT_PLAN", public_id=str(plan_id), status="SYNCED")],
            correlation_id=correlation_id,
        )
        db.commit()
        await _trigger_payment_record_intelligence_refresh(db, intelligence_change)
        outbound_notification_job_service.kick(notify_request)
        return response
    except PaymentRecordIdempotentReplay as exc:
        # A concurrent legacy request can win between the initial idempotency
        # read and the plan lock. Reconcile the command after rollback instead
        # of reporting a false amount-conflict to the user.
        db.rollback()
        try:
            execution, replay = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="PAYMENT_RECORD_CREATE",
                resource_type="PAYMENT_RECORD",
                resource_public_id=str(exc.record.id),
                operation_id=cast("str", execution.operation_id),
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            if replay:
                return _payment_record_from_command_replay(execution)
            response = _payment_record_response(
                exc.record,
                operation_id=cast("str", execution.operation_id),
                status=CommandExecutionStatus.SUCCEEDED,
            )
            command_execution_service.succeed(
                db,
                execution,
                data=response.model_dump(mode="json"),
                resource=CommandResource(type="PAYMENT_RECORD", public_id=str(exc.record.id)),
                correlation_id=correlation_id,
            )
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="回款登记发生并发冲突\uff0c请刷新后确认结果",
            ) from exc
    except PaymentRecordIdempotencyConflict as exc:
        db.rollback()
        _persist_payment_command_failure(
            db,
            team_id=team_id,
            customer_id=contract.customer_id,
            actor_id=str(current_user.id),
            command_type="PAYMENT_RECORD_CREATE",
            resource_type="PAYMENT_PLAN",
            resource_public_id=str(plan_id),
            operation_id=cast("str", execution.operation_id),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
            error_code="PAYMENT_IDEMPOTENCY_CONFLICT",
            error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        _persist_payment_command_failure(
            db,
            team_id=team_id,
            customer_id=contract.customer_id,
            actor_id=str(current_user.id),
            command_type="PAYMENT_RECORD_CREATE",
            resource_type="PAYMENT_PLAN",
            resource_public_id=str(plan_id),
            operation_id=cast("str", execution.operation_id),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
            error_code="PAYMENT_RECORD_CONFLICT",
            error_message="回款登记发生并发冲突\uff0c请刷新后确认结果",
        )
        logger.error("[Payment] 回款登记唯一性冲突", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="回款登记发生并发冲突\uff0c请刷新后确认结果",
        ) from exc
    except ValueError as exc:
        db.rollback()
        _persist_payment_command_failure(
            db,
            team_id=team_id,
            customer_id=contract.customer_id,
            actor_id=str(current_user.id),
            command_type="PAYMENT_RECORD_CREATE",
            resource_type="PAYMENT_PLAN",
            resource_public_id=str(plan_id),
            operation_id=cast("str", execution.operation_id),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
            error_code="PAYMENT_RECORD_VALIDATION",
            error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        _persist_payment_command_failure(
            db,
            team_id=team_id,
            customer_id=contract.customer_id,
            actor_id=str(current_user.id),
            command_type="PAYMENT_RECORD_CREATE",
            resource_type="PAYMENT_PLAN",
            resource_public_id=str(plan_id),
            operation_id=cast("str", execution.operation_id),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
            error_code="PAYMENT_RECORD_UNKNOWN",
            error_message="回款登记结果暂未确认\uff0c请通过操作编号查询最终状态",
            command_status=CommandExecutionStatus.UNKNOWN,
        )
        logger.error("[Payment] 登记回款失败", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "operation_id": execution.operation_id,
                "message": "回款登记结果暂未确认\uff0c请稍后查询操作结果",
            },
        ) from exc


@router.get(
    "/payment-plans/{plan_id}/records",
    response_model=list[PaymentRecordResponse],
    summary="查询回款记录",
    description="获取指定回款计划下的所有回款记录\uff0c按回款日期倒序排列。包含每笔回款的详细信息\uff0c如回款金额、回款日期、登记人等。",
)
def get_payment_records(
    plan_id: int,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> list[PaymentRecordResponse]:
    check_payment_view_permission(plan_id, team_id, current_user, db)
    
    return [
        _payment_record_response(record)
        for record in payment_record_crud.get_by_plan_id(db, plan_id, team_id)
    ]


def _payment_approval_info(
    db: Session,
    approval: Approval | None,
    team_id: int,
    *,
    records: list[ApprovalRecord] | None = None,
    include_times: bool = False,
) -> dict[str, object] | None:
    """Serialize frozen assignments separately from recorded actions."""
    if approval is None or approval.team_id != team_id:
        return None
    if records is None:
        records = db.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == approval.id,
            ApprovalRecord.team_id == team_id,
        ).order_by(ApprovalRecord.created_time, ApprovalRecord.id).all()
    last_action = {row.node_id: row for row in records}
    current_ids = current_approver_ids(db, approval) if approval.status == ApprovalStatus.PENDING else []
    if approval.nodes_snapshot is not None:
        entries = [
            (
                entry.get("node_id"),
                order,
                entry.get("node_name", ""),
                entry.get("node_type", NODE_TYPE_APPROVAL),
                [int(uid) for uid in entry.get("user_ids", [])],
            )
            for order, entry in enumerate(approval.nodes_snapshot, start=1)
        ]
    else:
        entries = [
            (node.id, node.node_order, node.node_name, node.node_type, [])
            for node in db.query(ApprovalNode).filter(
                ApprovalNode.flow_id == approval.flow_id,
                ApprovalNode.team_id == team_id,
                or_(ApprovalNode.is_archived == 0, ApprovalNode.id.in_(last_action)),
            ).order_by(ApprovalNode.node_order, ApprovalNode.id).all()
        ] if approval.flow_id else []
    user_ids = set(current_ids)
    for _, _, _, node_type, frozen_ids in entries:
        if node_type == NODE_TYPE_APPROVAL:
            user_ids.update(frozen_ids)
    names_by_id: dict[int, str] = {
        int(uid): name for uid, name in db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    def names(ids: list[int]) -> list[str]:
        return [names_by_id[uid] for uid in ids if names_by_id.get(uid)]
    nodes = []
    current_node_name = None
    for node_id, order, node_name, node_type, frozen_ids in entries:
        if node_id == approval.current_node_id:
            current_node_name = node_name
        ids = frozen_ids if node_type == NODE_TYPE_APPROVAL else []
        action = last_action.get(node_id)
        node = {
            "id": node_id,
            "node_order": order,
            "node_name": node_name,
            "node_type": node_type,
            "status": action.action if action else "PENDING",
            "approver_ids": ids,
            "approver_names": names(ids),
            "approver_id": action.approver_id if action else None,
            "approver_name": action.approver_name if action else None,
            "comment": action.comment if action else None,
        }
        if include_times:
            node["approved_time"] = action.created_time.isoformat() if action else None
        nodes.append(node)
    return {
        "id": approval.id,
        "status": approval.status,
        "current_node_name": current_node_name,
        "current_approver_ids": current_ids,
        "current_approver_name": ", ".join(names(current_ids)) or None,
        "nodes": nodes,
    }


def _payment_record_detail_response(
    record: PaymentRecord,
    team_id: int,
    current_user: User,
    db: Session,
    *,
    authorized: bool = False,
) -> PaymentRecordDetailResponse:
    """Build the authoritative payment detail response used by recovery flows."""
    if not authorized:
        check_payment_view_permission(record.payment_plan_id, team_id, current_user, db)
    plan = record.payment_plan
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="回款记录所属计划不存在\uff0c请联系管理员处理",
        )

    approval = record.approval
    if approval is None:
        approval = (
            db.query(Approval)
            .filter(
                Approval.business_type == BusinessType.PAYMENT,
                Approval.business_id == record.id,
                Approval.team_id == team_id,
            )
            .order_by(Approval.created_time.desc())
            .first()
        )

    response = _payment_record_response(record).model_dump()
    response["approval_id"] = approval.id if approval else record.approval_id
    response["approval"] = _payment_approval_info(db, approval, team_id)
    response["confirmation_status"] = (
        record.confirmation_status.value
        if hasattr(record.confirmation_status, "value")
        else record.confirmation_status
    )
    response["updated_time"] = getattr(record, "updated_time", None)
    response["payment_plan"] = PaymentPlanStatusSummary.model_validate({
        "id": plan.id,
        "plan_number": plan.plan_number,
        "stage_name": plan.stage_name,
        "planned_amount": float(plan.planned_amount),
        "paid_amount": float(plan.paid_amount),
        "remaining_amount": float(plan.remaining_amount),
        "due_date": plan.due_date,
        "status": plan.status,
        "last_modified_time": plan.last_modified_time,
    })
    return PaymentRecordDetailResponse.model_validate(response)


@router.get(
    "/payment-records/resolve",
    response_model=PaymentRecordDetailResponse,
    summary="按幂等键确认回款登记结果",
    description="按系统生成的幂等键查询回款登记是否已落库\uff0c用于请求超时后的结果确认。",
)
def resolve_payment_record(
    idempotency_key: str = Query(..., min_length=1, max_length=128),
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency,
) -> PaymentRecordDetailResponse:
    record = payment_record_crud.get_by_idempotency_key(db, team_id, idempotency_key.strip())
    if record is None or not _payment_record_visible_to_caller(record, team_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款登记结果尚未确认",
        )
    return _payment_record_detail_response(record, team_id, current_user, db, authorized=True)


class _PaymentRecordPopulation(TypedDict):
    contract_id: int | None
    payment_plan_id: int | None
    payment_date_start: date | None
    payment_date_end: date | None
    min_amount: float | None
    actual_amount: float | None
    creator_id: str | None
    keyword: str | None
    search: str | None
    record_number: str | None
    record_number_exclude: str | None
    customer_name: str | None
    customer_name_exclude: str | None
    actual_payer_name: str | None
    actual_payer_name_exclude: str | None
    invoice_title_text: str | None
    invoice_title_text_exclude: str | None
    contract_name: str | None
    contract_name_exclude: str | None
    owner_name: str | None
    owner_name_exclude: str | None
    commission_member_name: str | None
    commission_member_name_exclude: str | None
    confirmation_status: str | None
    confirmation_status_exclude: str | None
    created_time_start: date | None
    created_time_end: date | None
    me: bool
    approval_status: str | None
    approval_status_exclude: str | None
    sort: str | None
    order_by: str | None
    order_dir: str | None
    filters: str | None
    sorts: str | None


def payment_record_population_filters(
    contract_id: int | None = Query(None),
    payment_plan_id: int | None = Query(None),
    payment_date_start: date | None = _chart_payment_date_start_query,
    payment_date_end: date | None = _chart_payment_date_end_query,
    min_amount: float | None = Query(None, ge=0),
    actual_amount: float | None = Query(None, ge=0),
    creator_id: str | None = Query(None),
    keyword: str | None = Query(None),
    search: str | None = Query(None),
    record_number: str | None = Query(None),
    record_number_exclude: str | None = Query(None),
    customer_name: str | None = Query(None),
    customer_name_exclude: str | None = Query(None),
    actual_payer_name: str | None = Query(None),
    actual_payer_name_exclude: str | None = Query(None),
    invoice_title_text: str | None = Query(None),
    invoice_title_text_exclude: str | None = Query(None),
    contract_name: str | None = Query(None),
    contract_name_exclude: str | None = Query(None),
    owner_name: str | None = Query(None),
    owner_name_exclude: str | None = Query(None),
    commission_member_name: str | None = Query(None),
    commission_member_name_exclude: str | None = Query(None),
    confirmation_status: str | None = Query(None),
    confirmation_status_exclude: str | None = Query(None),
    created_time_start: date | None = _chart_created_time_start_query,
    created_time_end: date | None = _chart_created_time_end_query,
    me: bool = Query(False),
    approval_status: str | None = Query(None),
    approval_status_exclude: str | None = Query(None),
    sort: str | None = Query(None),
    order_by: str | None = Query(None),
    order_dir: str | None = Query(None),
    filters: str | None = Query(None),
    sorts: str | None = Query(None),
) -> _PaymentRecordPopulation:
    """列表和图表共用的筛选参数。图表不分页。"""
    return {
        "contract_id": contract_id,
        "payment_plan_id": payment_plan_id,
        "payment_date_start": payment_date_start,
        "payment_date_end": payment_date_end,
        "min_amount": min_amount,
        "actual_amount": actual_amount,
        "creator_id": creator_id,
        "keyword": keyword,
        "search": search,
        "record_number": record_number,
        "record_number_exclude": record_number_exclude,
        "customer_name": customer_name,
        "customer_name_exclude": customer_name_exclude,
        "actual_payer_name": actual_payer_name,
        "actual_payer_name_exclude": actual_payer_name_exclude,
        "invoice_title_text": invoice_title_text,
        "invoice_title_text_exclude": invoice_title_text_exclude,
        "contract_name": contract_name,
        "contract_name_exclude": contract_name_exclude,
        "owner_name": owner_name,
        "owner_name_exclude": owner_name_exclude,
        "commission_member_name": commission_member_name,
        "commission_member_name_exclude": commission_member_name_exclude,
        "confirmation_status": confirmation_status,
        "confirmation_status_exclude": confirmation_status_exclude,
        "created_time_start": created_time_start,
        "created_time_end": created_time_end,
        "me": me,
        "approval_status": approval_status,
        "approval_status_exclude": approval_status_exclude,
        "sort": sort,
        "order_by": order_by,
        "order_dir": order_dir,
        "filters": filters,
        "sorts": sorts,
    }


def _payment_record_chart_rows(
    db: Session, team_id: int, current_user: User, population: _PaymentRecordPopulation,
) -> list[PaymentRecord]:
    current_user_id = resolve_payment_scope_user_id(
        db,
        current_user,
        team_id,
        me=bool(population["me"]),
        missing_detail="没有查看回款记录的权限",
    )
    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=population["filters"],
        sorts_raw=population["sorts"],
    )
    return run_or_400(lambda: payment_record_crud.build_population_query(
        db,
        team_id=team_id,
        contract_id=population["contract_id"],
        payment_plan_id=population["payment_plan_id"],
        payment_date_start=population["payment_date_start"],
        payment_date_end=population["payment_date_end"],
        min_amount=population["min_amount"],
        actual_amount=population["actual_amount"],
        creator_id=population["creator_id"],
        keyword=population["keyword"],
        search=population["search"],
        record_number=population["record_number"],
        record_number_exclude=population["record_number_exclude"],
        customer_name=population["customer_name"],
        customer_name_exclude=population["customer_name_exclude"],
        actual_payer_name=population["actual_payer_name"],
        actual_payer_name_exclude=population["actual_payer_name_exclude"],
        invoice_title_text=population["invoice_title_text"],
        invoice_title_text_exclude=population["invoice_title_text_exclude"],
        contract_name=population["contract_name"],
        contract_name_exclude=population["contract_name_exclude"],
        owner_name=population["owner_name"],
        owner_name_exclude=population["owner_name_exclude"],
        commission_member_name=population["commission_member_name"],
        commission_member_name_exclude=population["commission_member_name_exclude"],
        confirmation_status=population["confirmation_status"],
        confirmation_status_exclude=population["confirmation_status_exclude"],
        created_time_start=population["created_time_start"],
        created_time_end=population["created_time_end"],
        current_user_id=current_user_id,
        approval_status=population["approval_status"],
        approval_status_exclude=population["approval_status_exclude"],
        sort=population["sort"],
        order_by=population["order_by"],
        order_dir=population["order_dir"],
        filters=parsed_filters,
        sorts=parsed_sorts,
    ).all())


_population_dependency = Depends(payment_record_population_filters)


@router.get("/payment-records/chart", response_model=PaymentRecordChartResponse, summary="查询回款图表")
def get_payment_record_chart(
    population: _PaymentRecordPopulation = _population_dependency,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency,
) -> PaymentRecordChartResponse:
    rows = _payment_record_chart_rows(db, team_id, current_user, population)
    return PaymentRecordChartResponse.model_validate(build_payment_record_chart(rows))


@router.get(
    "/payment-records/chart/records",
    response_model=PaymentRecordChartBucketRecords,
    summary="查询回款图表一段里的回款",
)
def get_payment_record_chart_records(
    chart: str = Query(..., description="图表键"),
    bucket: str = Query(..., description="段键"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    population: _PaymentRecordPopulation = _population_dependency,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency,
) -> PaymentRecordChartBucketRecords:
    rows = _payment_record_chart_rows(db, team_id, current_user, population)
    try:
        total, records = list_chart_bucket_records(rows, chart, bucket, skip=skip, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PaymentRecordChartBucketRecords.model_validate(
        {"chart": chart, "bucket": bucket, "total": total, "records": records}
    )


@router.get(
    "/payment-records/{record_id}",
    response_model=PaymentRecordDetailResponse,
    summary="查询回款记录详情",
    description="查询单条回款记录及审批、所属计划汇总状态\uff0c用于详情展示和请求超时后的最终状态确认。",
)
def get_payment_record_detail(
    record_id: int,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency,
) -> PaymentRecordDetailResponse:
    record = payment_record_crud.get_by_id(db, record_id, team_id)
    if record is None or not _payment_record_visible_to_caller(record, team_id, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款记录不存在",
        )
    return _payment_record_detail_response(record, team_id, current_user, db, authorized=True)


def _payment_record_visible_to_caller(record: PaymentRecord, team_id: int, current_user: User, db: Session) -> bool:
    """Own-scope callers may read only records on contracts they created."""
    from app.models.contract import Contract

    scope_user_id = resolve_payment_scope_user_id(
        db,
        current_user,
        team_id,
        me=False,
        missing_detail="没有查看回款记录的权限",
    )
    if scope_user_id is None:
        return True
    plan = record.payment_plan
    contract = plan.contract if plan is not None else None
    if contract is None and plan is not None and plan.contract_id is not None:
        contract = (
            db.query(Contract)
            .filter(Contract.id == plan.contract_id, Contract.team_id == team_id)
            .first()
        )
    return contract is not None and contract.creator_id == scope_user_id


@router.put(
    "/payment-records/{record_id}",
    response_model=PaymentRecordResponse,
    summary="更新回款记录",
    description="更新指定的回款记录。更新后会自动重新计算相关金额、计划状态和合同回款状态。支持修改回款金额、回款日期、凭证附件和备注信息。",
)
async def update_payment_record(
    record_id: int,
    record_data: PaymentRecordUpdate,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> PaymentRecordResponse:
    """
    更新回款记录\uff08用于驳回后修正\uff09

    仅允许更新\uff1a
    - actual_amount\uff08回款金额\uff09
    - payment_date\uff08回款日期\uff09
    - proof_attachment\uff08凭证附件\uff09
    - notes\uff08备注\uff09

    注意\uff1a审批撤回后的草稿、审批驳回的记录可由登记人修改\uff1b具备
    payment:record:edit 的用户也可修改。
    """
    record = payment_record_crud.get_by_id(db, record_id, team_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款记录不存在"
        )
    check_payment_view_permission(record.payment_plan_id, team_id, current_user, db)
    if record_data.commission_member_id is not None:
        customer_id = (
            record.payment_plan.contract.customer_id
            if record.payment_plan and record.payment_plan.contract else None
        )
        _validate_payment_commission_member(
            db,
            team_id=team_id,
            customer_id=customer_id,
            current_user_id=str(current_user.id),
            commission_member_id=record_data.commission_member_id,
        )

    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}
    has_global_edit_permission = "payment:record:edit" in permission_codes
    is_creator = record.creator_id == str(current_user.id)
    editable_phases = {
        ApprovalPhase.DRAFT.value,
        ApprovalPhase.REJECTED.value,
        ApprovalPhase.DRAFT,
        ApprovalPhase.REJECTED,
    }

    if not has_global_edit_permission and not is_creator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能修改自己登记的回款记录"
        )

    if record.approval is not None and record.approval.status == ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="审批中的回款记录不能修改"
        )

    if record.approval_phase not in editable_phases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有审批撤回或被驳回的回款记录才能修改"
        )

    try:
        updated_record = payment_record_crud.update(db, record, record_data)
        await _trigger_payment_record_intelligence_refresh(
            db,
            _build_payment_record_intelligence_change(
                db,
                updated_record,
                change_type="updated",
                actor_id=str(current_user.id),
            ),
        )
        return _payment_record_response(updated_record)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.delete(
    "/payment-records/{record_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除回款记录",
    description="删除指定的回款记录。审批中或审批通过后不可删除\uff1b删除后会自动重新计算相关金额、计划状态和合同回款状态。",
)
async def delete_payment_record(
    record_id: int,
    team_id: int = _team_dependency,
    current_user: User = _delete_record_permission,
    db: Session = _db_dependency
) -> None:
    try:
        record = payment_record_crud.get_by_id(db, record_id, team_id)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款记录不存在"
            )
        check_payment_view_permission(record.payment_plan_id, team_id, current_user, db)

        change = _build_payment_record_intelligence_change(
            db,
            record,
            change_type="deleted",
            actor_id=str(current_user.id),
        )
        success = payment_record_crud.delete(db, record_id, team_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款记录不存在"
            )
        await _trigger_payment_record_intelligence_refresh(
            db,
            change,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@router.get(
    "/payment-records",
    response_model=PaymentRecordListResponse[PaymentRecordListItem],
    summary="查询回款记录列表",
    description="支持按合同、计划、日期范围、金额、审批状态等条件筛选并分页查询回款记录。返回记录详情及关联的客户、商机、合同、回款阶段信息、审批信息、待我审批数量。可用于前端表格渲染和回款历史查询。",
)
def list_payment_records(
    contract_id: int | None = Query(None, description="合同ID筛选"),
    payment_plan_id: int | None = Query(None, description="回款计划ID筛选"),
    payment_date_start: date | None = _payment_date_start_query,
    payment_date_end: date | None = _payment_date_end_query,
    min_amount: float | None = Query(None, ge=0, description="最小回款金额"),
    actual_amount: float | None = Query(None, ge=0, description="回款金额"),
    creator_id: str | None = Query(None, description="登记人飞书ID"),
    keyword: str | None = Query(
        None, description="关键词\uff0c支持回款编号、客户、合同、阶段、付款方、发票抬头、负责人、团队成员"
    ),
    search: str | None = Query(
        None,
        description=(
            "统一搜索词\uff0c支持回款编号、阶段、客户全称/简称/别名、"
            "合同、付款方、负责人、团队成员、发票抬头"
        ),
    ),
    record_number: str | None = Query(None, description="回款编号"),
    record_number_exclude: str | None = Query(None, description="排除的回款编号关键词"),
    customer_name: str | None = Query(None, description="客户名称"),
    customer_name_exclude: str | None = Query(None, description="排除的客户名称关键词"),
    actual_payer_name: str | None = Query(None, description="实际付款方"),
    actual_payer_name_exclude: str | None = Query(None, description="排除的实际付款方关键词"),
    invoice_title_text: str | None = Query(None, description="发票抬头"),
    invoice_title_text_exclude: str | None = Query(None, description="排除的发票抬头关键词"),
    contract_name: str | None = Query(None, description="合同名称"),
    contract_name_exclude: str | None = Query(None, description="排除的合同名称关键词"),
    owner_name: str | None = Query(None, description="负责人姓名"),
    owner_name_exclude: str | None = Query(None, description="排除的负责人姓名关键词"),
    commission_member_name: str | None = Query(None, description="团队成员姓名"),
    commission_member_name_exclude: str | None = Query(None, description="排除的团队成员姓名关键词"),
    confirmation_status: str | None = Query(
        None, description="确认状态\uff1aPENDING, CONFIRMED, DISPUTED\uff0c多个值用逗号分隔"
    ),
    confirmation_status_exclude: str | None = Query(None, description="排除的确认状态\uff0c多个值用逗号分隔"),
    created_time_start: date | None = _created_time_start_query,
    created_time_end: date | None = _created_time_end_query,
    me: bool = Query(False, description="是否只查询当前用户登记的记录"),
    approval_status: str | None = Query(
        None,
        description=(
            "审批状态筛选: pending_submit(待提交), pending_approval(审批中), "
            "rejected(已驳回), approved(已通过)\uff0c多个值用逗号分隔"
        ),
    ),
    approval_status_exclude: str | None = Query(None, description="排除的审批状态\uff0c多个值用逗号分隔"),
    sort: str | None = Query(None, description="多字段排序\uff0c格式\uff1afield:asc,field2:desc"),
    order_by: str | None = Query(None, description="兼容旧版单字段排序"),
    order_dir: str | None = Query(None, description="兼容旧版排序方向\uff08asc/desc\uff09"),
    filters: str | None = Query(None, description="通用筛选条件 JSON"),
    sorts: str | None = Query(None, description="通用排序条件 JSON"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> dict[str, object]:
    """
    查询回款记录列表\uff08添加权限隔离\uff09

    权限逻辑\uff1a
    - payment:view:all → 可查看所有回款记录
    - payment:view:own → 只能查看自己登记的回款记录
    - 都没有 → 403 Forbidden
    """
    from app.crud.permission import permission_crud

    # 权限检查
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    has_view_all = "payment:view:all" in permission_codes
    has_view_own = "payment:view:own" in permission_codes

    if not has_view_all and not has_view_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有查看回款记录的权限"
        )

    skip = (page - 1) * page_size

    # 数据所有权隔离
    current_user_id = None
    if me or (has_view_own and not has_view_all):
        # 如果只有 view:own 权限,或者用户明确选择只看自己的数据
        current_user_id = str(current_user.id)

    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )

    try:
        records, total = run_or_400(lambda: payment_record_crud.list_records(
            db,
            team_id=team_id,
            skip=skip,
            limit=page_size,
            contract_id=contract_id,
            payment_plan_id=payment_plan_id,
            payment_date_start=payment_date_start,
            payment_date_end=payment_date_end,
            min_amount=min_amount,
            actual_amount=actual_amount,
            creator_id=creator_id,
            keyword=keyword,
            search=search,
            record_number=record_number,
            record_number_exclude=record_number_exclude,
            customer_name=customer_name,
            customer_name_exclude=customer_name_exclude,
            actual_payer_name=actual_payer_name,
            actual_payer_name_exclude=actual_payer_name_exclude,
            invoice_title_text=invoice_title_text,
            invoice_title_text_exclude=invoice_title_text_exclude,
            contract_name=contract_name,
            contract_name_exclude=contract_name_exclude,
            owner_name=owner_name,
            owner_name_exclude=owner_name_exclude,
            commission_member_name=commission_member_name,
            commission_member_name_exclude=commission_member_name_exclude,
            confirmation_status=confirmation_status,
            confirmation_status_exclude=confirmation_status_exclude,
            created_time_start=created_time_start,
            created_time_end=created_time_end,
            current_user_id=current_user_id,
            approval_status=approval_status,
            approval_status_exclude=approval_status_exclude,
            sort=sort,
            order_by=order_by,
            order_dir=order_dir,
            filters=parsed_filters,
            sorts=parsed_sorts,
        ))

        pending_approval_me_count = query_pending_approval_me(db, team_id, current_user.id)
        items = _build_payment_record_list_items(db, records, team_id)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "pending_approval_me_count": pending_approval_me_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询回款记录失败: {e!s}"
        ) from e


@router.post(
    "/payment-records/export",
    dependencies=[Depends(require_permission("payment:record:export"))],
    summary="导出回款记录列表",
    description="按当前筛选条件导出全部匹配回款记录为 Excel",
)
def export_payment_records(
    request: PaymentRecordListExportRequest,
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency,
) -> FileResponse:
    current_user_id = _payment_view_own_user_id(db, current_user, team_id)
    query = run_or_400(lambda: payment_record_crud.build_list_query(
        db,
        team_id=team_id,
        approval_status=PAYMENT_RECORD_TAB_APPROVAL_STATUS.get(request.tab),
        current_user_id=current_user_id,
        search=request.search,
        filters=request.filters,
        sorts=request.sorts,
    ))
    stream = query.enable_eagerloads(False).execution_options(stream_results=True).yield_per(500)
    rows = _iter_payment_record_export_rows(stream, team_id, projection_session_factory=SessionLocal)
    generated = run_list_export_or_400(lambda: create_list_export_file(
        catalog=PAYMENT_RECORDS_LIST_EXPORT_CATALOG,
        selected_keys=request.fields,
        rows=rows,
        file_stem=f"回款记录列表-{PAYMENT_RECORD_TAB_STEMS.get(request.tab, '全部记录')}",
    ))
    return list_export_file_response(generated)



@router.get(
    "/reminders/overdue",
    response_model=list[PaymentReminder],
    summary="查询逾期回款",
    description="获取所有逾期的回款计划\uff0c用于催收提醒",
)
def get_overdue_payments(
    team_id: int = _team_dependency,
    current_user: User = _user_dependency,
    db: Session = _db_dependency
) -> list[PaymentReminder]:
    del current_user  # Keep the authentication dependency for this route.
    plans = payment_plan_crud.get_overdue_payments(db, team_id)
    
    reminders = []
    for plan in plans:
        days_overdue = (date.today() - plan.due_date).days
        
        customer_name = None
        opportunity_name = None
        
        if hasattr(plan, 'contract') and plan.contract:
            if hasattr(plan.contract, 'customer') and plan.contract.customer:
                customer_name = plan.contract.customer.account_name
            if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                opportunity_name = plan.contract.opportunity.opportunity_name
        
        reminders.append(PaymentReminder(
            plan_id=plan.id,
            contract_name=plan.contract.contract_name,
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            due_date=plan.due_date,
            days_until_due=-days_overdue,
            contract_owner_id=plan.contract.creator_id,
            customer_name=customer_name,
            opportunity_name=opportunity_name
        ))

    return reminders


# ---------- B1: 回款审批提交 & 财务直确认 -----------------------------------
#
# 业务语义 sugar 端点(通用引擎 /v1/approvals/PAYMENT/{id}/submit 已可覆盖)。
# 本端点叠加 payment:submit 权限码;未匹配审批流程时统一报错并提示管理员配置。


@router.post(
    "/records/{record_id}/submit-approval",
    response_model=None,
    summary="提交回款审批",
    description=(
        "为指定回款记录提交审批。系统按回款金额匹配审批流程\uff0c审批通过后自动确认入账。"
        "权限码\uff1apayment:submit。"
    ),
)
def submit_payment_approval(
    record_id: int,
    team_id: int = _team_dependency,
    current_user: User = _submit_payment_permission,
    db: Session = _db_dependency,
) -> dict[str, object]:
    """
    提交回款审批\uff08统一走审批流程\uff09

    所有回款必须走审批流程\uff0c审批通过后自动确认入账\uff08confirmation_status=CONFIRMED\uff09。
    """
    record = payment_record_crud.get_by_id(db, record_id, team_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回款记录不存在")
    check_payment_view_permission(record.payment_plan_id, team_id, current_user, db)

    approval, error_msg = approval_transaction_manager.submit_for_approval(
        db=db,
        business_type=BusinessType.PAYMENT,
        entity_id=record.id,
        team_id=team_id,
        submitter_id=str(current_user.id),
        submitter_name=current_user.name,
    )
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "提交回款审批失败",
        )

    return {
        "approval_id": approval.id,
        "status": approval.status,
        "message": "回款审批已提交" if error_msg is None else "回款审批已在处理中",
    }

# ========== 已废弃:财务直接确认 API(统一走审批流程)==========
# 所有回款必须走审批流程,审批通过后自动确认入账。
# 此 API 已废弃,保留仅用于向后兼容,请勿使用。
#
# @router.post(
#     "/records/{record_id}/confirm",
#     response_model=PaymentRecordWithConfirmation,
#     summary="[已废弃] 财务确认回款入账",
#     description="已废弃:所有回款统一走审批流程,审批通过后自动确认入账。请使用审批中心进行审批操作。",
#     deprecated=True,
# )
# def confirm_payment_record(...):
#     pass
