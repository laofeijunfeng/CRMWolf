"""Read-only opportunity target safety, independent of command-effect attribution."""

from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.schemas.opportunity import OpportunityCreate
from app.services.assistant.opportunity_target_matching import match_opportunity_target


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Product.__table__,
            ProductModule.__table__,
            Opportunity.__table__,
            OpportunityProductModule.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)()
    session.add_all(
        [
            Product(
                id=11, public_id="prd_analysis", team_id=1, code="ANALYSIS", name="分析平台", created_by="fictional"
            ),
            Product(
                id=12, public_id="prd_training", team_id=1, code="TRAINING", name="培训服务", created_by="fictional"
            ),
            Product(
                id=21, public_id="prd_foreign", team_id=2, code="ANALYSIS", name="分析平台", created_by="fictional"
            ),
            ProductModule(
                id=101,
                public_id="prm_base",
                team_id=1,
                product_id=11,
                code="BASE",
                name="基础模块",
                created_by="fictional",
            ),
            ProductModule(
                id=102,
                public_id="prm_addon",
                team_id=1,
                product_id=11,
                code="ADDON",
                name="扩展模块",
                created_by="fictional",
            ),
            ProductModule(
                id=103,
                public_id="prm_training",
                team_id=1,
                product_id=12,
                code="TRAINING",
                name="培训模块",
                created_by="fictional",
            ),
            ProductModule(
                id=201,
                public_id="prm_foreign",
                team_id=2,
                product_id=21,
                code="BASE",
                name="基础模块",
                created_by="fictional",
            ),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _data(**changes):
    return OpportunityCreate.model_validate(
        {
            "customer_id": "cus_fictional",
            "opportunity_name": "分析平台",
            "total_amount": 12000,
            "user_count": 10,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 1,
            "purchase_type": "NEW",
            "expected_closing_date": "2026-12-01",
            "product_public_id": "prd_analysis",
            "product_module_public_ids": ["prm_base"],
            **changes,
        }
    )


def _opportunity(
    db, *, identifier=1, name="分析平台", team_id=1, customer_id=7, product_id=11, modules=(101,), **changes
):
    row = Opportunity(
        id=identifier,
        public_id=f"opp_fictional_{identifier}",
        opportunity_number=f"FICTIONAL-{identifier}",
        opportunity_name=name,
        team_id=team_id,
        customer_id=customer_id,
        product_id=product_id,
        total_amount=12000,
        user_count=10,
        unit_price=1200,
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=date(2026, 12, 1),
        owner_id="fictional",
        creator_id="fictional",
    )
    for field, value in changes.items():
        setattr(row, field, value)
    db.add(row)
    db.add_all(
        [
            OpportunityProductModule(opportunity_id=identifier, product_module_id=module_id, team_id=team_id)
            for module_id in modules
        ]
    )
    db.commit()
    return row


def test_identical_explicit_target_is_a_duplicate_not_a_creation(db):
    existing = _opportunity(db, modules=(101, 102))
    result = match_opportunity_target(
        db,
        team_id=1,
        customer_id=7,
        data=_data(product_module_public_ids=["prm_addon", "prm_base", "prm_base"]),
    )
    assert result.status == "DUPLICATE"
    assert result.target_public_ids == (existing.public_id,)


@pytest.mark.parametrize("persisted_name", ["  分析平台  ", "\t分析平台\n", "\u3000分析平台\u3000"])
def test_trimmed_persisted_name_is_the_same_explicit_target(db, persisted_name):
    existing = _opportunity(db, name=persisted_name)
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "DUPLICATE"
    assert result.target_public_ids == (existing.public_id,)


def test_same_name_with_unresolved_legacy_identity_never_permits_creation_or_writes(db):
    existing = _opportunity(db, product_id=None, modules=())
    pending = Product(
        id=99, public_id="prd_pending", team_id=1, code="PENDING", name="待保存产品", created_by="fictional"
    )
    db.add(pending)
    statements = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", record_statement)
    try:
        result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    finally:
        event.remove(db.bind, "before_cursor_execute", record_statement)
    assert result.status == "AMBIGUOUS"
    assert result.target_public_ids == (existing.public_id,)
    assert pending in db.new
    assert statements and all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def test_multiple_matching_targets_are_ambiguous(db):
    _opportunity(db, identifier=1)
    _opportunity(db, identifier=2)
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "AMBIGUOUS"
    assert set(result.target_public_ids) == {"opp_fictional_1", "opp_fictional_2"}


def test_exact_match_does_not_override_another_unresolved_possible_target(db):
    _opportunity(db, identifier=1)
    _opportunity(db, identifier=2, product_id=None, modules=())
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "AMBIGUOUS"
    assert set(result.target_public_ids) == {"opp_fictional_1", "opp_fictional_2"}


def test_containment_does_not_merge_distinct_named_procurements(db):
    _opportunity(db, name="分析平台")
    result = match_opportunity_target(
        db,
        team_id=1,
        customer_id=7,
        data=_data(opportunity_name="分析平台培训服务"),
    )
    assert result.status == "DISTINCT"
    assert result.target_public_ids == ()


@pytest.mark.parametrize(
    "identity",
    [
        {"product_public_id": "prd_training", "product_module_public_ids": ["prm_training"]},
        {"product_module_public_ids": ["prm_addon"]},
        {"purchase_type": "RENEWAL"},
        {"license_type": "PERPETUAL", "subscription_years": None},
        {"subscription_years": 2},
    ],
)
def test_same_name_does_not_override_explicitly_different_procurement_identity(db, identity):
    _opportunity(db)
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data(**identity))
    assert result.status == "DISTINCT"
    assert result.target_public_ids == ()


def test_other_customer_and_team_records_do_not_interfere(db):
    _opportunity(db, identifier=1, customer_id=8)
    _opportunity(db, identifier=2, team_id=2, product_id=21, modules=(201,))
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "DISTINCT"
    assert result.target_public_ids == ()


@pytest.mark.parametrize(
    "identity",
    [
        {"product_public_id": "prd_missing"},
        {"product_public_id": "prd_foreign", "product_module_public_ids": ["prm_foreign"]},
        {"product_module_public_ids": ["prm_missing"]},
        {"product_module_public_ids": ["prm_foreign"]},
        {"product_module_public_ids": ["prm_training"]},
    ],
)
def test_unresolved_or_foreign_catalog_identity_never_permits_creation(db, identity):
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data(**identity))
    assert result.status == "AMBIGUOUS"
    assert result.target_public_ids == ()


def test_inactive_catalog_identity_never_permits_creation(db):
    db.query(ProductModule).filter(ProductModule.id == 101).update({"is_active": False})
    db.commit()
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "AMBIGUOUS"


def test_missing_module_identity_on_same_named_target_is_ambiguous(db):
    _opportunity(db, modules=())
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "AMBIGUOUS"
    assert result.target_public_ids == ("opp_fictional_1",)


@pytest.mark.parametrize("link_team_id,module_id", [(1, 201), (2, 102)])
def test_invalid_module_link_cannot_make_a_same_named_target_a_duplicate(db, link_team_id, module_id):
    _opportunity(db)
    db.add(OpportunityProductModule(opportunity_id=1, product_module_id=module_id, team_id=link_team_id))
    db.commit()
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "AMBIGUOUS"
    assert result.target_public_ids == ("opp_fictional_1",)


def test_persisted_target_identity_is_rechecked_despite_cached_orm_state(db):
    cached = _opportunity(db)
    db.query(Opportunity).filter(Opportunity.id == cached.id).update(
        {"purchase_type": "RENEWAL"},
        synchronize_session=False,
    )
    db.commit()
    assert cached.purchase_type == "NEW"
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data())
    assert result.status == "DISTINCT"


def test_auto_generated_name_is_distinct_without_existing_possible_targets(db):
    statements = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", record_statement)
    try:
        result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data(opportunity_name=None))
    finally:
        event.remove(db.bind, "before_cursor_execute", record_statement)
    assert result.status == "DISTINCT"
    assert result.target_public_ids == ()
    assert statements and all("opportunity_name IS NULL" not in statement for statement in statements)


def test_auto_generated_name_with_compatible_existing_target_is_ambiguous(db):
    _opportunity(db)
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data(opportunity_name=None))
    assert result.status == "AMBIGUOUS"
    assert result.target_public_ids == ("opp_fictional_1",)


def test_auto_generated_name_with_only_explicitly_different_targets_is_distinct(db):
    _opportunity(db, purchase_type="RENEWAL")
    result = match_opportunity_target(db, team_id=1, customer_id=7, data=_data(opportunity_name=None))
    assert result.status == "DISTINCT"
    assert result.target_public_ids == ()
