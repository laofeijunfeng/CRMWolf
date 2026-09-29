"""Customer binding returns only customers authorized for activity writes."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.crud.permission import permission_crud
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_identity_term import CustomerIdentityTerm, CustomerIdentityTermStatus
from app.services.assistant.customer_resolution import resolve_customer_candidates_for_assistant
from app.services.customer_identity_resolution_service import customer_identity_resolution_service


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[Customer.__table__, CustomerProduct.__table__, CustomerMember.__table__, CustomerIdentityTerm.__table__],
    )
    session = sessionmaker(bind=engine)()
    grants = {1: ["customer:edit:all"]}
    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda db, user_id, team_id: [SimpleNamespace(code=code) for code in grants.get(team_id, [])],
    )
    try:
        yield session, grants
    finally:
        session.close()
        engine.dispose()


def _customer(session, name: str, public_id: str, *, team_id: int = 1, owner_id: str = "99") -> Customer:
    customer = Customer(
        team_id=team_id, account_name=name, public_id=public_id, city="上海", creator_id="1", owner_id=owner_id
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def _alias(session, customer: Customer, term: str, *, confidence: float = 0.95) -> None:
    session.add(
        CustomerIdentityTerm(
            tenant_id=customer.team_id,
            team_id=customer.team_id,
            customer_id=customer.id,
            term=term,
            normalized_term=term,
            term_type="alias",
            source="human",
            confidence=confidence,
            status=CustomerIdentityTermStatus.ACTIVE,
        )
    )
    session.commit()


def _resolve(session, customer_name: str, *, team_id: int = 1):
    return resolve_customer_candidates_for_assistant(session, team_id=team_id, user_id=2, customer_name=customer_name)


def test_exact_name_precedes_alias_and_exposes_only_identity(db_session, monkeypatch):
    session, _ = db_session
    exact = _customer(session, "睿狐科技", "cus_exact")
    other = _customer(session, "广州睿狐科技有限公司", "cus_other")
    _alias(session, other, "睿狐科技")

    def unexpected_resolution(*args, **kwargs):
        pytest.fail("exact name must not consult identity terms")

    monkeypatch.setattr(customer_identity_resolution_service, "resolve", unexpected_resolution)
    result = _resolve(session, " 睿狐科技 ")
    assert result.status == "RESOLVED"
    assert result.customer.id == exact.id
    assert result.candidates == [{"id": exact.public_id, "account_name": exact.account_name}]


def test_duplicate_exact_names_are_ambiguous_when_legacy_data_lacks_unique_constraint(db_session):
    session, _ = db_session
    session.connection().exec_driver_sql("DROP INDEX uq_customer_team_account_name")
    first = _customer(session, "睿狐科技", "cus_duplicate_a")
    second = _customer(session, "睿狐科技", "cus_duplicate_b")

    result = _resolve(session, "睿狐科技")
    assert result.status == "AMBIGUOUS"
    assert result.customer is None
    assert result.candidates == [
        {"id": first.public_id, "account_name": first.account_name},
        {"id": second.public_id, "account_name": second.account_name},
    ]


def test_identity_result_cannot_bind_customer_from_another_team(db_session, monkeypatch):
    session, grants = db_session
    grants[2] = ["customer:edit:all"]
    other = _customer(session, "睿狐科技", "cus_other_team", team_id=2)
    monkeypatch.setattr(
        customer_identity_resolution_service,
        "resolve",
        lambda *args, **kwargs: SimpleNamespace(
            metadata={"identity_decision": "auto_select"}, items=[{"id": other.public_id}]
        ),
    )
    result = _resolve(session, "睿狐")
    assert (result.status, result.customer, result.candidates) == ("NOT_FOUND", None, [])


def test_deactivated_follow_up_member_is_removed_from_candidates(db_session):
    session, grants = db_session
    grants[1] = []
    customer = _customer(session, "睿狐科技", "cus_member")
    member = CustomerMember(
        team_id=1, customer_id=customer.id, user_id="2", access_level="FOLLOW_UP", created_by="1"
    )
    session.add(member)
    session.commit()
    assert _resolve(session, customer.account_name).status == "RESOLVED"

    member.is_active = False
    session.commit()
    result = _resolve(session, customer.account_name)
    assert (result.status, result.customer, result.candidates) == ("PERMISSION_DENIED", None, [])


def test_short_name_resolves_authorized_alias(db_session):
    session, _ = db_session
    customer = _customer(session, "广州睿狐科技有限公司", "cus_alias")
    _alias(session, customer, "睿狐科技")

    result = _resolve(session, "睿狐科技")
    assert result.status == "RESOLVED"
    assert result.customer.id == customer.id
    assert result.candidates == [{"id": "cus_alias", "account_name": customer.account_name}]


def test_generated_short_name_resolves_without_persisted_alias(db_session):
    session, _ = db_session
    customer = _customer(session, "华米（北京）信息科技有限公司", "cus_generated")
    result = _resolve(session, "华米科技")
    assert result.status == "RESOLVED"
    assert result.customer.id == customer.id


def test_ranked_identity_candidates_require_user_selection(db_session):
    session, _ = db_session
    preferred = _customer(session, "广州睿狐科技有限公司", "cus_ranked")
    alternative = _customer(session, "深圳睿狐软件有限公司", "cus_alternative")
    _alias(session, preferred, "睿狐")
    _alias(session, alternative, "睿狐科技研发", confidence=0.5)

    result = _resolve(session, "睿狐")
    assert result.status == "AMBIGUOUS"
    assert result.customer is None
    assert result.candidates == [
        {"id": "cus_ranked", "account_name": preferred.account_name},
        {"id": "cus_alternative", "account_name": alternative.account_name},
    ]


def test_weak_single_candidate_requires_confirmation(db_session):
    session, _ = db_session
    weak = _customer(session, "华南米科新技有限公司", "cus_weak")
    resolution = customer_identity_resolution_service.resolve(
        session, team_id=1, query_text="华米科技", lexical_items=[], semantic_items=[]
    )
    assert resolution.items[0]["match"]["score"] < 0.86

    result = _resolve(session, "华米科技")
    assert result.status == "AMBIGUOUS"
    assert result.customer is None
    assert result.candidates == [{"id": weak.public_id, "account_name": weak.account_name}]


def test_same_alias_for_two_customers_remains_ambiguous(db_session):
    session, _ = db_session
    first = _customer(session, "广州睿狐科技有限公司", "cus_a")
    second = _customer(session, "深圳睿狐软件有限公司", "cus_b")
    _alias(session, first, "睿狐")
    _alias(session, second, "睿狐")

    result = _resolve(session, "睿狐")
    assert result.status == "AMBIGUOUS"
    assert result.customer is None
    assert {item["id"] for item in result.candidates} == {first.public_id, second.public_id}


def test_cross_team_customer_is_not_found_and_never_exposed(db_session):
    session, grants = db_session
    grants[2] = ["customer:edit:all"]
    other = _customer(session, "广州睿狐科技有限公司", "cus_other_team", team_id=2)
    _alias(session, other, "睿狐科技")

    result = _resolve(session, "睿狐科技")
    assert (result.status, result.customer, result.candidates) == ("NOT_FOUND", None, [])


def test_exact_match_without_activity_rights_is_denied_without_identity_leak(db_session, monkeypatch):
    session, grants = db_session
    grants[1] = []
    _customer(session, "睿狐科技", "cus_private")

    def unexpected_resolution(*args, **kwargs):
        pytest.fail("exact unauthorized name must not fall back to identity search")

    monkeypatch.setattr(customer_identity_resolution_service, "resolve", unexpected_resolution)
    result = _resolve(session, "睿狐科技")
    assert (result.status, result.customer, result.candidates) == ("PERMISSION_DENIED", None, [])


def test_alias_candidates_filter_inaccessible_customers_before_exposure(db_session):
    session, grants = db_session
    grants[1] = []
    allowed = _customer(session, "广州睿狐科技有限公司", "cus_allowed", owner_id="2")
    denied = _customer(session, "深圳睿狐软件有限公司", "cus_denied")
    _alias(session, allowed, "睿狐")
    _alias(session, denied, "睿狐")
    grants[1] = ["customer:activity:create"]

    result = _resolve(session, "睿狐")
    assert result.status == "AMBIGUOUS"
    assert result.customer is None
    assert result.candidates == [{"id": allowed.public_id, "account_name": allowed.account_name}]


def test_all_alias_matches_inaccessible_returns_permission_denied(db_session):
    session, grants = db_session
    grants[1] = []
    denied = _customer(session, "广州睿狐科技有限公司", "cus_denied")
    _alias(session, denied, "睿狐")
    result = _resolve(session, "睿狐")
    assert (result.status, result.customer, result.candidates) == ("PERMISSION_DENIED", None, [])


def test_withdrawn_owner_permission_prevents_resolving_on_next_attempt(db_session):
    session, grants = db_session
    customer = _customer(session, "睿狐科技", "cus_owner", owner_id="2")
    grants[1] = ["customer:activity:create"]
    assert _resolve(session, customer.account_name).status == "RESOLVED"

    grants[1] = []
    result = _resolve(session, customer.account_name)
    assert (result.status, result.customer, result.candidates) == ("PERMISSION_DENIED", None, [])


def test_identity_service_exception_is_dependency_failure_not_missing(db_session, monkeypatch):
    session, _ = db_session

    def boom(*args, **kwargs):
        raise RuntimeError("identity service down")

    monkeypatch.setattr(customer_identity_resolution_service, "resolve", boom)
    result = _resolve(session, "睿狐科技")
    assert (result.status, result.customer, result.candidates) == ("DEPENDENCY_FAILURE", None, [])


def test_permission_lookup_exception_is_dependency_failure(db_session, monkeypatch):
    session, _ = db_session
    _customer(session, "睿狐科技", "cus_present")

    def boom(*args, **kwargs):
        raise RuntimeError("permissions unavailable")

    monkeypatch.setattr(permission_crud, "get_user_permissions", boom)
    result = _resolve(session, "睿狐科技")
    assert (result.status, result.customer, result.candidates) == ("DEPENDENCY_FAILURE", None, [])


def test_blank_name_has_no_customer_or_candidates(db_session, monkeypatch):
    session, _ = db_session

    def unexpected_resolution(*args, **kwargs):
        pytest.fail("resolver must not be called for blank input")

    monkeypatch.setattr(customer_identity_resolution_service, "resolve", unexpected_resolution)
    result = _resolve(session, "  ")
    assert (result.status, result.customer, result.candidates) == ("NOT_FOUND", None, [])
