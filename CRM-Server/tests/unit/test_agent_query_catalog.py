"""Behavioral tests for the deterministic CRM query catalog and policy seam."""

from unittest.mock import Mock

import pytest

from app.services.agent.query import CRMFilter, CRMQuerySpec, CRMSort
from app.services.agent.query.catalog import CRMQueryCatalog
from app.services.agent.query.policy import QueryPolicyError, QueryPolicyValidator
from app.services.agent.tools.base import AgentToolContext


def _context(*, permission_codes: frozenset[str] = frozenset()) -> AgentToolContext:
    return AgentToolContext(
        db=Mock(),
        team_id=7,
        user_id=42,
        session_id=11,
        authorization="Bearer signed-token",
        permission_codes=permission_codes,
    )


def test_customer_catalog_is_the_single_declaration_for_query_capabilities() -> None:
    definition = CRMQueryCatalog().resolve("customer")

    assert definition.adapter_key == "customers_api"
    assert definition.default_projection == (
        "public_id",
        "account_name",
        "city",
        "industry",
        "status",
        "owner",
    )
    assert definition.filter_operators("city") == frozenset({"eq", "in"})
    assert definition.filter_operators("created_time") == frozenset({"gte", "lte", "between"})
    assert definition.sortable_fields == frozenset(
        {"created_time", "last_modified_time", "account_name", "city", "status"}
    )
    assert definition.relations == frozenset(
        {"contacts", "activities", "opportunities", "contracts", "payments", "invoices"}
    )
    assert definition.default_scope == "accessible"


def test_policy_accepts_a_catalog_backed_accessible_customer_query() -> None:
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city", "owner"],
        filters=[CRMFilter(field="city", operator="eq", value="上海")],
        sorts=[CRMSort(field="last_modified_time", direction="desc")],
        scope="accessible",
        page_size=20,
    )

    validated = QueryPolicyValidator().validate(spec, _context())

    assert validated == spec


@pytest.mark.parametrize(
    ("spec", "field", "operator"),
    [
        (
            CRMQuerySpec(resource="customer", projection=["public_id", "secret_note"]),
            "secret_note",
            None,
        ),
        (
            CRMQuerySpec(
                resource="customer",
                projection=["public_id"],
                filters=[CRMFilter(field="city", operator="contains", value="上海")],
            ),
            "city",
            "contains",
        ),
        (
            CRMQuerySpec(
                resource="customer",
                projection=["public_id"],
                sorts=[CRMSort(field="owner_id", direction="asc")],
            ),
            "owner_id",
            None,
        ),
    ],
)
def test_policy_rejects_projection_filter_and_sort_outside_catalog(
    spec: CRMQuerySpec,
    field: str,
    operator: str | None,
) -> None:
    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"
    assert raised.value.error.field == field
    assert raised.value.error.operator == operator


def test_policy_requires_customer_view_all_for_team_scope() -> None:
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name"],
        scope="team",
    )

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context(permission_codes=frozenset({"customer:view:own"})))

    assert raised.value.error.code == "PERMISSION_DENIED"
    assert raised.value.error.retryable is False


def test_policy_accepts_team_scope_when_server_context_has_view_all() -> None:
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name"],
        scope="team",
    )

    assert QueryPolicyValidator().validate(
        spec,
        _context(permission_codes=frozenset({"customer:view:all"})),
    ) == spec

@pytest.mark.parametrize(
    ("resource", "adapter_key", "default_scope"),
    [
        ("contact", "customer_contacts_api", "accessible"),
        ("customer_activity", "customer_activities_api", "accessible"),
        ("follow_up_task", "follow_up_tasks_api", "mine"),
        ("completed_work", "completed_work_api", "mine"),
    ],
)
def test_p0_resource_definitions_are_registered(
    resource: str,
    adapter_key: str,
    default_scope: str,
) -> None:
    definition = CRMQueryCatalog().resolve(resource)  # type: ignore[arg-type]

    assert definition.adapter_key == adapter_key
    assert definition.default_scope == default_scope
    assert definition.default_projection


@pytest.mark.parametrize("resource", ["contact", "customer_activity"])
def test_single_customer_resources_require_an_exact_customer_filter(resource: str) -> None:
    spec = CRMQuerySpec(resource=resource, projection=["customer_id"])  # type: ignore[arg-type]

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"
    assert raised.value.error.field == "customer_id"




@pytest.mark.parametrize("resource", ["follow_up_task", "completed_work"])
def test_personal_query_resources_reject_accessible_scope(resource: str) -> None:
    spec = CRMQuerySpec(
        resource=resource,  # type: ignore[arg-type]
        projection=["public_id"] if resource == "follow_up_task" else ["fact_id"],
        scope="accessible",
    )

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"


def test_policy_normalizes_mixed_timezone_temporal_range_before_comparison() -> None:
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id"],
        filters=[
            CRMFilter(
                field="created_time",
                operator="between",
                value=["2026-08-01T00:00:00", "2026-08-21T00:00:00+08:00"],
            )
        ],
    )

    assert QueryPolicyValidator().validate(spec, _context()) == spec


@pytest.mark.parametrize("resource", ["follow_up_task", "completed_work"])
def test_personal_query_resources_reject_team_scope(resource: str) -> None:
    spec = CRMQuerySpec(resource=resource, projection=["title"], scope="team")  # type: ignore[arg-type]

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"

@pytest.mark.parametrize(
    ("operator", "value"),
    [
        ("in", "上海"),
        ("in", []),
        ("not_in", "互联网"),
        ("between", ["2026-08-01"]),
        ("between", ["2026-08-01", "2026-08-31", "2026-09-01"]),
    ],
)
def test_policy_rejects_invalid_collection_filter_values(operator: str, value: object) -> None:
    field = "created_time" if operator == "between" else "city" if operator == "in" else "industry"
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id"],
        filters=[CRMFilter(field=field, operator=operator, value=value)],  # type: ignore[arg-type]
    )

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"
    assert raised.value.error.field == field
    assert raised.value.error.operator == operator


@pytest.mark.parametrize(
    "value",
    ["not-a-date", ["2026-08-01", "not-a-date"], ["2026-09-01", "2026-08-01"]],
)
def test_policy_rejects_invalid_temporal_filter_values(value: object) -> None:
    operator = "between" if isinstance(value, list) else "gte"
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id"],
        filters=[CRMFilter(field="created_time", operator=operator, value=value)],  # type: ignore[arg-type]
    )

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"
    assert raised.value.error.field == "created_time"


def test_policy_rejects_relation_traversal_instead_of_interpreting_dotted_fields() -> None:
    spec = CRMQuerySpec(resource="customer", projection=["contacts.name"])

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_UNSUPPORTED"
    assert raised.value.error.field == "contacts.name"


def test_policy_rejects_metrics_and_grouping_until_catalog_declares_aggregate_support() -> None:
    from app.services.agent.query import CRMMetric

    metric_spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id"],
        metrics=[CRMMetric(key="customer_count", operator="count")],
    )
    grouped_spec = CRMQuerySpec(
        resource="customer",
        projection=["city"],
        group_by=["city"],
    )

    for spec in (metric_spec, grouped_spec):
        with pytest.raises(QueryPolicyError) as raised:
            QueryPolicyValidator().validate(spec, _context())
        assert raised.value.error.code == "QUERY_UNSUPPORTED"


def test_policy_enforces_p0_single_tool_row_limit() -> None:
    spec = CRMQuerySpec(resource="customer", projection=["public_id"], page_size=51)

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "context",
    [
        AgentToolContext(db=Mock(), team_id=0, user_id=42, session_id=11, authorization="Bearer x"),
        AgentToolContext(db=Mock(), team_id=7, user_id=0, session_id=11, authorization="Bearer x"),
        AgentToolContext(db=Mock(), team_id=7, user_id=42, session_id=0, authorization="Bearer x"),
        AgentToolContext(db=Mock(), team_id=7, user_id=42, session_id=11, authorization=""),
    ],
)
def test_policy_rejects_untrusted_or_incomplete_server_context(context: AgentToolContext) -> None:
    spec = CRMQuerySpec(resource="customer", projection=["public_id"])

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, context)

    assert raised.value.error.code in {"QUERY_INVALID", "PERMISSION_DENIED"}


def test_policy_does_not_claim_multi_status_support_for_follow_up_endpoint() -> None:
    spec = CRMQuerySpec(
        resource="follow_up_task",
        projection=["public_id"],
        filters=[CRMFilter(field="status", operator="in", value=["open", "completed"])],
        scope="mine",
    )

    with pytest.raises(QueryPolicyError) as raised:
        QueryPolicyValidator().validate(spec, _context())

    assert raised.value.error.code == "QUERY_INVALID"
    assert raised.value.error.field == "status"
