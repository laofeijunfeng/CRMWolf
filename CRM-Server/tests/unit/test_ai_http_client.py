"""AI HTTP transport configuration tests."""

import socket
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
    assert created[0].kwargs["timeout"].connect == 60.0
    assert created[0].kwargs["timeout"].read == 60.0
    socket_options = created[0].kwargs["transport"]._pool._socket_options
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in socket_options


def test_ai_httpx_timeout_keeps_all_phase_budget(monkeypatch):
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(AI_HTTP_TIMEOUT_SECONDS=60.0),
    )

    timeout = ai_http_client.ai_httpx_timeout()

    assert timeout.connect == 60.0
    assert timeout.read == 60.0
    assert timeout.write == 60.0
    assert timeout.pool == 60.0


def test_ai_httpx_streaming_timeout_uses_phase_budgets(monkeypatch):
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(
            AI_HTTP_CONNECT_TIMEOUT_SECONDS=10.0,
            AI_HTTP_WRITE_TIMEOUT_SECONDS=10.0,
            AI_HTTP_READ_TIMEOUT_SECONDS=20.0,
            AI_HTTP_POOL_TIMEOUT_SECONDS=5.0,
        ),
    )

    timeout = ai_http_client.ai_httpx_streaming_timeout()

    assert timeout.connect == 10.0
    assert timeout.write == 10.0
    assert timeout.read == 20.0
    assert timeout.pool == 5.0


@pytest.mark.asyncio
async def test_managed_ai_http_clients_accept_explicit_streaming_timeout(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created.append(self)

        def close(self):
            return None

        async def aclose(self):
            return None

    monkeypatch.setattr(ai_http_client.httpx, "Client", FakeClient)
    monkeypatch.setattr(ai_http_client.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(
            AI_HTTP_TRUST_ENV=False,
            AI_HTTP_PROXY="",
            AI_HTTP_CONNECT_TIMEOUT_SECONDS=10.0,
            AI_HTTP_WRITE_TIMEOUT_SECONDS=10.0,
            AI_HTTP_READ_TIMEOUT_SECONDS=20.0,
            AI_HTTP_POOL_TIMEOUT_SECONDS=5.0,
        ),
    )

    timeout = ai_http_client.ai_httpx_streaming_timeout()
    async with ai_http_client.managed_ai_http_clients(timeout=timeout) as clients:
        assert set(clients) == {"http_client", "http_async_client"}

    assert created[0].kwargs["timeout"].read == 20.0
    assert created[1].kwargs["timeout"].connect == 10.0


def test_ai_httpx_streaming_timeout_accepts_read_override(monkeypatch):
    monkeypatch.setattr(
        ai_http_client,
        "get_settings",
        lambda: SimpleNamespace(
            AI_HTTP_CONNECT_TIMEOUT_SECONDS=10.0,
            AI_HTTP_WRITE_TIMEOUT_SECONDS=10.0,
            AI_HTTP_READ_TIMEOUT_SECONDS=45.0,
            AI_HTTP_POOL_TIMEOUT_SECONDS=5.0,
        ),
    )

    timeout = ai_http_client.ai_httpx_streaming_timeout(read=12.0)

    assert timeout.connect == 10.0
    assert timeout.write == 10.0
    assert timeout.read == 12.0
    assert timeout.pool == 5.0
