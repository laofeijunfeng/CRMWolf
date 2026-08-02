from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.models.approval import ApprovalAction, ApprovalStatus
from app.models.license_application import LicenseApplicationStatus
from app.services import customer_approval_intelligence_service as service_module
from app.services.customer_approval_intelligence_service import (
    CustomerApprovalChangeRefreshInput,
    CustomerApprovalIntelligenceService,
)


def test_customer_approval_intelligence_enqueues_license_change(monkeypatch) -> None:
    calls = []
    application = SimpleNamespace(
        id=1001,
        team_id=2,
        customer_id=101,
        application_number="LIC-202608-001",
        deployment_info_id=901,
        contract_id=401,
        expiry_date=date(2027, 8, 2),
        license_type="OFFICIAL",
        enterprise_id=None,
        supported_modules="desktop,web",
        server_license_code="server-secret",
        client_license_code=None,
        remark="正式授权",
        status=LicenseApplicationStatus.APPROVED,
        approval_phase=ApprovalPhase.APPROVED.value,
    )
    approval = SimpleNamespace(status=ApprovalStatus.APPROVED)

    def fake_enqueue(db, change):
        calls.append(change)
        return object()

    monkeypatch.setattr(
        service_module.customer_business_object_intelligence_service,
        "enqueue_change_refresh",
        fake_enqueue,
    )

    result = CustomerApprovalIntelligenceService().enqueue_approval_change_refresh(
        object(),
        CustomerApprovalChangeRefreshInput(
            entity_type=BusinessType.LICENSE,
            entity=application,
            approval=approval,
            actor_id="9",
            action=ApprovalAction.APPROVE,
        ),
    )

    assert result is calls[0]
    assert calls[0].source_type == "license_application"
    assert calls[0].source_id == 1001
    assert calls[0].change_type == "updated"
    assert calls[0].payload["approval_status"] == ApprovalStatus.APPROVED
    assert calls[0].payload["approval_action"] == ApprovalAction.APPROVE
    assert calls[0].payload["has_server_license_code"] is True
    assert "server-secret" not in calls[0].payload.values()


def test_customer_approval_intelligence_enqueues_invoice_change(monkeypatch) -> None:
    calls = []
    application = SimpleNamespace(
        id=701,
        team_id=2,
        customer_id=101,
        application_number="INV-20260802-0001",
        invoice_amount=Decimal("50000"),
        invoice_type="VAT_SPECIAL",
        status="APPROVED",
        approval_phase=ApprovalPhase.APPROVED.value,
        invoice_title_text="越秀金融科技有限公司",
        invoice_number=None,
        contract_id=401,
        opportunity_id=301,
        payment_plan_id=501,
        issued_time=None,
    )
    approval = SimpleNamespace(status=ApprovalStatus.APPROVED)

    def fake_enqueue(db, change):
        calls.append(change)
        return object()

    monkeypatch.setattr(
        service_module.customer_business_object_intelligence_service,
        "enqueue_change_refresh",
        fake_enqueue,
    )

    CustomerApprovalIntelligenceService().enqueue_approval_change_refresh(
        object(),
        CustomerApprovalChangeRefreshInput(
            entity_type=BusinessType.INVOICE,
            entity=application,
            approval=approval,
            actor_id="9",
            action=ApprovalAction.APPROVE,
        ),
    )

    assert calls[0].source_type == "invoice_application"
    assert calls[0].source_id == 701
    assert calls[0].payload["invoice_amount"] == 50000.0
    assert calls[0].payload["approval_status"] == ApprovalStatus.APPROVED


def test_customer_approval_intelligence_skips_unsupported_business_type(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        service_module.customer_business_object_intelligence_service,
        "enqueue_change_refresh",
        lambda db, change: calls.append(change),
    )

    result = CustomerApprovalIntelligenceService().enqueue_approval_change_refresh(
        object(),
        CustomerApprovalChangeRefreshInput(
            entity_type=BusinessType.CONTRACT,
            entity=SimpleNamespace(),
            approval=SimpleNamespace(status=ApprovalStatus.APPROVED),
            actor_id="9",
            action=ApprovalAction.APPROVE,
        ),
    )

    assert result is None
    assert calls == []
