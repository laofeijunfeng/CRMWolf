"""Behavioral tests for the public deterministic CRMQueryExecutor seam."""

import json
from unittest.mock import Mock

import pytest

from app.services.agent.query import CRMFilter, CRMQuerySpec, CRMSort
from app.services.agent.query.executor import CRMQueryExecutionError, DefaultCRMQueryExecutor
from app.services.agent.tools.api_client import CRMAPIClientError
from app.services.agent.tools.base import AgentToolContext


class FakeAPIClient:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def request(self, method, path, authorization, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "authorization": authorization,
                **kwargs,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


def _context() -> AgentToolContext:
    return AgentToolContext(
        db=Mock(),
        team_id=7,
        user_id=42,
        session_id=11,
        authorization="Bearer signed-token",
    )


@pytest.mark.asyncio
async def test_executor_maps_customer_query_to_authoritative_api_and_normalizes_result() -> None:
    client = FakeAPIClient(
        {
            "items": [
                {
                    "public_id": "cus_01",
                    "account_name": "上海示例科技",
                    "city": "上海",
                    "status": 0,
                    "owner_id": "42",
                    "creator_id": "42",
                    "owner_info": {"id": "42", "name": "销售一"},
                    "created_time": "2026-08-01T10:00:00",
                    "last_modified_time": "2026-08-21T10:00:00",
                    "version": 1,
                },
                {
                    "public_id": "cus_02",
                    "account_name": "上海第二科技",
                    "city": "上海",
                    "status": 1,
                    "owner_id": "9",
                    "creator_id": "9",
                    "owner_info": {"id": "9", "name": "销售二"},
                    "created_time": "2026-08-02T10:00:00",
                    "last_modified_time": "2026-08-20T10:00:00",
                    "version": 1,
                },
            ],
            "total": 3,
            "page": 1,
            "page_size": 2,
            "total_pages": 2,
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city", "status", "owner"],
        filters=[CRMFilter(field="city", operator="eq", value="上海")],
        sorts=[CRMSort(field="last_modified_time", direction="desc")],
        scope="accessible",
        page_size=2,
    )

    result = await executor.execute(spec, _context())

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/v1/customers/"
    assert call["authorization"] == "Bearer signed-token"
    params = call["params"]
    assert isinstance(params, dict)
    assert params["skip"] == 0
    assert params["limit"] == 2
    assert params["scope"] == "accessible"
    assert json.loads(str(params["filters"])) == [{"field": "city", "op": "eq", "value": "上海"}]
    assert json.loads(str(params["sorts"])) == [{"field": "last_modified_time", "direction": "desc"}]

    assert result.resource == "customer"
    assert result.status == "PARTIAL"
    assert result.total == 3
    assert result.next_cursor is not None
    assert result.rows == [
        {
            "public_id": "cus_01",
            "account_name": "上海示例科技",
            "city": "上海",
            "status": 0,
            "owner": {"id": "42", "name": "销售一", "avatar_url": None},
        },
        {
            "public_id": "cus_02",
            "account_name": "上海第二科技",
            "city": "上海",
            "status": 1,
            "owner": {"id": "9", "name": "销售二", "avatar_url": None},
        },
    ]
    assert [ref.public_id for ref in result.entity_refs] == ["cus_01", "cus_02"]
    assert [ref.display_name for ref in result.entity_refs] == ["上海示例科技", "上海第二科技"]
    assert result.warnings[0].code == "RESULT_TRUNCATED"
    assert result.query_id.startswith("qry_")


@pytest.mark.asyncio
async def test_executor_preserves_exact_customer_name_and_returns_permission_scoped_empty() -> None:
    client = FakeAPIClient(
        {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    hidden_customer_name = "跨团队不可访问-上海隐私客户"
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name"],
        filters=[CRMFilter(field="account_name", operator="eq", value=hidden_customer_name)],
        scope="accessible",
    )

    result = await executor.execute(spec, _context())

    assert len(client.calls) == 1
    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["scope"] == "accessible"
    assert json.loads(str(params["filters"])) == [
        {"field": "account_name", "op": "eq", "value": hidden_customer_name}
    ]
    assert result.status == "EMPTY"
    assert result.total == 0
    assert result.rows == []
    assert result.entity_refs == []


@pytest.mark.asyncio
async def test_executor_uses_customer_detail_endpoint_for_exact_public_id() -> None:
    client = FakeAPIClient(
        {
            "public_id": "cus_01",
            "account_name": "上海示例科技",
            "industry": "software",
            "city": "上海",
            "status": 0,
            "owner_id": "42",
            "creator_id": "42",
            "owner_info": {"id": "42", "name": "销售一"},
            "created_time": "2026-08-01T10:00:00",
            "last_modified_time": "2026-08-21T10:00:00",
            "version": 1,
            "contacts": [],
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name", "city", "owner"],
        filters=[CRMFilter(field="public_id", operator="eq", value="cus_01")],
    )

    result = await executor.execute(spec, _context())

    assert client.calls == [
        {
            "method": "GET",
            "path": "/v1/customers/cus_01",
            "authorization": "Bearer signed-token",
        }
    ]
    assert result.status == "SUCCESS"
    assert result.total == 1
    assert result.next_cursor is None
    assert result.rows == [
        {
            "public_id": "cus_01",
            "account_name": "上海示例科技",
            "city": "上海",
            "owner": {"id": "42", "name": "销售一", "avatar_url": None},
        }
    ]
    assert [ref.public_id for ref in result.entity_refs] == ["cus_01"]


@pytest.mark.asyncio
async def test_executor_maps_hidden_or_missing_exact_customer_to_permission_boundary() -> None:
    client = FakeAPIClient(
        error=CRMAPIClientError(
            "客户不存在",
            status_code=404,
            response_json={"detail": "客户不存在"},
        )
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name"],
        filters=[CRMFilter(field="public_id", operator="eq", value="cus_hidden")],
    )

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == "PERMISSION_DENIED"
    assert raised.value.error.message == "客户不存在或不在当前权限范围内"


@pytest.mark.asyncio
async def test_executor_preserves_permission_denied_instead_of_returning_empty() -> None:
    client = FakeAPIClient(error=CRMAPIClientError("无权查看客户", status_code=403))
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == "PERMISSION_DENIED"
    assert raised.value.error.message == "无权查看客户"
    assert raised.value.error.retryable is False


@pytest.mark.asyncio
async def test_executor_maps_structured_http_error_detail_without_contract_failure() -> None:
    structured_detail = {
        "code": "PERMISSION_DENIED",
        "status_code": 403,
        "detail": "无权查看该客户",
    }
    client = FakeAPIClient(
        error=CRMAPIClientError(
            structured_detail,  # type: ignore[arg-type]
            status_code=403,
            response_json={"detail": structured_detail},
        )
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == "PERMISSION_DENIED"
    assert raised.value.error.message == "无权查看该客户"


@pytest.mark.asyncio
async def test_executor_maps_single_customer_contacts_and_applies_local_pagination() -> None:
    client = FakeAPIClient(
        [
            {
                "id": 101,
                "customer_id": "cus_01",
                "name": "联系人一",
                "gender": 1,
                "position": "采购负责人",
                "is_decision_maker": True,
                "mobile": "13800000001",
                "email": None,
                "wechat_id": None,
                "remark": None,
                "reports_to": None,
                "is_primary": True,
                "created_time": "2026-08-01T10:00:00",
            },
            {
                "id": 102,
                "customer_id": "cus_01",
                "name": "联系人二",
                "gender": 0,
                "position": None,
                "is_decision_maker": False,
                "mobile": "13800000002",
                "email": None,
                "wechat_id": None,
                "remark": None,
                "reports_to": None,
                "is_primary": False,
                "created_time": "2026-08-02T10:00:00",
            },
        ]
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="contact",
        projection=["id", "customer_id", "name", "position", "mobile", "is_primary"],
        filters=[CRMFilter(field="customer_id", operator="eq", value="cus_01")],
        page_size=1,
    )

    result = await executor.execute(spec, _context())

    assert client.calls[0]["path"] == "/v1/customers/cus_01/contacts"
    assert result.status == "PARTIAL"
    assert result.total == 2
    assert result.rows == [
        {
            "id": 101,
            "customer_id": "cus_01",
            "name": "联系人一",
            "position": "采购负责人",
            "mobile": "13800000001",
            "is_primary": True,
        }
    ]
    assert result.entity_refs == []
    assert result.next_cursor is not None


@pytest.mark.asyncio
async def test_executor_maps_customer_activities_with_authoritative_skip_limit() -> None:
    client = FakeAPIClient(
        [
            {
                "id": 201,
                "customer_id": "cus_01",
                "activity_kind": "FOLLOW_UP",
                "activity_category": "FOLLOW_UP",
                "activity_label": "客户跟进",
                "title": "需求确认",
                "source_content": "已确认需求",
                "content_json": None,
                "summary": "客户确认采购范围",
                "processing_status": "COMPLETED",
                "processing_error": None,
                "processed_at": None,
                "next_follow_time": None,
                "next_follow_time_source": None,
                "next_action": "发送方案",
                "occurred_at": "2026-08-21T09:00:00",
                "creator_id": "42",
                "owner_id": "42",
                "created_time": "2026-08-21T09:00:00",
                "updated_time": "2026-08-21T10:00:00",
                "creator_info": {"id": "42", "name": "销售一"},
                "owner_info": {"id": "42", "name": "销售一"},
                "customer_info": {"id": "cus_01", "account_name": "示例客户"},
            }
        ]
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="customer_activity",
        projection=["id", "customer_id", "activity_kind", "summary", "owner"],
        filters=[CRMFilter(field="customer_id", operator="eq", value="cus_01")],
        page_size=2,
    )

    result = await executor.execute(spec, _context())

    assert client.calls[0]["path"] == "/v1/customer-activities/cus_01"
    assert client.calls[0]["params"] == {"skip": 0, "limit": 2}
    assert result.status == "SUCCESS"
    assert result.total is None
    assert result.rows == [
        {
            "id": 201,
            "customer_id": "cus_01",
            "activity_kind": "FOLLOW_UP",
            "summary": "客户确认采购范围",
            "owner": {"id": "42", "name": "销售一", "avatar_url": None},
        }
    ]


@pytest.mark.asyncio
async def test_executor_maps_follow_up_task_scope_filters_sorts_and_page() -> None:
    client = FakeAPIClient(
        {
            "items": [
                {
                    "id": "301",
                    "public_id": "fut_01",
                    "customer": {
                        "id": "cus_01",
                        "public_id": "cus_01",
                        "name": "示例客户",
                        "account_name": "示例客户",
                    },
                    "owner_id": "42",
                    "owner_info": {"id": "42", "name": "销售一"},
                    "creator_id": "42",
                    "creator_info": {"id": "42", "name": "销售一"},
                    "title": "发送方案",
                    "description": None,
                    "status": "OPEN",
                    "due_at": "2026-08-22T09:00:00",
                    "overdue_days": 0,
                }
            ],
            "total": 1,
            "filters": {
                "status": "open",
                "due_window": None,
                "customer_id": "cus_01",
                "owner_scope": "customer",
                "retrieval_mode": "structured",
                "query_text": None,
                "query_text_ignored_reason": None,
            },
            "customer_summary": [],
            "semantic_retrieval": {},
            "usage_policy": {
                "task_state_source": "mysql",
                "semantic_evidence_source": "none",
                "rule": "structured",
            },
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="follow_up_task",
        projection=["public_id", "customer", "title", "status", "due_at", "owner"],
        filters=[
            CRMFilter(field="status", operator="eq", value="open"),
            CRMFilter(field="customer_id", operator="eq", value="cus_01"),
            CRMFilter(field="tracking_content", operator="contains", value="方案"),
        ],
        sorts=[CRMSort(field="tracking_time", direction="asc")],
        scope="mine",
        page_size=10,
    )

    result = await executor.execute(spec, _context())

    call = client.calls[0]
    assert call["path"] == "/v1/follow-up-tasks"
    params = call["params"]
    assert isinstance(params, dict)
    assert params["status"] == "open"
    assert params["customer_id"] == "cus_01"
    assert params["owner_scope"] == "customer"
    assert json.loads(str(params["filters"])) == [{"field": "tracking_content", "op": "contains", "value": "方案"}]
    assert json.loads(str(params["sorts"])) == [{"field": "tracking_time", "direction": "asc"}]
    assert result.rows[0]["owner"] == {"id": "42", "name": "销售一", "avatar_url": None}
    assert result.entity_refs[0].public_id == "fut_01"


@pytest.mark.asyncio
async def test_executor_passes_completed_work_cursor_through_without_offset_decoding() -> None:
    client = FakeAPIClient(
        {
            "items": [],
            "available_total": 0,
            "returned_count": 0,
            "truncated": False,
            "next_cursor": None,
            "source_counts": {"completed_follow_up_task": 0, "customer_activity": 0},
            "source_total_counts": {"completed_follow_up_task": 0, "customer_activity": 0},
            "source_status": {
                "completed_tasks": "queried",
                "customer_activities": "queried",
                "business_events": "skipped",
            },
            "filters": {
                "window": "custom",
                "starts_at": "2026-08-01T00:00:00",
                "ends_at": "2026-08-22T00:00:00",
                "starts_on": "2026-08-01",
                "ends_before": "2026-08-22",
                "timezone": "Asia/Shanghai",
                "customer_id": "cus_01",
                "include_tasks": True,
                "include_activities": True,
                "include_business_events": False,
            },
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="completed_work",
        projection=["fact_id", "fact_type", "occurred_at", "customer", "title", "payload"],
        filters=[
            CRMFilter(field="customer_id", operator="eq", value="cus_01"),
            CRMFilter(
                field="occurred_at",
                operator="between",
                value=["2026-08-01T00:00:00", "2026-08-22T00:00:00"],
            ),
        ],
        scope="mine",
        page_size=20,
        cursor="work-summary-opaque-cursor",
    )

    result = await executor.execute(spec, _context())

    assert client.calls[0] == {
        "method": "GET",
        "path": "/v1/agent-query/completed-work",
        "authorization": "Bearer signed-token",
        "params": {
            "window": "custom",
            "customer_id": "cus_01",
            "start_at": "2026-08-01T00:00:00",
            "end_at": "2026-08-22T00:00:00",
            "cursor": "work-summary-opaque-cursor",
            "limit": 20,
        },
    }
    assert result.status == "EMPTY"
    assert result.total == 0


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (408, "UPSTREAM_TIMEOUT"),
        (429, "UPSTREAM_UNAVAILABLE"),
        (500, "UPSTREAM_UNAVAILABLE"),
        (503, "UPSTREAM_UNAVAILABLE"),
    ],
)
@pytest.mark.asyncio
async def test_executor_maps_retryable_crm_api_statuses_to_stable_upstream_errors(
    status_code: int, expected_code: str
) -> None:
    client = FakeAPIClient(error=CRMAPIClientError("upstream failure", status_code=status_code))
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == expected_code
    assert raised.value.error.retryable is True
    assert raised.value.error.message not in {"upstream failure", "CRM API query failed"}


@pytest.mark.asyncio
async def test_executor_keeps_non_retryable_crm_api_status_as_internal_error() -> None:
    client = FakeAPIClient(error=CRMAPIClientError("bad gateway input", status_code=409))
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == "INTERNAL_ERROR"
    assert raised.value.error.retryable is False


@pytest.mark.asyncio
async def test_executor_maps_malformed_authoritative_response_to_internal_error() -> None:
    client = FakeAPIClient({"items": "not-a-list"})
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == "INTERNAL_ERROR"
    assert raised.value.error.message == "CRM API returned an invalid response"
    assert raised.value.error.retryable is False


@pytest.mark.asyncio
async def test_executor_hides_unexpected_exception_details() -> None:
    client = FakeAPIClient(error=RuntimeError("secret upstream implementation detail"))
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(resource="customer", projection=["public_id", "account_name"])

    with pytest.raises(CRMQueryExecutionError) as raised:
        await executor.execute(spec, _context())

    assert raised.value.error.code == "INTERNAL_ERROR"
    assert raised.value.error.message == "CRM query failed"
    assert "secret" not in raised.value.error.message
    assert raised.value.error.retryable is False


@pytest.mark.asyncio
async def test_executor_sends_customer_keyword_through_dedicated_parameter() -> None:
    client = FakeAPIClient(
        {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="customer",
        projection=["public_id", "account_name"],
        filters=[CRMFilter(field="keyword", operator="contains", value="示例科技")],
    )

    await executor.execute(spec, _context())

    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["keyword"] == "示例科技"
    assert "filters" not in params


@pytest.mark.asyncio
async def test_executor_expands_follow_up_tracking_time_range_for_authoritative_api() -> None:
    client = FakeAPIClient(
        {
            "items": [],
            "total": 0,
            "filters": {
                "status": "all",
                "due_window": None,
                "customer_id": None,
                "owner_scope": "mine",
                "retrieval_mode": "structured",
                "query_text": None,
                "query_text_ignored_reason": None,
            },
            "customer_summary": [],
            "semantic_retrieval": {},
            "usage_policy": {
                "task_state_source": "mysql",
                "semantic_evidence_source": "none",
                "rule": "structured",
            },
        }
    )
    executor = DefaultCRMQueryExecutor(api_client=client)
    spec = CRMQuerySpec(
        resource="follow_up_task",
        projection=["public_id", "title"],
        filters=[
            CRMFilter(
                field="tracking_time",
                operator="between",
                value=["2026-08-01T00:00:00", "2026-08-22T00:00:00"],
            )
        ],
        scope="mine",
    )

    await executor.execute(spec, _context())

    params = client.calls[0]["params"]
    assert isinstance(params, dict)
    assert json.loads(str(params["filters"])) == [
        {"field": "tracking_time", "op": "after", "value": "2026-08-01T00:00:00"},
        {"field": "tracking_time", "op": "before", "value": "2026-08-22T00:00:00"},
    ]
