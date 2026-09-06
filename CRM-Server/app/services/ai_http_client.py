"""Shared HTTP transport for outbound AI requests.

The AI configuration test and LangChain used to construct different HTTP
clients.  That made a local system proxy affect Agent calls while the
configuration test explicitly bypassed it.  Keep proxy behavior explicit and
centralized so every modern AI path has the same network semantics.
"""
from __future__ import annotations

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
    """Return the phase timeout used by outbound AI HTTP clients."""

    return httpx.Timeout(get_settings().AI_HTTP_TIMEOUT_SECONDS)


@asynccontextmanager
async def managed_ai_http_clients(
    *,
    enabled: bool = True,
) -> AsyncIterator[dict[str, object]]:
    """Create and close sync/async HTTPX clients for a LangChain model.

    LangChain/OpenAI accepts caller-owned ``http_client`` and
    ``http_async_client`` instances.  The clients are intentionally scoped to
    one model invocation so ownership and cleanup are unambiguous; the outer
    Agent timeout remains the total request deadline.

    When disabled, no clients are created and an empty mapping is yielded.
    This preserves dependency injection seams used by unit tests and callers
    that provide their own model implementation.
    """

    if not enabled:
        yield {}
        return

    client_options = ai_httpx_client_kwargs()
    timeout = ai_httpx_timeout()
    sync_client = httpx.Client(timeout=timeout, **client_options)
    async_client = httpx.AsyncClient(timeout=timeout, **client_options)
    try:
        yield {
            "http_client": sync_client,
            "http_async_client": async_client,
        }
    finally:
        sync_client.close()
        await async_client.aclose()
