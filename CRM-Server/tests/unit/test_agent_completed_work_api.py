"""HTTP seam tests for the authoritative completed-work CRM query endpoint."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agent_query


def _payload() -> dict[str, object]:
    return {
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
            "window": "this_week",
            "starts_at": "2026-08-17T00:00:00",
            "ends_at": "2026-08-24T00:00:00",
            "starts_on": "2026-08-17",
            "ends_before": "2026-08-24",
            "timezone": "Asia/Shanghai",
            "customer_id": None,
            "include_tasks": True,
            "include_activities": True,
            "include_business_events": False,
        },
    }


def _client(monkeypatch, service_result=None, service_error=None):
    captured = {}

    def list_completed_work(_db, **kwargs):
        captured.update(kwargs)
        if service_error is not None:
            raise service_error
        return service_result or _payload()

    monkeypatch.setattr(agent_query.work_summary_service, "list_completed_work", list_completed_work)
    app = FastAPI()
    app.include_router(agent_query.router)
    app.dependency_overrides[agent_query.get_db] = lambda: Mock()
    app.dependency_overrides[agent_query.get_current_user_team] = lambda: 7
    app.dependency_overrides[agent_query.get_current_active_user] = lambda: SimpleNamespace(id=42)
    return TestClient(app), captured


def test_completed_work_endpoint_uses_authenticated_team_scoped_domain_service(monkeypatch) -> None:
    client, captured = _client(monkeypatch)

    response = client.get("/v1/agent-query/completed-work?window=this_week&limit=20")

    assert response.status_code == 200
    assert response.json() == _payload()
    assert captured == {
        "team_id": 7,
        "user_id": 42,
        "window": "this_week",
        "customer_public_id": None,
        "include_tasks": True,
        "include_activities": True,
        "include_business_events": False,
        "start_at": None,
        "end_at": None,
        "cursor": None,
        "limit": 20,
    }


def test_completed_work_endpoint_projects_internal_raw_bounds_from_service_filters(monkeypatch) -> None:
    service_payload = _payload()
    service_payload["filters"] = {
        **service_payload["filters"],
        "start_at": None,
        "end_at": None,
    }
    client, _ = _client(monkeypatch, service_result=service_payload)

    response = client.get("/v1/agent-query/completed-work?window=this_week")

    assert response.status_code == 200
    assert response.json() == _payload()


def test_completed_work_endpoint_preserves_permission_error(monkeypatch) -> None:
    client, _ = _client(monkeypatch, service_error=PermissionError("无权查看该客户"))

    response = client.get("/v1/agent-query/completed-work?customer_id=cus_forbidden")

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "PERMISSION_DENIED",
            "status_code": 403,
            "detail": "无权查看该客户",
        }
    }


def test_completed_work_endpoint_passes_custom_window_bounds(monkeypatch) -> None:
    payload = _payload()
    payload["filters"] = {
        **payload["filters"],
        "window": "custom",
        "starts_at": "2026-08-01T00:00:00",
        "ends_at": "2026-08-22T00:00:00",
        "starts_on": "2026-08-01",
        "ends_before": "2026-08-22",
        "customer_id": "cus_01",
    }
    client, captured = _client(monkeypatch, service_result=payload)

    response = client.get(
        "/v1/agent-query/completed-work",
        params={
            "window": "custom",
            "customer_id": "cus_01",
            "start_at": "2026-08-01T00:00:00",
            "end_at": "2026-08-22T00:00:00",
        },
    )

    assert response.status_code == 200
    assert captured["window"] == "custom"
    assert captured["customer_public_id"] == "cus_01"
    assert captured["start_at"] == "2026-08-01T00:00:00"
    assert captured["end_at"] == "2026-08-22T00:00:00"


def test_completed_work_endpoint_rejects_invalid_custom_bounds_before_service(monkeypatch) -> None:
    client, captured = _client(monkeypatch)

    response = client.get(
        "/v1/agent-query/completed-work",
        params={
            "window": "custom",
            "start_at": "2026-08-22T00:00:00",
            "end_at": "2026-08-01T00:00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "QUERY_INVALID"
    assert captured == {}


def test_completed_work_endpoint_maps_domain_value_error_to_query_invalid(monkeypatch) -> None:
    client, _ = _client(monkeypatch, service_error=ValueError("invalid summary window"))

    response = client.get("/v1/agent-query/completed-work")

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "code": "QUERY_INVALID",
            "status_code": 400,
            "detail": "invalid summary window",
        }
    }


def test_completed_work_endpoint_maps_malformed_service_result_to_internal_error(monkeypatch) -> None:
    client, _ = _client(monkeypatch, service_result={"items": "secret malformed payload"})

    response = client.get("/v1/agent-query/completed-work")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "INTERNAL_ERROR",
            "status_code": 500,
            "detail": "completed-work query failed",
        }
    }
    assert "secret" not in response.text


@pytest.mark.parametrize("missing_field", ["source_counts", "source_status", "filters"])
def test_completed_work_endpoint_rejects_missing_service_contract_fields(
    monkeypatch,
    missing_field: str,
) -> None:
    payload = _payload()
    payload.pop(missing_field)
    client, _ = _client(monkeypatch, service_result=payload)

    response = client.get("/v1/agent-query/completed-work")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"


def test_main_application_registers_completed_work_query_route() -> None:
    from app.main import app

    assert any(
        route.path == "/api/v1/agent-query/completed-work" and "GET" in (route.methods or set()) for route in app.routes
    )
