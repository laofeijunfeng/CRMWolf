"""AI HTTP transport configuration tests."""

from types import SimpleNamespace

import pytest

from app.services import ai_http_client


def test_ai_httpx_client_kwargs_disable_implicit_environment_proxy(monkeypatch):
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(AI_HTTP_TRUST_ENV=False, AI_HTTP_PROXY=""),
    )

    assert ai_http_client.ai_httpx_client_kwargs() == {"trust_env": False}


def test_ai_httpx_client_kwargs_allow_explicit_proxy(monkeypatch):
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(
            AI_HTTP_TRUST_ENV=False,
            AI_HTTP_PROXY="http://127.0.0.1:7890",
        ),
    )

    assert ai_http_client.ai_httpx_client_kwargs() == {
        "trust_env": False,
        "proxy": "http://127.0.0.1:7890",
    }


@pytest.mark.asyncio
async def test_managed_ai_http_clients_closes_both_clients(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(ai_http_client.httpx, "Client", FakeClient)
    monkeypatch.setattr(ai_http_client.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(
            AI_HTTP_TRUST_ENV=False,
            AI_HTTP_PROXY="",
            AI_HTTP_TIMEOUT_SECONDS=60.0,
        ),
    )

    async with ai_http_client.managed_ai_http_clients() as clients:
        assert set(clients) == {"http_client", "http_async_client"}
        assert clients["http_client"] is created[0]
        assert clients["http_async_client"] is created[1]
        assert not created[0].closed
        assert not created[1].closed

    assert created[0].closed
    assert created[1].closed
