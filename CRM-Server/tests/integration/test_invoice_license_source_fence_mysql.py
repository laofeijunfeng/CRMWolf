"""Isolated MySQL regressions for invoice snapshots and serialized License issuance."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.constants.business_types import BusinessType
from app.core.database import SessionLocal, engine
from app.crud.crud_license_application import license_application_crud
from app.crud.invoice import invoice_application_crud
from app.models.approval import Approval, ApprovalStatus
from app.models.contract import Contract, ContractStatus
from app.models.customer import Contact, Customer
from app.models.deal_journey import CustomerDealJourney
from app.models.invoice import InvoiceApplication, InvoiceTitle, InvoiceType
from app.models.license_application import LicenseApplication, LicenseApplicationStatus
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan
from app.models.team import Team
from app.schemas.invoice import InvoiceApplicationCreate
from app.schemas.license_application import LicenseApplicationApprove, LicenseApplicationApproveFull

pytestmark = pytest.mark.integration


def _isolated_mysql() -> bool:
    url = engine.url
    return (
        os.getenv("RUN_MYSQL_INTEGRATION") == "1"
        and url.drivername == "mysql+pymysql"
        and url.username == "root"
        and url.password == "assistant-test-only"
        and url.host == "127.0.0.1"
        and url.port == 3308
        and url.database == "crm_assistant_acceptance"
    )


@pytest.fixture
def invoice_rows():
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"Invoice fence {suffix}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(
            team_id=team.id, account_name=f"Invoice fence {suffix}", city="深圳", creator_id="990126011",
        )
        seed.add(customer)
        seed.flush()
        journey = CustomerDealJourney(team_id=team.id, customer_id=customer.id, name=f"Journey {suffix}")
        seed.add(journey)
        seed.flush()
        opportunity = Opportunity(
            team_id=team.id, opportunity_number=f"OPP{suffix}", opportunity_name=f"Opportunity {suffix}",
            customer_id=customer.id, deal_journey_id=journey.id, total_amount=Decimal("500.00"),
            user_count=1, unit_price=Decimal("500.00"), license_type="PERPETUAL", purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31), owner_id="990126011", creator_id="990126011",
        )
        seed.add(opportunity)
        seed.flush()
        signing_contact = Contact(
            team_id=team.id, customer_id=customer.id, name=f"Signing contact {suffix}", mobile="13800000000",
        )
        seed.add(signing_contact)
        seed.flush()
        contracts = [
            Contract(
                team_id=team.id, contract_number=f"CT{suffix}{index}", contract_name=f"Contract {index}",
                customer_id=customer.id, opportunity_id=opportunity.id, deal_journey_id=journey.id,
                signing_contact_id=signing_contact.id,
                user_count=1, total_amount=Decimal("500.00"), license_type="PERPETUAL",
                standard_unit_price=Decimal("500.00"), status=ContractStatus.SIGNED,
                owner_id="990126011", creator_id="990126011",
            )
            for index in (1, 2)
        ]
        seed.add_all(contracts)
        seed.flush()
        plan = PaymentPlan(
            team_id=team.id, contract_id=contracts[0].id, deal_journey_id=journey.id,
            plan_number=f"PP{suffix}", stage_name="First", planned_amount=Decimal("500.00"),
            due_date=date(2026, 12, 31),
        )
        title = InvoiceTitle(
            team_id=team.id, customer_id=customer.id, title_type="COMPANY",
            title=f"Old title {suffix}", taxpayer_id=f"TAX{suffix}",
        )
        seed.add_all([plan, title])
        seed.commit()
        ids = (team.id, customer.id, journey.id, contracts[0].id, contracts[1].id, plan.id, title.id)

    try:
        yield ids
    finally:
        team_id, customer_id, journey_id, contract_id, other_contract_id, plan_id, title_id = ids
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "journey": journey_id,
                      "plan": plan_id, "title": title_id}
            cleanup.execute(text("DELETE FROM crm_customer_deal_journey_events WHERE team_id=:team AND deal_journey_id=:journey"), params)
            cleanup.execute(text("DELETE FROM crm_invoice_applications WHERE team_id=:team AND payment_plan_id=:plan"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_invoice_titles WHERE team_id=:team AND id=:title"), params)
            cleanup.execute(text("DELETE FROM crm_contract_payment_plans WHERE team_id=:team AND id=:plan"), params)
            cleanup.execute(text("DELETE FROM crm_contracts WHERE team_id=:team AND id IN (:first, :second)"),
                            {"team": team_id, "first": contract_id, "second": other_contract_id})
            cleanup.execute(text("DELETE FROM crm_opportunities WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_deal_journeys WHERE team_id=:team AND id=:journey"), params)
            cleanup.execute(text("DELETE FROM crm_contacts WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_invoice_snapshot_uses_title_committed_after_repeatable_read_started(invoice_rows, monkeypatch):
    team_id, customer_id, _, _, _, plan_id, title_id = invoice_rows
    suffix = uuid4().hex
    monkeypatch.setattr("app.crud.invoice.BusinessNumberGenerator.generate", lambda prefix, db: f"{prefix}{suffix}")
    request = InvoiceApplicationCreate(
        payment_plan_id=plan_id, invoice_title_id=title_id,
        invoice_amount=Decimal("125.00"), invoice_type=InvoiceType.VAT_NORMAL,
    )
    with SessionLocal() as stale, SessionLocal() as updater:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        assert stale.query(InvoiceTitle).filter_by(id=title_id).one().title.startswith("Old title")
        updater.execute(
            text("UPDATE crm_invoice_titles SET title=:title, taxpayer_id=:tax WHERE id=:id AND team_id=:team"),
            {"title": f"Current title {suffix}", "tax": f"CURRENT{suffix}", "id": title_id, "team": team_id},
        )
        updater.commit()
        created = invoice_application_crud.create(stale, request, "990126011", team_id)
        assert (created.customer_id, created.invoice_title_text, created.invoice_taxpayer_id) == (
            customer_id, f"Current title {suffix}", f"CURRENT{suffix}",
        )
        with SessionLocal() as persisted:
            invoice = persisted.query(InvoiceApplication).filter_by(id=created.id, team_id=team_id).one()
            assert (invoice.invoice_title_text, invoice.invoice_taxpayer_id) == (f"Current title {suffix}", f"CURRENT{suffix}")


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_invoice_rejects_plan_reassigned_after_repeatable_read_started(invoice_rows, monkeypatch):
    team_id, _, _, original_contract_id, other_contract_id, plan_id, title_id = invoice_rows
    suffix = uuid4().hex
    monkeypatch.setattr("app.crud.invoice.BusinessNumberGenerator.generate", lambda prefix, db: f"{prefix}{suffix}")
    with SessionLocal() as stale, SessionLocal() as updater:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        assert stale.query(PaymentPlan).filter_by(id=plan_id).one().contract_id == original_contract_id
        updater.execute(
            text("UPDATE crm_contract_payment_plans SET contract_id=:contract WHERE id=:id AND team_id=:team"),
            {"contract": other_contract_id, "id": plan_id, "team": team_id},
        )
        updater.commit()
        with pytest.raises(ValueError, match="回款计划所属合同已变更"):
            invoice_application_crud.create(stale, InvoiceApplicationCreate(
                payment_plan_id=plan_id, invoice_title_id=title_id,
                invoice_amount=Decimal("125.00"), invoice_type=InvoiceType.VAT_NORMAL,
            ), "990126011", team_id)
        stale.rollback()
        with SessionLocal() as persisted:
            assert persisted.query(InvoiceApplication).filter_by(team_id=team_id, payment_plan_id=plan_id).count() == 0


@pytest.fixture
def license_rows():
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"License fence {suffix}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(
            team_id=team.id, account_name=f"License fence {suffix}", city="深圳", creator_id="990126011",
        )
        seed.add(customer)
        seed.flush()
        application = LicenseApplication(
            team_id=team.id, customer_id=customer.id, application_number=f"LIC{suffix}",
            expiry_date=date(2027, 12, 31), license_type="TRIAL", authorized_users=1,
            applicant_id="990126011", status=LicenseApplicationStatus.APPROVED,
        )
        seed.add(application)
        seed.flush()
        approval = Approval(
            team_id=team.id, business_type=BusinessType.LICENSE, business_id=application.id,
            status=ApprovalStatus.APPROVED, submitter_id="990126011",
        )
        seed.add(approval)
        seed.commit()
        ids = (team.id, customer.id, application.id, approval.id)
    try:
        yield ids
    finally:
        team_id, customer_id, application_id, approval_id = ids
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "application": application_id, "approval": approval_id}
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_contract_approvals WHERE team_id=:team AND id=:approval"), params)
            cleanup.execute(text("DELETE FROM crm_license_applications WHERE team_id=:team AND id=:application"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
@pytest.mark.parametrize("full", [False, True], ids=["simple", "full"])
def test_license_issue_checks_locked_current_status_after_competing_issue(license_rows, full):
    team_id, _, application_id, _ = license_rows
    reached_application_read = Event()

    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if "crm_license_applications.customer_id" in statement and "FOR UPDATE" not in statement:
            # The scalar lookup establishes the issuer's RR snapshot while the
            # competing transaction has only an uncommitted status change.
            reached_application_read.set()

    def issue():
        with SessionLocal() as issuer:
            if full:
                return license_application_crud.issue_full(
                    issuer, team_id, application_id,
                    LicenseApplicationApproveFull(license_info="Enterprise ID: 12345"), "990126011",
                )
            return license_application_crud.issue(
                issuer, team_id, application_id,
                LicenseApplicationApprove(license_code="second-issue"), "990126011",
            )

    with SessionLocal() as winner, ThreadPoolExecutor(max_workers=1) as pool:
        assert winner.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        row = winner.query(LicenseApplication).filter_by(id=application_id, team_id=team_id).with_for_update().one()
        row.status = LicenseApplicationStatus.ISSUED
        row.license_code = "first-issue"
        winner.flush()
        event.listen(engine, "after_cursor_execute", after_cursor_execute)
        try:
            loser = pool.submit(issue)
            assert reached_application_read.wait(5), "issuer did not reach application lookup"
            winner.commit()
            with pytest.raises(ValueError, match="License申请已发放"):
                loser.result(timeout=15)
        finally:
            winner.rollback()
            event.remove(engine, "after_cursor_execute", after_cursor_execute)

    with SessionLocal() as persisted:
        row = persisted.query(LicenseApplication).filter_by(id=application_id, team_id=team_id).one()
        assert (row.status, row.license_code) == (LicenseApplicationStatus.ISSUED, "first-issue")

@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_license_issue_rejects_approval_revoked_after_repeatable_read_started(license_rows):
    team_id, _, application_id, approval_id = license_rows
    with SessionLocal() as stale, SessionLocal() as updater:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        assert stale.query(Approval).filter_by(id=approval_id).one().status == ApprovalStatus.APPROVED
        updater.execute(
            text("UPDATE crm_contract_approvals SET status=:status WHERE id=:id AND team_id=:team"),
            {"status": ApprovalStatus.REJECTED, "id": approval_id, "team": team_id},
        )
        updater.commit()
        with pytest.raises(ValueError, match="License申请未通过审批"):
            license_application_crud.issue(
                stale, team_id, application_id, LicenseApplicationApprove(license_code="stale"), "990126011",
            )
        stale.rollback()
        with SessionLocal() as persisted:
            row = persisted.query(LicenseApplication).filter_by(id=application_id, team_id=team_id).one()
            assert row.status == LicenseApplicationStatus.APPROVED
            assert row.license_code is None


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_license_issue_uses_expiry_committed_after_repeatable_read_started(license_rows):
    team_id, customer_id, application_id, _ = license_rows
    current_expiry = date(2028, 12, 31)
    with SessionLocal() as stale, SessionLocal() as updater:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        assert stale.query(LicenseApplication).filter_by(id=application_id).one().expiry_date == date(2027, 12, 31)
        updater.execute(
            text("UPDATE crm_license_applications SET expiry_date=:expiry WHERE id=:id AND team_id=:team"),
            {"expiry": current_expiry, "id": application_id, "team": team_id},
        )
        updater.commit()
        issued = license_application_crud.issue(
            stale, team_id, application_id, LicenseApplicationApprove(license_code="current-expiry"), "990126011",
        )
        assert issued.expiry_date == current_expiry
        with SessionLocal() as persisted:
            customer = persisted.query(Customer).filter_by(id=customer_id, team_id=team_id).one()
            assert customer.license_expiry_date == current_expiry
            assert customer.license_type == "TRIAL"
