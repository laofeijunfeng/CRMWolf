"""Real target checks at proposal offer and executor revalidation boundaries."""
# ruff: noqa: RUF001

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity, OpportunityProductModule
from app.models.product import Product, ProductModule
from app.models.team import Team, UserTeam
from app.models.user import User, UserStatus
from app.schemas.opportunity import OpportunityCreate
from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor, validate_candidate
from app.services.assistant.opportunity_target_matching import match_opportunity_target
from app.services.assistant.proposals import offer_next_proposal


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


SOURCE = "客户确认分析平台培训服务，预算12000.0元，10用户，2026-12-01成交。"


@pytest.fixture
def crm_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            CustomerActivity.__table__,
            User.__table__,
            Team.__table__,
            UserTeam.__table__,
            Customer.__table__,
            CustomerMember.__table__,
            CustomerProduct.__table__,
            Product.__table__,
            ProductModule.__table__,
            Opportunity.__table__,
            OpportunityProductModule.__table__,
        ],
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add_all(
        [
            User(id=2, name="虚构销售", email="fictional@example.invalid"),
            Team(id=1, name="虚构团队", code="FICTIONAL", owner_id=2),
            Team(id=2, name="另一虚构团队", code="FICTIONAL-OTHER", owner_id=2),
            UserTeam(user_id=2, team_id=1),
            Customer(
                id=7,
                public_id="cus_fictional",
                team_id=1,
                account_name="虚构采购客户",
                city="虚构城市",
                owner_id="2",
                creator_id="2",
            ),
            Customer(
                id=8,
                public_id="cus_other",
                team_id=1,
                account_name="另一虚构客户",
                city="虚构城市",
                owner_id="2",
                creator_id="2",
            ),
            Customer(
                id=9,
                public_id="cus_foreign",
                team_id=2,
                account_name="跨团队虚构客户",
                city="虚构城市",
                owner_id="2",
                creator_id="2",
            ),
            Product(id=11, public_id="prd_analysis", team_id=1, code="ANALYSIS", name="分析平台", created_by="2"),
            Product(id=12, public_id="prd_training", team_id=1, code="TRAINING", name="培训服务", created_by="2"),
            Product(id=21, public_id="prd_foreign", team_id=2, code="ANALYSIS", name="分析平台", created_by="2"),
            ProductModule(
                id=101, public_id="prm_base", team_id=1, product_id=11, code="BASE", name="基础模块", created_by="2"
            ),
            ProductModule(
                id=102,
                public_id="prm_training",
                team_id=1,
                product_id=12,
                code="TRAINING",
                name="培训模块",
                created_by="2",
            ),
            ProductModule(
                id=201, public_id="prm_foreign", team_id=2, product_id=21, code="BASE", name="基础模块", created_by="2"
            ),
        ]
    )
    session.commit()
    permissions = {"opportunity:create", "customer:edit:own"}
    from app.crud.permission import permission_crud

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda db, user_id, team_id: [SimpleNamespace(code=code) for code in permissions],
    )
    try:
        yield session, permissions
    finally:
        session.close()
        engine.dispose()


def _candidate(**payload_changes):
    return {
        "kind": "opportunity_create",
        "evidence_quote": SOURCE,
        "payload": {
            "opportunity_name": "分析平台",
            "total_amount": 12000,
            "user_count": 10,
            "license_type": "SUBSCRIPTION",
            "subscription_years": 1,
            "purchase_type": "NEW",
            "expected_closing_date": "2026-12-01",
            "product_public_id": "prd_analysis",
            "product_module_public_ids": ["prm_base"],
            **payload_changes,
        },
    }


def _task(db, candidate):
    activity = CustomerActivity(
        id=1,
        team_id=1,
        customer_id=7,
        activity_kind="FOLLOW_UP",
        source_content=SOURCE,
        content_json="{}",
        creator_id="2",
        owner_id="2",
        submission_source="AGENT",
    )
    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录虚构采购需求",
        draft_json={},
        authority_json={"proposal_candidates": [candidate]},
        committed_json=[{"kind": "customer_activity", "public_id": "1"}],
        version=0,
    )
    db.add_all([activity, task])
    db.commit()
    return task


def _target(db, *, identifier=1, name="分析平台", team_id=1, customer_id=7, product_id=11, modules=(101,)):
    target = Opportunity(
        id=identifier,
        public_id=f"opp_fictional_{identifier}",
        team_id=team_id,
        opportunity_number=f"FICTIONAL-{identifier}",
        opportunity_name=name,
        customer_id=customer_id,
        product_id=product_id,
        total_amount=12000,
        user_count=10,
        unit_price=1200,
        license_type="SUBSCRIPTION",
        subscription_years=1,
        purchase_type="NEW",
        expected_closing_date=date(2026, 12, 1),
        owner_id="2",
        creator_id="2",
    )
    db.add(target)
    db.add_all(
        [
            OpportunityProductModule(opportunity_id=identifier, product_module_id=module, team_id=team_id)
            for module in modules
        ]
    )
    db.commit()
    return target


def _match(db, candidate):
    return match_opportunity_target(
        db,
        team_id=1,
        customer_id=7,
        data=OpportunityCreate.model_validate({**candidate["payload"], "customer_id": "cus_fictional"}),
    )


@pytest.mark.parametrize(
    "target_changes,status",
    [
        ({}, "DUPLICATE"),
        ({"name": "\t分析平台\u3000"}, "DUPLICATE"),
        ({"product_id": None, "modules": ()}, "AMBIGUOUS"),
        ({"name": "分析平台培训服务"}, "DISTINCT"),
        ({"product_id": 12, "modules": (102,)}, "DISTINCT"),
        ({"customer_id": 8}, "DISTINCT"),
        ({"team_id": 2, "customer_id": 9, "product_id": 21, "modules": (201,)}, "DISTINCT"),
    ],
    ids=[
        "duplicate",
        "trimmed-duplicate",
        "legacy-ambiguous",
        "contained-distinct",
        "catalog-distinct",
        "other-customer",
        "other-team",
    ],
)
async def test_real_target_classification_controls_pre_offer(crm_session, target_changes, status):
    db, _ = crm_session
    _target(db, **target_changes)
    candidate = _candidate()
    task = _task(db, candidate)
    assert _match(db, candidate).status == status
    assert (validate_candidate(db, task, candidate) is not None) == (status == "DISTINCT")

    offered, _, active = await offer_next_proposal(db, task)
    assert active == (status == "DISTINCT")
    assert offered.waiting_field == ("proposal:opportunity_create" if active else None)
    assert db.query(Opportunity.public_id).all() == [("opp_fictional_1",)]


@pytest.mark.parametrize(
    "late_change,status",
    [
        ("duplicate", "DUPLICATE"),
        ("trimmed-duplicate", "DUPLICATE"),
        ("legacy", "AMBIGUOUS"),
        ("multiple", "AMBIGUOUS"),
        ("inactive-catalog", "AMBIGUOUS"),
    ],
)
async def test_distinct_offer_rechecks_persisted_targets_before_execution(crm_session, late_change, status):
    db, _ = crm_session
    candidate = _candidate()
    task = _task(db, candidate)
    assert _match(db, candidate).status == "DISTINCT"
    offered, _, active = await offer_next_proposal(db, task)
    assert active
    proposal = offered.waiting_json["payload"]["confirmation_payload"]["candidate"]
    db.commit()

    if late_change == "inactive-catalog":
        db.query(ProductModule).filter(ProductModule.id == 101).update({"is_active": False})
        db.commit()
    elif late_change == "legacy":
        _target(db, product_id=None, modules=())
    elif late_change == "trimmed-duplicate":
        _target(db, name="\u3000分析平台\n")
    else:
        _target(db)
        if late_change == "multiple":
            _target(db, identifier=2)
    before = db.query(Opportunity.public_id).order_by(Opportunity.id).all()
    assert _match(db, candidate).status == status
    assert validate_candidate(db, task, proposal) is None

    with pytest.raises(ValueError):
        await RealCRMProposalExecutor().execute(db, offered, proposal)
    assert db.query(Opportunity.public_id).order_by(Opportunity.id).all() == before


async def test_distinct_contained_target_reaches_real_executor_creation_boundary(crm_session, monkeypatch):
    db, _ = crm_session
    _target(db, name="分析平台")
    candidate = _candidate(opportunity_name="分析平台培训服务")
    task = _task(db, candidate)
    offered, _, active = await offer_next_proposal(db, task)
    assert active
    proposal = offered.waiting_json["payload"]["confirmation_payload"]["candidate"]

    class CreationBoundaryReached(Exception):
        pass

    async def stop_at_creation(**kwargs):
        raise CreationBoundaryReached

    from app.api import opportunities

    monkeypatch.setattr(opportunities, "create_opportunity", stop_at_creation)
    with pytest.raises(CreationBoundaryReached):
        await RealCRMProposalExecutor().execute(db, offered, proposal)
    # This proves real revalidation allows DISTINCT, not successful API creation.
    assert db.query(Opportunity.public_id).all() == [("opp_fictional_1",)]


@pytest.mark.parametrize(
    "invalidated",
    [
        "create-permission",
        "customer-permission",
        "membership",
        "inactive-user",
        "source-quote",
        "source-amount",
        "incomplete-form",
        "foreign-customer-authority",
    ],
)
async def test_distinct_target_does_not_bypass_existing_validation(crm_session, invalidated):
    db, permissions = crm_session
    candidate = _candidate()
    task = _task(db, candidate)
    assert validate_candidate(db, task, candidate) is not None
    if invalidated == "create-permission":
        permissions.remove("opportunity:create")
    elif invalidated == "customer-permission":
        permissions.remove("customer:edit:own")
    elif invalidated == "membership":
        db.delete(db.query(UserTeam).one())
    elif invalidated == "inactive-user":
        db.query(User).one().status = UserStatus.INACTIVE
    elif invalidated == "source-quote":
        db.query(CustomerActivity).one().source_content = "客户只讨论了其他内容。"
    elif invalidated == "source-amount":
        candidate["payload"]["total_amount"] = 90000
    elif invalidated == "incomplete-form":
        del candidate["payload"]["expected_closing_date"]
    else:
        task.authority_json = {**task.authority_json, "customer_public_id": "cus_other"}
    task.authority_json = {**task.authority_json, "proposal_candidates": [candidate]}
    db.commit()
    assert validate_candidate(db, task, candidate) is None
    finished, _, active = await offer_next_proposal(db, task)
    assert not active and finished.waiting_field is None
    assert db.query(Opportunity.public_id).all() == []


async def test_executor_rejects_source_revision_change_even_when_target_remains_distinct(crm_session):
    db, _ = crm_session
    task = _task(db, _candidate())
    offered, _, active = await offer_next_proposal(db, task)
    assert active
    proposal = offered.waiting_json["payload"]["confirmation_payload"]["candidate"]
    db.query(CustomerActivity).one().activity_revision += 1
    db.commit()
    assert _match(db, proposal).status == "DISTINCT"
    with pytest.raises(ValueError):
        await RealCRMProposalExecutor().execute(db, offered, proposal)
    assert db.query(Opportunity.public_id).all() == []
