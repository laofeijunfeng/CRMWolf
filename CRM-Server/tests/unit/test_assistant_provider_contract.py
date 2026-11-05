"""Observable structured provider contracts: refusal, schema and bounded correction."""
import json
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.services.assistant import model_transport
from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["UNKNOWN", "RELATIVE_MONTH"]


async def invoke(**kwargs):
    return await AssistantModelTransport().ainvoke_structured(
        api_host="https://provider.example/v1", api_key="secret-key", model="model",
        temperature=0, system_prompt="Extract time", user_prompt="大概明年联系",
        response_model=Decision, error_prefix="整理", **kwargs,
    )


def provider(monkeypatch, respond):
    original = httpx.AsyncClient
    monkeypatch.setattr(model_transport.httpx, "AsyncClient", lambda **kw: original(
        transport=httpx.MockTransport(respond), **kw,
    ))


async def test_json_mode_works_with_input_keyword_validation_without_changing_business_text(monkeypatch):
    def respond(request):
        data = json.loads(request.content)
        users = [m["content"] for m in data["messages"] if m["role"] == "user"]
        assert users[0] == "大概明年联系"
        if not any("json" in text.lower() for text in users):
            return httpx.Response(400, json={"error": {"type": "invalid_request_error", "param": "input"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"kind":"UNKNOWN"}'}}]})
    provider(monkeypatch, respond)
    assert (await invoke()).kind == "UNKNOWN"


async def test_invalid_enum_gets_only_one_correction_and_never_coerces(monkeypatch):
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"kind":"RELATIVE_YEAR"}'}}]})
    provider(monkeypatch, respond)
    with pytest.raises(AssistantLLMError) as error:
        await invoke()
    assert error.value.code.value == "MODEL_OUTPUT_INVALID"
    assert len(calls) == 2
    assert calls[1]["messages"][1]["content"] == "大概明年联系"


async def test_valid_correction_returns_validated_result(monkeypatch):
    calls = 0
    def respond(request):
        nonlocal calls
        calls += 1
        content = '{"kind":"RELATIVE_YEAR"}' if calls == 1 else '{"kind":"UNKNOWN"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    provider(monkeypatch, respond)
    assert (await invoke()).kind == "UNKNOWN"
    assert calls == 2


async def test_provider_echoed_api_key_never_reaches_error_metadata_or_logs(monkeypatch, caplog):
    def respond(request):
        return httpx.Response(401, headers={"x-request-id": "req-secret-key"}, json={"error": {
            "type": "secret-key-invalid", "param": "key.secret-key",
        }})
    provider(monkeypatch, respond)
    with pytest.raises(AssistantLLMError) as error:
        await invoke()
    exc = error.value
    assert exc.code.value == "AUTHENTICATION_ERROR"
    assert (exc.provider_request_id, exc.provider_error_type, exc.provider_error_param) == (None, None, None)
    assert "secret-key" not in caplog.text


async def test_strict_mode_never_falls_back_on_rejected_request(monkeypatch):
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {
            "message": "response_format json_schema is not supported",
            "param": "response_format",
            "type": "invalid_request_error",
        }})
    provider(monkeypatch, respond)
    with pytest.raises(AssistantLLMError) as error:
        await invoke(output_mode="json_schema")
    assert error.value.code.value == "REQUEST_PROTOCOL_ERROR"
    assert error.value.schema_protocol_rejected
    assert len(calls) == 1


@pytest.mark.parametrize("status,code", [
    (401, "AUTHENTICATION_ERROR"), (403, "AUTHENTICATION_ERROR"), (400, "REQUEST_PROTOCOL_ERROR"),
])
async def test_provider_failure_retains_safe_diagnostics_without_configuration_mislabel(monkeypatch,status,code):
    def respond(request):
        return httpx.Response(status, headers={"x-request-id": "trace-123"}, json={"error": {
            "type": "invalid_request_error", "param": "input", "message": "secret-key customer private text",
        }})
    provider(monkeypatch, respond)
    with pytest.raises(AssistantLLMError) as error:
        await invoke()
    assert error.value.code.value == code
    assert error.value.provider_status == status
    assert error.value.provider_request_id == "trace-123"
    assert error.value.provider_error_param == "input"
    assert "secret-key" not in str(error.value)


async def test_truncated_response_is_not_accepted_even_when_json_parses(monkeypatch):
    def respond(request):
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "length", "message": {"content": '{"kind":"UNKNOWN"}'}}],
        })
    provider(monkeypatch, respond)
    with pytest.raises(AssistantLLMError) as error:
        await invoke()
    assert error.value.code.value == "MODEL_OUTPUT_INVALID"
