from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import payments
from app.core import deps


class _Query:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


def _record() -> SimpleNamespace:
    contract = SimpleNamespace(
        license_type="SUBSCRIPTION",
        opportunity=SimpleNamespace(purchase_type="NEW"),
        customer=SimpleNamespace(account_name="甲"),
    )
    return SimpleNamespace(
        id=8,
        record_number="HK008",
        actual_amount=Decimal("100000"),
        payment_date=date(2026, 10, 2),
        payment_plan=SimpleNamespace(contract=contract),
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(payments.router)
    app.dependency_overrides[deps.get_current_user_team] = lambda: 7
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(id=42, status="active")
    app.dependency_overrides[deps.get_db] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_chart_uses_unpaginated_population_for_the_current_team(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    db = object()
    client.app.dependency_overrides[deps.get_db] = lambda: db

    monkeypatch.setattr(
        payments.permission_crud,
        "get_user_permissions",
        lambda actual_db, user_id, team_id: (
            captured.update(permission=(actual_db, user_id, team_id)) or [SimpleNamespace(code="payment:view:all")]
        ),
    )

    def build_population_query(actual_db: Any, **kwargs: Any) -> _Query:
        captured["db"] = actual_db
        captured["builder"] = kwargs
        return _Query([_record()])

    monkeypatch.setattr(payments.payment_record_crud, "build_population_query", build_population_query)
    monkeypatch.setattr(
        payments.payment_record_crud,
        "list_records",
        lambda **_: pytest.fail("chart must not paginate through list_records"),
    )

    response = client.get("/v1/payments/payment-records/chart", params={"search": "甲", "approval_status": "approved"})

    assert response.status_code == 200
    body = response.json()
    assert body["population"] == 1
    assert body["total_amount"] == 100000
    assert [card["key"] for card in body["cards"]] == [
        "license_type",
        "purchase_type",
        "amount_band",
        "payment_month",
        "arr_ratio",
    ]
    assert captured["permission"] == (db, 42, 7)
    assert captured["db"] is db
    assert captured["builder"]["team_id"] == 7
    assert captured["builder"]["search"] == "甲"
    assert captured["builder"]["approval_status"] == "approved"
    assert captured["builder"]["current_user_id"] is None
    assert "skip" not in captured["builder"]
    assert "limit" not in captured["builder"]


def test_chart_narrows_to_the_caller_without_view_all(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        payments.permission_crud,
        "get_user_permissions",
        lambda *_args: [SimpleNamespace(code="payment:view:own")],
    )
    monkeypatch.setattr(
        payments.payment_record_crud,
        "build_population_query",
        lambda _db, **kwargs: captured.update(kwargs) or _Query([]),
    )

    response = client.get("/v1/payments/payment-records/chart")

    assert response.status_code == 200
    assert captured["current_user_id"] == "42"
    assert captured["team_id"] == 7
    assert response.json()["population"] == 0


def test_chart_rejects_callers_without_payment_view(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(payments.permission_crud, "get_user_permissions", lambda *_args: [])
    response = client.get("/v1/payments/payment-records/chart")
    assert response.status_code == 403


def test_chart_bucket_returns_the_segment_and_rejects_unknown_segment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        payments.permission_crud,
        "get_user_permissions",
        lambda *_args: [SimpleNamespace(code="payment:view:all")],
    )
    monkeypatch.setattr(
        payments.payment_record_crud,
        "build_population_query",
        lambda _db, **_kwargs: _Query([_record()]),
    )

    found = client.get(
        "/v1/payments/payment-records/chart/records",
        params={"chart": "license_type", "bucket": "SUBSCRIPTION"},
    )
    assert found.status_code == 200
    body = found.json()
    assert body["total"] == 1
    assert body["records"][0]["record_number"] == "HK008"
    assert body["records"][0]["customer_name"] == "甲"

    missing = client.get(
        "/v1/payments/payment-records/chart/records",
        params={"chart": "approval", "bucket": "approved"},
    )
    assert missing.status_code == 400
