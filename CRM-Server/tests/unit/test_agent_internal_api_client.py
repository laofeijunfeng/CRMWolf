"""Internal CRM API transport idempotency contract."""

import httpx
import pytest

from app.services.agent.tools.api_client import InternalCRMAPIClient


@pytest.mark.asyncio
async def test_internal_api_client_sends_idempotency_key_header(monkeypatch):
    captured = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            captured.update({"method": method, "url": url, **kwargs})
            return httpx.Response(
                200,
                json={"id": 9001},
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr("app.services.agent.tools.api_client.httpx.AsyncClient", FakeAsyncClient)

    result = await InternalCRMAPIClient(base_url="http://crm.local").request(
        "POST",
        "/v1/customer-activities/cus_101",
        "Bearer token",
        idempotency_key="create_customer_activity:3:act_123",
        json={"source_content": "跟进记录"},
    )

    assert result == {"id": 9001}
    assert captured["headers"] == {
        "Authorization": "Bearer token",
        "Idempotency-Key": "create_customer_activity:3:act_123",
    }
