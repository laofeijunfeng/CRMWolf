from datetime import date, datetime

import pytest
from sqlalchemy import Column, Date, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.list_query.catalog import ListQueryCatalog, ListQueryField
from app.core.list_query.engine import apply_filters, apply_optional_list_query, apply_sorts
from app.core.list_query.errors import ListQueryError
from app.core.list_query.license_status import classify_license_status, license_status_expression
from app.core.list_query.parse import (
    parse_filters,
    parse_sorts,
    resolve_list_query,
    uses_unified_list_query,
)
from app.core.list_query.types import FilterCondition, JoinSpec, ListQueryContext, SortCondition

Base = declarative_base()


class Item(Base):
    __tablename__ = "list_query_items"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    status = Column(String)
    amount = Column(Integer)
    created_on = Column(Date)
    created_at = Column(DateTime)
    owner_id = Column(String)
    license_expiry_date = Column(Date)
    license_type = Column(String)
    category_id = Column(Integer)


class Category(Base):
    __tablename__ = "list_query_categories"

    id = Column(Integer, primary_key=True)
    title = Column(String)


def _catalog() -> ListQueryCatalog:
    return ListQueryCatalog(
        name="items",
        fields=[
            ListQueryField(key="name", type="text", expression=Item.name),
            ListQueryField(key="status", type="enum", expression=Item.status),
            ListQueryField(key="amount", type="number", expression=Item.amount),
            ListQueryField(
                key="created_on",
                type="date",
                expression=Item.created_on,
                date_kind="date",
            ),
            ListQueryField(
                key="created_at",
                type="date",
                expression=Item.created_at,
                date_kind="datetime",
            ),
            ListQueryField(
                key="legacy_created_at",
                type="date",
                expression=Item.created_at,
                date_kind="datetime",
                date_semantics="exclusive",
            ),
            ListQueryField(
                key="owner_id",
                type="enum",
                expression=Item.owner_id,
                resolve_person_aliases=True,
            ),
            ListQueryField(
                key="license_status",
                type="enum",
                expression_builder=lambda ctx: license_status_expression(
                    Item.license_expiry_date,
                    Item.license_type,
                    ctx.business_today(),
                ),
            ),
            ListQueryField(
                key="category_title",
                type="text",
                expression=Category.title,
                joins=[
                    JoinSpec(
                        key="category",
                        target=Category,
                        onclause=Item.category_id == Category.id,
                        isouter=True,
                    )
                ],
            ),
        ],
        default_sorts=[SortCondition(field="name", direction="asc")],
    )


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    session.add_all(
        [
            Category(id=1, title="Alpha"),
            Category(id=2, title="Beta"),
            Item(
                id=1,
                name="Acme",
                status="open",
                amount=10,
                created_on=date(2026, 8, 10),
                created_at=datetime(2026, 8, 10, 15, 30),
                owner_id="1",
                license_expiry_date=None,
                license_type=None,
                category_id=1,
            ),
            Item(
                id=2,
                name="Beta Co",
                status="won",
                amount=20,
                created_on=date(2026, 8, 11),
                created_at=datetime(2026, 8, 11, 9, 0),
                owner_id="2",
                license_expiry_date=date(2026, 8, 1),
                license_type="OFFICIAL",
                category_id=2,
            ),
            Item(
                id=3,
                name="Trial Co",
                status="open",
                amount=30,
                created_on=date(2026, 8, 19),
                created_at=datetime(2026, 8, 19, 8, 0),
                owner_id="1",
                license_expiry_date=date(2026, 8, 30),
                license_type="TRIAL",
                category_id=1,
            ),
        ]
    )
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _names(session: Session, filters=None, sorts=None, context=None):
    query = session.query(Item)
    query = apply_filters(query, _catalog(), filters or [], context=context)
    query = apply_sorts(query, _catalog(), sorts or [], context=context)
    return [row.name for row in query.all()]


def test_parse_filters_and_sorts_accept_json_and_legacy_shapes():
    filters = parse_filters('[{"field":"name","op":"contains","value":"Acme"}]')
    sorts = parse_sorts("name:desc,amount:asc")

    assert filters[0].field == "name"
    assert sorts == [
        SortCondition(field="name", direction="desc"),
        SortCondition(field="amount", direction="asc"),
    ]

    resolved = resolve_list_query(
        filters_raw=None,
        sorts_raw=None,
        legacy_filters=[{"field": "status", "op": "eq", "value": "open"}],
        legacy_sorts=[{"field": "name", "direction": "asc"}],
    )
    assert resolved[0][0].field == "status"
    assert resolved[1][0].direction == "asc"


def test_unified_protocol_is_active_when_either_parameter_is_explicit():
    assert uses_unified_list_query(filters=[], sorts=None)
    assert uses_unified_list_query(filters=None, sorts=[])
    assert not uses_unified_list_query(filters=None, sorts=None)


def test_json_filters_win_over_legacy_and_do_not_stack():
    filters, sorts = resolve_list_query(
        filters_raw=[{"field": "name", "op": "eq", "value": "Acme"}],
        sorts_raw=[{"field": "amount", "dir": "desc"}],
        legacy_filters=[{"field": "status", "op": "eq", "value": "open"}],
        legacy_sorts=[{"field": "name", "dir": "asc"}],
    )
    assert [item.field for item in filters] == ["name"]
    assert [item.field for item in sorts] == ["amount"]


def test_unknown_field_is_rejected():
    with pytest.raises(ListQueryError, match="未知筛选字段: missing"):
        apply_filters(None, _catalog(), [{"field": "missing", "op": "eq", "value": "x"}])


def test_illegal_operator_is_rejected(db_session):
    with pytest.raises(ListQueryError, match="不支持操作符 contains"):
        apply_filters(
            db_session.query(Item),
            _catalog(),
            [{"field": "amount", "op": "contains", "value": "1"}],
        )


def test_empty_value_is_skipped(db_session):
    names = _names(db_session, [{"field": "name", "op": "eq", "value": ""}])
    assert names == ["Acme", "Beta Co", "Trial Co"]


def test_enum_in_and_not_in_are_executed(db_session):
    assert _names(db_session, [{"field": "status", "op": "in", "value": ["open"]}]) == [
        "Acme",
        "Trial Co",
    ]
    assert _names(db_session, [{"field": "status", "op": "not_in", "value": ["open"]}]) == [
        "Beta Co",
    ]


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("gt", 20, ["Trial Co"]),
        ("gte", 20, ["Beta Co", "Trial Co"]),
        ("lt", 20, ["Acme"]),
        ("lte", 20, ["Acme", "Beta Co"]),
    ],
)
def test_number_comparison_operators_are_executed(db_session, op, value, expected):
    assert _names(db_session, [{"field": "amount", "op": op, "value": value}]) == expected


def test_date_column_eq_matches_the_calendar_day(db_session):
    names = _names(db_session, [{"field": "created_on", "op": "eq", "value": "2026-08-10"}])
    assert names == ["Acme"]


def test_datetime_day_bounds_after_includes_that_morning(db_session):
    names = _names(db_session, [{"field": "created_at", "op": "after", "value": "2026-08-11"}])
    assert names == ["Beta Co", "Trial Co"]


def test_exclusive_datetime_after_keeps_legacy_strict_comparison(db_session):
    names = _names(db_session, [{"field": "legacy_created_at", "op": "after", "value": "2026-08-11T09:00:00"}])
    assert names == ["Trial Co"]


def test_person_alias_resolves_to_current_user(db_session):
    names = _names(
        db_session,
        [{"field": "owner_id", "op": "eq", "value": "me"}],
        context=ListQueryContext(current_user_id="1"),
    )
    assert names == ["Acme", "Trial Co"]


def test_license_status_case_matches_classifier(db_session):
    today = date(2026, 8, 19)
    context = ListQueryContext(today=today)
    query = apply_filters(
        db_session.query(Item),
        _catalog(),
        [{"field": "license_status", "op": "eq", "value": "trial"}],
        context=context,
    )
    rows = query.all()
    assert [row.name for row in rows] == ["Trial Co"]
    assert classify_license_status(rows[0].license_expiry_date, rows[0].license_type, today) == "trial"
    assert classify_license_status(None, None, today) == "none"
    assert classify_license_status(date(2026, 8, 1), "OFFICIAL", today) == "expired"
    assert classify_license_status(date(2026, 8, 30), "OFFICIAL", today) == "official"


def test_join_is_applied_once_for_filter_and_sort(db_session):
    query = db_session.query(Item)
    query = apply_filters(
        query,
        _catalog(),
        [{"field": "category_title", "op": "eq", "value": "Alpha"}],
    )
    query = apply_sorts(
        query,
        _catalog(),
        [{"field": "category_title", "dir": "desc"}, {"field": "name", "dir": "desc"}],
    )
    compiled = str(query.statement.compile(compile_kwargs={"literal_binds": False})).lower()
    assert compiled.count(" join ") == 1
    assert [row.name for row in query.all()] == ["Trial Co", "Acme"]


def test_owner_scope_only_treats_positive_owner_filters_as_requested_scope():
    from app.core.list_query.http import enforce_owner_view_scope, owner_values_from_filters

    filters = [
        {"field": "owner_id", "op": "neq", "value": "2"},
        {"field": "owner_id", "op": "not_contains", "value": "3"},
        {"field": "owner_id", "op": "in", "value": ["me"]},
    ]

    assert owner_values_from_filters(filters) == ["me"]
    assert (
        enforce_owner_view_scope(
            filters,
            current_user_id="1",
            has_view_all=False,
            permission_detail="forbidden",
        )
        is None
    )


def test_owner_scope_can_preserve_accessible_base_scope_without_defaulting_to_self():
    from fastapi import HTTPException

    from app.core.list_query.http import enforce_owner_view_scope

    assert (
        enforce_owner_view_scope(
            [],
            current_user_id="1",
            has_view_all=False,
            permission_detail="forbidden",
            default_to_self=False,
        )
        is None
    )

    with pytest.raises(HTTPException) as exc_info:
        enforce_owner_view_scope(
            [{"field": "owner_id", "op": "eq", "value": "2"}],
            current_user_id="1",
            has_view_all=False,
            permission_detail="forbidden",
            default_to_self=False,
        )
    assert exc_info.value.status_code == 403


def test_without_filter_field_removes_tab_owned_condition_without_mutating_input():
    from app.core.list_query.catalogs.common import without_filter_field

    filters = [
        FilterCondition(field="status", op="eq", value="open"),
        FilterCondition(field="owner_id", op="eq", value="1"),
    ]

    assert without_filter_field(filters, "status") == [FilterCondition(field="owner_id", op="eq", value="1")]
    assert len(filters) == 2


def test_optional_request_list_query_preserves_explicit_protocol_presence():
    from app.core.list_query.http import optional_request_list_query

    assert optional_request_list_query() == (None, None)
    assert optional_request_list_query(filters_raw="[]") == ([], None)
    assert optional_request_list_query(sorts_raw="[]") == (None, [])


def test_sorts_only_unified_query_does_not_mix_in_legacy_filters(db_session):
    query, total = apply_optional_list_query(
        db_session.query(Item),
        _catalog(),
        filters=None,
        sorts=[],
        legacy_filters=lambda legacy_query: legacy_query.filter(Item.name == "Acme"),
    )

    assert total == 3
    assert [row.name for row in query.all()] == ["Acme", "Beta Co", "Trial Co"]
