"""Catalog source changes must advance the same customer fence as profile publication."""

from datetime import date

from sqlalchemy.orm import sessionmaker

from app.crud.product import product_crud
from app.models.customer import Customer, CustomerProduct
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.lead import Lead, LeadProduct
from app.models.opportunity import Opportunity
from app.models.team import Team
from app.models.user import User
from app.schemas.product import ProductCreate, ProductModuleCreate, ProductModuleUpdate, ProductUpdate
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from tests.unit.test_customer_intelligence_context_service import _session


def _catalog_state(sessions, customer_id: int) -> tuple[int, int, str, list[dict]]:
    with sessions() as db:
        context = CustomerIntelligenceContextService()._build_strong_context(
            db, customer=db.get(Customer, customer_id), team_id=1,
        )
        watermark = context.source_watermarks
        progress = db.query(CustomerLegacySourceProgress).filter_by(team_id=1, customer_id=customer_id).one_or_none()
        return (
            int(watermark["eligible_revision"]),
            int(watermark["deletion_revision"]),
            str(watermark["source_snapshot_hash"]),
            context.product_catalog,
        )


def _setup_catalog():
    engine, writer = _session()
    User.__table__.create(engine, checkfirst=True)
    writer.add(User(id=1, email="catalog@example.com", name="Catalog"))
    writer.flush()
    Lead.__table__.create(engine, checkfirst=True)
    LeadProduct.__table__.create(engine, checkfirst=True)
    Team.__table__.create(engine, checkfirst=True)
    writer.add(Team(id=1, name="catalog", code="CATALOG", owner_id=1))
    writer.add_all([
        Customer(id=101, team_id=1, account_name="甲", city="广州", creator_id="1"),
        Customer(id=102, team_id=1, account_name="乙", city="广州", creator_id="1"),
    ])
    writer.commit()
    return engine, writer, sessionmaker(bind=engine)


def test_active_product_catalog_create_rename_deactivate_and_delete_advance_every_customer():
    engine, writer, sessions = _setup_catalog()
    try:
        initial = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}
        product = product_crud.create(writer, 1, ProductCreate(name="原产品"), "1")
        created = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}
        for cid in (101, 102):
            assert created[cid][:2] == (initial[cid][0] + 1, initial[cid][1])
            assert created[cid][2] != initial[cid][2]
            assert [row["name"] for row in created[cid][3]] == ["原产品"]

        product_crud.update(writer, product, ProductUpdate(name="新产品"), "2")
        renamed = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}
        for cid in (101, 102):
            assert renamed[cid][:2] == (created[cid][0] + 1, created[cid][1])
            assert renamed[cid][2] != created[cid][2]
            assert [row["name"] for row in renamed[cid][3]] == ["新产品"]
        product_crud.update(writer, product, ProductUpdate(description="只更新描述"), "2")
        assert {cid: _catalog_state(sessions, cid) for cid in (101, 102)} == renamed

        product_crud.update(writer, product, ProductUpdate(name="新产品"), "2")
        assert {cid: _catalog_state(sessions, cid) for cid in (101, 102)} == renamed

        product_crud.update(writer, product, ProductUpdate(is_active=False), "2")
        inactive = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}
        for cid in (101, 102):
            assert inactive[cid][:2] == (renamed[cid][0] + 1, renamed[cid][1])
            assert inactive[cid][2] != renamed[cid][2]
            assert inactive[cid][3] == []

        product_crud.delete(writer, product)
        for cid in (101, 102):
            assert _catalog_state(sessions, cid) == inactive[cid]
    finally:
        writer.close()
        engine.dispose()

def test_deleting_active_product_advances_deletion_progress_with_catalog_removal():
    engine, writer, sessions = _setup_catalog()
    try:
        product = product_crud.create(writer, 1, ProductCreate(name="产品"), "1")
        before = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}

        product_crud.delete(writer, product)
        for cid in (101, 102):
            revision, deleted, snapshot_hash, catalog = _catalog_state(sessions, cid)
            assert (revision, deleted) == (before[cid][0] + 1, before[cid][1] + 1)
            assert snapshot_hash != before[cid][2]
            assert catalog == []
    finally:
        writer.close()
        engine.dispose()


def test_inactive_product_rename_advances_only_customer_whose_intent_uses_it():
    engine, writer, sessions = _setup_catalog()
    try:
        product = product_crud.create(writer, 1, ProductCreate(name="原产品"), "1")
        writer.add(CustomerProduct(customer_id=101, product_id=product.id, team_id=1))
        writer.commit()
        product_crud.update(writer, product, ProductUpdate(is_active=False), "2")
        before = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}

        product_crud.update(writer, product, ProductUpdate(name="改名后"), "2")
        linked = _catalog_state(sessions, 101)
        unrelated = _catalog_state(sessions, 102)
        assert linked[0] == before[101][0] + 1
        assert linked[2] != before[101][2]
        assert linked[3] == []
        assert unrelated == before[102]
    finally:
        writer.close()
        engine.dispose()

def test_inactive_product_rename_advances_customer_with_opportunity_product():
    engine, writer, sessions = _setup_catalog()
    try:
        product = product_crud.create(writer, 1, ProductCreate(name="原产品"), "1")
        writer.add(Opportunity(
            id=301, team_id=1, customer_id=102, product_id=product.id,
            opportunity_number="OPP-CATALOG", opportunity_name="采购项目", total_amount=100,
            user_count=1, unit_price=100, license_type="PERPETUAL", purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31),
            owner_id="1", creator_id="1",
        ))
        writer.commit()
        product_crud.update(writer, product, ProductUpdate(is_active=False), "2")
        before = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}

        product_crud.update(writer, product, ProductUpdate(name="商机产品新名"), "2")
        assert _catalog_state(sessions, 101) == before[101]
        assert _catalog_state(sessions, 102)[0] == before[102][0] + 1
        assert _catalog_state(sessions, 102)[2] != before[102][2]
        with sessions() as db:
            context = CustomerIntelligenceContextService()._build_strong_context(
                db, customer=db.get(Customer, 102), team_id=1,
            )
            assert context.opportunities[0].product_name == "商机产品新名"
    finally:
        writer.close()
        engine.dispose()


def test_module_changes_do_not_advance_progress_when_legacy_snapshot_excludes_modules():
    engine, writer, sessions = _setup_catalog()
    try:
        product = product_crud.create(writer, 1, ProductCreate(name="产品"), "1")
        before = {cid: _catalog_state(sessions, cid) for cid in (101, 102)}

        module = product_crud.create_module(writer, product, ProductModuleCreate(name="扩展"), "1")
        product_crud.update_module(writer, module, ProductModuleUpdate(name="扩展版"), "2")
        product_crud.delete_module(writer, module)
        assert {cid: _catalog_state(sessions, cid) for cid in (101, 102)} == before
    finally:
        writer.close()
        engine.dispose()
