"""Frozen HTTP-boundary contracts for the completed-work Query capability."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.agent.query.completed_work_contracts import (
    CompletedWorkHTTPError,
    CompletedWorkQueryRequest,
    CompletedWorkQueryResponse,
    CustomerActivityPayload,
)

_EXAMPLES_PATH = (
    Path(__file__).parents[1] / "fixtures" / "agent_contracts" / "crm_agent_contract_examples.json"
)


def _completed_work_response_example() -> dict[str, object]:
    examples = json.loads(_EXAMPLES_PATH.read_text(encoding="utf-8"))
    return deepcopy(examples["completed_work_response"])


def test_completed_work_request_defaults_to_this_week_with_bounded_page() -> None:
    request = CompletedWorkQueryRequest.model_validate({})

    assert request.model_dump() == {
        "window": "this_week",
        "customer_id": None,
        "start_at": None,
        "end_at": None,
        "cursor": None,
        "limit": 50,
    }


def test_completed_work_request_accepts_customer_filter_custom_range_and_opaque_cursor() -> None:
    request = CompletedWorkQueryRequest.model_validate({
        "window": "custom",
        "customer_id": "cus_11111111111111111111111111111111",
        "start_at": "2026-08-01",
        "end_at": "2026-08-21T23:59:59+08:00",
        "cursor": "eyJvZmZzZXQiOjUwfQ==",
        "limit": 100,
    })

    assert request.window == "custom"
    assert request.customer_id == "cus_11111111111111111111111111111111"
    assert request.limit == 100


@pytest.mark.parametrize(
    "payload",
    [
        {"window": "custom", "start_at": "2026-08-01"},
        {"window": "custom", "start_at": "not-a-date", "end_at": "2026-08-21"},
        {"window": "custom", "start_at": "2026-08-22", "end_at": "2026-08-21"},
        {"window": "today", "start_at": "2026-08-21", "end_at": "2026-08-21"},
        {"limit": 0},
        {"limit": 101},
        {"limit": "50"},
        {"cursor": ""},
        {"unknown": "field"},
    ],
)
def test_completed_work_request_rejects_malformed_or_ambiguous_queries(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CompletedWorkQueryRequest.model_validate(payload)


def test_completed_work_response_is_a_closed_typed_fact_page() -> None:
    response = CompletedWorkQueryResponse.model_validate({
        "items": [
            {
                "fact_id": "completed_follow_up_task:fut_01:2026-08-21T10:00:00",
                "fact_type": "completed_follow_up_task",
                "source_group": "task",
                "source_table": "crm_follow_up_tasks",
                "source_public_id": "fut_01",
                "business_key": None,
                "occurred_at": "2026-08-21T10:00:00",
                "customer": {
                    "id": "cus_01",
                    "public_id": "cus_01",
                    "name": "示例客户",
                    "account_name": "示例客户",
                },
                "attribution": {
                    "user_id": "42",
                    "field": "owner_id",
                    "source": "crm_follow_up_tasks.owner_id",
                },
                "title": "完成方案确认",
                "payload": {
                    "id": "fut_01",
                    "public_id": "fut_01",
                    "customer": {
                        "id": "cus_01",
                        "public_id": "cus_01",
                        "name": "示例客户",
                        "account_name": "示例客户",
                    },
                    "owner_id": "42",
                    "creator_id": "42",
                    "title": "完成方案确认",
                    "description": None,
                    "status": "COMPLETED",
                    "due_at": "2026-08-21T09:00:00",
                    "due_at_text": None,
                    "completed_at": "2026-08-21T10:00:00",
                },
            },
            {
                "fact_id": "customer_activity:微信同步:2026-08-21T09:00:00",
                "fact_type": "customer_activity",
                "source_group": "activity",
                "source_table": "crm_customer_activities",
                "source_public_id": None,
                "business_key": None,
                "occurred_at": "2026-08-21T09:00:00",
                "customer": None,
                "attribution": {
                    "user_id": "42",
                    "field": "owner_id",
                    "source": "crm_customer_activities.owner_id",
                },
                "title": "微信同步",
                "payload": {
                    "customer": None,
                    "activity_kind": "FOLLOW_UP",
                    "title": "微信同步",
                    "summary": "客户确认下周评审",
                    "next_action": None,
                    "next_follow_time": None,
                    "occurred_at": "2026-08-21T09:00:00",
                    "owner_id": "42",
                },
            },
        ],
        "available_total": 3,
        "returned_count": 2,
        "truncated": True,
        "next_cursor": "eyJvZmZzZXQiOjJ9",
        "source_counts": {"completed_follow_up_task": 1, "customer_activity": 1},
        "source_total_counts": {"completed_follow_up_task": 1, "customer_activity": 2},
        "source_status": {
            "completed_tasks": "queried",
            "customer_activities": "queried",
            "business_events": "skipped",
        },
        "filters": {
            "window": "today",
            "starts_at": "2026-08-21T00:00:00",
            "ends_at": "2026-08-22T00:00:00",
            "starts_on": "2026-08-21",
            "ends_before": "2026-08-22",
            "timezone": "Asia/Shanghai",
            "customer_id": None,
            "include_tasks": True,
            "include_activities": True,
            "include_business_events": False,
        },
    })

    assert [item.fact_type for item in response.items] == [
        "completed_follow_up_task",
        "customer_activity",
    ]
    assert response.returned_count == 2


def test_completed_work_response_rejects_inconsistent_pagination() -> None:
    with pytest.raises(ValidationError):
        CompletedWorkQueryResponse.model_validate({
            "items": [],
            "available_total": 0,
            "returned_count": 1,
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
                "window": "today",
                "starts_at": "2026-08-21T00:00:00",
                "ends_at": "2026-08-22T00:00:00",
                "starts_on": "2026-08-21",
                "ends_before": "2026-08-22",
                "timezone": "Asia/Shanghai",
                "customer_id": None,
                "include_tasks": True,
                "include_activities": True,
                "include_business_events": False,
            },
        })


def test_completed_work_response_rejects_unknown_nested_payload_fields() -> None:
    with pytest.raises(ValidationError):
        CompletedWorkQueryResponse.model_validate({
            "items": [
                {
                    "fact_id": "completed_follow_up_task:fut_01:2026-08-21T10:00:00",
                    "fact_type": "completed_follow_up_task",
                    "source_group": "task",
                    "source_table": "crm_follow_up_tasks",
                    "source_public_id": "fut_01",
                    "business_key": None,
                    "occurred_at": "2026-08-21T10:00:00",
                    "customer": {
                        "id": "cus_01",
                        "public_id": "cus_01",
                        "name": "示例客户",
                        "account_name": "示例客户",
                    },
                    "attribution": {
                        "user_id": "42",
                        "field": "owner_id",
                        "source": "crm_follow_up_tasks.owner_id",
                    },
                    "title": "完成方案确认",
                    "payload": {
                        "id": "fut_01",
                        "public_id": "fut_01",
                        "customer": {
                            "id": "cus_01",
                            "public_id": "cus_01",
                            "name": "示例客户",
                            "account_name": "示例客户",
                        },
                        "owner_id": "42",
                        "creator_id": "42",
                        "title": "完成方案确认",
                        "description": None,
                        "status": "COMPLETED",
                        "due_at": "2026-08-21T09:00:00",
                        "due_at_text": None,
                        "completed_at": "2026-08-21T10:00:00",
                        "owner_info": {"id": "42"},
                    },
                }
            ],
            "available_total": 1,
            "returned_count": 1,
            "truncated": False,
            "next_cursor": None,
            "source_counts": {"completed_follow_up_task": 1, "customer_activity": 0},
            "source_total_counts": {"completed_follow_up_task": 1, "customer_activity": 0},
            "source_status": {
                "completed_tasks": "queried",
                "customer_activities": "queried",
                "business_events": "skipped",
            },
            "filters": {
                "window": "today",
                "starts_at": "2026-08-21T00:00:00",
                "ends_at": "2026-08-22T00:00:00",
                "starts_on": "2026-08-21",
                "ends_before": "2026-08-22",
                "timezone": "Asia/Shanghai",
                "customer_id": None,
                "include_tasks": True,
                "include_activities": True,
                "include_business_events": False,
            },
        })


@pytest.mark.parametrize(
    "path",
    [
        ("items", 0, "occurred_at"),
        ("items", 0, "payload", "due_at"),
        ("items", 0, "payload", "completed_at"),
        ("filters", "starts_at"),
        ("filters", "ends_at"),
        ("filters", "starts_on"),
        ("filters", "ends_before"),
    ],
)
def test_completed_work_response_rejects_invalid_iso_temporal_values(
    path: tuple[str | int, ...],
) -> None:
    payload = _completed_work_response_example()
    target: object = payload
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[index]
    target[path[-1]] = "not-a-date"  # type: ignore[index]

    with pytest.raises(ValidationError):
        CompletedWorkQueryResponse.model_validate(payload)


@pytest.mark.parametrize("field", ["occurred_at", "next_follow_time"])
def test_customer_activity_payload_rejects_invalid_iso_datetimes(field: str) -> None:
    payload = {
        "customer": None,
        "activity_kind": "FOLLOW_UP",
        "title": None,
        "summary": None,
        "next_action": None,
        "next_follow_time": "2026-08-22T09:00:00",
        "occurred_at": "2026-08-21T09:00:00",
        "owner_id": "42",
    }
    payload[field] = "not-a-datetime"

    with pytest.raises(ValidationError):
        CustomerActivityPayload.model_validate(payload)


def test_completed_work_error_rejects_code_status_mismatch() -> None:
    with pytest.raises(ValidationError):
        CompletedWorkHTTPError.model_validate({
            "code": "PERMISSION_DENIED",
            "status_code": 400,
            "detail": "无权查看该客户",
        })


@pytest.mark.parametrize("status_code", [400, 422])
def test_completed_work_query_invalid_error_accepts_request_and_validation_statuses(
    status_code: int,
) -> None:
    error = CompletedWorkHTTPError.model_validate({
        "code": "QUERY_INVALID",
        "status_code": status_code,
        "detail": "查询条件无效",
    })

    assert error.status_code == status_code


def test_completed_work_error_mapping_is_frozen_without_endpoint_implementation() -> None:
    from pydantic import ValidationError as PydanticValidationError

    from app.services.agent.query.completed_work_contracts import (
        CompletedWorkQueryRequest,
        map_completed_work_http_error,
    )

    permission = map_completed_work_http_error(PermissionError("无权查看该客户"))
    invalid = map_completed_work_http_error(ValueError("工作总结 cursor 无效"))
    try:
        CompletedWorkQueryRequest.model_validate({"limit": 101})
    except PydanticValidationError as exc:
        validation = map_completed_work_http_error(exc)
    internal = map_completed_work_http_error(RuntimeError("database detail must not leak"))

    assert permission.model_dump() == {
        "code": "PERMISSION_DENIED",
        "status_code": 403,
        "detail": "无权查看该客户",
    }
    assert invalid.model_dump() == {
        "code": "QUERY_INVALID",
        "status_code": 400,
        "detail": "工作总结 cursor 无效",
    }
    assert validation.code == "QUERY_INVALID"
    assert validation.status_code == 422
    assert internal.model_dump() == {
        "code": "INTERNAL_ERROR",
        "status_code": 500,
        "detail": "completed-work query failed",
    }
