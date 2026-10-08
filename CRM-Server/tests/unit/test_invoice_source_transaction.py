"""Invoice source revisions and journey events share the business transaction."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.business_types import BusinessType
from app.core.database import Base
from app.crud.invoice import invoice_application_crud
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent, DealJourneyEventType
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceTitle, InvoiceType
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.schemas.invoice import InvoiceApplicationCreate, InvoiceApplicationUpdate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kwargs):
    return "INTEGER"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(engine, tables=[
        Customer.__table__, CustomerLegacySourceProgress.__table__,
        Opportunity.__table__, Contract.__table__, PaymentPlan.__table__,
        InvoiceTitle.__table__, InvoiceApplication.__table__,
        CustomerDealJourney.__table__, CustomerDealJourneyEvent.__table__,
        Approval.__table__,
    ])
    session = sessionmaker(bind=engine)()
    session.add_all([
        Customer(id=1, team_id=1, account_name="Invoice customer", city="Beijing", creator_id="1"),
        Opportunity(
            id=1, team_id=1, opportunity_number="OPP-1", opportunity_name="Opportunity",
            customer_id=1, total_amount=Decimal("1000"), user_count=10,
            unit_price=Decimal("100"), license_type="SUBSCRIPTION", purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31), owner_id="1", creator_id="1",
        ),
        CustomerDealJourney(id=1, team_id=1, customer_id=1, name="Journey"),
        Contract(
            id=1, team_id=1, contract_number="CT-1", contract_name="Contract",
            customer_id=1, opportunity_id=1, deal_journey_id=1, user_count=10,
            total_amount=Decimal("1000"), license_type="SUBSCRIPTION",
            standard_unit_price=Decimal("100"), owner_id="1", creator_id="1",
        ),
        PaymentPlan(
            id=1, team_id=1, contract_id=1, deal_journey_id=1,
            plan_number="PP-1", stage_name="First", planned_amount=Decimal("1000"),
            due_date=date(2026, 10, 1),
        ),
        InvoiceTitle(
            id=1, team_id=1, customer_id=1, title_type="COMPANY",
            title="Invoice title", taxpayer_id="TAX-1",
        ),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _revision(db):
    progress = db.query(CustomerLegacySourceProgress).filter_by(team_id=1, customer_id=1).one_or_none()
    return progress.eligible_revision if progress else 0


def _event_types(db):
    return [row.event_type for row in db.query(CustomerDealJourneyEvent).order_by(CustomerDealJourneyEvent.id)]


def test_invoice_create_and_issue_rollback_when_qualified_event_cannot_be_written(db):
    request = InvoiceApplicationCreate(
        payment_plan_id=1, invoice_title_id=1,
        invoice_amount=Decimal("800"), invoice_type=InvoiceType.VAT_NORMAL,
    )

    def reject_event(mapper, connection, target):
        raise RuntimeError("journey insertion interrupted")

    event.listen(CustomerDealJourneyEvent, "before_insert", reject_event)
    try:
        with pytest.raises(RuntimeError, match="journey insertion interrupted"):
            invoice_application_crud.create(db, request, "1", 1)
    finally:
        event.remove(CustomerDealJourneyEvent, "before_insert", reject_event)
    db.rollback()
    assert db.query(InvoiceApplication).count() == 0
    assert _event_types(db) == []
    assert _revision(db) == 0

    application = invoice_application_crud.create(db, request, "1", 1)
    assert _event_types(db) == [DealJourneyEventType.INVOICE_APPLIED]
    assert _revision(db) == 2  # invoice row and qualifying event

    application.status = InvoiceApplicationStatus.APPROVED
    db.add(Approval(
        team_id=1, business_type=BusinessType.INVOICE, business_id=application.id,
        status=ApprovalStatus.APPROVED, submitter_id="1",
    ))
    db.commit()
    event.listen(CustomerDealJourneyEvent, "before_insert", reject_event)
    try:
        with pytest.raises(RuntimeError, match="journey insertion interrupted"):
            invoice_application_crud.mark_issued(db, application.id, team_id=1, invoice_number="NO-1")
    finally:
        event.remove(CustomerDealJourneyEvent, "before_insert", reject_event)
    db.rollback()
    db.refresh(application)
    assert application.status == InvoiceApplicationStatus.APPROVED
    assert application.invoice_number is None
    assert _event_types(db) == [DealJourneyEventType.INVOICE_APPLIED]
    assert _revision(db) == 2

    issued = invoice_application_crud.mark_issued(db, application.id, team_id=1, invoice_number="NO-1")
    assert issued.status == InvoiceApplicationStatus.ISSUED
    assert _event_types(db) == [DealJourneyEventType.INVOICE_APPLIED, DealJourneyEventType.INVOICE_ISSUED]
    assert _revision(db) == 4


def test_invoice_update_advances_only_when_invoice_changes(db):
    application = invoice_application_crud.create(db, InvoiceApplicationCreate(
        payment_plan_id=1, invoice_title_id=1,
        invoice_amount=Decimal("800"), invoice_type=InvoiceType.VAT_NORMAL,
    ), "1", 1)
    assert _revision(db) == 2
    invoice_application_crud.update(db, application, InvoiceApplicationUpdate(invoice_amount=Decimal("800")))
    assert _revision(db) == 2
    updated = invoice_application_crud.update(db, application, InvoiceApplicationUpdate(invoice_amount=Decimal("900")))
    assert updated.invoice_amount == Decimal("900")
    assert _revision(db) == 3
    assert _event_types(db) == [DealJourneyEventType.INVOICE_APPLIED]


def test_invoice_update_checks_locked_current_status_not_stale_instance(db):
    application = invoice_application_crud.create(db, InvoiceApplicationCreate(
        payment_plan_id=1, invoice_title_id=1,
        invoice_amount=Decimal("800"), invoice_type=InvoiceType.VAT_NORMAL,
    ), "1", 1)
    # A previously loaded ORM invoice must not authorize an edit against a newer status.
    db.connection().exec_driver_sql(
        "UPDATE crm_invoice_applications SET status = 'APPROVED' WHERE id = ?", (application.id,),
    )
    assert application.status == InvoiceApplicationStatus.DRAFT

    with pytest.raises(ValueError, match="只有草稿或已拒绝状态"):
        invoice_application_crud.update(db, application, InvoiceApplicationUpdate(invoice_amount=Decimal("900")))
    db.rollback()
    assert db.query(InvoiceApplication).filter_by(id=application.id).one().invoice_amount == Decimal("800")
    assert _revision(db) == 2
