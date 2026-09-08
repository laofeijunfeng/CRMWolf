"""Structured model transport tests at the public call seam."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from langchain_openai import StreamChunkTimeoutError
from pydantic import BaseModel

from app.services.agent.structured_model_call import (
    StructuredModelCallError,
    ainvoke_structured_output,
)


class SampleStructuredOutput(BaseModel):
    route: str


MESSAGES = [
    {"role": "system", "content": "classify"},
    {"role": "user", "content": "上海有哪些客户"},
]


class StreamingStructuredModel:
    def __init__(
        self,
        *,
        chunks: list[object] | None = None,
        error: Exception | None = None,
        delay_seconds: float = 0.0,
        ainvoke_result: object | None = None,
    ) -> None:
        self.chunks = list(chunks or [])
        self.error = error
        self.delay_seconds = delay_seconds
        self.ainvoke_result = ainvoke_result
        self.schema: object | None = None
        self.method: str | None = None
        self.stream_calls: list[object] = []
        self.invoke_calls: list[object] = []

    def with_structured_output(self, schema: type[BaseModel], *, method: str) -> StreamingStructuredModel:
        self.schema = schema
        self.method = method
        return self

    async def astream(self, messages: object):
        self.stream_calls.append(messages)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk

    async def ainvoke(self, messages: object) -> object:
        self.invoke_calls.append(messages)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return self.ainvoke_result


class AinvokeOnlyStructuredModel:
    """Matches current Root/Query fakes that only implement ainvoke."""

    def __init__(self, *, result: object) -> None:
        self.result = result
        self.schema: object | None = None
        self.method: str | None = None
        self.invoke_calls: list[object] = []

    def with_structured_output(self, schema: type[BaseModel], *, method: str) -> AinvokeOnlyStructuredModel:
        self.schema = schema
        self.method = method
        return self

    async def ainvoke(self, messages: object) -> object:
        self.invoke_calls.append(messages)
        return self.result


class RecordingModelFactory:
    def __init__(self, model: StreamingStructuredModel | AinvokeOnlyStructuredModel) -> None:
        self.model = model
        self.kwargs: dict[str, object] | None = None

    def __call__(self, **kwargs: object) -> StreamingStructuredModel | AinvokeOnlyStructuredModel:
        self.kwargs = kwargs
        return self.model


def _httpx_request() -> httpx.Request:
    return httpx.Request("POST", "https://ai.example.com/v1/chat/completions")


async def _invoke(
    factory: RecordingModelFactory,
    *,
    timeout_seconds: float = 0.4,
    max_tokens: int | None = None,
    enable_thinking: bool | None = None,
) -> object:
    return await ainvoke_structured_output(
        SampleStructuredOutput,
        MESSAGES,
        chat_model_factory=factory,
        model="grok-4.6",
        api_key="test-key",
        base_url="https://ai.example.com/v1",
        temperature=0.0,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )


@pytest.mark.asyncio
async def test_structured_call_keeps_last_stream_chunk_when_first_byte_arrives_soon() -> None:
    model = StreamingStructuredModel(
        chunks=[
            SampleStructuredOutput(route="CLARIFY"),
            SampleStructuredOutput(route="QUERY"),
        ],
        delay_seconds=0.02,
    )
    factory = RecordingModelFactory(model)

    result = await _invoke(factory, timeout_seconds=0.4)

    assert result == SampleStructuredOutput(route="QUERY")
    assert model.method == "function_calling"
    assert model.stream_calls == [MESSAGES]
    assert model.invoke_calls == []
    assert factory.kwargs is not None
    assert factory.kwargs["streaming"] is True
    assert factory.kwargs["stream_chunk_timeout"] == 0.4
    assert factory.kwargs["max_tokens"] == 1024
    assert factory.kwargs["max_retries"] == 0
    assert "http_client" not in factory.kwargs


@pytest.mark.asyncio
async def test_structured_call_completes_when_first_byte_arrives_within_deadline() -> None:
    model = StreamingStructuredModel(
        chunks=[SampleStructuredOutput(route="QUERY")],
        delay_seconds=0.07,
    )

    result = await _invoke(RecordingModelFactory(model), timeout_seconds=0.2)

    assert result == SampleStructuredOutput(route="QUERY")


@pytest.mark.asyncio
async def test_structured_call_maps_read_timeout_before_first_byte_to_ttfb() -> None:
    model = StreamingStructuredModel(
        error=httpx.ReadTimeout("Read timed out", request=_httpx_request()),
    )

    with pytest.raises(StructuredModelCallError) as captured:
        await _invoke(RecordingModelFactory(model))

    assert captured.value.phase == "TTFB"
    assert captured.value.reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_structured_call_maps_connect_timeout_to_connect_phase() -> None:
    model = StreamingStructuredModel(
        error=httpx.ConnectTimeout("Connect timed out", request=_httpx_request()),
    )

    with pytest.raises(StructuredModelCallError) as captured:
        await _invoke(RecordingModelFactory(model))

    assert captured.value.phase == "CONNECT"
    assert captured.value.reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_structured_call_maps_idle_stream_chunk_timeout_after_first_byte() -> None:
    model = StreamingStructuredModel(
        error=StreamChunkTimeoutError(0.02, model_name="grok-4.6", chunks_received=2),
    )

    with pytest.raises(StructuredModelCallError) as captured:
        await _invoke(RecordingModelFactory(model), timeout_seconds=0.4)

    assert captured.value.phase == "IDLE"
    assert captured.value.reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_structured_call_maps_first_byte_stream_chunk_timeout_to_ttfb() -> None:
    model = StreamingStructuredModel(
        error=StreamChunkTimeoutError(0.02, model_name="grok-4.6", chunks_received=0),
    )

    with pytest.raises(StructuredModelCallError) as captured:
        await _invoke(RecordingModelFactory(model))

    assert captured.value.phase == "TTFB"
    assert captured.value.reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_structured_call_maps_deadline_timeout_to_deadline_phase() -> None:
    model = StreamingStructuredModel(
        chunks=[SampleStructuredOutput(route="QUERY")],
        delay_seconds=0.2,
    )

    with pytest.raises(StructuredModelCallError) as captured:
        await _invoke(RecordingModelFactory(model), timeout_seconds=0.05)

    assert captured.value.phase == "DEADLINE"
    assert captured.value.reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_structured_call_maps_ordinary_provider_errors_to_unavailable() -> None:
    model = StreamingStructuredModel(error=RuntimeError("provider exploded"))

    with pytest.raises(StructuredModelCallError) as captured:
        await _invoke(RecordingModelFactory(model))

    assert captured.value.phase == "UNAVAILABLE"
    assert captured.value.reason == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_structured_call_falls_back_to_ainvoke_when_stream_is_unavailable() -> None:
    model = AinvokeOnlyStructuredModel(result=SampleStructuredOutput(route="QUERY"))
    factory = RecordingModelFactory(model)

    result = await _invoke(factory)

    assert result == SampleStructuredOutput(route="QUERY")
    assert model.invoke_calls == [MESSAGES]
    assert factory.kwargs is not None
    assert factory.kwargs["streaming"] is True
    assert factory.kwargs["max_tokens"] == 1024


@pytest.mark.asyncio
async def test_structured_call_uses_configured_max_tokens_and_thinking_flag() -> None:
    model = AinvokeOnlyStructuredModel(result=SampleStructuredOutput(route="WORKFLOW"))
    factory = RecordingModelFactory(model)

    result = await _invoke(factory, max_tokens=2048, enable_thinking=False)

    assert result == SampleStructuredOutput(route="WORKFLOW")
    assert factory.kwargs is not None
    assert factory.kwargs["max_tokens"] == 2048
    assert factory.kwargs["extra_body"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_structured_call_uses_streaming_http_timeout_for_chat_openai_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: list[dict[str, object]] = []

    class RecordingChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created_kwargs.append(kwargs)

        def with_structured_output(self, schema: type[BaseModel], *, method: str) -> StreamingStructuredModel:
            del schema, method
            model = StreamingStructuredModel(chunks=[SampleStructuredOutput(route="QUERY")])
            return model

    monkeypatch.setattr(
        "app.services.agent.structured_model_call.ChatOpenAI",
        RecordingChatOpenAI,
    )

    result = await ainvoke_structured_output(
        SampleStructuredOutput,
        MESSAGES,
        chat_model_factory=RecordingChatOpenAI,
        model="grok-4.6",
        api_key="test-key",
        base_url="https://ai.example.com/v1",
        temperature=0.0,
        timeout_seconds=0.4,
    )

    assert result == SampleStructuredOutput(route="QUERY")
    assert len(created_kwargs) == 1
    http_async_client = created_kwargs[0]["http_async_client"]
    assert isinstance(http_async_client, httpx.AsyncClient)
    assert http_async_client.timeout.read == 0.4
    assert http_async_client.timeout.connect == 10.0
    assert created_kwargs[0]["streaming"] is True
    assert created_kwargs[0]["stream_chunk_timeout"] == 0.4



@pytest.mark.asyncio
async def test_structured_call_caps_stream_chunk_timeout_to_remaining_deadline() -> None:
    model = StreamingStructuredModel(chunks=[SampleStructuredOutput(route="QUERY")])
    factory = RecordingModelFactory(model)

    result = await _invoke(factory, timeout_seconds=12.0)

    assert result == SampleStructuredOutput(route="QUERY")
    assert factory.kwargs is not None
    assert factory.kwargs["stream_chunk_timeout"] == 12.0


@pytest.mark.asyncio
async def test_structured_call_uses_configured_idle_timeout_when_deadline_is_larger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = StreamingStructuredModel(chunks=[SampleStructuredOutput(route="QUERY")])
    factory = RecordingModelFactory(model)
    monkeypatch.setattr(
        "app.services.agent.structured_model_call.get_settings",
        lambda: type("Settings", (), {"AGENT_STRUCTURED_STREAM_CHUNK_TIMEOUT": 45.0, "AGENT_STRUCTURED_MAX_TOKENS": 1024})(),
    )

    result = await _invoke(factory, timeout_seconds=60.0)

    assert result == SampleStructuredOutput(route="QUERY")
    assert factory.kwargs is not None
    assert factory.kwargs["stream_chunk_timeout"] == 45.0
