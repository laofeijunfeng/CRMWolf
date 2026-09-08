import logging
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.invoices import _invoice_title_response, _populate_application_info
from app.core.database import get_db
from app.core.deps import (
    check_customer_delete_permission,
    check_customer_edit_permission,
    check_customer_member_manage_permission,
    check_customer_view_permission,
    get_current_active_user,
    get_current_user_team,
    require_permission,
)
from app.core.list_query import (
    enforce_owner_view_scope,
    optional_request_list_query,
    run_or_400,
    uses_unified_list_query,
)
from app.crud.contract import contract_crud
from app.crud.customer import contact_crud, customer_crud
from app.crud.customer_member import customer_member_crud
from app.crud.invoice import invoice_application_crud, invoice_title_crud
from app.crud.lead import lead_crud
from app.crud.team import team_crud
from app.crud.user import user_crud
from app.models.command_execution import CommandExecutionStatus
from app.models.customer import Contact
from app.schemas.common import PaginatedResponse
from app.schemas.command import CommandEffect, CommandNextAction, CommandResource
from app.schemas.contract import ContractListResponse, ContractStatusEnum
from app.schemas.customer import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    ConvertLeadToCustomer,
    ConvertResponse,
    CustomerAssignRequest,
    CustomerAssignResponse,
    CustomerAssignmentResult,
    CustomerAssignmentPreviewResponse,
    CustomerTransferScope,
    CustomerClaimRequest,
    CustomerCreate,
    CustomerDetailResponse,
    CustomerIdentityResolutionResponse,
    CustomerIndustryOption,
    CustomerIntelligenceBatchRebuildRequest,
    CustomerIntelligenceBatchRebuildResponse,
    CustomerIntelligenceRegenerateRequest,
    CustomerIntelligenceRetryDueResponse,
    CustomerIntelligenceRunDiagnosticListResponse,
    CustomerIntelligenceRunDiagnosticResponse,
    CustomerListResponse,
    CustomerLoseRequest,
    CustomerMemberCandidate,
    CustomerMemberCreate,
    CustomerMemberResponse,
    CustomerMemberUpdate,
    CustomerMemberUserInfo,
    CustomerResponse,
    CustomerReturnRequest,
    CustomerReturnResponse,
    CustomerStatusUpdate,
    CustomerUpdate,
    MessageResponse,
    StatisticsResponse,
    TrendResponse,
)
from app.schemas.invoice import InvoiceApplicationResponse, InvoiceTitleResponse
from app.schemas.payment import PaymentPlanResponse
from app.services.operation_log_service import operation_log_service
from app.services.command_execution_service import (
    CommandAlreadyInProgress,
    CommandIdempotencyConflict,
    CommandOperationConflict,
    command_execution_service,
    request_fingerprint,
)
from app.services.acquisition_source_service import (
    AcquisitionSourceError,
    build_source_info,
    get_by_id,
    map_sources_by_ids,
    resolve_public_ids_to_ids,
)
from app.services.customer_identity_resolution_application_service import (
    customer_identity_resolution_application_service,
)
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeType,
    CustomerBusinessObjectSourceType,
    customer_business_object_intelligence_service,
)
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
    customer_intelligence_refresh_service,
)
from app.services.customer_intelligence_run_service import CustomerIntelligenceRunDiagnostic
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.services.outbound_notification_job_service import outbound_notification_job_service

router = APIRouter(prefix="/v1/customers", tags=["客户管理"])
logger = logging.getLogger(__name__)


def _queue_customer_returned_notification(
    db: Session,
    *,
    team_id: int,
    customer,
    previous_owner,
    return_reason: str,
    actor_id: str,
) -> None:
    outbound_notification_job_service.queue_committed(
        db,
        team_id=team_id,
        event_type=OutboundNotificationEventType.CUSTOMER_RETURNED,
        business_type="CUSTOMER",
        business_id=int(customer.id),
        recipient_user_ids=[previous_owner],
        actor_id=actor_id,
        payload_json={
            "account_name": customer.account_name,
            "return_reason": return_reason,
            "previous_owner": previous_owner,
        },
    )


def _customer_name_conflict_error(
    db: Session,
    account_name: str,
    team_id: int,
    exclude_customer_id: Optional[int] = None,
    allowed_source_lead_id: Optional[int] = None,
) -> Optional[str]:
    existing_customer = customer_crud.get_by_name(db, account_name, team_id)
    if existing_customer and existing_customer.id != exclude_customer_id:
        return "客户名称已存在"
    existing_lead = lead_crud.get_by_name(db, account_name, team_id)
    excluded_customer = customer_crud.get_by_id(db, exclude_customer_id, team_id) if exclude_customer_id else None
    if existing_lead and existing_lead.id != allowed_source_lead_id and not (
        excluded_customer and excluded_customer.source_lead_id == existing_lead.id
    ):
        return "该名称已存在线索，请先处理或转化线索"
    return None


def _ensure_customer_name_available(
    db: Session,
    account_name: str,
    team_id: int,
    exclude_customer_id: Optional[int] = None,
    allowed_source_lead_id: Optional[int] = None,
) -> None:
    error = _customer_name_conflict_error(
        db,
        account_name,
        team_id,
        exclude_customer_id=exclude_customer_id,
        allowed_source_lead_id=allowed_source_lead_id,
    )
    if error:
        logger.warning(
            "客户名称校验失败: team_id=%s account_name=%s reason=%s",
            team_id,
            account_name,
            error,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )


def _raise_source_error(exc: AcquisitionSourceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_optional_header_text(value: object) -> Optional[str]:
    """Normalize FastAPI Header defaults for both HTTP and direct function calls."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_header_int(value: object) -> Optional[int]:
    """Normalize an optional integer header without leaking FastAPI markers."""
    return value if isinstance(value, int) else None


def _customer_source_fields(db: Session, customer, source_map: Optional[dict] = None) -> dict:
    source_row = None
    if customer.source_id:
        if source_map is not None:
            source_row = source_map.get(int(customer.source_id))
        else:
            source_row = get_by_id(db, customer.source_id, customer.team_id)
    current_name = source_row.name if source_row else customer.source
    return {
        "source": current_name,
        "source_info": build_source_info(source_row),
    }


def _get_customer_or_404(db: Session, customer_public_id: str, team_id: int):
    customer = customer_crud.get_by_public_id(db, customer_public_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户不存在"
        )
    return customer


def _get_viewable_customer(db: Session, customer_public_id: str, team_id: int, current_user):
    return check_customer_view_permission(customer_public_id, team_id, current_user, db)


def _get_editable_customer(db: Session, customer_public_id: str, team_id: int, current_user):
    return check_customer_edit_permission(customer_public_id, team_id, current_user, db)


def _persist_customer_business_object_refresh_after_commit(
    *,
    business_object: object,
    source_type: CustomerBusinessObjectSourceType,
    actor_id: str | None,
    change_type: CustomerBusinessObjectChangeType = "updated",
    summary: str | None = None,
    payload: dict | None = None,
    scope: Literal["full", "partial"] = "partial",
) -> CustomerIntelligenceCommittedEventRequest | None:
    """Register a committed change through the shared object registry.

    CRUD endpoints only provide the changed domain object and an optional
    business-specific delta.  Source identity, default payload, event key and
    trigger type stay in CustomerBusinessObjectIntelligenceService.
    """

    return customer_business_object_intelligence_service.enqueue_object_change_refresh_after_commit(
        source_type=source_type,
        business_object=business_object,
        change_type=change_type,
        actor_id=actor_id,
        summary=summary,
        payload=payload,
        scope=scope,
    )


def _get_user_basic_info(db: Session, user_id: Optional[str]) -> Optional[dict]:
    if not user_id:
        return None

    user_data = db.execute(text("""
        SELECT id, name, email, mobile, avatar_url
        FROM users
        WHERE id = CAST(:user_id AS SIGNED)
    """), {"user_id": user_id}).first()

    if not user_data:
        return None

    return {
        "id": str(user_data[0]),
        "name": user_data[1],
        "email": user_data[2],
        "mobile": user_data[3],
        "avatar_url": user_data[4],
    }


def _contract_response_base(contract) -> dict:
    if not getattr(contract, "customer", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="合同关联客户数据异常",
        )
    opportunity = getattr(contract, "opportunity", None)
    return {
        "id": contract.id,
        "contract_number": contract.contract_number,
        "contract_name": contract.contract_name,
        "customer_id": contract.customer.public_id,
        "opportunity_id": opportunity.public_id if opportunity else None,
        "signing_contact_id": contract.signing_contact_id,
        "user_count": contract.user_count,
        "total_amount": contract.total_amount,
        "license_type": contract.license_type,
        "subscription_years": contract.subscription_years,
        "standard_unit_price": contract.standard_unit_price,
        "status": contract.status,
        "signing_date": contract.signing_date,
        "effective_date": contract.effective_date,
        "expiry_date": contract.expiry_date,
        "owner_id": contract.owner_id,
        "creator_id": contract.creator_id,
        "created_time": contract.created_time,
        "last_modified_time": contract.last_modified_time,
        "contract_file_path": contract.contract_file_path,
        "contract_file_name": contract.contract_file_name,
        "contract_file_size": contract.contract_file_size,
        "contract_file_mime_type": contract.contract_file_mime_type,
    }


def _contract_status_info(status_value) -> Optional[dict]:
    if not status_value:
        return None

    raw_status = status_value.value if hasattr(status_value, "value") else status_value
    try:
        status_enum = ContractStatusEnum(raw_status)
    except ValueError:
        return None

    return {
        "code": status_enum.value,
        "name": status_enum.description,
    }


def _contact_response(contact: Contact, customer_public_id: str) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        customer_id=customer_public_id,
        name=contact.name,
        gender=contact.gender,
        position=contact.position,
        is_decision_maker=bool(contact.is_decision_maker),
        mobile=contact.mobile,
        email=contact.email,
        wechat_id=contact.wechat_id,
        remark=contact.remark,
        reports_to=contact.reports_to,
        is_primary=bool(contact.is_primary),
        created_time=contact.created_time,
    )


def _customer_response(db: Session, customer) -> CustomerResponse:
    source_lead_public_id = None
    if customer.source_lead_id:
        source_lead = lead_crud.get_by_id(db, customer.source_lead_id, customer.team_id)
        source_lead_public_id = source_lead.public_id if source_lead else None

    return CustomerResponse(**{
        "id": customer.public_id,
        "public_id": customer.public_id,
        "account_name": customer.account_name,
        "industry": customer.industry,
        "city": customer.city,
        "address": customer.address,
        "company_scale": customer.company_scale,
        **_customer_source_fields(db, customer),
        "status": customer.status,
        "owner_id": customer.owner_id,
        "source_lead_id": source_lead_public_id,
        "default_procurement_method_id": customer.default_procurement_method_id,
        "loss_reason": customer.loss_reason,
        "return_reason": customer.return_reason,
        "returned_time": customer.returned_time,
        "creator_id": customer.creator_id,
        "created_time": customer.created_time,
        "last_modified_time": customer.last_modified_time,
        "version": customer.version,
        "license_expiry_date": customer.license_expiry_date,
        "license_type": customer.license_type,
    })


def _customer_intelligence_run_response(
    db: Session,
    team_id: int,
    diagnostic: CustomerIntelligenceRunDiagnostic,
) -> CustomerIntelligenceRunDiagnosticResponse:
    result_summary = dict(diagnostic.result)
    result_summary.pop("route", None)
    customer = customer_crud.get_by_id(db, diagnostic.customer_id, team_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="客户智能任务关联客户数据异常",
        )
    return CustomerIntelligenceRunDiagnosticResponse(
        id=diagnostic.id,
        request_id=diagnostic.request_id,
        customer_id=customer.public_id,
        actor_id=diagnostic.actor_id,
        trigger_type=diagnostic.trigger_type,
        scope=diagnostic.scope,
        status=diagnostic.status,
        attempt_count=diagnostic.attempt_count,
        max_attempts=diagnostic.max_attempts,
        route_label=_customer_intelligence_route_label(diagnostic.route),
        result=result_summary,
        visible_trace=diagnostic.visible_trace,
        trace_events=diagnostic.trace_events,
        error_message=diagnostic.error_message,
        created_time=diagnostic.created_time,
        started_time=diagnostic.started_time,
        finished_time=diagnostic.finished_time,
        next_retry_at=diagnostic.next_retry_at,
        last_duration_ms=diagnostic.last_duration_ms,
    )


def _customer_intelligence_route_label(route: str | None) -> Optional[str]:
    if route == "refresh_profile":
        return "刷新客户档案"
    if route == "answer_customer_question":
        return "回答客户问题"
    return None


@router.get("/industries", response_model=List[CustomerIndustryOption], summary="获取客户所属行业选项", description="""
获取客户所属行业的下拉选项列表（用于客户创建、编辑等场景）。

**业务规则：**
- 返回预定义的行业枚举列表
- 轻量级接口，无需查询数据库
- 通过枚举实现数据统一管理
""")
def get_customer_industries(
    current_user = Depends(get_current_active_user)
):
    from app.models.customer import CustomerIndustry
    
    industries = []
    for industry in CustomerIndustry:
        industries.append(CustomerIndustryOption(
            value=industry.name,
            label=industry.value
        ))
    return industries


@router.post(
    "/convert-from-lead",
    response_model=ConvertResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="线索转化",
    description="根据线索ID原子转化客户和主联系人；AI/Agent 不属于本命令边界。",
)
async def convert_from_lead(
    data: ConvertLeadToCustomer,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
    operation_id: Optional[str] = Header(None, alias="X-Operation-Id"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
) -> ConvertResponse:
    """Atomically convert a lead into a customer and expose a durable outcome.

    The legacy response shape is retained when callers do not send command
    headers. New clients should always send both operation and idempotency
    identifiers so a timeout can be resolved without replaying the conversion.
    """
    if operation_id is not None:
        operation_id = operation_id.strip()
        if not operation_id or len(operation_id) > 64:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Operation-Id 必须为 1-64 个字符")
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key 必须为 1-128 个字符")
    if correlation_id is not None:
        correlation_id = correlation_id.strip() or None

    modern_command = operation_id is not None or idempotency_key is not None
    if not modern_command:
        source_lead = lead_crud.get_by_public_id(db, data.lead_id, team_id)
        if not source_lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="线索不存在")

        # Migration compatibility for old clients and scripts: retain the
        # historical payload while using the same atomic domain conversion.
        try:
            _ensure_customer_name_available(
                db,
                data.account_name or source_lead.lead_name,
                team_id,
                allowed_source_lead_id=source_lead.id,
            )
            customer, contact = customer_crud.convert_from_lead(
                db=db,
                lead_id=source_lead.id,
                account_name=data.account_name,
                address=data.address,
                default_procurement_method_id=data.default_procurement_method_id,
                contact_name=data.contact_name,
                contact_phone=data.contact_phone,
                industry=data.industry,
                creator_id=str(current_user.id),
                operator_name=current_user.name,
                team_id=team_id,
                commit=True,
            )
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="客户或联系人数据已被其他操作占用") from exc
        try:
            customer_business_object_intelligence_service.enqueue_customer_lifecycle_refresh_after_commit(
                customer=customer,
                actor_id=str(current_user.id),
                trigger_type="customer_converted_from_lead",
                source_lead_id=source_lead.id,
            )
        except Exception:
            logger.exception("线索转客户后的客户智能刷新调度失败")
        outbound_notification_job_service.queue_committed(
            db,
            team_id=team_id,
            event_type=OutboundNotificationEventType.ACCOUNT_CREATED,
            business_type="CUSTOMER",
            business_id=int(customer.id),
            recipient_user_ids=[customer.owner_id],
            actor_id=str(current_user.id),
            payload_json={
                "account_name": customer.account_name,
                "contact_name": contact.name,
            },
        )
        return ConvertResponse(
            customer_id=customer.public_id,
            contact_id=contact.id,
            message="转化成功，客户智能档案正在整理",
        )

    fingerprint = request_fingerprint({
        "lead_id": data.lead_id,
        "account_name": data.account_name,
        "address": data.address,
        "default_procurement_method_id": data.default_procurement_method_id,
        "contact_name": data.contact_name,
        "contact_phone": data.contact_phone,
        "industry": data.industry,
    })
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=str(current_user.id),
            command_type="LEAD_CONVERT_TO_CUSTOMER",
            resource_type="LEAD",
            resource_public_id=data.lead_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
    except CommandIdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommandAlreadyInProgress as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"operation_id": str(exc), "message": "转化正在处理中，请查询操作结果"},
        ) from exc
    except CommandOperationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if replay:
        db.rollback()
        payload = command_execution_service.to_response_payload(execution)
        stored_data = payload.get("data")
        if isinstance(stored_data, dict):
            return ConvertResponse(
                **payload,
                customer_id=stored_data.get("customer_id"),
                contact_id=stored_data.get("contact_id"),
                message=stored_data.get("message"),
            )
        return ConvertResponse(**payload)

    # Resolve the source only after the durable command record exists. This
    # makes a terminal idempotent replay independent of the current lead row
    # and gives a failed first attempt an operation id that can be audited.
    source_lead = lead_crud.get_by_public_id(db, data.lead_id, team_id)
    if not source_lead:
        try:
            command_execution_service.fail(
                db,
                execution,
                error_code="LEAD_NOT_FOUND",
                error_message="线索不存在",
                retryable=False,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "LEAD_NOT_FOUND",
                "message": "线索不存在",
                "operation_id": execution.operation_id,
            },
        )

    try:
        _ensure_customer_name_available(
            db,
            data.account_name or source_lead.lead_name,
            team_id,
            allowed_source_lead_id=source_lead.id,
        )
        customer, contact = customer_crud.convert_from_lead(
            db=db,
            lead_id=source_lead.id,
            account_name=data.account_name,
            address=data.address,
            default_procurement_method_id=data.default_procurement_method_id,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            industry=data.industry,
            creator_id=str(current_user.id),
            operator_name=current_user.name,
            team_id=team_id,
            commit=False,
        )
        db.flush()

        result_data = {
            "lead_id": source_lead.public_id,
            "converted_lead_id": source_lead.public_id,
            "customer_id": customer.public_id,
            "customer_public_id": customer.public_id,
            "contact_id": contact.id,
            "contact_public_id": None,
            "message": "转化成功，客户智能档案正在整理",
            "created_customer": True,
            "created_contact": True,
            "inherited_fields": ["lead_name", "city", "company_scale", "source", "owner_id", "contact_name", "contact_phone", "follow_ups", "operation_logs"],
            "source_relation": {
                "lead_public_id": source_lead.public_id,
                "customer_public_id": customer.public_id,
                "relation": "CONVERTED_FROM_LEAD",
            },
            "warnings": [],
        }
        command_execution_service.succeed(
            db,
            execution,
            data=result_data,
            resource=CommandResource(type="CUSTOMER", public_id=customer.public_id, version=customer.version),
            effects=[
                CommandEffect(type="LEAD", public_id=source_lead.public_id, status="SYNCED"),
                CommandEffect(type="CUSTOMER", public_id=customer.public_id, status="SYNCED"),
                CommandEffect(type="CONTACT", public_id=None, status="SYNCED", detail="主联系人使用兼容内部ID"),
            ],
            next_actions=[
                CommandNextAction(id="view-customer", label="查看客户", kind="view-detail"),
            ],
            correlation_id=correlation_id,
        )
        db.commit()
        db.refresh(customer)
        db.refresh(contact)
    except ValueError as exc:
        db.rollback()
        try:
            failed_execution, failed_replay = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="LEAD_CONVERT_TO_CUSTOMER",
                resource_type="LEAD",
                resource_public_id=data.lead_id,
                operation_id=execution.operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            if not failed_replay:
                command_execution_service.fail(
                    db,
                    failed_execution,
                    error_code="LEAD_CONVERSION_REJECTED",
                    error_message=str(exc),
                    retryable=False,
                )
                db.commit()
        except Exception:
            db.rollback()
        if modern_command:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "LEAD_CONVERSION_REJECTED", "message": str(exc), "operation_id": execution.operation_id}) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        try:
            failed_execution, failed_replay = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="LEAD_CONVERT_TO_CUSTOMER",
                resource_type="LEAD",
                resource_public_id=data.lead_id,
                operation_id=execution.operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            if not failed_replay:
                command_execution_service.fail(db, failed_execution, error_code="LEAD_CONVERSION_CONFLICT", error_message="客户或联系人数据已被其他操作占用", retryable=True)
                db.commit()
        except Exception:
            db.rollback()
        if modern_command:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "LEAD_CONVERSION_CONFLICT", "message": "客户或联系人数据已被其他操作占用", "operation_id": execution.operation_id}) from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="客户或联系人数据已被其他操作占用") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("线索转客户提交失败", extra={"operation_id": execution.operation_id})
        if modern_command:
            # The transaction may have failed before commit, but a commit
            # failure can also leave the client unable to know whether the
            # business fact was persisted. Keep a durable UNKNOWN outcome when
            # the database is available so the client can query instead of
            # replaying the conversion.
            try:
                unknown_execution, unknown_replay = command_execution_service.begin(
                    db,
                    team_id=team_id,
                    actor_id=str(current_user.id),
                    command_type="LEAD_CONVERT_TO_CUSTOMER",
                    resource_type="LEAD",
                    resource_public_id=data.lead_id,
                    operation_id=execution.operation_id,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    correlation_id=correlation_id,
                )
                if not unknown_replay:
                    command_execution_service.fail(
                        db,
                        unknown_execution,
                        status=CommandExecutionStatus.UNKNOWN,
                        error_code="LEAD_CONVERSION_UNKNOWN",
                        error_message="转化结果暂未确认，请查询操作结果",
                        retryable=False,
                    )
                    db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail={
                    "code": "LEAD_CONVERSION_UNKNOWN",
                    "message": "转化结果暂未确认，请查询操作结果",
                    "operation_id": execution.operation_id,
                },
            ) from exc
        raise

    # Notifications and intelligence refresh are post-commit side effects. A
    # failure here must not turn a committed customer conversion into a false
    # failure response.
    warnings: list[str] = []
    try:
        db.refresh(customer)
        customer_business_object_intelligence_service.enqueue_customer_lifecycle_refresh_after_commit(
            customer=customer,
            actor_id=str(current_user.id),
            trigger_type="customer_converted_from_lead",
            source_lead_id=source_lead.id,
        )
    except Exception:
        logger.exception("线索转客户后的客户智能刷新调度失败", extra={"operation_id": execution.operation_id})
        warnings.append("客户智能档案将在后台补偿整理")
    queued = outbound_notification_job_service.queue_committed(
        db,
        team_id=team_id,
        event_type=OutboundNotificationEventType.ACCOUNT_CREATED,
        business_type="CUSTOMER",
        business_id=int(customer.id),
        recipient_user_ids=[customer.owner_id],
        actor_id=str(current_user.id),
        payload_json={
            "account_name": customer.account_name,
            "contact_name": contact.name,
        },
    )
    if queued is None:
        warnings.append("飞书通知排队失败，可在操作记录中查看转化结果")

    warning_data: Optional[dict] = None
    if warnings:
        # Keep the business fact successful; only enrich the stored display data.
        # A failure while persisting this optional metadata must not turn an
        # already committed conversion into a false 5xx result.
        stored_result = execution.result_json.get("data") if isinstance(execution.result_json, dict) else None
        if isinstance(stored_result, dict):
            warning_data = {**stored_result, "warnings": warnings}
            execution.result_json["data"] = warning_data
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("线索转客户结果提示保存失败", extra={"operation_id": execution.operation_id})

    payload = command_execution_service.to_response_payload(execution)
    if warning_data is not None:
        payload["data"] = warning_data
    stored_data = payload.get("data")
    if isinstance(stored_data, dict):
        payload.update(
            customer_id=stored_data.get("customer_id"),
            contact_id=stored_data.get("contact_id"),
            message=stored_data.get("message"),
        )
    return ConvertResponse(**payload)


@router.get(
    "/{customer_id}/assignment-preview",
    response_model=CustomerAssignmentPreviewResponse,
    summary="预览客户移交影响范围",
    description="只读计算客户移交将影响的商机、合同及不可同步的锁定合同，不修改任何业务事实。",
)
def preview_customer_assignment(
    customer_id: str,
    transfer_scope: CustomerTransferScope = Query(CustomerTransferScope.CUSTOMER_ONLY),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> CustomerAssignmentPreviewResponse:
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    legacy_scope, _ = CustomerAssignRequest(
        owner_id="preview", transfer_scope=transfer_scope
    ).normalized_transfer_scope()
    preview = customer_crud.get_assignment_preview(
        db, customer, team_id, legacy_scope
    )
    return CustomerAssignmentPreviewResponse(
        customer_id=customer.public_id,
        customer_version=customer.version,
        transfer_scope=transfer_scope,
        opportunity_count=int(preview["opportunity_count"]),
        contract_count=int(preview["contract_count"]),
        locked_contract_count=int(preview["locked_contract_count"]),
        locked_contracts=preview["locked_contracts"],
    )


@router.get("/{customer_id}/contracts", response_model=List[ContractListResponse], summary="获取客户合同列表", description="""
获取指定客户的所有合同，支持按状态筛选和分页查询。

**功能说明：**
- 查询客户的所有合同
- 支持按合同状态筛选
- 支持分页查询
- 返回合同详细信息

**业务场景：**
- 查看客户的合同历史
- 了解客户的合同状态
- 客户详情页展示合同列表

**路径参数：**
- customer_id: 客户对外ID

**查询参数：**
- status: 合同状态筛选（可选）
- skip: 分页跳过记录数（默认0）
- limit: 每页记录数（默认20，最大100）

**返回字段：**
- 合同基本信息：ID、名称、编号、金额等
- 客户信息：客户名称
- 商机信息：商机名称
- 负责人信息：负责人姓名
""")
def get_customer_contracts(
    customer_id: str,
    status: Optional[str] = Query(None, description="合同状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.contract import ContractStatus

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    internal_customer_id = customer.id

    contracts, total = contract_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        customer_id=internal_customer_id,
        status=ContractStatus[status] if status else None
    )

    result = []
    for contract in contracts:
        opportunity_info = None
        if contract.opportunity_id:
            opportunity_data = db.execute(text("""
                SELECT public_id, opportunity_name
                FROM crm_opportunities
                WHERE id = :opportunity_id
            """), {"opportunity_id": contract.opportunity_id}).first()

            if opportunity_data:
                opportunity_info = {
                    "id": opportunity_data[0],
                    "opportunity_name": opportunity_data[1],
                }

        contract_dict = _contract_response_base(contract)
        contract_dict.update({
            "customer_info": {
                "id": customer.public_id,
                "public_id": customer.public_id,
                "account_name": customer.account_name,
            },
            "opportunity_info": opportunity_info,
            "owner_info": _get_user_basic_info(db, contract.owner_id),
            "creator_info": _get_user_basic_info(db, contract.creator_id),
            "status_info": _contract_status_info(contract.status),
        })

        result.append(ContractListResponse(**contract_dict))

    return result


@router.get("/{customer_id}/payment-plans", response_model=List[PaymentPlanResponse], summary="获取客户回款计划列表", description="""
获取指定客户的所有回款计划，支持按状态筛选和分页查询。

**功能说明：**
- 查询客户的所有回款计划
- 支持按回款状态筛选
- 支持分页查询
- 返回回款计划详细信息

**业务场景：**
- 查看客户的回款计划
- 了解客户的回款进度
- 客户详情页展示回款计划

**路径参数：**
- customer_id: 客户对外ID

**查询参数：**
- status: 回款状态筛选（可选）：PENDING待回款、OVERDUE已逾期、PARTIAL部分回款、COMPLETED已登记
- skip: 分页跳过记录数（默认0）
- limit: 每页记录数（默认20，最大100）

**返回字段：**
- 回款计划基本信息：ID、阶段名称、计划金额、计划日期等
- 已回款金额：paid_amount
- 待回款金额：remaining_amount
- 回款记录列表：payment_records
- 合同信息：contract_name
- 客户信息：customer_name、opportunity_name
""")
def get_customer_payment_plans(
    customer_id: str,
    status: Optional[str] = Query(None, description="回款状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.payment import PaymentPlanStatus

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    internal_customer_id = customer.id
    
    status_map = {
        PaymentPlanStatus.PENDING: "待回款",
        PaymentPlanStatus.OVERDUE: "已逾期",
        PaymentPlanStatus.PARTIAL: "部分回款",
        PaymentPlanStatus.COMPLETED: "已登记"
    }
    
    from sqlalchemy import text
    
    plans_query = text("""
        SELECT
            p.*,
            c.contract_name AS contract_name,
            c.contract_number AS contract_number,
            c.customer_id AS customer_id,
            c.opportunity_id AS opportunity_id,
            o.opportunity_name AS opportunity_name,
            c.owner_id AS owner_id,
            c.creator_id AS creator_id
        FROM crm_contract_payment_plans p
        JOIN crm_contracts c ON p.contract_id = c.id
        LEFT JOIN crm_opportunities o ON c.opportunity_id = o.id
        WHERE c.customer_id = :customer_id
          AND p.team_id = :team_id
          AND c.team_id = :team_id
          AND c.deleted_at IS NULL
        ORDER BY p.due_date ASC, p.id DESC
    """)
    if status:
        plans_query = text("""
            SELECT
                p.*,
                c.contract_name AS contract_name,
                c.contract_number AS contract_number,
                c.customer_id AS customer_id,
                c.opportunity_id AS opportunity_id,
                o.opportunity_name AS opportunity_name,
                c.owner_id AS owner_id,
                c.creator_id AS creator_id
            FROM crm_contract_payment_plans p
            JOIN crm_contracts c ON p.contract_id = c.id
            LEFT JOIN crm_opportunities o ON c.opportunity_id = o.id
            WHERE c.customer_id = :customer_id
              AND p.team_id = :team_id
              AND c.team_id = :team_id
              AND c.deleted_at IS NULL
              AND p.status = :status
            ORDER BY p.due_date ASC, p.id DESC
        """)
    
    plans_result = db.execute(
        plans_query,
        {"customer_id": internal_customer_id, "team_id": team_id, "status": status}
    ).fetchall()
    
    plans = []
    for row in plans_result:
        plan_dict = dict(row._mapping)
        
        paid_amount = 0.0
        payment_records = []
        
        records_query = text("""
            SELECT * FROM crm_payment_records
            WHERE payment_plan_id = :plan_id
            ORDER BY payment_date DESC
        """)
        records_result = db.execute(records_query, {"plan_id": plan_dict['id']}).fetchall()
        
        for record_row in records_result:
            record_dict = dict(record_row._mapping)
            payment_records.append(record_dict)
            if record_dict.get('approval_phase') == 'approved':
                paid_amount += float(record_dict['actual_amount'])
        
        plan_dict['paid_amount'] = paid_amount
        plan_dict['remaining_amount'] = float(plan_dict['planned_amount']) - paid_amount
        plan_dict['payment_records'] = payment_records
        plan_dict['contract_name'] = plan_dict.get('contract_name')
        plan_dict['customer_id'] = customer.public_id
        plan_dict['customer_name'] = customer.account_name
        plan_dict['opportunity_name'] = plan_dict.get('opportunity_name')
        plan_dict['status_name'] = status_map.get(plan_dict['status'], plan_dict['status'])
        
        invoice_query = text("""
            SELECT COUNT(*) as count, COALESCE(SUM(invoice_amount), 0) as total_amount
            FROM crm_invoice_applications
            WHERE payment_plan_id = :plan_id AND status != 'DRAFT'
        """)
        invoice_result = db.execute(invoice_query, {"plan_id": plan_dict['id']}).first()
        plan_dict['is_invoiced'] = invoice_result.count > 0
        plan_dict['invoice_count'] = invoice_result.count
        plan_dict['invoiced_amount'] = float(invoice_result.total_amount) if invoice_result.total_amount else 0.0
        
        plans.append(plan_dict)
    
    if skip:
        plans = plans[skip:]
    if limit:
        plans = plans[:limit]
    
    return plans


@router.get("/{customer_id}/invoices", response_model=List[InvoiceApplicationResponse], summary="获取客户发票列表", description="""
获取指定客户的所有发票申请，支持按状态筛选和分页查询。

**功能说明：**
- 查询客户的所有发票申请
- 支持按发票状态筛选
- 支持分页查询
- 返回发票申请详细信息

**业务场景：**
- 查看客户的发票申请
- 了解客户的发票进度
- 客户详情页展示发票列表

**路径参数：**
- customer_id: 客户对外ID

**查询参数：**
- status: 发票状态筛选（可选）
- skip: 分页跳过记录数（默认0）
- limit: 每页记录数（默认20，最大100）

**返回字段：**
- 发票申请基本信息：ID、申请编号、发票类型、金额等
- 关联合同信息：contract_name、contract_number
- 回款计划信息：stage_name、planned_amount
- 申请人信息：applicant_name
- 审批状态：status、approval_status
""")
def get_customer_invoices(
    customer_id: str,
    status: Optional[str] = Query(None, description="发票状态筛选"),
    skip: int = Query(0, ge=0, description="分页跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    invoices, total = invoice_application_crud.list_applications(
        db=db,
        team_id=team_id,
        customer_id=customer.id,
        status=status,
        skip=skip,
        limit=limit
    )
    
    populated_invoices = []
    for invoice in invoices:
        if hasattr(invoice, 'contract') and invoice.contract:
            invoice.contract_name = invoice.contract.contract_name
            invoice.contract_number = invoice.contract.contract_number
        if hasattr(invoice, 'payment_plan') and invoice.payment_plan:
            invoice.stage_name = invoice.payment_plan.stage_name
            invoice.planned_amount = float(invoice.payment_plan.planned_amount)
        if hasattr(invoice, 'applicant') and invoice.applicant:
            invoice.applicant_name = invoice.applicant.name
        populated_invoices.append(_populate_application_info(db, invoice, team_id))
    
    return populated_invoices


@router.get("/{customer_id}/invoice-titles", response_model=List[InvoiceTitleResponse], summary="获取客户发票抬头列表", description="""
获取指定客户的所有发票抬头。

**功能说明：**
- 查询客户的所有发票抬头
- 默认抬头排在前面
- 返回抬头详细信息

**业务场景：**
- 查看客户的发票抬头
- 创建发票时选择抬头
- 客户详情页展示抬头列表

**路径参数：**
- customer_id: 客户对外ID

**返回字段：**
- 抬头基本信息：ID、抬头名称、纳税人识别号
- 抬头类型：COMPANY(单位)、PERSONAL(个人)
- 账户信息：开户行、开户账号
- 联系信息：地址、电话
- 默认标识：is_default
""")
def get_customer_invoice_titles(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    invoice_titles = invoice_title_crud.get_by_customer_id(db, customer.id, team_id)
    return [_invoice_title_response(db, invoice_title, team_id) for invoice_title in invoice_titles]


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, summary="创建客户", description="手动创建客户，AI自动生成档案")
async def create_customer(
    customer: CustomerCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    _ensure_customer_name_available(db, customer.account_name, team_id)

    try:
        new_customer = customer_crud.create(
            db=db,
            obj_in=customer,
            creator_id=str(current_user.id),
            team_id=team_id,
            operator_name=current_user.name
        )
    except AcquisitionSourceError as exc:
        _raise_source_error(exc)
    if customer.primary_contact:
        contact_crud.create(
            db=db,
            obj_in=customer.primary_contact,
            customer_id=new_customer.id,
            team_id=team_id,
            is_primary=True
        )

    # 客户创建完成后，通过统一业务对象事件边界进入档案投影流水线。
    # 这里使用 full scope，确保企业基础信息、旅程和历史上下文一次性建立。
    db.refresh(new_customer)
    customer_business_object_intelligence_service.enqueue_object_change_refresh_after_commit(
        source_type="customer",
        business_object=new_customer,
        change_type="created",
        actor_id=str(current_user.id),
        summary="客户已创建，生成客户档案",
        scope="full",
    )

    return _customer_response(db, new_customer)


@router.get("/", response_model=PaginatedResponse[CustomerListResponse], summary="查询客户列表", description="支持分页、按客户名称/行业/城市/状态/负责人等多条件筛选，支持动态排序，返回负责人和创建人信息")
def get_customers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    customer_status: Optional[str] = Query(None, alias="status", description="客户状态，多个值用逗号分隔"),
    status_exclude: Optional[str] = Query(None, description="排除的客户状态，多个值用逗号分隔"),
    industry: str = Query(None, description="所属行业"),
    industry_exclude: Optional[str] = Query(None, description="排除的所属行业，多个值用逗号分隔"),
    city: str = Query(None, description="所在城市"),
    source_public_id: Optional[str] = Query(None, description="获客来源对外ID，多个值用逗号分隔"),
    source_public_id_exclude: Optional[str] = Query(None, description="排除的获客来源对外ID，多个值用逗号分隔"),
    company_scale: str = Query(None, description="公司规模"),
    company_scale_exclude: Optional[str] = Query(None, description="排除的公司规模，多个值用逗号分隔"),
    owner_id: str = Query(None, description="负责人ID（支持 'me' 表示当前用户）"),
    owner_id_exclude: Optional[str] = Query(None, description="排除的负责人ID，多个值用逗号分隔"),
    keyword: str = Query(None, description="关键词搜索"),
    search: Optional[str] = Query(None, description="统一搜索，可搜索客户名称、简称或别名"),
    created_time_start: Optional[date] = Query(None, description="创建时间起始"),
    created_time_end: Optional[date] = Query(None, description="创建时间结束"),
    order_by: str = Query(None, description="排序字段（created_time/last_modified_time/account_name/city/status/industry）"),
    order_dir: str = Query(None, description="排序方向（asc/desc）"),
    scope: Optional[str] = Query(None, description="客户范围：collaborated/accessible"),
    filters: Optional[str] = Query(None, description="通用筛选条件 JSON"),
    sorts: Optional[str] = Query(None, description="通用排序条件 JSON"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.crud.permission import permission_crud

    # 获取用户权限码
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    # 检查是否有 view:all 权限
    has_view_all = "customer:view:all" in permission_codes

    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    allowed_scopes = {None, "collaborated", "accessible"}
    if scope not in allowed_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope 仅支持 collaborated/accessible"
        )

    current_user_id = str(current_user.id)
    include_collaborated = scope == "accessible" and not has_view_all
    if uses_unified_list_query(filters=parsed_filters, sorts=parsed_sorts):
        actual_owner_id = enforce_owner_view_scope(
            parsed_filters or [],
            current_user_id=current_user_id,
            has_view_all=has_view_all,
            permission_detail="只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据",
            default_to_self=scope not in {"collaborated", "accessible"},
        )
    else:
        actual_owner_id = owner_id
        if owner_id in ["me", "my"]:
            actual_owner_id = current_user_id
        requested_owner_ids = [item.strip() for item in actual_owner_id.split(",") if item.strip()] if actual_owner_id else []
        if requested_owner_ids and any(item != current_user_id for item in requested_owner_ids) and not has_view_all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据"
            )
        if scope in {"collaborated", "accessible"}:
            actual_owner_id = None
        elif actual_owner_id is None and not has_view_all:
            actual_owner_id = current_user_id

    source_ids = None
    if source_public_id is not None:
        source_ids = resolve_public_ids_to_ids(db, team_id, _split_csv(source_public_id))
    source_ids_exclude = None
    if source_public_id_exclude is not None:
        source_ids_exclude = resolve_public_ids_to_ids(db, team_id, _split_csv(source_public_id_exclude))

    customers, total = run_or_400(lambda: customer_crud.get_multi(
        db=db,
        team_id=team_id,
        skip=skip,
        limit=limit,
        status=customer_status,
        status_exclude=status_exclude,
        industry=industry,
        industry_exclude=industry_exclude,
        city=city,
        source_ids=source_ids,
        source_ids_exclude=source_ids_exclude,
        company_scale=company_scale,
        company_scale_exclude=company_scale_exclude,
        owner_id=actual_owner_id,
        owner_id_exclude=owner_id_exclude,
        keyword=keyword,
        search=search,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        order_by=order_by,
        order_dir=order_dir,
        scope=scope,
        current_user_id=current_user_id,
        include_collaborated=include_collaborated,
        filters=parsed_filters,
        sorts=parsed_sorts,
    ))
    
    result = []
    owner_ids = set(c.owner_id for c in customers if c.owner_id)
    creator_ids = set(c.creator_id for c in customers if c.creator_id)
    customer_ids = [c.id for c in customers]
    source_lead_ids = [c.source_lead_id for c in customers if c.source_lead_id]
    source_map = map_sources_by_ids(db, team_id, [c.source_id for c in customers])
    procurement_method_ids = set(c.default_procurement_method_id for c in customers if c.default_procurement_method_id)
    
    users_info = {}
    if owner_ids or creator_ids:
        all_user_ids = owner_ids.union(creator_ids)
        if all_user_ids:
            placeholders = ','.join(':user_id_' + str(i) for i in range(len(all_user_ids)))
            users_query = text(f"""
                SELECT id, name, avatar_url
                FROM users
                WHERE id IN ({placeholders})
            """)

            params = {f'user_id_{i}': int(user_id) for i, user_id in enumerate(all_user_ids)}
            users_result = db.execute(users_query, params).fetchall()

            for row in users_result:
                users_info[str(row[0])] = {
                    'id': str(row[0]),
                    'name': row[1],
                    'avatar_url': row[2]
                }

    collaborator_user_ids = set()
    collaborator_member_rows = []
    if customer_ids:
        placeholders = ','.join(':customer_id_' + str(i) for i in range(len(customer_ids)))
        collaborators_query = text(f"""
            SELECT customer_id, user_id
            FROM crm_customer_members cm
            WHERE cm.team_id = :team_id
              AND cm.customer_id IN ({placeholders})
              AND cm.is_active = TRUE
            ORDER BY cm.created_time ASC, cm.id ASC
        """)
        params = {'team_id': team_id}
        params.update({f'customer_id_{i}': customer_id for i, customer_id in enumerate(customer_ids)})
        collaborator_member_rows = db.execute(collaborators_query, params).fetchall()

        collaborator_user_ids = {str(row[1]) for row in collaborator_member_rows if str(row[1]).isdigit()}

    collaborator_users_info = {}
    if collaborator_user_ids:
        placeholders = ','.join(':user_id_' + str(i) for i in range(len(collaborator_user_ids)))
        users_query = text(f"""
            SELECT id, name, avatar_url
            FROM users
            WHERE id IN ({placeholders})
        """)
        params = {f'user_id_{i}': int(user_id) for i, user_id in enumerate(collaborator_user_ids)}
        users_result = db.execute(users_query, params).fetchall()

        for row in users_result:
            collaborator_users_info[str(row[0])] = {
                'id': str(row[0]),
                'name': row[1],
                'avatar_url': row[2]
            }

    collaborators_by_customer = {}
    for customer_id, user_id in collaborator_member_rows:
        user_info = collaborator_users_info.get(str(user_id))
        if user_info:
            collaborators_by_customer.setdefault(customer_id, []).append(user_info)

    source_lead_public_ids = {}
    if source_lead_ids:
        placeholders = ','.join(':lead_id_' + str(i) for i in range(len(source_lead_ids)))
        source_leads_query = text(f"""
            SELECT id, public_id
            FROM crm_leads
            WHERE id IN ({placeholders})
        """)
        params = {f'lead_id_{i}': lead_id for i, lead_id in enumerate(source_lead_ids)}
        source_leads_result = db.execute(source_leads_query, params).fetchall()
        source_lead_public_ids = {row[0]: row[1] for row in source_leads_result}
    
    procurement_methods_info = {}
    if procurement_method_ids:
        from app.models.procurement import ProcurementMethod
        methods = db.query(ProcurementMethod).filter(
            ProcurementMethod.id.in_(procurement_method_ids)
        ).all()
        for m in methods:
            procurement_methods_info[m.id] = {
                'id': m.id,
                'code': m.code,
                'name': m.name,
                'is_active': m.is_active
            }
    
    industries_info = {}
    industry_values = set()
    for customer in customers:
        if customer.industry:
            industry_values.add(customer.industry)

    # 批量查询所有行业信息（含父行业）
    if industry_values:
        from app.crud.industry import industry_crud

        industries_map = industry_crud.get_by_codes_with_parent(db, list(industry_values))
        for industry_code, industry in industries_map.items():
            # 构建完整路径：一级行业/二级行业
            if industry.level == 2 and industry.parent:
                full_name = f"{industry.parent.name}/{industry.name}"
                parent_code = industry.parent.code
            else:
                full_name = industry.name
                parent_code = None

            industries_info[industry_code] = {
                'code': industry.code,
                'name': full_name,
                'primary_code': parent_code,
                'primary_name': industry.parent.name if industry.parent else None,
                'secondary_name': industry.name if industry.level == 2 else None
            }
    
    for customer in customers:
        customer_dict = {
            'id': customer.public_id,
            'public_id': customer.public_id,
            'account_name': customer.account_name,
            'industry': customer.industry,
            'industry_info': industries_info.get(customer.industry),
            'city': customer.city,
            'address': customer.address,
            'company_scale': customer.company_scale,
            **_customer_source_fields(db, customer, source_map),
            'status': customer.status,
            'owner_id': customer.owner_id,
            'source_lead_id': source_lead_public_ids.get(customer.source_lead_id),
            'default_procurement_method_id': customer.default_procurement_method_id,
            'return_reason': customer.return_reason,
            'returned_time': customer.returned_time,
            'creator_id': customer.creator_id,
            'created_time': customer.created_time,
            'last_modified_time': customer.last_modified_time,
            'version': customer.version,
            'license_expiry_date': customer.license_expiry_date,
            'license_type': customer.license_type,
            'owner_info': users_info.get(customer.owner_id) if customer.owner_id else None,
            'collaborator_infos': collaborators_by_customer.get(customer.id, []),
            'creator_info': users_info.get(customer.creator_id) if customer.creator_id else None,
            'default_procurement_method_info': procurement_methods_info.get(customer.default_procurement_method_id) if customer.default_procurement_method_id else None
        }
        result.append(CustomerListResponse(**customer_dict))
    
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[CustomerListResponse](
        items=result,
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


@router.get(
    "/identity-resolution",
    response_model=CustomerIdentityResolutionResponse,
    summary="解析客户身份",
)
def resolve_customer_identity(
    query: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(10, ge=1, le=50),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from app.crud.permission import permission_crud

    permission_codes = {
        permission.code
        for permission in permission_crud.get_user_permissions(db, current_user.id, team_id)
    }
    resolution = customer_identity_resolution_application_service.resolve(
        db,
        team_id=team_id,
        user_id=current_user.id,
        permission_codes=permission_codes,
        query_text=query.strip(),
        limit=limit,
    )
    return {
        "decision": resolution.metadata.get("identity_decision", "no_match"),
        "items": resolution.items,
        "related_customers": resolution.related_customers,
        "metadata": resolution.metadata,
    }


def _can_manage_customer_members(db: Session, customer, team_id: int, current_user) -> bool:
    from app.crud.permission import permission_crud
    from app.crud.role import role_crud

    if customer.owner_id == str(current_user.id):
        return True

    permission_codes = {p.code for p in permission_crud.get_user_permissions(db, current_user.id, team_id)}
    if "customer:assign" in permission_codes or "customer:edit:all" in permission_codes:
        return True

    role_codes = {r.code for r in role_crud.get_user_roles(db, current_user.id, team_id)}
    return "TEAM_ADMIN" in role_codes


def _build_customer_member_response(db: Session, member, customer_public_id: str, can_manage: bool) -> CustomerMemberResponse:
    user_info = None
    if member.user_id:
        row = db.execute(text("""
            SELECT id, name, avatar_url
            FROM users
            WHERE id = :user_id
        """), {"user_id": int(member.user_id)}).first()
        if row:
            user_info = CustomerMemberUserInfo(
                id=str(row[0]),
                name=row[1],
                avatar_url=row[2],
            )

    return CustomerMemberResponse(
        id=member.id,
        customer_id=customer_public_id,
        user_id=member.user_id,
        member_role=member.member_role,
        access_level=member.access_level,
        remark=member.remark,
        created_by=member.created_by,
        created_time=member.created_time,
        updated_time=member.updated_time,
        user_info=user_info,
        can_manage=can_manage,
    )


@router.get("/{customer_id}/members", response_model=List[CustomerMemberResponse], summary="查询客户团队成员")
def get_customer_members(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_view_permission(customer_id, team_id, current_user, db)
    can_manage = _can_manage_customer_members(db, customer, team_id, current_user)
    members = customer_member_crud.get_by_customer(db, team_id, customer.id)
    return [_build_customer_member_response(db, member, customer.public_id, can_manage) for member in members]


@router.get("/{customer_id}/member-candidates", response_model=List[CustomerMemberCandidate], summary="查询客户团队成员候选人")
def get_customer_member_candidates(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    return customer_member_crud.get_candidates(db, team_id, customer.id)


@router.post("/{customer_id}/members", response_model=CustomerMemberResponse, status_code=status.HTTP_201_CREATED, summary="添加客户团队成员")
def add_customer_member(
    customer_id: str,
    member_in: CustomerMemberCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    if customer.owner_id == str(member_in.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="客户负责人无需添加为团队成员"
        )
    if not team_crud.is_member(db, team_id, int(member_in.user_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能添加当前团队成员"
        )

    member = customer_member_crud.create_or_restore(
        db=db,
        team_id=team_id,
        customer_id=customer.id,
        obj_in=member_in,
        created_by=str(current_user.id),
    )
    _persist_customer_business_object_refresh_after_commit(
        business_object=member,
        source_type="customer_member",
        summary="客户访问成员已更新，刷新客户智能档案可见性",
        change_type="created",
        actor_id=str(current_user.id),
        payload={
            "change_type": "member_upserted",
            "member_id": member.id,
            "user_id": member.user_id,
            "access_level": member.access_level,
            "member_role": member.member_role,
            "is_active": bool(member.is_active),
        },
    )
    return _build_customer_member_response(db, member, customer.public_id, True)


@router.put("/{customer_id}/members/{member_id}", response_model=CustomerMemberResponse, summary="更新客户团队成员")
def update_customer_member(
    customer_id: str,
    member_id: int,
    member_in: CustomerMemberUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    member = customer_member_crud.get_by_id(db, member_id, team_id)
    if not member or member.customer_id != customer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户团队成员不存在"
        )
    updated = customer_member_crud.update(db, member, member_in)
    _persist_customer_business_object_refresh_after_commit(
        business_object=updated,
        source_type="customer_member",
        summary="客户访问成员权限已更新，刷新客户智能档案可见性",
        actor_id=str(current_user.id),
        payload={
            "change_type": "member_updated",
            "member_id": updated.id,
            "user_id": updated.user_id,
            "access_level": updated.access_level,
            "member_role": updated.member_role,
            "is_active": bool(updated.is_active),
        },
    )
    return _build_customer_member_response(db, updated, customer.public_id, True)


@router.delete("/{customer_id}/members/{member_id}", response_model=MessageResponse, summary="移除客户团队成员")
def remove_customer_member(
    customer_id: str,
    member_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = check_customer_member_manage_permission(customer_id, team_id, current_user, db)
    member = customer_member_crud.get_by_id(db, member_id, team_id)
    if not member or member.customer_id != customer.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户团队成员不存在"
        )
    customer_member_crud.deactivate(db, member)
    _persist_customer_business_object_refresh_after_commit(
        business_object=member,
        source_type="customer_member",
        summary="客户访问成员已移除，刷新客户智能档案可见性",
        change_type="deleted",
        actor_id=str(current_user.id),
        payload={
            "change_type": "member_deactivated",
            "member_id": member.id,
            "user_id": member.user_id,
            "is_active": False,
        },
    )
    return MessageResponse(message="移除成功")


@router.get("/{customer_id}", response_model=CustomerDetailResponse, summary="获取客户详情", description="返回客户信息及其所有联系人列表")
def get_customer(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    contacts = contact_crud.get_by_customer_id(db, customer.id, team_id)
    
    owner_info = None
    if customer.owner_id:
        from app.crud.user import user_crud
        owner = user_crud.get_by_id(db, int(customer.owner_id))
        if owner:
            owner_info = {
                'id': str(owner.id),
                'name': owner.name,
                'avatar_url': owner.avatar_url
            }
    
    creator_info = None
    if customer.creator_id:
        from app.crud.user import user_crud
        creator = user_crud.get_by_id(db, int(customer.creator_id))
        if creator:
            creator_info = {
                'id': str(creator.id),
                'name': creator.name,
                'avatar_url': creator.avatar_url
            }
    
    procurement_method_info = None
    if customer.default_procurement_method_id:
        from app.crud.procurement import procurement_method_crud
        procurement_method = procurement_method_crud.get(db, customer.default_procurement_method_id)
        if procurement_method:
            procurement_method_info = {
                'id': procurement_method.id,
                'code': procurement_method.code,
                'name': procurement_method.name,
                'is_active': procurement_method.is_active
            }
    
    industry_info = None
    if customer.industry:
        from app.crud.industry import industry_crud

        # 从 crm_industries 表获取行业信息（含父行业）
        industry = industry_crud.get_by_code_with_parent(db, customer.industry)
        if industry:
            # 构建完整路径：一级行业/二级行业
            if industry.level == 2 and industry.parent:
                full_name = f"{industry.parent.name}/{industry.name}"
                parent_code = industry.parent.code
            else:
                full_name = industry.name
                parent_code = None

            industry_info = {
                'code': industry.code,
                'name': full_name,
                'primary_code': parent_code,
                'primary_name': industry.parent.name if industry.parent else None,
                'secondary_name': industry.name if industry.level == 2 else None
            }
    
    customer_payload = {
        **customer.__dict__,
        "id": customer.public_id,
        "public_id": customer.public_id,
        **_customer_source_fields(db, customer),
        "source_lead_id": source_lead.public_id if (source_lead := lead_crud.get_by_id(db, customer.source_lead_id, team_id)) else None,
    }

    return CustomerDetailResponse(
        **customer_payload,
        contacts=[_contact_response(contact, customer.public_id) for contact in contacts],
        owner_info=owner_info,
        creator_info=creator_info,
        default_procurement_method_info=procurement_method_info,
        industry_info=industry_info,
        customer_intelligence_has_inputs=customer_intelligence_refresh_service.has_customer_business_data(
            db,
            customer_id=customer.id,
            team_id=team_id,
        ),
    )


@router.put("/{customer_id}", response_model=CustomerResponse, summary="编辑客户", description="更新客户信息")
def update_customer(
    customer_id: str,
    customer_update: CustomerUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    if customer_update.account_name:
        _ensure_customer_name_available(db, customer_update.account_name, team_id, exclude_customer_id=customer.id)

    try:
        updated = customer_crud.update(db, customer, customer_update)
    except AcquisitionSourceError as exc:
        _raise_source_error(exc)
    changed_fields = customer_update.model_fields_set - {"expected_version"}
    if changed_fields:
        _persist_customer_business_object_refresh_after_commit(
            business_object=updated,
            source_type="customer",
            summary="客户主数据已更新，刷新客户智能档案",
            actor_id=str(current_user.id),
            payload={"change_type": "updated", "changed_fields": sorted(changed_fields)},
        )
    return _customer_response(db, updated)


@router.patch("/{customer_id}/status", response_model=CustomerResponse, summary="更新客户状态", description="用于标记赢单、输单等关键状态变更")
async def update_customer_status(
    customer_id: str,
    status_update: CustomerStatusUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    new_status = status_update.status
    previous_status = customer.status
    updated_customer = customer_crud.update_status(db, customer, new_status)
    _persist_customer_business_object_refresh_after_commit(
        business_object=updated_customer,
        source_type="customer",
        summary="客户状态已更新，刷新客户智能档案",
        actor_id=str(current_user.id),
        payload={"change_type": "status_updated", "previous_status": previous_status, "new_status": new_status},
    )

    if new_status == 1:
        event_type = OutboundNotificationEventType.ACCOUNT_STATUS_WON
    elif new_status == 2:
        event_type = OutboundNotificationEventType.ACCOUNT_STATUS_LOST
    else:
        event_type = None
    if event_type is not None:
        outbound_notification_job_service.queue_committed(
            db,
            team_id=team_id,
            event_type=event_type,
            business_type="CUSTOMER",
            business_id=int(updated_customer.id),
            recipient_user_ids=[updated_customer.owner_id],
            actor_id=str(current_user.id),
            payload_json={"account_name": updated_customer.account_name},
        )

    return _customer_response(db, updated_customer)


@router.patch("/{customer_id}/lose", response_model=CustomerResponse, summary="标记输单", description="将客户标记为输单，必须记录输单原因")
async def mark_customer_as_lost(
    customer_id: str,
    lose_data: CustomerLoseRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    if customer.status == 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该客户已标记为输单"
        )

    previous_status = customer.status
    updated_customer = customer_crud.mark_as_lost(
        db, customer, lose_data.loss_reason, str(current_user.id), current_user.name
    )
    _persist_customer_business_object_refresh_after_commit(
        business_object=updated_customer,
        source_type="customer",
        summary="客户已标记输单，刷新客户智能档案",
        actor_id=str(current_user.id),
        payload={
            "change_type": "lost",
            "previous_status": previous_status,
            "new_status": updated_customer.status,
            "loss_reason": lose_data.loss_reason,
        },
    )

    outbound_notification_job_service.queue_committed(
        db,
        team_id=team_id,
        event_type=OutboundNotificationEventType.ACCOUNT_STATUS_LOST,
        business_type="CUSTOMER",
        business_id=int(updated_customer.id),
        recipient_user_ids=[updated_customer.owner_id],
        actor_id=str(current_user.id),
        payload_json={"account_name": updated_customer.account_name},
    )

    return _customer_response(db, updated_customer)


@router.delete("/{customer_id}", response_model=MessageResponse, summary="删除客户", description="逻辑删除，需校验权限")
def delete_customer(
    customer_id: str,
    customer = Depends(check_customer_delete_permission),
    db: Session = Depends(get_db)
):
    try:
        # 客户删除会由数据库级联清理客户档案投影；这里不再发起普通
        # Customer Intelligence refresh，避免对已不存在的客户重算。
        # 删除审计由 customer_crud.delete() 的操作日志负责。
        customer_crud.delete(db, customer, str(customer.owner_id) if customer.owner_id else None)
        return MessageResponse(message="删除成功")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{customer_id}/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED, summary="添加联系人", description="为指定客户添加新联系人")
async def create_contact(
    customer_id: str,
    contact: ContactCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_editable_customer(db, customer_id, team_id, current_user)

    created_contact = contact_crud.create(db, contact, customer.id, team_id)
    _persist_customer_business_object_refresh_after_commit(
        business_object=created_contact,
        source_type="customer_contact",
        change_type="created",
        actor_id=str(current_user.id),
    )
    return _contact_response(created_contact, customer.public_id)


@router.get("/{customer_id}/contacts", response_model=List[ContactResponse], summary="查询联系人列表", description="获取指定客户下的全部联系人")
def get_contacts(
    customer_id: str,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    customer = _get_viewable_customer(db, customer_id, team_id, current_user)

    return [_contact_response(contact, customer.public_id) for contact in contact_crud.get_by_customer_id(db, customer.id, team_id)]


@router.put("/contacts/{contact_id}", response_model=ContactResponse, summary="编辑联系人", description="更新联系人信息")
async def update_contact(
    contact_id: int,
    contact_update: ContactUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contact = contact_crud.get_by_id(db, contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )
    customer = _get_editable_customer(db, contact.customer_id, team_id, current_user)

    updated_contact = contact_crud.update(db, contact, contact_update)
    _persist_customer_business_object_refresh_after_commit(
        business_object=updated_contact,
        source_type="customer_contact",
        change_type="updated",
        actor_id=str(current_user.id),
    )
    return _contact_response(updated_contact, customer.public_id)


@router.patch("/contacts/{contact_id}/set-primary", response_model=ContactResponse, summary="设置主联系人", description="设置某联系人为主联系人")
async def set_primary_contact(
    contact_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contact = contact_crud.get_by_id(db, contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )
    customer = _get_editable_customer(db, contact.customer_id, team_id, current_user)

    updated_contact = contact_crud.set_primary(db, contact, team_id)
    _persist_customer_business_object_refresh_after_commit(
        business_object=updated_contact,
        source_type="customer_contact",
        change_type="updated",
        actor_id=str(current_user.id),
    )
    return _contact_response(updated_contact, customer.public_id)


@router.delete("/contacts/{contact_id}", response_model=MessageResponse, summary="删除联系人", description="删除联系人")
async def delete_contact(
    contact_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contact = contact_crud.get_by_id(db, contact_id, team_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="联系人不存在"
        )
    _get_editable_customer(db, contact.customer_id, team_id, current_user)

    try:
        contact_crud.delete(db, contact)
        _persist_customer_business_object_refresh_after_commit(
            business_object=contact,
            source_type="customer_contact",
            change_type="deleted",
            actor_id=str(current_user.id),
        )
        return MessageResponse(message="删除成功")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/statistics/summary", response_model=StatisticsResponse, summary="查询统计", description="查询客户统计数据")
def get_statistics(
    owner_id: str = Query(None, description="负责人ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return StatisticsResponse(**customer_crud.get_statistics(db, team_id, owner_id))


@router.get("/statistics/trend", response_model=List[TrendResponse], summary="查询趋势", description="查询客户创建趋势")
def get_trend(
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    owner_id: str = Query(None, description="负责人ID"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    trend_data = customer_crud.get_trend(db, team_id, days, owner_id)
    return [TrendResponse(**item) for item in trend_data]


@router.post(
    "/{customer_id}/return-to-pool",
    response_model=None,
    summary="客户退回公海",
    description="将客户退回到公海池，解除与负责人的绑定。新客户端使用命令结果查询保证幂等和并发安全。",
)
async def return_customer_to_pool(
    customer_id: str,
    return_data: CustomerReturnRequest,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
    operation_id: Optional[str] = Header(None, alias="X-Operation-Id"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    expected_version_header: Optional[int] = Header(None, alias="X-Expected-Version"),
) -> object:
    from app.crud.role import role_crud

    operation_id = _normalize_optional_header_text(operation_id)
    idempotency_key = _normalize_optional_header_text(idempotency_key)
    correlation_id = _normalize_optional_header_text(correlation_id)
    expected_version_header = _normalize_optional_header_int(expected_version_header)
    if operation_id is not None and len(operation_id) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Operation-Id 必须为 1-64 个字符")
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key 必须为 1-128 个字符")

    if (
        expected_version_header is not None
        and return_data.expected_version is not None
        and expected_version_header != return_data.expected_version
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户版本号不一致，请刷新后重试")
    expected_version = return_data.expected_version if return_data.expected_version is not None else expected_version_header
    customer = _get_customer_or_404(db, customer_id, team_id)
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    is_admin = "TEAM_ADMIN" in role_codes
    is_director = "SALES_DIRECTOR" in role_codes
    if not (is_admin or is_director or customer.owner_id == str(current_user.id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限操作此客户")

    modern_command = operation_id is not None or idempotency_key is not None
    if not modern_command:
        try:
            previous_owner = customer.owner_id
            updated_customer = customer_crud.return_to_pool(
                db,
                customer,
                return_data.return_reason,
                team_id,
                return_data.detailed_reason,
                expected_version=expected_version,
                commit=False,
            )
            operation_log_service.log(
                db=db,
                event_type="CUSTOMER_RETURNED_TO_POOL",
                event_action="UPDATE",
                resource_type="CUSTOMER",
                resource_id=updated_customer.id,
                operator_id=str(current_user.id),
                operator_name=getattr(current_user, "name", None),
                team_id=team_id,
                commit=False,
                remark=return_data.detailed_reason,
                content={
                    "previous_owner_id": previous_owner,
                    "new_owner_id": None,
                    "return_reason": return_data.return_reason,
                    "detailed_reason": return_data.detailed_reason,
                },
            )
            db.commit()
            db.refresh(updated_customer)
        except ValueError as exc:
            db.rollback()
            code = "RESOURCE_VERSION_CONFLICT" if str(exc) == "RESOURCE_VERSION_CONFLICT" else "CUSTOMER_RETURN_REJECTED"
            message = "客户已被其他操作更新，请刷新后重试" if code == "RESOURCE_VERSION_CONFLICT" else str(exc)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT if code == "RESOURCE_VERSION_CONFLICT" else status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message}) from exc

        _persist_customer_business_object_refresh_after_commit(
            business_object=updated_customer,
            source_type="customer",
            summary="客户已退回公海，刷新客户智能档案",
            actor_id=str(current_user.id),
            payload={
                "change_type": "returned_to_pool",
                "previous_owner_id": previous_owner,
                "new_owner_id": None,
                "return_reason": updated_customer.return_reason,
            },
        )
        _queue_customer_returned_notification(
            db,
            team_id=team_id,
            customer=updated_customer,
            previous_owner=previous_owner,
            return_reason=return_data.return_reason,
            actor_id=str(current_user.id),
        )
        return CustomerReturnResponse(
            customer_id=updated_customer.public_id,
            previous_owner=previous_owner,
            returned_time=updated_customer.returned_time,
            return_reason=updated_customer.return_reason,
            message="客户已成功退回公海",
        )

    fingerprint = request_fingerprint({
        "customer_id": customer_id,
        "return_reason": return_data.return_reason,
        "detailed_reason": return_data.detailed_reason,
        "expected_version": expected_version,
    })
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=str(current_user.id),
            command_type="CUSTOMER_RETURN_TO_POOL",
            resource_type="CUSTOMER",
            resource_public_id=customer_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
    except CommandIdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)}) from exc
    except CommandAlreadyInProgress as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail={"operation_id": str(exc), "message": "退回公海正在处理中，请查询操作结果"}) from exc
    except CommandOperationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "OPERATION_CONFLICT", "message": str(exc)}) from exc

    if replay:
        db.rollback()
        return command_execution_service.to_response_payload(execution)

    command_operation_id = execution.operation_id
    try:
        previous_owner = customer.owner_id
        updated_customer = customer_crud.return_to_pool(
            db,
            customer,
            return_data.return_reason,
            team_id,
            return_data.detailed_reason,
            expected_version=expected_version,
            commit=False,
        )
        operation_log_service.log(
            db=db,
            event_type="CUSTOMER_RETURNED_TO_POOL",
            event_action="UPDATE",
            resource_type="CUSTOMER",
            resource_id=updated_customer.id,
            operator_id=str(current_user.id),
            operator_name=getattr(current_user, "name", None),
            team_id=team_id,
            commit=False,
            remark=return_data.detailed_reason,
            content={
                "previous_owner_id": previous_owner,
                "new_owner_id": None,
                "return_reason": return_data.return_reason,
                "detailed_reason": return_data.detailed_reason,
            },
        )
        command_execution_service.succeed(
            db,
            execution,
            data={
                "customer": _customer_response(db, updated_customer).model_dump(mode="json"),
                "previous_owner_id": previous_owner,
                "return_reason": updated_customer.return_reason,
                "message": "客户已成功退回公海",
            },
            resource=CommandResource(
                type="CUSTOMER",
                public_id=str(updated_customer.public_id),
                version=int(updated_customer.version),
            ),
            next_actions=[CommandNextAction(id="refresh-list", label="刷新客户列表", kind="continue")],
            correlation_id=correlation_id,
        )
        db.commit()
        db.refresh(updated_customer)
    except ValueError as exc:
        db.rollback()
        error_code = "RESOURCE_VERSION_CONFLICT" if str(exc) == "RESOURCE_VERSION_CONFLICT" else "CUSTOMER_RETURN_REJECTED"
        error_message = "客户已被其他操作更新，请刷新后重试" if error_code == "RESOURCE_VERSION_CONFLICT" else str(exc)
        try:
            execution, _ = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="CUSTOMER_RETURN_TO_POOL",
                resource_type="CUSTOMER",
                resource_public_id=customer_id,
                operation_id=command_operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            command_execution_service.fail(
                db,
                execution,
                status=CommandExecutionStatus.CONFLICT,
                error_code=error_code,
                error_message=error_message,
                retryable=True,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if error_code == "RESOURCE_VERSION_CONFLICT" else status.HTTP_400_BAD_REQUEST,
            detail={"code": error_code, "message": error_message, "operation_id": command_operation_id},
        ) from exc
    except Exception as exc:
        logger.exception("客户退回公海提交失败", extra={"operation_id": command_operation_id})
        db.rollback()
        try:
            execution, _ = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="CUSTOMER_RETURN_TO_POOL",
                resource_type="CUSTOMER",
                resource_public_id=customer_id,
                operation_id=command_operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            command_execution_service.fail(
                db,
                execution,
                status=CommandExecutionStatus.UNKNOWN,
                error_code="CUSTOMER_RETURN_UNKNOWN",
                error_message="退回公海结果暂未确认，请查询操作结果",
                retryable=True,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CUSTOMER_RETURN_UNKNOWN", "message": "退回公海结果暂未确认，请查询操作结果", "operation_id": command_operation_id},
        ) from exc

    try:
        _persist_customer_business_object_refresh_after_commit(
            business_object=updated_customer,
            source_type="customer",
            summary="客户已退回公海，刷新客户智能档案",
            actor_id=str(current_user.id),
            payload={
                "change_type": "returned_to_pool",
                "previous_owner_id": previous_owner,
                "new_owner_id": None,
                "return_reason": updated_customer.return_reason,
            },
        )
    except Exception:
        # The customer ownership fact is already committed. A projection
        # enqueue failure must not turn a successful command into a 500.
        logger.exception("客户退回公海后的智能档案刷新入队失败", extra={"operation_id": command_operation_id})
    _queue_customer_returned_notification(
        db,
        team_id=team_id,
        customer=updated_customer,
        previous_owner=previous_owner,
        return_reason=return_data.return_reason,
        actor_id=str(current_user.id),
    )
    return command_execution_service.to_response_payload(execution)


@router.get("/public/list", response_model=PaginatedResponse[CustomerResponse], summary="查询公海客户", description="获取公海池中的客户列表，支持动态排序")
def get_public_customers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="返回记录数"),
    status: Optional[int] = Query(None, description="客户状态"),
    city: Optional[str] = Query(None, description="所在城市"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    search: Optional[str] = Query(None, description="统一搜索，可搜索客户名称、简称或别名"),
    order_by: Optional[str] = Query(None, description="排序字段"),
    order_dir: Optional[str] = Query(None, description="排序方向（asc/desc）"),
    filters: Optional[str] = Query(None, description="通用筛选条件 JSON"),
    sorts: Optional[str] = Query(None, description="通用排序条件 JSON"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    customers, total = run_or_400(lambda: customer_crud.get_public_customers(
        db, team_id=team_id, skip=skip, limit=limit,
        status=status, city=city, keyword=keyword, search=search,
        order_by=order_by, order_dir=order_dir,
        filters=parsed_filters, sorts=parsed_sorts,
    ))
    page = skip // limit + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return PaginatedResponse[CustomerResponse](
        items=[_customer_response(db, customer) for customer in customers],
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages
    )


@router.post(
    "/{customer_id}/claim",
    response_model=None,
    summary="领取客户",
    description="从公海池中领取客户。新客户端使用命令结果查询保证幂等和并发安全。",
)
def claim_customer(
    customer_id: str,
    claim_data: CustomerClaimRequest,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
    operation_id: Optional[str] = Header(None, alias="X-Operation-Id"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    expected_version_header: Optional[int] = Header(None, alias="X-Expected-Version"),
) -> object:
    operation_id = _normalize_optional_header_text(operation_id)
    idempotency_key = _normalize_optional_header_text(idempotency_key)
    correlation_id = _normalize_optional_header_text(correlation_id)
    expected_version_header = _normalize_optional_header_int(expected_version_header)
    if operation_id is not None and len(operation_id) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Operation-Id 必须为 1-64 个字符")
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key 必须为 1-128 个字符")

    try:
        target_owner_id = int(claim_data.owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="负责人ID无效") from exc
    target_user = user_crud.get_by_id(db, target_owner_id)
    if not target_user or not team_crud.is_member(db, team_id, target_owner_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标负责人不存在或不属于当前团队")

    if (
        expected_version_header is not None
        and claim_data.expected_version is not None
        and expected_version_header != claim_data.expected_version
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户版本号不一致，请刷新后重试")
    expected_version = claim_data.expected_version if claim_data.expected_version is not None else expected_version_header
    customer = _get_customer_or_404(db, customer_id, team_id)
    modern_command = operation_id is not None or idempotency_key is not None
    if not modern_command:
        try:
            updated_customer = customer_crud.claim_customer(
                db,
                customer,
                claim_data.owner_id,
                team_id,
                expected_version=expected_version,
                commit=False,
            )
            operation_log_service.log(
                db=db,
                event_type="CUSTOMER_CLAIMED",
                event_action="UPDATE",
                resource_type="CUSTOMER",
                resource_id=updated_customer.id,
                operator_id=str(current_user.id),
                operator_name=getattr(current_user, "name", None),
                team_id=team_id,
                commit=False,
                content={
                    "previous_owner_id": None,
                    "new_owner_id": updated_customer.owner_id,
                },
            )
            db.commit()
            db.refresh(updated_customer)
            return _customer_response(db, updated_customer)
        except ValueError as exc:
            db.rollback()
            code = "RESOURCE_VERSION_CONFLICT" if str(exc) == "RESOURCE_VERSION_CONFLICT" else "CUSTOMER_CLAIM_REJECTED"
            message = "客户已被其他操作更新，请刷新后重试" if code == "RESOURCE_VERSION_CONFLICT" else str(exc)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT if code == "RESOURCE_VERSION_CONFLICT" else status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message}) from exc

    fingerprint = request_fingerprint({
        "customer_id": customer_id,
        "owner_id": claim_data.owner_id,
        "expected_version": expected_version,
    })
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=str(current_user.id),
            command_type="CUSTOMER_CLAIM",
            resource_type="CUSTOMER",
            resource_public_id=customer_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
    except CommandIdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)}) from exc
    except CommandAlreadyInProgress as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail={"operation_id": str(exc), "message": "客户领取正在处理中，请查询操作结果"}) from exc
    except CommandOperationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "OPERATION_CONFLICT", "message": str(exc)}) from exc

    if replay:
        db.rollback()
        return command_execution_service.to_response_payload(execution)

    command_operation_id = execution.operation_id
    try:
        updated_customer = customer_crud.claim_customer(
            db,
            customer,
            claim_data.owner_id,
            team_id,
            expected_version=expected_version,
            commit=False,
        )
        operation_log_service.log(
            db=db,
            event_type="CUSTOMER_CLAIMED",
            event_action="UPDATE",
            resource_type="CUSTOMER",
            resource_id=updated_customer.id,
            operator_id=str(current_user.id),
            operator_name=getattr(current_user, "name", None),
            team_id=team_id,
            commit=False,
            content={
                "previous_owner_id": None,
                "new_owner_id": updated_customer.owner_id,
            },
        )
        command_execution_service.succeed(
            db,
            execution,
            data={
                "customer": _customer_response(db, updated_customer).model_dump(mode="json"),
                "message": "客户领取成功",
            },
            resource=CommandResource(
                type="CUSTOMER",
                public_id=str(updated_customer.public_id),
                version=int(updated_customer.version),
            ),
            next_actions=[CommandNextAction(id="refresh-list", label="刷新客户列表", kind="continue")],
            correlation_id=correlation_id,
        )
        db.commit()
        db.refresh(updated_customer)
    except ValueError as exc:
        db.rollback()
        error_code = "RESOURCE_VERSION_CONFLICT" if str(exc) == "RESOURCE_VERSION_CONFLICT" else "CUSTOMER_CLAIM_REJECTED"
        error_message = "客户已被其他操作更新，请刷新后重试" if error_code == "RESOURCE_VERSION_CONFLICT" else str(exc)
        try:
            execution, _ = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="CUSTOMER_CLAIM",
                resource_type="CUSTOMER",
                resource_public_id=customer_id,
                operation_id=command_operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            command_execution_service.fail(
                db,
                execution,
                status=CommandExecutionStatus.CONFLICT,
                error_code=error_code,
                error_message=error_message,
                retryable=True,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT if error_code == "RESOURCE_VERSION_CONFLICT" else status.HTTP_400_BAD_REQUEST,
            detail={"code": error_code, "message": error_message, "operation_id": command_operation_id},
        ) from exc
    except Exception as exc:
        logger.exception("客户领取提交失败", extra={"operation_id": command_operation_id})
        db.rollback()
        try:
            execution, _ = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(current_user.id),
                command_type="CUSTOMER_CLAIM",
                resource_type="CUSTOMER",
                resource_public_id=customer_id,
                operation_id=command_operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            command_execution_service.fail(
                db,
                execution,
                status=CommandExecutionStatus.UNKNOWN,
                error_code="CUSTOMER_CLAIM_UNKNOWN",
                error_message="领取结果暂未确认，请查询操作结果",
                retryable=True,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CUSTOMER_CLAIM_UNKNOWN", "message": "领取结果暂未确认，请查询操作结果", "operation_id": command_operation_id},
        ) from exc

    try:
        _persist_customer_business_object_refresh_after_commit(
            business_object=updated_customer,
            source_type="customer",
            summary="客户已被领取，刷新客户智能档案",
            actor_id=str(current_user.id),
            payload={
                "change_type": "claimed",
                "previous_owner_id": None,
                "new_owner_id": updated_customer.owner_id,
            },
        )
    except Exception:
        # Projection refresh is an after-commit side effect and must not
        # invalidate the committed customer claim.
        logger.exception("客户领取后的智能档案刷新入队失败", extra={"operation_id": command_operation_id})
    return command_execution_service.to_response_payload(execution)


@router.post(
    "/{customer_id}/assign",
    response_model=None,
    summary="移交客户",
    description="有 customer:assign 权限的用户可移交客户，并可选择同步移交关联商机及其合同。新客户端使用命令结果查询保证幂等和并发安全。",
)
def assign_customer(
    customer_id: str,
    assign_data: CustomerAssignRequest,
    team_id: int = Depends(get_current_user_team),
    _current_user=Depends(require_permission("customer:assign")),
    db: Session = Depends(get_db),
    operation_id: Optional[str] = Header(None, alias="X-Operation-Id"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    expected_version_header: Optional[int] = Header(None, alias="X-Expected-Version"),
) -> object:
    """Transfer a customer as one durable, auditable command.

    Requests without command headers retain the historical response shape for
    existing scripts. The migrated UI sends command headers and receives a
    durable outcome whose ``data`` contains the explicit transfer summary.
    """
    # FastAPI injects concrete header values at runtime, while direct unit
    # calls receive the ``Header(...)`` marker as the default. Normalize the
    # latter to ``None`` so the legacy function contract remains testable.
    operation_id = _normalize_optional_header_text(operation_id)
    idempotency_key = _normalize_optional_header_text(idempotency_key)
    correlation_id = _normalize_optional_header_text(correlation_id)
    expected_version_header = _normalize_optional_header_int(expected_version_header)
    if operation_id is not None and len(operation_id) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Operation-Id 必须为 1-64 个字符")
    if idempotency_key is not None and len(idempotency_key) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key 必须为 1-128 个字符")
    if (
        expected_version_header is not None
        and assign_data.expected_version is not None
        and expected_version_header != assign_data.expected_version
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户版本号不一致，请刷新后重试")
    expected_version = assign_data.expected_version if assign_data.expected_version is not None else expected_version_header
    legacy_scope, normalized_scope = assign_data.normalized_transfer_scope()
    modern_command = operation_id is not None or idempotency_key is not None

    try:
        target_user_id = int(assign_data.owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标负责人ID无效") from exc

    target_user = user_crud.get_by_id(db, target_user_id)
    if not target_user or not team_crud.is_member(db, team_id, target_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目标负责人不存在或不属于当前团队",
        )

    customer = _get_customer_or_404(db, customer_id, team_id)
    if not modern_command:
        try:
            previous_owner = customer.owner_id
            updated_customer, transferred_opportunities, transferred_contracts = customer_crud.assign_customer(
                db,
                customer,
                assign_data.owner_id,
                team_id,
                legacy_scope,
            )
            operation_log_service.log(
                db=db,
                event_type="CUSTOMER_ASSIGNED",
                event_action="UPDATE",
                resource_type="CUSTOMER",
                resource_id=updated_customer.id,
                operator_id=str(_current_user.id),
                operator_name=getattr(_current_user, "name", None),
                team_id=team_id,
                remark=assign_data.normalized_reason(),
                content={
                    "previous_owner_id": previous_owner,
                    "new_owner_id": updated_customer.owner_id,
                    "opportunity_transfer_scope": legacy_scope,
                    "transferred_opportunities": transferred_opportunities,
                    "transferred_contracts": transferred_contracts,
                },
            )
            _persist_customer_business_object_refresh_after_commit(
                business_object=updated_customer,
                source_type="customer",
                summary="客户负责人已变更，刷新客户智能档案",
                actor_id=str(_current_user.id),
                payload={
                    "change_type": "assigned",
                    "previous_owner_id": previous_owner,
                    "new_owner_id": updated_customer.owner_id,
                    "opportunity_transfer_scope": legacy_scope,
                    "transferred_opportunities": transferred_opportunities,
                    "transferred_contracts": transferred_contracts,
                },
            )
            return CustomerAssignResponse(
                customer=_customer_response(db, updated_customer),
                transferred_opportunities=transferred_opportunities,
                transferred_contracts=transferred_contracts,
                message="客户已移交",
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    fingerprint = request_fingerprint({
        "customer_id": customer_id,
        "owner_id": assign_data.owner_id,
        "transfer_scope": normalized_scope.value,
        "expected_version": expected_version,
        "reason": assign_data.normalized_reason(),
    })
    try:
        execution, replay = command_execution_service.begin(
            db,
            team_id=team_id,
            actor_id=str(_current_user.id),
            command_type="CUSTOMER_ASSIGN",
            resource_type="CUSTOMER",
            resource_public_id=customer_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            correlation_id=correlation_id,
        )
    except CommandIdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)}) from exc
    except CommandAlreadyInProgress as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"operation_id": str(exc), "message": "移交正在处理中，请查询操作结果"},
        ) from exc
    except CommandOperationConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "OPERATION_CONFLICT", "message": str(exc)}) from exc

    if replay:
        db.rollback()
        return command_execution_service.to_response_payload(execution)

    command_operation_id = execution.operation_id
    try:
        details = customer_crud.assign_customer(
            db,
            customer,
            assign_data.owner_id,
            team_id,
            legacy_scope,
            expected_version=expected_version,
            reason=assign_data.normalized_reason(),
            commit=False,
            return_details=True,
        )
        if not isinstance(details, dict):
            raise RuntimeError("客户移交结果格式异常")
        updated_customer = details["customer"]
        if not hasattr(updated_customer, "public_id"):
            raise RuntimeError("客户移交结果缺少客户")
        assignment_result = CustomerAssignmentResult(
            customer=_customer_response(db, updated_customer),
            previous_owner_id=details["previous_owner_id"],
            new_owner_id=details["new_owner_id"],
            transfer_scope=normalized_scope,
            transferred_opportunities=details["transferred_opportunities"],
            transferred_contracts=details["transferred_contracts"],
            updated_objects=details["updated_objects"],
            skipped_objects=details["skipped_objects"],
            message="客户已移交，部分锁定合同未同步" if details["skipped_objects"] else "客户已移交",
        )
        effects = [
            CommandEffect(
                type=str(item["object_type"]),
                public_id=str(item["public_id"]),
                status=str(item["status"]),
                detail=item.get("detail"),
            )
            for item in [*details["updated_objects"], *details["skipped_objects"]]
        ]
        operation_log_service.log(
            db=db,
            event_type="CUSTOMER_ASSIGNED",
            event_action="UPDATE",
            resource_type="CUSTOMER",
            resource_id=updated_customer.id,
            operator_id=str(_current_user.id),
            operator_name=getattr(_current_user, "name", None),
            team_id=team_id,
            commit=False,
            remark=assign_data.normalized_reason(),
            content={
                "previous_owner_id": details["previous_owner_id"],
                "new_owner_id": details["new_owner_id"],
                "transfer_scope": normalized_scope.value,
                "transferred_opportunities": details["transferred_opportunities"],
                "transferred_contracts": details["transferred_contracts"],
                "updated_objects": details["updated_objects"],
                "skipped_objects": details["skipped_objects"],
            },
        )
        command_execution_service.succeed(
            db,
            execution,
            data=assignment_result.model_dump(mode="json"),
            resource=CommandResource(
                type="CUSTOMER",
                public_id=str(updated_customer.public_id),
                version=int(updated_customer.version),
            ),
            effects=effects,
            next_actions=[
                CommandNextAction(id="view-customer", label="查看客户详情", kind="view-detail"),
                CommandNextAction(id="refresh-list", label="刷新客户列表", kind="continue"),
            ],
            correlation_id=correlation_id,
        )
        db.commit()
        db.refresh(updated_customer)
    except ValueError as exc:
        db.rollback()
        # The command record is itself the durable conflict result.
        try:
            execution, _ = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(_current_user.id),
                command_type="CUSTOMER_ASSIGN",
                resource_type="CUSTOMER",
                resource_public_id=customer_id,
                operation_id=command_operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            error_code = "RESOURCE_VERSION_CONFLICT" if str(exc) == "RESOURCE_VERSION_CONFLICT" else "OWNER_CHANGED"
            command_execution_service.fail(
                db,
                execution,
                status=CommandExecutionStatus.CONFLICT,
                error_code=error_code,
                error_message="客户已被其他操作更新，请刷新后重试" if error_code == "RESOURCE_VERSION_CONFLICT" else str(exc),
                retryable=True,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "RESOURCE_VERSION_CONFLICT" if str(exc) == "RESOURCE_VERSION_CONFLICT" else "OWNER_CHANGED",
                "message": "客户已被其他操作更新，请刷新后重试" if str(exc) == "RESOURCE_VERSION_CONFLICT" else str(exc),
                "operation_id": command_operation_id,
            },
        ) from exc
    except Exception as exc:
        logger.exception("客户移交提交失败", extra={"operation_id": command_operation_id})
        db.rollback()
        try:
            execution, _ = command_execution_service.begin(
                db,
                team_id=team_id,
                actor_id=str(_current_user.id),
                command_type="CUSTOMER_ASSIGN",
                resource_type="CUSTOMER",
                resource_public_id=customer_id,
                operation_id=command_operation_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
            )
            command_execution_service.fail(
                db,
                execution,
                status=CommandExecutionStatus.UNKNOWN,
                error_code="CUSTOMER_ASSIGN_UNKNOWN",
                error_message="移交结果暂未确认，请查询操作结果",
                retryable=True,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "CUSTOMER_ASSIGN_UNKNOWN",
                "message": "移交结果暂未确认，请查询操作结果",
                "operation_id": command_operation_id,
            },
        ) from exc

    try:
        _persist_customer_business_object_refresh_after_commit(
            business_object=updated_customer,
            source_type="customer",
            summary="客户负责人已变更，刷新客户智能档案",
            actor_id=str(_current_user.id),
            payload={
                "change_type": "assigned",
                "previous_owner_id": details["previous_owner_id"],
                "new_owner_id": details["new_owner_id"],
                "transfer_scope": normalized_scope.value,
                "transferred_opportunities": details["transferred_opportunities"],
                "transferred_contracts": details["transferred_contracts"],
                "skipped_objects": details["skipped_objects"],
            },
        )
    except Exception:
        # Ownership and related-object updates are already committed; keep the
        # command result successful and let observability/retry handle the
        # non-critical projection side effect.
        logger.exception("客户移交后的智能档案刷新入队失败", extra={"operation_id": command_operation_id})
    return command_execution_service.to_response_payload(execution)


@router.post(
    "/{customer_id}/regenerate-intelligence",
    response_model=MessageResponse,
    summary="重新生成客户智能档案",
    description="AI重新生成客户档案和客户概况",
)
async def regenerate_customer_intelligence(
    customer_id: str,
    payload: CustomerIntelligenceRegenerateRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    customer = _get_viewable_customer(db, customer_id, team_id, current_user)
    await customer_intelligence_refresh_service.trigger_manual_refresh(
        db,
        team_id=team_id,
        customer_id=customer.id,
        actor_id=str(current_user.id),
        scope=payload.scope,
    )

    return MessageResponse(message="客户智能档案正在生成")


@router.post(
    "/intelligence/batch-rebuild",
    response_model=CustomerIntelligenceBatchRebuildResponse,
    summary="批量重建客户智能档案",
    description="通过客户智能 LangGraph 运行时批量重建客户档案/客户概况",
)
async def rebuild_customer_intelligence_batch(
    payload: CustomerIntelligenceBatchRebuildRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    customer_ids = None
    if payload.customer_ids is not None:
        customers = [
            _get_customer_or_404(db, customer_public_id, team_id)
            for customer_public_id in payload.customer_ids
        ]
        customer_ids = [customer.id for customer in customers]

    result = await customer_intelligence_refresh_service.trigger_batch_rebuild(
        db,
        team_id=team_id,
        actor_id=str(current_user.id),
        scope=payload.scope,
        customer_ids=customer_ids,
        limit=payload.limit,
    )
    result_customers = [
        customer_crud.get_by_id(db, customer_id, team_id)
        for customer_id in result.customer_ids
    ]
    return CustomerIntelligenceBatchRebuildResponse(
        message="客户智能档案批量重建已开始",
        request_id=result.request_id,
        scope=result.scope,
        total=result.total,
        scheduled=result.scheduled,
        customer_ids=[customer.public_id for customer in result_customers if customer],
    )


@router.get(
    "/intelligence/runs",
    response_model=CustomerIntelligenceRunDiagnosticListResponse,
    summary="查询客户智能运行诊断",
    description="查询客户智能 LangGraph 运行审计和用户可见执行轨迹",
)
def list_customer_intelligence_runs(
    customer_id: Optional[str] = Query(None, description="客户对外ID"),
    request_id: Optional[str] = Query(None, min_length=1, max_length=120, description="请求ID"),
    run_status: Optional[str] = Query(None, alias="status", min_length=1, max_length=30, description="运行状态"),
    limit: int = Query(20, ge=1, le=100, description="返回记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_run_service import customer_intelligence_run_service

    customer = _get_customer_or_404(db, customer_id, team_id) if customer_id else None
    diagnostics = customer_intelligence_run_service.list_diagnostics(
        db,
        team_id=team_id,
        customer_id=customer.id if customer else None,
        request_id=request_id,
        status=run_status,
        limit=limit,
    )
    return CustomerIntelligenceRunDiagnosticListResponse(
        items=[_customer_intelligence_run_response(db, team_id, diagnostic) for diagnostic in diagnostics],
        total=len(diagnostics),
        limit=limit,
    )


@router.get(
    "/intelligence/runs/{run_id}",
    response_model=CustomerIntelligenceRunDiagnosticResponse,
    summary="查询客户智能运行详情",
    description="查询单次客户智能 LangGraph 运行审计和可回放执行轨迹",
)
def get_customer_intelligence_run(
    run_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
    db: Session = Depends(get_db),
):
    from app.services.customer_intelligence_run_service import customer_intelligence_run_service

    diagnostic = customer_intelligence_run_service.get_diagnostic(
        db,
        team_id=team_id,
        run_id=run_id,
    )
    if diagnostic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="客户智能运行记录不存在",
        )
    return _customer_intelligence_run_response(db, team_id, diagnostic)


@router.post(
    "/intelligence/retries/run-due",
    response_model=CustomerIntelligenceRetryDueResponse,
    summary="执行到期客户智能重试",
    description="调度已到重试时间的客户智能 LangGraph 运行",
)
async def run_due_customer_intelligence_retries(
    limit: int = Query(20, ge=1, le=100, description="本次最多处理数量"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("customer:edit:all")),
):
    from app.services.customer_intelligence_refresh_service import customer_intelligence_refresh_service

    result = await customer_intelligence_refresh_service.run_due_retries(team_id=team_id, limit=limit)
    return CustomerIntelligenceRetryDueResponse(
        success=result.get("success") is True,
        total=int(result.get("total") or 0),
        succeeded=int(result.get("succeeded") or 0),
        failed=int(result.get("failed") or 0),
        results=[
            item
            for item in result.get("results", [])
            if isinstance(item, dict)
        ],
    )
