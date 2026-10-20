from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import opportunities
from app.core import deps


class _FakeQuery:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.all_calls = 0

    def all(self) -> list[Any]:
        self.all_calls += 1
        return self.rows


@pytest.fixture
def api_app() -> FastAPI:
    app = FastAPI()
    app.include_router(opportunities.router)
    app.dependency_overrides[deps.get_current_user_team] = lambda: 7
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=42,
        name="查询用户",
        status="active",
    )
    app.dependency_overrides[deps.get_db] = lambda: object()
    return app


@pytest.fixture
def client(api_app: FastAPI):
    with TestClient(api_app) as test_client:
        yield test_client
    api_app.dependency_overrides.clear()


def _permissions(*codes: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(code=code) for code in codes]


def _chart_payload() -> dict[str, Any]:
    return {
        "population": 2,
        "total_amount": 300000,
        "cards": [
            {"key": key, "buckets": []}
            for key in (
                "status",
                "purchase_type",
                "license_type",
                "amount_band",
                "product",
                "win_probability",
                "expected_closing_month",
            )
        ],
    }


def _bucket_payload() -> dict[str, Any]:
    return {
        "chart": "status",
        "bucket": "1",
        "total": 1,
        "opportunities": [
            {
                "id": "opp-1",
                "name": "重要商机",
                "customer_name": "示例客户",
                "owner_name": "查询用户",
                "amount": 300000,
                "expected_closing_date": "2026-12-01",
            }
        ],
    }


def test_chart_rebuilds_authorized_unpaginated_population_and_preserves_query_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    query = _FakeQuery(rows)
    db = object()

    client.app.dependency_overrides[deps.get_db] = lambda: db
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda actual_db, user_id, team_id: (
            captured.update(permission=(actual_db, user_id, team_id)) or _permissions("opportunity:view:all")
        ),
    )

    def build_list_query(actual_db: Any, **kwargs: Any) -> _FakeQuery:
        captured["builder_db"] = actual_db
        captured["builder"] = kwargs
        return query

    monkeypatch.setattr(opportunities.opportunity_crud, "build_list_query", build_list_query)
    monkeypatch.setattr(
        "app.services.opportunity_chart_stats.build_opportunity_chart",
        lambda actual_db, team_id, population: captured.update(
            service=(actual_db, team_id, population)
        )
        or _chart_payload(),
    )
    monkeypatch.setattr(
        opportunities.opportunity_crud,
        "get_multi",
        lambda **_: pytest.fail("chart must use the unpaginated query builder, not get_multi"),
    )

    response = client.get(
        "/v1/opportunities/chart",
        params={
            "status": "1,2",
            "search": "重要",
            "filters": '[{"field":"owner_id","op":"eq","value":"99"}]',
            "sorts": '[{"field":"total_amount","direction":"desc"}]',
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == _chart_payload()
    assert captured["permission"] == (db, 42, 7)
    assert captured["builder_db"] is db
    assert captured["builder"]["team_id"] == 7
    assert captured["builder"]["status"] == "1,2"
    assert captured["builder"]["owner_id"] is None
    assert captured["builder"]["search"] == "重要"
    assert [(item.field, item.op, item.value) for item in captured["builder"]["filters"]] == [
        ("owner_id", "eq", "99")
    ]
    assert [(item.field, item.direction) for item in captured["builder"]["sorts"]] == [
        ("total_amount", "desc")
    ]
    assert query.all_calls == 1
    assert captured["service"] == (db, 7, rows)


def test_bucket_endpoint_rebuilds_population_and_passes_it_to_bucket_service(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    rows = [SimpleNamespace(id=11)]
    query = _FakeQuery(rows)
    db = object()
    client.app.dependency_overrides[deps.get_db] = lambda: db

    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda actual_db, user_id, team_id: _permissions("opportunity:view:all"),
    )

    def build_list_query(actual_db: Any, **kwargs: Any) -> _FakeQuery:
        captured["builder_db"] = actual_db
        captured["builder"] = kwargs
        return query

    monkeypatch.setattr(opportunities.opportunity_crud, "build_list_query", build_list_query)
    monkeypatch.setattr(
        "app.services.opportunity_chart_stats.list_chart_bucket_opportunities",
        lambda actual_db, team_id, population, chart, bucket: captured.update(
            service=(actual_db, team_id, population, chart, bucket)
        )
        or _bucket_payload()["opportunities"],
    )

    response = client.get(
        "/v1/opportunities/chart/opportunities",
        params={
            "chart": "status",
            "bucket": "1",
            "status": "1",
            "search": "重要",
            "filters": '[{"field":"purchase_type","op":"eq","value":"NEW"}]',
            "sorts": '[{"field":"created_time","direction":"asc"}]',
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == _bucket_payload()
    assert captured["builder_db"] is db
    assert captured["builder"]["team_id"] == 7
    assert captured["builder"]["status"] == "1"
    assert captured["builder"]["owner_id"] is None
    assert captured["builder"]["search"] == "重要"
    assert [(item.field, item.op, item.value) for item in captured["builder"]["filters"]] == [
        ("purchase_type", "eq", "NEW")
    ]
    assert [(item.field, item.direction) for item in captured["builder"]["sorts"]] == [
        ("created_time", "asc")
    ]
    assert query.all_calls == 1
    assert captured["service"] == (db, 7, rows, "status", "1")

def test_chart_rejects_other_owner_without_view_all_permission(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda db, user_id, team_id: _permissions("opportunity:view:own"),
    )
    monkeypatch.setattr(
        opportunities.opportunity_crud,
        "build_list_query",
        lambda **_: pytest.fail("authorization must happen before population retrieval"),
    )

    response = client.get(
        "/v1/opportunities/chart",
        params={"filters": '[{"field":"owner_id","op":"eq","value":"99"}]'},
    )

    assert response.status_code == 403
    assert "只能查看自己负责的商机" in response.json()["detail"]
