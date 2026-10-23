"""Removed customer-profile routes expose one stable gone contract."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.customer_profiles import router


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("subpath", ["", "/changes", "/evidence", "/journeys", "/follow-ups", "/versions", "/refresh"])
def test_every_profile_route_returns_the_same_gone_contract(method: str, subpath: str) -> None:
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.request(method, f"/v1/customers/missing/profile{subpath}")
    assert response.status_code == 410
    assert response.json() == {
        "code": "CUSTOMER_PROFILE_REMOVED",
        "message": "客户档案能力已移除",
    }
