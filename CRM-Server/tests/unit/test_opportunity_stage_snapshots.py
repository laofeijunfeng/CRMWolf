from datetime import date

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.procurement import opportunity_stage_snapshot_crud
from app.models.customer import Customer
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.opportunity import Opportunity
from app.models.procurement import (
    OpportunityStageSnapshot,
    ProcurementMethod,
    ProcurementStageTemplate,
)


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stage-snapshots.db'}")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_duplicate_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerLegacySourceProgress.__table__,
            Opportunity.__table__,
            ProcurementMethod.__table__,
            ProcurementStageTemplate.__table__,
            OpportunityStageSnapshot.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add_all([
        Customer(id=1, public_id="cus-stage-1", team_id=7, account_name="客户一", city="北京", creator_id="owner"),
        Customer(id=2, public_id="cus-stage-2", team_id=7, account_name="客户二", city="上海", creator_id="owner"),
        Opportunity(
            id=3, public_id="opp-stage-3", team_id=7, customer_id=1,
            opportunity_number="STAGE-3", opportunity_name="商机", total_amount=100,
            user_count=1, unit_price=100, license_type="PERPETUAL", purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31), owner_id="owner", creator_id="owner",
        ),
        ProcurementMethod(id=4, team_id=7, code="method", name="采购方式", sort_order=1, created_by="owner"),
        ProcurementStageTemplate(
            id=5, team_id=7, procurement_method_id=4, template_code="initial",
            stage_name="初始阶段", win_probability=10, sort_order=1,
            is_default_start=1, created_by="owner",
        ),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _revision(db, customer_id=1):
    row = db.query(CustomerLegacySourceProgress).filter_by(customer_id=customer_id, team_id=7).one_or_none()
    return 0 if row is None else row.eligible_revision


def test_direct_snapshot_creation_holds_customer_fence_and_commits_progress_with_snapshot(db, monkeypatch):
    from app.crud import procurement

    stage = db.get(ProcurementStageTemplate, 5)
    original_lock = procurement.lock_source_customer
    locked_customers = []

    def trace_lock(session, *, team_id, customer_id):
        customer = original_lock(session, team_id=team_id, customer_id=customer_id)
        locked_customers.append(customer.id)
        return customer

    monkeypatch.setattr(procurement, "lock_source_customer", trace_lock)
    snapshot = opportunity_stage_snapshot_crud.create(db, 3, stage, commit=False)
    assert locked_customers == [1]
    assert snapshot.id is not None
    assert _revision(db) == 1

    db.rollback()
    assert db.query(OpportunityStageSnapshot).count() == 0
    assert _revision(db) == 0

    snapshot = opportunity_stage_snapshot_crud.create(db, 3, stage)
    assert locked_customers == [1, 1]
    assert snapshot.id is not None
    db.expire_all()
    assert db.query(OpportunityStageSnapshot).count() == 1
    assert _revision(db) == 1

    with pytest.raises(ValueError, match="已有阶段"):
        opportunity_stage_snapshot_crud.create(db, 3, stage, commit=False)
    assert db.query(OpportunityStageSnapshot).count() == 1
    assert _revision(db) == 1


def test_rebinding_after_customer_lock_rejects_stale_snapshot_without_progress(db, monkeypatch):
    from app.crud import procurement

    stage = db.get(ProcurementStageTemplate, 5)
    original_lock = procurement.lock_source_customer

    def concurrent_rebind(session, *, team_id, customer_id):
        customer = original_lock(session, team_id=team_id, customer_id=customer_id)
        session.query(Opportunity).filter_by(id=3).update({"customer_id": 2}, synchronize_session=False)
        return customer

    monkeypatch.setattr(procurement, "lock_source_customer", concurrent_rebind)
    with pytest.raises(ValueError, match="客户归属已变更"):
        opportunity_stage_snapshot_crud.create(db, 3, stage, commit=False)
    assert db.query(OpportunityStageSnapshot).count() == 0
    assert _revision(db) == 0
    assert _revision(db, 2) == 0


def test_direct_snapshot_creation_rejects_terminal_opportunity_without_progress(db):
    opportunity = db.get(Opportunity, 3)
    opportunity.status = 1
    db.commit()

    with pytest.raises(ValueError, match="跟进中"):
        opportunity_stage_snapshot_crud.create(db, 3, db.get(ProcurementStageTemplate, 5), commit=False)

    assert db.query(OpportunityStageSnapshot).count() == 0
    assert _revision(db) == 0
