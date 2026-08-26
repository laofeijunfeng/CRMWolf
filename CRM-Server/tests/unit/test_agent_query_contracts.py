"""Contract tests for the CRM Agent root router and deterministic query seam."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.agent.orchestrator import (
    ContextPolicy,
    ResultSetContext,
    RootContextSnapshot,
    RootDecision,
)
from app.services.agent.query import (
    CRMFilter,
    CRMMetric,
    CRMQueryResult,
    CRMQuerySpec,
    CRMSort,
    EntityRef,
    GroundedFact,
    QueryError,
    QueryWarning,
)


def test_root_decision_and_context_snapshot_use_explicit_context_policy() -> None:
    entity_ref = EntityRef(
        ref_id="eref_01J1",
        resource="customer",
        public_id="cus_01J1",
        display_name="示例科技有限公司",
        result_set_id="rs_01JEXAMPLE",
    )
    query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city", "owner"],
        filters=[CRMFilter(field="city", operator="eq", value="上海")],
        sorts=[CRMSort(field="last_modified_time", direction="desc")],
    )

    decision = RootDecision(
        task_relation="NEW_TASK",
        route="QUERY",
        risk="READ_ONLY",
        context_policy=ContextPolicy(
            selected_entity="IGNORE",
            previous_query="IGNORE",
            result_set="IGNORE",
            active_workflow="NONE",
        ),
        confidence=0.98,
        reason_code="NEW_READ_ONLY_QUERY",
        evidence=["用户明确指定上海客户"],
    )
    context = RootContextSnapshot(
        previous_query=query,
        result_set=ResultSetContext(
            result_set_id="rs_01JEXAMPLE",
            ordered_entity_refs=[entity_ref],
        ),
    )

    assert decision.route == "QUERY"
    assert decision.context_policy.selected_entity == "IGNORE"
    assert context.previous_query == query
    assert context.result_set is not None
    assert context.result_set.ordered_entity_refs == [entity_ref]


def test_query_contract_rejects_unknown_fields_and_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        CRMQuerySpec.model_validate(
            {
                "resource": "customer",
                "projection": ["public_id"],
                "page_size": 101,
                "raw_sql": "select * from customers",
            }
        )

    with pytest.raises(ValidationError):
        RootDecision.model_validate(
            {
                "task_relation": "NEW_TASK",
                "route": "QUERY",
                "risk": "READ_ONLY",
                "context_policy": {
                    "selected_entity": "IGNORE",
                    "previous_query": "IGNORE",
                    "result_set": "IGNORE",
                    "active_workflow": "NONE",
                },
                "confidence": 1.1,
                "reason_code": "NEW_READ_ONLY_QUERY",
                "evidence": [],
            }
        )


def test_query_contract_defaults_to_the_full_per_tool_row_budget() -> None:
    query = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name"],
    )

    assert query.page_size == 50


def test_query_result_keeps_deterministic_rows_facts_warnings_and_errors_typed() -> None:
    entity_ref = EntityRef(
        ref_id="eref_01J1",
        resource="customer",
        public_id="cus_01J1",
        display_name="示例科技有限公司",
        result_set_id="rs_01JEXAMPLE",
    )
    result = CRMQueryResult(
        query_id="qry_01JEXAMPLE",
        result_set_id="rs_01JEXAMPLE",
        resource="customer",
        status="PARTIAL",
        rows=[{"public_id": "cus_01J1", "account_name": "示例科技有限公司", "city": "上海"}],
        entity_refs=[entity_ref],
        total=18,
        next_cursor="cursor_2",
        applied_filters=[CRMFilter(field="city", operator="eq", value="上海")],
        applied_sorts=[CRMSort(field="last_modified_time", direction="desc")],
        facts=[
            GroundedFact(
                fact_id="fact_total",
                label="客户总数",
                value=18,
                source="CRM_API",
            )
        ],
        warnings=[
            QueryWarning(
                code="RESULT_TRUNCATED",
                message="当前仅返回前 10 条结果。",
                resource="customer",
            )
        ],
    )
    error = QueryError(
        code="QUERY_INVALID",
        message="字段不支持筛选。",
        retryable=False,
        field="unknown_field",
    )
    metric = CRMMetric(key="customer_count", operator="count")

    assert result.rows[0]["city"] == "上海"
    assert result.warnings[0].code == "RESULT_TRUNCATED"
    assert error.code == "QUERY_INVALID"
    assert metric.field is None
    assert UUID("6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be").version == 4


def test_non_count_metric_requires_a_field() -> None:
    with pytest.raises(ValidationError):
        CRMMetric(key="total_amount", operator="sum")


def test_query_contracts_do_not_coerce_transport_scalars() -> None:
    with pytest.raises(ValidationError):
        CRMQuerySpec.model_validate(
            {
                "resource": "customer",
                "projection": ["public_id"],
                "page_size": "20",
            }
        )

    with pytest.raises(ValidationError):
        RootDecision.model_validate(
            {
                "task_relation": "NEW_TASK",
                "route": "QUERY",
                "risk": "READ_ONLY",
                "context_policy": {
                    "selected_entity": "IGNORE",
                    "previous_query": "IGNORE",
                    "result_set": "IGNORE",
                    "active_workflow": "NONE",
                },
                "confidence": "0.98",
                "reason_code": "NEW_READ_ONLY_QUERY",
                "evidence": [],
            }
        )
