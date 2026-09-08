"""Shared HTTP transport for outbound AI requests.

The AI configuration test and LangChain used to construct different HTTP
clients.  That made a local system proxy affect Agent calls while the
configuration test explicitly bypassed it.  Keep proxy behavior explicit and
centralized so every modern AI path has the same network semantics.
"""
from __future__ import annotations

import socket
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx

from app.core.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def ai_httpx_client_kwargs() -> dict[str, Any]:
    """Return explicit HTTPX networking options for outbound AI calls.

    Environment proxy discovery is disabled by default.  If a deployment
    needs a proxy, it must set ``AI_HTTP_PROXY`` explicitly instead of relying
    on an implicit machine-level proxy.
    """

    settings = get_settings()
    options: dict[str, Any] = {"trust_env": settings.AI_HTTP_TRUST_ENV}
    if settings.AI_HTTP_PROXY.strip():
        options["proxy"] = settings.AI_HTTP_PROXY.strip()
    return options


def ai_httpx_timeout() -> httpx.Timeout:
    """Return the all-phase timeout used by non-streaming AI HTTP clients."""

    return httpx.Timeout(get_settings().AI_HTTP_TIMEOUT_SECONDS)


def ai_httpx_streaming_timeout(*, read: float | None = None) -> httpx.Timeout:
    """Return per-phase timeouts for streaming AI HTTP clients.

    httpx has no total deadline.  Streaming callers must wrap the request in
    ``asyncio.timeout``.  The read budget should match the LangChain
    ``stream_chunk_timeout`` for that invocation so a healthy mid-stream pause
    is not aborted earlier than the Agent idle timeout.
    """

    settings = get_settings()
    return httpx.Timeout(
        connect=settings.AI_HTTP_CONNECT_TIMEOUT_SECONDS,
        write=settings.AI_HTTP_WRITE_TIMEOUT_SECONDS,
        read=settings.AI_HTTP_READ_TIMEOUT_SECONDS if read is None else read,
        pool=settings.AI_HTTP_POOL_TIMEOUT_SECONDS,
    )


def _ai_keepalive_socket_options() -> list[tuple[int, int, int]]:
    return [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]


def _client_construct_kwargs(timeout: httpx.Timeout) -> tuple[dict[str, Any], dict[str, Any]]:
    client_options = ai_httpx_client_kwargs()
    proxy = client_options.pop("proxy", None)
    socket_options = _ai_keepalive_socket_options()
    sync_kwargs: dict[str, Any] = {
        **client_options,
        "timeout": timeout,
        "transport": httpx.HTTPTransport(socket_options=socket_options, proxy=proxy),
    }
    async_kwargs: dict[str, Any] = {
        **client_options,
        "timeout": timeout,
        "transport": httpx.AsyncHTTPTransport(socket_options=socket_options, proxy=proxy),
    }
    return sync_kwargs, async_kwargs


@asynccontextmanager
async def managed_ai_http_clients(
    *,
    enabled: bool = True,
    timeout: httpx.Timeout | None = None,
) -> AsyncIterator[dict[str, object]]:
    """Create and close sync/async HTTPX clients for a LangChain model.

    LangChain/OpenAI accepts caller-owned ``http_client`` and
    ``http_async_client`` instances.  The clients are intentionally scoped to
    one model invocation so ownership and cleanup are unambiguous; the outer
    Agent timeout remains the total request deadline.

    Custom clients bypass ChatOpenAI's default TCP keepalive, so managed
    clients re-apply ``SO_KEEPALIVE`` on the HTTPX transport.

    When disabled, no clients are created and an empty mapping is yielded.
    This preserves dependency injection seams used by unit tests and callers
    that provide their own model implementation.
    """

    if not enabled:
        yield {}
        return

    sync_kwargs, async_kwargs = _client_construct_kwargs(timeout or ai_httpx_timeout())
    sync_client = httpx.Client(**sync_kwargs)
    async_client = httpx.AsyncClient(**async_kwargs)
    try:
        yield {
            "http_client": sync_client,
            "http_async_client": async_client,
        }
    finally:
        sync_client.close()
        await async_client.aclose()
