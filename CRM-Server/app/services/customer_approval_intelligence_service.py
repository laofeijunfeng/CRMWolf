"""Customer intelligence refreshes for approval state changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.models.approval import Approval
from app.models.invoice import InvoiceApplication
from app.models.license_application import LicenseApplication
from app.services.customer_business_object_intelligence_service import (
    CustomerBusinessObjectChangeRefreshInput,
    customer_business_object_intelligence_service,
)

ApprovalSupportedEntity: TypeAlias = InvoiceApplication | LicenseApplication
ApprovalSupportedSourceType: TypeAlias = Literal["invoice_application", "license_application"]


@dataclass(frozen=True)
class CustomerApprovalChangeRefreshInput:
    entity_type: str
    entity: ApprovalSupportedEntity
    approval: Approval
    actor_id: str | None
    action: str


class CustomerApprovalIntelligenceService:
    """Converts committed approval transitions into customer intelligence events."""

    def enqueue_approval_change_refresh(
        self,
        db: Session,
        change: CustomerApprovalChangeRefreshInput,
    ) -> CustomerBusinessObjectChangeRefreshInput | None:
        source_type = self._source_type(change.entity_type)
        if source_type is None:
            return None
        refresh_input = CustomerBusinessObjectChangeRefreshInput(
            team_id=int(change.entity.team_id),
            customer_id=int(change.entity.customer_id),
            actor_id=change.actor_id,
            source_type=source_type,
            source_id=int(change.entity.id),
            change_type="updated",
            object_name=self._object_name(source_type, change.entity),
            payload={
                **self._entity_payload(source_type, change.entity),
                "approval_status": change.approval.status,
                "approval_action": change.action,
            },
        )
        customer_business_object_intelligence_service.enqueue_change_refresh(db, refresh_input)
        return refresh_input

    def _source_type(self, entity_type: str) -> ApprovalSupportedSourceType | None:
        if entity_type == BusinessType.INVOICE:
            return "invoice_application"
        if entity_type == BusinessType.LICENSE:
            return "license_application"
        return None

    def _object_name(self, source_type: ApprovalSupportedSourceType, entity: ApprovalSupportedEntity) -> str:
        if source_type == "invoice_application":
            return str(entity.application_number or entity.invoice_title_text or "发票申请")
        return str(entity.application_number or "License申请")

    def _entity_payload(
        self,
        source_type: ApprovalSupportedSourceType,
        entity: ApprovalSupportedEntity,
    ) -> dict[str, str | int | float | bool | None]:
        if source_type == "invoice_application":
            return {
                "application_number": entity.application_number,
                "invoice_amount": float(entity.invoice_amount) if entity.invoice_amount is not None else None,
                "invoice_type": entity.invoice_type,
                "status": entity.status,
                "approval_phase": getattr(entity.approval_phase, "value", entity.approval_phase),
                "invoice_title_text": entity.invoice_title_text,
                "invoice_number": entity.invoice_number,
                "contract_id": int(entity.contract_id) if entity.contract_id is not None else None,
                "opportunity_id": int(entity.opportunity_id) if entity.opportunity_id is not None else None,
                "payment_plan_id": int(entity.payment_plan_id) if entity.payment_plan_id is not None else None,
                "issued_time": entity.issued_time.isoformat() if entity.issued_time else None,
            }
        return {
            "application_number": entity.application_number,
            "license_type": entity.license_type,
            "status": entity.status,
            "approval_phase": getattr(entity.approval_phase, "value", entity.approval_phase),
            "expiry_date": entity.expiry_date.isoformat() if entity.expiry_date else None,
            "deployment_info_id": int(entity.deployment_info_id) if entity.deployment_info_id else None,
            "contract_id": int(entity.contract_id) if entity.contract_id else None,
            "has_enterprise_id": bool(entity.enterprise_id),
            "has_supported_modules": bool(entity.supported_modules),
            "has_server_license_code": bool(entity.server_license_code),
            "has_client_license_code": bool(entity.client_license_code),
            "has_remark": bool(entity.remark),
        }


customer_approval_intelligence_service = CustomerApprovalIntelligenceService()
