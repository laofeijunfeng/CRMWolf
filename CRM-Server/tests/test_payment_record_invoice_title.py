from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.payments import payment_record_crud
from app.api.payments import router as payments_router
from app.core import deps
from app.core.database import Base
from app.crud.permission import permission_crud
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import InvoiceApplication
from app.models.opportunity import Opportunity
from app.models.payment import PaymentConfirmationStatus, PaymentPlan, PaymentPlanStatus
from app.models.user import User


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_payment_record_list_uses_plan_level_invoice_title_when_record_link_is_null(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Customer.__table__,
            Opportunity.__table__,
            Contract.__table__,
            PaymentPlan.__table__,
            InvoiceApplication.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, email="user1@example.com", name="测试用户"))
    session.add(Customer(
        id=1,
        public_id="cus_00000000000000000000000000000001",
        team_id=1,
        account_name="测试客户",
        city="上海",
        creator_id="1",
    ))
    session.add(Opportunity(
        id=1,
        public_id="opp_00000000000000000000000000000001",
        team_id=1,
        opportunity_number="OPP-001",
        opportunity_name="测试商机",
        customer_id=1,
        total_amount=Decimal("1000"),
        user_count=10,
        unit_price=Decimal("100"),
        license_type="SUBSCRIPTION",
        purchase_type="NEW",
        expected_closing_date=date(2026, 12, 31),
        owner_id="1",
        creator_id="1",
    ))
    session.add(Contract(
        id=1,
        team_id=1,
        contract_number="CT-001",
        contract_name="测试合同",
        customer_id=1,
        opportunity_id=1,
        user_count=10,
        total_amount=Decimal("1000"),
        license_type="SUBSCRIPTION",
        standard_unit_price=Decimal("100"),
        owner_id="1",
        creator_id="1",
    ))
    session.add(PaymentPlan(
        id=42,
        team_id=1,
        contract_id=1,
        plan_number="PP-042",
        stage_name="首付款",
        planned_amount=Decimal("1000.00"),
        due_date=date(2026, 9, 10),
        status=PaymentPlanStatus.PENDING,
    ))
    session.flush()
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
