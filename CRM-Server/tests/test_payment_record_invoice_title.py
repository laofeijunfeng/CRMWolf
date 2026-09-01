from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.payments import payment_record_crud
from app.api.payments import router as payments_router
from app.core import deps
from app.core.database import Base
from app.crud.permission import permission_crud
from app.models.invoice import InvoiceApplication
from app.models.payment import PaymentConfirmationStatus


def test_payment_record_list_uses_plan_level_invoice_title_when_record_link_is_null(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[InvoiceApplication.__table__])
    session = sessionmaker(bind=engine)()
    session.execute(
        InvoiceApplication.__table__.insert().values(
            id=1,
            team_id=1,
            application_number="INV-1",
            customer_id=1,
            contract_id=1,
            opportunity_id=1,
            payment_plan_id=42,
            payment_record_id=None,
            invoice_title_id=1,
            invoice_amount=100,
            invoice_type="VAT_NORMAL",
            status="DRAFT",
            approval_phase="draft",
            applicant_id="1",
            invoice_title_type="COMPANY",
            invoice_title_text="按计划关联的发票抬头",
            invoice_taxpayer_id="TAX-1",
        )
    )
    session.commit()

    record = SimpleNamespace(
        id=7,
        payment_plan_id=42,
        record_number="PAY-7",
        actual_amount=100,
        actual_payer_name=None,
        payment_date=datetime(2026, 8, 31).date(),
        proof_attachment=None,
        commission_member_id=None,
        commission_member_name=None,
        notes=None,
        creator_id="1",
        creator_name="测试用户",
        approval_phase="approved",
        confirmation_status=PaymentConfirmationStatus.CONFIRMED,
        created_time=datetime(2026, 8, 31, 10, 0),
        approval_id=None,
        approval=None,
        payment_plan=None,
    )
    monkeypatch.setattr(
        payment_record_crud,
        "list_records",
        lambda *args, **kwargs: ([record], 1),
    )
    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code="payment:view:all")],
    )
    monkeypatch.setattr(
        "app.api.payments.query_pending_approval_me",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "app.api.payments.role_crud.get_user_roles",
        lambda *args, **kwargs: [],
    )

    app = FastAPI()
    app.include_router(payments_router)
    app.dependency_overrides[deps.get_db] = lambda: session
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=1, name="测试用户")
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1

    try:
        with TestClient(app) as client:
            response = client.get("/v1/payments/payment-records")
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["invoice_title_text"] == "按计划关联的发票抬头"
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()
