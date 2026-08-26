from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api import customer_activities, customers, follow_up_tasks
from app.core import deps


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(customers.router)
    test_app.include_router(customer_activities.router)
    test_app.include_router(follow_up_tasks.router)
    test_app.dependency_overrides[deps.get_db] = lambda: object()
    test_app.dependency_overrides[deps.get_current_user_team] = lambda: 7
    test_app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=42,
        name="查询用户",
        status="active",
    )
    return test_app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _permissions(*codes: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(code=code) for code in codes]


def _empty_follow_up_payload(**overrides: Any) -> dict[str, Any]:
    filters = {
        "status": "open",
        "due_window": None,
        "customer_id": None,
        "owner_scope": "mine",
        "retrieval_mode": "structured",
        "query_text": None,
        "query_text_ignored_reason": None,
    }
    filters.update(overrides)
    return {
        "items": [],
        "total": 0,
        "filters": filters,
        "customer_summary": [],
        "semantic_retrieval": {},
        "usage_policy": {
            "task_state_source": "mysql",
            "semantic_evidence_source": "none",
            "rule": "structured",
        },
    }


def test_query_customers_preserves_city_accessible_scope_and_pagination(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda db, user_id, team_id: _permissions("customer:view:own"),
    )

    def _get_multi(**kwargs: Any) -> tuple[list[Any], int]:
        captured.update(kwargs)
        return [], 23

    monkeypatch.setattr(customers.customer_crud, "get_multi", _get_multi)
    monkeypatch.setattr(customers, "map_sources_by_ids", lambda db, team_id, source_ids: {})

    response = client.get(
        "/v1/customers/",
        params={
            "city": "上海",
            "scope": "accessible",
            "skip": 20,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 23,
        "page": 3,
        "page_size": 10,
        "total_pages": 3,
    }
    assert captured["team_id"] == 7
    assert captured["current_user_id"] == "42"
    assert captured["city"] == "上海"
    assert captured["scope"] == "accessible"
    assert captured["owner_id"] is None
    assert captured["include_collaborated"] is True
    assert captured["skip"] == 20
    assert captured["limit"] == 10


def test_query_customers_passes_supported_unified_filters_and_sorts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda db, user_id, team_id: _permissions("customer:view:all"),
    )

    def _get_multi(**kwargs: Any) -> tuple[list[Any], int]:
        captured.update(kwargs)
        return [], 0

    monkeypatch.setattr(customers.customer_crud, "get_multi", _get_multi)
    monkeypatch.setattr(customers, "map_sources_by_ids", lambda db, team_id, source_ids: {})

    response = client.get(
        "/v1/customers/",
        params={
            "filters": '[{"field":"city","op":"eq","value":"上海"}]',
            "sorts": '[{"field":"last_modified_time","direction":"desc"}]',
        },
    )

    assert response.status_code == 200
    assert [(item.field, item.op, item.value) for item in captured["filters"]] == [
        ("city", "eq", "上海")
    ]
    assert [(item.field, item.direction) for item in captured["sorts"]] == [
        ("last_modified_time", "desc")
    ]


def test_query_customers_rejects_other_owner_without_view_all(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda db, user_id, team_id: _permissions("customer:view:own"),
    )
    monkeypatch.setattr(
        customers.customer_crud,
        "get_multi",
        lambda **kwargs: pytest.fail("authorization must happen before customer retrieval"),
    )

    response = client.get("/v1/customers/", params={"owner_id": "99"})

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "只能查看自己负责的客户，或需要 customer:view:all 权限查看他人数据"  # noqa: RUF001
    )


def test_query_customers_rejects_unknown_scope_and_oversized_page(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda db, user_id, team_id: _permissions("customer:view:all"),
    )

    unknown_scope = client.get("/v1/customers/", params={"scope": "team"})
    oversized_page = client.get("/v1/customers/", params={"limit": 101})

    assert unknown_scope.status_code == 400
    assert unknown_scope.json()["detail"] == "scope 仅支持 collaborated/accessible"
    assert oversized_page.status_code == 422


def test_query_customer_contacts_authorizes_before_read_and_has_no_pagination_contract(
    app: FastAPI,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    customer = SimpleNamespace(id=301, public_id="cus_11111111111111111111111111111111")

    def _authorize(db: Any, customer_id: str, team_id: int, current_user: Any) -> Any:
        events.append("authorize")
        return customer

    def _read_contacts(db: Any, customer_id: int, team_id: int) -> list[Any]:
        events.append("read")
        assert customer_id == 301
        assert team_id == 7
        return []

    monkeypatch.setattr(customers, "_get_viewable_customer", _authorize)
    monkeypatch.setattr(customers.contact_crud, "get_by_customer_id", _read_contacts)

    response = client.get(f"/v1/customers/{customer.public_id}/contacts")

    assert response.status_code == 200
    assert response.json() == []
    assert events == ["authorize", "read"]

    operation = app.openapi()["paths"]["/v1/customers/{customer_id}/contacts"]["get"]
    parameter_names = {parameter["name"] for parameter in operation["parameters"]}
    assert parameter_names == {"customer_id"}


def test_query_customer_contacts_stops_on_forbidden_customer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*args: Any, **kwargs: Any) -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看客户")

    monkeypatch.setattr(customers, "_get_viewable_customer", _forbid)
    monkeypatch.setattr(
        customers.contact_crud,
        "get_by_customer_id",
        lambda *args, **kwargs: pytest.fail("contacts must not be read before authorization"),
    )

    response = client.get("/v1/customers/cus_11111111111111111111111111111111/contacts")

    assert response.status_code == 403
    assert response.json()["detail"] == "无权查看客户"


def test_query_customer_activities_passes_pagination_after_authorization(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    customer = SimpleNamespace(id=302)

    def _authorize(customer_id: str, team_id: int, current_user: Any, db: Any) -> Any:
        events.append("authorize")
        return customer

    def _read_activities(**kwargs: Any) -> tuple[list[Any], int]:
        events.append("read")
        assert kwargs.pop("db") is not None
        assert kwargs == {
            "customer_id": 302,
            "team_id": 7,
            "skip": 5,
            "limit": 25,
        }
        return [], 0

    monkeypatch.setattr(customer_activities, "check_customer_view_permission", _authorize)
    monkeypatch.setattr(customer_activities.customer_activity_crud, "get_by_customer_id", _read_activities)

    response = client.get(
        "/v1/customer-activities/cus_11111111111111111111111111111111",
        params={"skip": 5, "limit": 25},
    )

    assert response.status_code == 200
    assert response.json() == []
    assert events == ["authorize", "read"]


def test_query_customer_activities_rejects_forbidden_customer_and_oversized_page(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*args: Any, **kwargs: Any) -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看客户")

    monkeypatch.setattr(customer_activities, "check_customer_view_permission", _forbid)
    monkeypatch.setattr(
        customer_activities.customer_activity_crud,
        "get_by_customer_id",
        lambda **kwargs: pytest.fail("activities must not be read before authorization"),
    )

    forbidden = client.get("/v1/customer-activities/cus_11111111111111111111111111111111")
    oversized_page = client.get(
        "/v1/customer-activities/cus_11111111111111111111111111111111",
        params={"limit": 101},
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "无权查看客户"
    assert oversized_page.status_code == 422


def test_query_follow_up_tasks_passes_supported_filters_sorts_and_scope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _list_tasks(db: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _empty_follow_up_payload(
            status="completed",
            due_window="last_7_days",
            customer_id="cus_11111111111111111111111111111111",
            owner_scope="customer",
        )

    monkeypatch.setattr(follow_up_tasks.follow_up_task_query_service, "list_tasks", _list_tasks)

    response = client.get(
        "/v1/follow-up-tasks",
        params={
            "status": "completed",
            "due_window": "last_7_days",
            "customer_id": "cus_11111111111111111111111111111111",
            "owner_scope": "customer",
            "skip": 10,
            "limit": 20,
            "filters": '[{"field":"tracking_content","op":"contains","value":"回访"}]',
            "sorts": '[{"field":"due_at","direction":"desc"}]',
        },
    )

    assert response.status_code == 200
    assert captured["team_id"] == 7
    assert captured["user_id"] == 42
    assert captured["status"] == "completed"
    assert captured["due_window"] == "last_7_days"
    assert captured["customer_public_id"] == "cus_11111111111111111111111111111111"
    assert captured["owner_scope"] == "customer"
    assert captured["skip"] == 10
    assert captured["limit"] == 20
    assert [(item.field, item.op, item.value) for item in captured["filters"]] == [
        ("tracking_content", "contains", "回访")
    ]
    assert [(item.field, item.direction) for item in captured["sorts"]] == [("due_at", "desc")]


def test_query_follow_up_tasks_maps_permission_and_value_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        follow_up_tasks.follow_up_task_query_service,
        "list_tasks",
        lambda db, **kwargs: (_ for _ in ()).throw(PermissionError("无权查看任务")),
    )
    forbidden = client.get("/v1/follow-up-tasks")

    monkeypatch.setattr(
        follow_up_tasks.follow_up_task_query_service,
        "list_tasks",
        lambda db, **kwargs: (_ for _ in ()).throw(ValueError("未知任务归属范围")),
    )
    invalid_scope = client.get("/v1/follow-up-tasks", params={"owner_scope": "team"})

    malformed_filters = client.get("/v1/follow-up-tasks", params={"filters": "not-json"})
    oversized_page = client.get("/v1/follow-up-tasks", params={"limit": 101})

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "无权查看任务"
    assert invalid_scope.status_code == 400
    assert invalid_scope.json()["detail"] == "未知任务归属范围"
    assert malformed_filters.status_code == 400
    assert oversized_page.status_code == 422


def test_customer_detail_is_the_authorized_structured_context_seam(
    app: FastAPI,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _forbid(*args: Any, **kwargs: Any) -> None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看客户")

    monkeypatch.setattr(customers, "_get_viewable_customer", _forbid)
    monkeypatch.setattr(
        customers.contact_crud,
        "get_by_customer_id",
        lambda *args, **kwargs: pytest.fail("customer context must authorize before related reads"),
    )

    response = client.get("/v1/customers/cus_11111111111111111111111111111111")

    assert response.status_code == 403
    assert response.json()["detail"] == "无权查看客户"
    assert "/v1/customers/{customer_id}" in app.openapi()["paths"]



def test_query_customers_catalog_supports_frozen_agent_city_in_and_last_modified_sort() -> None:
    from app.core.list_query.catalogs.customers import CUSTOMERS_LIST_QUERY_CATALOG

    assert "in" in CUSTOMERS_LIST_QUERY_CATALOG.require("city").ops()
    assert CUSTOMERS_LIST_QUERY_CATALOG.require("last_modified_time").supports_sorting()
