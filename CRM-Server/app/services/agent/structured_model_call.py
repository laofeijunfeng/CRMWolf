"""One structured-output transport for Root and Query model calls.

Callers keep their own schemas and remaining-deadline math.  This module owns
the ChatOpenAI streaming transport, idle-chunk timeout, and timeout-phase
mapping so those details do not leak back into orchestrator code.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Literal

import httpx
from langchain_openai import ChatOpenAI, StreamChunkTimeoutError
from openai import APIError, APITimeoutError

from app.core.config import get_settings
from app.services.ai_http_client import ai_httpx_streaming_timeout, managed_ai_http_clients

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pydantic import BaseModel

StructuredModelCallPhase = Literal["CONNECT", "TTFB", "IDLE", "DEADLINE", "UNAVAILABLE"]
StructuredModelCallReason = Literal["TIMEOUT", "UNAVAILABLE"]

logger = logging.getLogger(__name__)


class StructuredModelCallError(RuntimeError):
    """Normalized failure from one structured model invocation."""

    def __init__(
        self,
        message: str,
        *,
        phase: StructuredModelCallPhase,
        reason: StructuredModelCallReason,
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.reason = reason


async def ainvoke_structured_output(
    schema: type[BaseModel],
    messages: Sequence[dict[str, str]],
    *,
    chat_model_factory: Callable[..., Any],
    model: str,
    api_key: str,
    base_url: str,
    temperature: float,
    timeout_seconds: float,
    enable_thinking: bool | None = None,
    max_tokens: int | None = None,
) -> object:
    """Run one structured-output call and return the last streamed chunk."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    settings = get_settings()
    chunk_timeout = max(
        0.001,
        min(settings.AGENT_STRUCTURED_STREAM_CHUNK_TIMEOUT, timeout_seconds),
    )
    model_kwargs: dict[str, object] = {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": temperature,
        "max_retries": 0,
        "streaming": True,
        "stream_chunk_timeout": chunk_timeout,
        "max_tokens": max_tokens if max_tokens is not None else settings.AGENT_STRUCTURED_MAX_TOKENS,
    }
    if enable_thinking is not None:
        model_kwargs["extra_body"] = {"enable_thinking": enable_thinking}

    try:
        async with asyncio.timeout(timeout_seconds):
            use_managed_transport = chat_model_factory is ChatOpenAI
            async with managed_ai_http_clients(
                enabled=use_managed_transport,
                timeout=(
                    ai_httpx_streaming_timeout(read=chunk_timeout)
                    if use_managed_transport
                    else None
                ),
            ) as transport_kwargs:
                chat_model = chat_model_factory(**model_kwargs, **transport_kwargs)
                structured_model = chat_model.with_structured_output(
                    schema,
                    method="function_calling",
                )
                return await _astream_or_ainvoke(structured_model, messages)
    except StructuredModelCallError:
        raise
    except StreamChunkTimeoutError as exc:
        phase: StructuredModelCallPhase = "TTFB" if exc.chunks_received == 0 else "IDLE"
        raise _timeout_error(phase, model=model) from exc
    except httpx.ConnectTimeout as exc:
        raise _timeout_error("CONNECT", model=model) from exc
    except httpx.ReadTimeout as exc:
        raise _timeout_error("TTFB", model=model) from exc
    except TimeoutError as exc:
        raise _timeout_error("DEADLINE", model=model) from exc
    except APITimeoutError as exc:
        raise _timeout_error("TTFB", model=model) from exc
    except APIError as exc:
        raise _unavailable_error(exc, model=model) from exc
    except Exception as exc:
        raise _unavailable_error(exc, model=model) from exc


async def _astream_or_ainvoke(structured_model: object, messages: object) -> object:
    astream = getattr(structured_model, "astream", None)
    if not callable(astream):
        ainvoke = getattr(structured_model, "ainvoke", None)
        if not callable(ainvoke):
            raise StructuredModelCallError(
                "structured model does not support invoke or stream",
                phase="UNAVAILABLE",
                reason="UNAVAILABLE",
            )
        return await ainvoke(messages)

    last_chunk: object | None = None
    async for chunk in astream(messages):
        last_chunk = chunk
    if last_chunk is None:
        raise StructuredModelCallError(
            "structured model stream completed without output",
            phase="UNAVAILABLE",
            reason="UNAVAILABLE",
        )
    return last_chunk


def _timeout_error(phase: StructuredModelCallPhase, *, model: str) -> StructuredModelCallError:
    logger.warning(
        "structured model call timed out",
        extra={"phase": phase, "reason": "TIMEOUT", "model": model},
    )
    return StructuredModelCallError(
        f"structured model call timed out during {phase}",
        phase=phase,
        reason="TIMEOUT",
    )


def _unavailable_error(exc: BaseException, *, model: str) -> StructuredModelCallError:
    logger.warning(
        "structured model call failed",
        extra={
            "phase": "UNAVAILABLE",
            "reason": "UNAVAILABLE",
            "model": model,
            "error_type": type(exc).__name__,
        },
    )
    return StructuredModelCallError(
        "structured model call failed",
        phase="UNAVAILABLE",
        reason="UNAVAILABLE",
    )
