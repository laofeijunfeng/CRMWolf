"""Business object change boundary for customer intelligence refreshes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Literal, cast

from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.payment import PaymentPlan
from app.services.customer_intelligence_event_service import JsonObject, JsonValue
from app.services.customer_intelligence_refresh_service import (
    CustomerIntelligenceCommittedEventRequest,
    customer_intelligence_refresh_service,
)

CustomerBusinessObjectSourceType = Literal[
    "opportunity",
    "contract",
    "payment_plan",
    "payment_record",
    "invoice_title",
    "invoice_application",
    "deployment_info",
    "license_application",
]
CustomerBusinessObjectChangeType = Literal["created", "updated", "deleted"]


@dataclass(frozen=True)
class CustomerBusinessObjectChangeRefreshInput:
    team_id: int
    customer_id: int
    actor_id: str | None
    source_type: CustomerBusinessObjectSourceType
    source_id: int
    change_type: CustomerBusinessObjectChangeType
    object_name: str
    payload: JsonObject = field(default_factory=dict)


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
    def __init__(self) -> None:
        self._specs: dict[CustomerBusinessObjectSourceType, CustomerBusinessObjectIntelligenceSpec] = {
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
        return self.enqueue_change_refresh(db, change)

    async def trigger_change_refresh(
        self,
        db: Session,
        change: CustomerBusinessObjectChangeRefreshInput,
    ) -> CustomerIntelligenceCommittedEventRequest:
        return await customer_intelligence_refresh_service.trigger_business_object_change_refresh(
            db,
            team_id=change.team_id,
            customer_id=change.customer_id,
            actor_id=change.actor_id,
            source_type=change.source_type,
            source_id=change.source_id,
            change_type=change.change_type,
            summary=self._summary(change),
            payload={
                **change.payload,
                "object_type": change.source_type,
                "object_name": change.object_name,
                "change_type": change.change_type,
            },
        )

    def enqueue_change_refresh(
        self,
        db: Session,
        change: CustomerBusinessObjectChangeRefreshInput,
    ) -> CustomerIntelligenceCommittedEventRequest:
        return customer_intelligence_refresh_service.enqueue_business_object_change_refresh(
            db,
            team_id=change.team_id,
            customer_id=change.customer_id,
            actor_id=change.actor_id,
            source_type=change.source_type,
            source_id=change.source_id,
            change_type=change.change_type,
            summary=self._summary(change),
            payload={
                **change.payload,
                "object_type": change.source_type,
                "object_name": change.object_name,
                "change_type": change.change_type,
            },
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
