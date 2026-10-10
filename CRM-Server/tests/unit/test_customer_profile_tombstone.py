"""Removed customer-profile routes expose one stable gone contract."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.customer_profiles import router


def test_every_profile_route_returns_the_same_gone_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    paths = (
        "/v1/customers/missing/profile",
        "/v1/customers/missing/profile/changes",
        "/v1/customers/missing/profile/evidence",
        "/v1/customers/missing/profile/journeys",
        "/v1/customers/missing/profile/follow-ups",
        "/v1/customers/missing/profile/versions",
    )

    for path in paths:
        response = client.get(path)
        assert response.status_code == 410
        assert response.json() == {
            "code": "CUSTOMER_PROFILE_REMOVED",
            "message": "客户档案能力已移除",
        }

    refresh = client.post("/v1/customers/missing/profile/refresh", json={})
    assert refresh.status_code == 410
    assert refresh.json()["code"] == "CUSTOMER_PROFILE_REMOVED"
