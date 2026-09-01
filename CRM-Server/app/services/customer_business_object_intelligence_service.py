"""Business object change boundary for customer intelligence refreshes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, cast

from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.payment import PaymentPlan
from app.services.customer_intelligence_event_publication_service import (
    CustomerIntelligenceEventPublicationService,
    customer_intelligence_event_publication_service,
)
from app.services.customer_intelligence_event_service import (
    CustomerIntelligenceBusinessObjectChangeType,
    CustomerIntelligenceEvent,
    JsonObject,
    JsonValue,
    customer_business_object_trigger_for_change,
    customer_intelligence_event_service,
)

if TYPE_CHECKING:
    from app.services.customer_intelligence_refresh_service import (
        CustomerIntelligenceCommittedEventRequest,
        CustomerIntelligenceRefreshScope,
    )

CustomerBusinessObjectSourceType = Literal[
    "customer",
    "customer_member",
    "customer_contact",
    "opportunity",
    "contract",
    "payment_plan",
    "payment_record",
    "invoice_title",
    "invoice_application",
    "deployment_info",
    "license_application",
]
CustomerBusinessObjectChangeType = CustomerIntelligenceBusinessObjectChangeType


@dataclass(frozen=True)
class CustomerBusinessObjectChangeRefreshInput:
    team_id: int
    customer_id: int
    actor_id: str | None
    source_type: CustomerBusinessObjectSourceType
    source_id: int
    change_type: CustomerBusinessObjectChangeType
    object_name: str
    source_version: int | str | None = None
    payload: JsonObject = field(default_factory=dict)
    summary: str | None = None
    scope: CustomerIntelligenceRefreshScope = "partial"


CustomerObjectNameBuilder = Callable[[Session | None, object], str]
CustomerObjectPayloadBuilder = Callable[[Session | None, object], JsonObject]
CustomerObjectCustomerIdBuilder = Callable[[Session | None, object], int | None]


@dataclass(frozen=True)
class CustomerBusinessObjectIntelligenceSpec:
    source_type: CustomerBusinessObjectSourceType
    label: str
    object_name: CustomerObjectNameBuilder
    customer_id: CustomerObjectCustomerIdBuilder
    payload: CustomerObjectPayloadBuilder


class CustomerBusinessObjectIntelligenceService:
    def __init__(
        self,
        *,
        publication_service: CustomerIntelligenceEventPublicationService | None = None,
    ) -> None:
        self.publication_service = publication_service or customer_intelligence_event_publication_service
        self._specs: dict[CustomerBusinessObjectSourceType, CustomerBusinessObjectIntelligenceSpec] = {
            "customer": CustomerBusinessObjectIntelligenceSpec(
                source_type="customer",
                label="客户主数据",
                object_name=lambda _db, obj: _string_attr(obj, "account_name"),
                customer_id=lambda _db, obj: _int_attr(obj, "id"),
                payload=_customer_payload,
            ),
            "customer_member": CustomerBusinessObjectIntelligenceSpec(
                source_type="customer_member",
                label="客户团队成员",
                object_name=lambda _db, obj: _string_attr(obj, "user_id"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_customer_member_payload,
            ),
            "customer_contact": CustomerBusinessObjectIntelligenceSpec(
                source_type="customer_contact",
                label="客户联系人",
                object_name=lambda _db, obj: _string_attr(obj, "name"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_customer_contact_payload,
            ),
            "opportunity": CustomerBusinessObjectIntelligenceSpec(
                source_type="opportunity",
                label="商机",
                object_name=lambda _db, obj: _string_attr(obj, "opportunity_name"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_opportunity_payload,
            ),
            "contract": CustomerBusinessObjectIntelligenceSpec(
                source_type="contract",
                label="合同",
                object_name=lambda _db, obj: _string_attr(obj, "contract_name"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_contract_payload,
            ),
            "payment_plan": CustomerBusinessObjectIntelligenceSpec(
                source_type="payment_plan",
                label="回款计划",
                object_name=lambda _db, obj: _string_attr(obj, "stage_name"),
                customer_id=_payment_plan_customer_id,
                payload=_payment_plan_payload,
            ),
            "payment_record": CustomerBusinessObjectIntelligenceSpec(
                source_type="payment_record",
                label="回款记录",
                object_name=_payment_record_name,
                customer_id=_payment_record_customer_id,
                payload=_payment_record_payload,
            ),
            "invoice_title": CustomerBusinessObjectIntelligenceSpec(
                source_type="invoice_title",
                label="开票抬头",
                object_name=lambda _db, obj: _string_attr(obj, "title"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_invoice_title_payload,
            ),
            "invoice_application": CustomerBusinessObjectIntelligenceSpec(
                source_type="invoice_application",
                label="发票申请",
                object_name=lambda _db, obj: _string_attr(obj, "application_number"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_invoice_application_payload,
            ),
            "deployment_info": CustomerBusinessObjectIntelligenceSpec(
                source_type="deployment_info",
                label="部署信息",
                object_name=lambda _db, obj: _string_attr(obj, "deployment_name"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_deployment_payload,
            ),
            "license_application": CustomerBusinessObjectIntelligenceSpec(
                source_type="license_application",
                label="License申请",
                object_name=lambda _db, obj: _string_attr(obj, "application_number"),
                customer_id=lambda _db, obj: _int_attr(obj, "customer_id"),
                payload=_license_application_payload,
            ),
        }

    def build_change(
        self,
        db: Session | None,
        *,
        source_type: CustomerBusinessObjectSourceType,
        business_object: object,
        change_type: CustomerBusinessObjectChangeType,
        actor_id: str | None,
    ) -> CustomerBusinessObjectChangeRefreshInput | None:
        spec = self._specs[source_type]
        team_id = _int_attr(business_object, "team_id")
        source_id = _int_attr(business_object, "id")
        customer_id = spec.customer_id(db, business_object)
        if team_id is None or source_id is None or customer_id is None:
            return None
        return CustomerBusinessObjectChangeRefreshInput(
            team_id=team_id,
            customer_id=customer_id,
            actor_id=actor_id,
            source_type=source_type,
            source_id=source_id,
            change_type=change_type,
            object_name=spec.object_name(db, business_object) or spec.label,
            source_version=_source_version_for_object(business_object, change_type=change_type),
            payload=spec.payload(db, business_object),
        )

    async def trigger_object_change_refresh(
        self,
        db: Session,
        *,
        source_type: CustomerBusinessObjectSourceType,
        business_object: object,
        change_type: CustomerBusinessObjectChangeType,
        actor_id: str | None,
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        change = self.build_change(
            db,
            source_type=source_type,
            business_object=business_object,
            change_type=change_type,
            actor_id=actor_id,
        )
        if change is None:
            return None
        return await self.trigger_change_refresh(db, change)

    def enqueue_object_change_refresh(
        self,
        db: Session,
        *,
        source_type: CustomerBusinessObjectSourceType,
        business_object: object,
        change_type: CustomerBusinessObjectChangeType,
        actor_id: str | None,
        summary: str | None = None,
        payload: JsonObject | None = None,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        change = self.build_change(
            db,
            source_type=source_type,
            business_object=business_object,
            change_type=change_type,
            actor_id=actor_id,
        )
        if change is None:
            return None
        if summary is not None or payload is not None or scope != change.scope:
            change = replace(
                change,
                summary=summary if summary is not None else change.summary,
                payload={**change.payload, **(payload or {})},
                scope=scope,
            )
        return self.enqueue_change_refresh(db, change)

    def enqueue_object_change_refresh_after_commit(
        self,
        *,
        source_type: CustomerBusinessObjectSourceType,
        business_object: object,
        change_type: CustomerBusinessObjectChangeType,
        actor_id: str | None,
        summary: str | None = None,
        payload: JsonObject | None = None,
        scope: CustomerIntelligenceRefreshScope = "partial",
    ) -> CustomerIntelligenceCommittedEventRequest | None:
        """Build a change from a committed domain object and persist its receipt.

        This is the public post-commit seam for CRUD endpoints that
        commit internally.  Callers do not construct event payloads or
        trigger types themselves; the object registry remains the single place
        that defines source identity and the default payload.
        """
        change = self.build_change(
            None,
            source_type=source_type,
            business_object=business_object,
            change_type=change_type,
            actor_id=actor_id,
        )
        if change is None:
            return None
        change = replace(
            change,
            summary=summary if summary is not None else change.summary,
            payload={**change.payload, **(payload or {})},
            scope=scope,
        )
        return self.enqueue_change_refresh_after_commit(change)

    async def trigger_change_refresh(
        self,
        db: Session,
        change: CustomerBusinessObjectChangeRefreshInput,
    ) -> CustomerIntelligenceCommittedEventRequest:
        """Run the async projection path for one canonical business event."""
        return await self.publication_service.trigger_committed_event_refresh(
            db,
            event=self._build_intelligence_event(change),
            scope=change.scope,
        )

    def enqueue_change_refresh(
        self,
        db: Session,
        change: CustomerBusinessObjectChangeRefreshInput,
    ) -> CustomerIntelligenceCommittedEventRequest:
        """Publish a business-object event inside the source transaction.

        The object registry and event builder own business meaning; the
        publication service owns durable registration and savepoint isolation.
        This keeps this boundary independent from the refresh scheduler's
        object-specific scheduler methods.
        """
        event = self._build_intelligence_event(change)
        request = self.publication_service.persist_in_transaction_request(
            db,
            event=event,
            scope=change.scope,
        )
        if request is None:  # event is always present, keep the seam defensive.
            raise RuntimeError("客户智能事件未构造")
        return request

    def enqueue_customer_lifecycle_refresh_after_commit(
        self,
        *,
        customer: object,
        actor_id: str | None,
        trigger_type: Literal["customer_created", "customer_converted_from_lead"],
        source_lead_id: int | None = None,
        scope: CustomerIntelligenceRefreshScope = "full",
    ) -> CustomerIntelligenceCommittedEventRequest:
        """Enqueue a customer lifecycle event without leaking scheduler details.

        Customer creation and lead conversion are lifecycle events rather than
        ordinary CRUD mutations, but they still use the same durable post-commit
        seam as every other customer intelligence refresh.
        """
        team_id = _int_attr(customer, "team_id")
        customer_id = _int_attr(customer, "id")
        if team_id is None or customer_id is None:
            raise ValueError("客户生命周期事件缺少团队或客户身份")
        source_version = _source_version_for_object(customer, change_type="created")
        version_key = str(source_version or "initial")
        request_id = f"customer-lifecycle-{trigger_type}:{customer_id}:{source_lead_id or customer_id}:{version_key}"
        event = customer_intelligence_event_service.customer_lifecycle_refresh_requested(
            team_id=team_id,
            customer_id=customer_id,
            actor_id=actor_id,
            request_id=request_id,
            trigger_type=trigger_type,
            source_lead_id=source_lead_id,
        )
        return self._enqueue_event_after_commit(event, scope=scope)

    def enqueue_change_refresh_after_commit(
        self,
        change: CustomerBusinessObjectChangeRefreshInput,
    ) -> CustomerIntelligenceCommittedEventRequest:
        """Persist and kick a durable refresh after the source transaction commits.

        This is the post-commit bridge for CRUD methods that
        commit internally.  It deliberately uses a new short-lived session so
        an expired/deleted ORM object is never re-read from the request session.
        The business API must call this only after its source write has
        succeeded.
        """
        return self._enqueue_event_after_commit(
            self._build_intelligence_event(change),
            scope=change.scope,
        )

    def _enqueue_event_after_commit(
        self,
        event: CustomerIntelligenceEvent,
        *,
        scope: CustomerIntelligenceRefreshScope,
    ) -> CustomerIntelligenceCommittedEventRequest:
        request = self.publication_service.enqueue_after_commit(
            event=event,
            scope=scope,
        )
        return request

    def _build_intelligence_event(
        self,
        change: CustomerBusinessObjectChangeRefreshInput,
    ) -> CustomerIntelligenceEvent:
        payload: JsonObject = {
            **change.payload,
            "object_type": change.source_type,
            "object_name": change.object_name,
            "change_type": change.change_type,
            "refresh_scope": change.scope,
        }
        source_version = change.source_version
        change_id = (
            f"{change.source_type}:{change.source_id}:{source_version}"
            if source_version is not None
            else f"{change.source_type}:{change.source_id}:{change.change_type}"
        )
        return customer_intelligence_event_service.business_object_changed(
            team_id=change.team_id,
            customer_id=change.customer_id,
            actor_id=change.actor_id,
            trigger_type=customer_business_object_trigger_for_change(
                change.change_type,
                source_type=change.source_type,
            ),
            source_type=change.source_type,
            source_id=change.source_id,
            change_id=change_id,
            summary=change.summary or self._summary(change),
            source_version=source_version,
            payload=payload,
        )

    def _summary(self, change: CustomerBusinessObjectChangeRefreshInput) -> str:
        object_label = self._specs[change.source_type].label
        action_label = {
            "created": "已新增",
            "updated": "已更新",
            "deleted": "已删除",
        }[change.change_type]
        name = change.object_name.strip() or object_label
        return f"{object_label}{action_label}: {name}"




def _source_version_for_object(
    business_object: object,
    *,
    change_type: CustomerBusinessObjectChangeType,
) -> int | str | None:
    """Return a stable business revision for event idempotency.

    Opportunity already exposes an optimistic-lock version.  Other
    business objects expose timestamps, so use the deletion timestamp for a
    delete and otherwise the last-modified/created timestamp.  The value is
    deliberately metadata only; it never becomes a business status.
    """

    if change_type == "deleted":
        deleted_at = _raw_attr(business_object, "deleted_at")
        if deleted_at is not None:
            return _date_iso_attr(business_object, "deleted_at")
    version = _raw_attr(business_object, "version")
    if version is None:
        version = _raw_attr(business_object, "post_commit_revision")
    if isinstance(version, bool):
        version = None
    if isinstance(version, int) and version >= 0:
        return version
    if isinstance(version, str) and version.strip():
        return version.strip()
    for field_name in ("last_modified_time", "updated_time", "created_time"):
        value = _raw_attr(business_object, field_name)
        if value is not None:
            return _date_iso_attr(business_object, field_name)
    return None

def _raw_attr(obj: object, name: str) -> object:
    return getattr(obj, name, None)


def _string_attr(obj: object, name: str) -> str:
    value = _raw_attr(obj, name)
    if value is None:
        return ""
    return str(value)


def _int_attr(obj: object, name: str) -> int | None:
    value = _raw_attr(obj, name)
    if value is None:
        return None
    try:
        return int(cast("int | str", value))
    except (TypeError, ValueError):
        return None


def _float_attr(obj: object, name: str) -> float | None:
    value = _raw_attr(obj, name)
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(cast("float | int | str", value))
    except (TypeError, ValueError):
        return None


def _enum_or_string(value: object) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)
    return str(value)


def _date_iso_attr(obj: object, name: str) -> str | None:
    value = _raw_attr(obj, name)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _has_attr_value(obj: object, name: str) -> bool:
    return bool(_raw_attr(obj, name))


def _payload(values: dict[str, JsonValue]) -> JsonObject:
    return values


def _customer_payload(_db: Session | None, customer: object) -> JsonObject:
    return _payload({
        "account_name": _string_attr(customer, "account_name"),
        "industry": _string_attr(customer, "industry") or None,
        "city": _string_attr(customer, "city") or None,
        "address": _string_attr(customer, "address") or None,
        "company_scale": _string_attr(customer, "company_scale") or None,
        "source": _string_attr(customer, "source") or None,
        "status": _int_attr(customer, "status"),
        "owner_id": _string_attr(customer, "owner_id") or None,
        "return_reason": _string_attr(customer, "return_reason") or None,
        "loss_reason": _string_attr(customer, "loss_reason") or None,
    })


def _customer_contact_payload(_db: Session | None, contact: object) -> JsonObject:
    return _payload({
        "name": _string_attr(contact, "name"),
        "gender": _string_attr(contact, "gender") or None,
        "position": _string_attr(contact, "position") or None,
        "is_decision_maker": bool(_raw_attr(contact, "is_decision_maker")),
        "is_primary": bool(_raw_attr(contact, "is_primary")),
        "reports_to": _string_attr(contact, "reports_to") or None,
        "remark": _string_attr(contact, "remark") or None,
    })


def _customer_member_payload(_db: Session | None, member: object) -> JsonObject:
    return _payload({
        "member_id": _int_attr(member, "id"),
        "user_id": _string_attr(member, "user_id"),
        "member_role": _string_attr(member, "member_role"),
        "access_level": _string_attr(member, "access_level"),
        "remark": _string_attr(member, "remark") or None,
        "is_active": bool(_raw_attr(member, "is_active")),
    })


def _opportunity_payload(_db: Session | None, opportunity: object) -> JsonObject:
    return _payload({
        "opportunity_name": _string_attr(opportunity, "opportunity_name"),
        "status": _enum_or_string(_raw_attr(opportunity, "status")),
        "stage_name": _raw_attr(opportunity, "current_stage_name"),
        "win_probability": _int_attr(opportunity, "current_win_probability"),
        "total_amount": _float_attr(opportunity, "total_amount"),
        "expected_closing_date": _date_iso_attr(opportunity, "expected_closing_date"),
        "purchase_type": _enum_or_string(_raw_attr(opportunity, "purchase_type")),
        "license_type": _enum_or_string(_raw_attr(opportunity, "license_type")),
    })


def _contract_payload(_db: Session | None, contract: object) -> JsonObject:
    return _payload({
        "contract_name": _string_attr(contract, "contract_name"),
        "contract_number": _string_attr(contract, "contract_number"),
        "status": _enum_or_string(_raw_attr(contract, "status")),
        "payment_status": _enum_or_string(_raw_attr(contract, "payment_status")),
        "total_amount": _float_attr(contract, "total_amount"),
        "signing_date": _date_iso_attr(contract, "signing_date"),
        "effective_date": _date_iso_attr(contract, "effective_date"),
        "expiry_date": _date_iso_attr(contract, "expiry_date"),
    })


def _payment_plan_contract(db: Session | None, plan: object) -> object | None:
    contract = _raw_attr(plan, "contract")
    if contract is not None:
        return contract
    if db is None:
        return None
    contract_id = _int_attr(plan, "contract_id")
    team_id = _int_attr(plan, "team_id")
    if contract_id is None or team_id is None:
        return None
    return db.query(Contract).filter(
        Contract.id == contract_id,
        Contract.team_id == team_id,
    ).first()


def _payment_plan_customer_id(db: Session | None, plan: object) -> int | None:
    contract = _payment_plan_contract(db, plan)
    if contract is None:
        return None
    return _int_attr(contract, "customer_id")


def _payment_plan_payload(db: Session | None, plan: object) -> JsonObject:
    contract = _payment_plan_contract(db, plan)
    return _payload({
        "stage_name": _string_attr(plan, "stage_name"),
        "plan_number": _string_attr(plan, "plan_number"),
        "planned_amount": _float_attr(plan, "planned_amount"),
        "due_date": _date_iso_attr(plan, "due_date"),
        "status": _enum_or_string(_raw_attr(plan, "status")),
        "contract_name": _string_attr(contract, "contract_name") if contract else None,
    })


def _payment_record_plan(db: Session | None, record: object) -> object | None:
    plan = _raw_attr(record, "payment_plan")
    if plan is not None:
        return plan
    if db is None:
        return None
    plan_id = _int_attr(record, "payment_plan_id")
    team_id = _int_attr(record, "team_id")
    if plan_id is None or team_id is None:
        return None
    return db.query(PaymentPlan).filter(
        PaymentPlan.id == plan_id,
        PaymentPlan.team_id == team_id,
    ).first()


def _payment_record_customer_id(db: Session | None, record: object) -> int | None:
    plan = _payment_record_plan(db, record)
    if plan is None:
        return None
    return _payment_plan_customer_id(db, plan)


def _payment_record_name(db: Session | None, record: object) -> str:
    record_number = _string_attr(record, "record_number")
    if record_number:
        return record_number
    plan = _payment_record_plan(db, record)
    return _string_attr(plan, "stage_name") if plan else ""


def _payment_record_payload(db: Session | None, record: object) -> JsonObject:
    plan = _payment_record_plan(db, record)
    contract = _payment_plan_contract(db, plan) if plan else None
    return _payload({
        "record_number": _string_attr(record, "record_number"),
        "actual_amount": _float_attr(record, "actual_amount"),
        "actual_payer_name": _string_attr(record, "actual_payer_name"),
        "payment_date": _date_iso_attr(record, "payment_date"),
        "confirmation_status": _enum_or_string(_raw_attr(record, "confirmation_status")),
        "approval_phase": _enum_or_string(_raw_attr(record, "approval_phase")),
        "stage_name": _string_attr(plan, "stage_name") if plan else None,
        "contract_name": _string_attr(contract, "contract_name") if contract else None,
    })


def _invoice_title_payload(_db: Session | None, title: object) -> JsonObject:
    return _payload({
        "title_type": _enum_or_string(_raw_attr(title, "title_type")),
        "title": _string_attr(title, "title"),
        "taxpayer_id": _string_attr(title, "taxpayer_id"),
        "has_bank_name": _has_attr_value(title, "bank_name"),
        "has_bank_account": _has_attr_value(title, "bank_account"),
        "has_address": _has_attr_value(title, "address"),
        "has_phone": _has_attr_value(title, "phone"),
        "is_default": bool(_raw_attr(title, "is_default")),
    })


def _invoice_application_payload(_db: Session | None, application: object) -> JsonObject:
    return _payload({
        "application_number": _string_attr(application, "application_number"),
        "invoice_amount": _float_attr(application, "invoice_amount"),
        "invoice_type": _enum_or_string(_raw_attr(application, "invoice_type")),
        "status": _enum_or_string(_raw_attr(application, "status")),
        "approval_phase": _enum_or_string(_raw_attr(application, "approval_phase")),
        "invoice_title_text": _string_attr(application, "invoice_title_text"),
        "invoice_number": _string_attr(application, "invoice_number") or None,
        "contract_id": _int_attr(application, "contract_id"),
        "opportunity_id": _int_attr(application, "opportunity_id"),
        "payment_plan_id": _int_attr(application, "payment_plan_id"),
        "issued_time": _date_iso_attr(application, "issued_time"),
    })


def _deployment_payload(_db: Session | None, deployment: object) -> JsonObject:
    return _payload({
        "deployment_name": _string_attr(deployment, "deployment_name"),
        "authorized_users": _int_attr(deployment, "authorized_users"),
        "is_default": bool(_raw_attr(deployment, "is_default")),
        "has_server_address": _has_attr_value(deployment, "server_address"),
    })


def _license_application_payload(_db: Session | None, application: object) -> JsonObject:
    return _payload({
        "application_number": _string_attr(application, "application_number"),
        "license_type": _enum_or_string(_raw_attr(application, "license_type")),
        "authorized_users": _int_attr(application, "authorized_users"),
        "status": _enum_or_string(_raw_attr(application, "status")),
        "approval_phase": _enum_or_string(_raw_attr(application, "approval_phase")),
        "expiry_date": _date_iso_attr(application, "expiry_date"),
        "deployment_info_id": _int_attr(application, "deployment_info_id"),
        "contract_id": _int_attr(application, "contract_id"),
        "has_enterprise_id": _has_attr_value(application, "enterprise_id"),
        "has_supported_modules": _has_attr_value(application, "supported_modules"),
        "has_server_license_code": _has_attr_value(application, "server_license_code"),
        "has_client_license_code": _has_attr_value(application, "client_license_code"),
        "has_remark": _has_attr_value(application, "remark"),
    })


customer_business_object_intelligence_service = CustomerBusinessObjectIntelligenceService()
