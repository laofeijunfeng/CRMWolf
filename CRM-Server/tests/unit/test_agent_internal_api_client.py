"""Internal CRM API transport idempotency contract."""

import httpx
import pytest

from app.services.agent.tools.api_client import CRMAPIClientError, InternalCRMAPIClient


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


@pytest.mark.asyncio
async def test_internal_api_client_surfaces_422_field_errors(monkeypatch):
    """Regression: long activity titles once surfaced only a bare 422 detail.

    The FastAPI 422 body carries per-field ``errors``; the Agent must see them
    so it can correct or explain the failing field instead of the generic
    "请求参数验证失败".
    """

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return httpx.Response(
                422,
                json={
                    "error_code": "VALIDATION_ERROR",
                    "detail": "请求参数验证失败",
                    "errors": [
                        {
                            "field": "body -> title",
                            "message": "String should have at most 255 characters",
                            "type": "string_too_long",
                        }
                    ],
                },
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr("app.services.agent.tools.api_client.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(CRMAPIClientError) as excinfo:
        await InternalCRMAPIClient(base_url="http://crm.local").request(
            "POST",
            "/v1/customer-activities/cus_101/agent-finalized",
            "Bearer token",
            json={"source_content": "跟进记录"},
        )

    assert excinfo.value.status_code == 422
    assert "body -> title" in excinfo.value.message
    assert "String should have at most 255 characters" in excinfo.value.message


def test_error_message_falls_back_without_field_errors():
    assert (
        InternalCRMAPIClient._error_message(500, {"text": "boom"})
        == "CRM API调用失败：500"  # noqa: RUF001
    )
    assert (
        InternalCRMAPIClient._error_message(422, {"detail": "自定义错误"})
        == "自定义错误"
    )
