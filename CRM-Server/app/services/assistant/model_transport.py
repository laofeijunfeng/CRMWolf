# ruff: noqa: RUF001
"""Bounded OpenAI-compatible structured calls; business source text stays immutable."""
from __future__ import annotations

import asyncio
import json
import logging
from time import monotonic
from typing import Any, Literal, TypeVar

import httpx
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError

from app.crud.ai_config import ai_config_crud
from app.services.assistant.failure_contract import (
    AssistantFailureCode,
    attempt_budget_remaining,
    root_failure_retryable,
)

logger = logging.getLogger(__name__)
OutputMode = Literal["json_object", "json_schema"]
ResultT = TypeVar("ResultT", bound=BaseModel)


class AssistantLLMError(RuntimeError):
    """Public message plus bounded diagnostics, never raw upstream business content."""

    def __init__(self, message: str, *, code: AssistantFailureCode = AssistantFailureCode.INTERNAL_ERROR,
                 cause: BaseException | None = None, provider_status: int | None = None,
                 provider_request_id: str | None = None, provider_error_type: str | None = None,
                 provider_error_param: str | None = None, schema_protocol_rejected: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = root_failure_retryable(code)
        self.cause = cause
        self.provider_status = provider_status
        self.provider_request_id = provider_request_id
        self.provider_error_type = provider_error_type
        self.provider_error_param = provider_error_param
        self.schema_protocol_rejected = schema_protocol_rejected


class AssistantModelTransport:
    """At most two inference calls sharing one timeout and the enclosing turn budget."""

    async def ainvoke_structured(self, *, api_host: str, api_key: str, model: str,
                                 temperature: float, system_prompt: str, user_prompt: str,
                                 response_model: type[ResultT], error_prefix: str,
                                 timeout_seconds: float = 120, stream: bool = False,
                                 retry_timeouts: bool = False,
                                 output_mode: OutputMode = "json_object") -> ResultT:
        if not api_host or not api_key or not model:
            raise AssistantLLMError(f"{error_prefix}：AI 配置不完整", code=AssistantFailureCode.CONFIGURATION_ERROR)
        if output_mode not in {"json_object", "json_schema"}:
            raise AssistantLLMError(f"{error_prefix}：结构化协议无效", code=AssistantFailureCode.REQUEST_PROTOCOL_ERROR)
        payload = _request_payload(model=model, temperature=temperature, system_prompt=system_prompt,
                                   user_prompt=user_prompt, response_model=response_model,
                                   stream=stream, output_mode=output_mode)
        deadline = monotonic() + timeout_seconds
        for attempt in range(2):
            turn_remaining = attempt_budget_remaining()
            if attempt == 0 and turn_remaining is None:
                remaining = timeout_seconds
            else:
                remaining = deadline - monotonic()
                if turn_remaining is not None:
                    remaining = min(remaining, turn_remaining)
            if remaining <= 0:
                raise AssistantLLMError(f"{error_prefix}：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)
            try:
                return await self._invoke_once(api_host=api_host, api_key=api_key, payload=payload,
                                               response_model=response_model, error_prefix=error_prefix,
                                               timeout_seconds=remaining, stream=stream)
            except AssistantLLMError as exc:
                logger.warning("assistant_model_failure stage=%s mode=%s stream=%s attempt=%s code=%s "
                               "status=%s request_id=%s provider_type=%s provider_param=%s",
                               error_prefix, output_mode, stream, attempt + 1, exc.code.value,
                               exc.provider_status, exc.provider_request_id, exc.provider_error_type,
                               exc.provider_error_param)
                if attempt:
                    raise
                if exc.code is AssistantFailureCode.MODEL_OUTPUT_INVALID and _is_bounded_correction(exc):
                    validation_errors = exc.cause.errors(
                        include_input=False, include_context=False, include_url=False
                    )[:12]
                    errors = [{"path": [part if isinstance(part, int) else (_safe_token(part) or "<field>")
                                        for part in e["loc"][:12]], "type": e["type"]}
                              for e in validation_errors]
                    payload["messages"].append({"role": "user", "content":
                        "上一份 JSON 未通过契约校验：" + json.dumps(errors, ensure_ascii=False)
                        + "。请按系统 schema 从原始业务输入重新生成；遵守字段类型与枚举，不补造事实。"})
                elif retry_timeouts and exc.code is AssistantFailureCode.UPSTREAM_TIMEOUT:
                    continue
                else:
                    raise
        raise AssertionError("unreachable")

    async def _invoke_once(self, *, api_host: str, api_key: str, payload: dict[str, Any],
                           response_model: type[ResultT], error_prefix: str,
                           timeout_seconds: float, stream: bool) -> ResultT:
        try:
            if stream:
                return await _invoke_stream(api_host=api_host, api_key=api_key, payload=payload,
                                            response_model=response_model, error_prefix=error_prefix,
                                            timeout_seconds=timeout_seconds)
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
                    response = await client.post(
                        f"{api_host.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
            failure = _status_failure(response, error_prefix, api_key)
            if failure is not None:
                raise failure
            return _parse_structured(response, response_model, error_prefix)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise AssistantLLMError(f"{error_prefix}：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT,
                                    cause=exc) from exc
        except httpx.HTTPError as exc:
            raise AssistantLLMError(f"{error_prefix}：AI 请求失败", code=AssistantFailureCode.UPSTREAM_UNAVAILABLE,
                                    cause=exc) from exc


def _safe_token(value: object) -> str | None:
    if isinstance(value, str) and len(value) <= 160 and all(
        c.isascii() and (c.isalnum() or c in "_-.[]") for c in value
    ):
        return value
    return None


def _safe_metadata(value: object, secret: str) -> str | None:
    # Providers may echo credentials in error fields; any 8-char run of the key disqualifies the value.
    token = _safe_token(value)
    if token is None or not secret:
        return token
    window = min(8, len(secret))
    if any(secret[i:i + window] in token for i in range(len(secret) - window + 1)):
        return None
    return token


def _status_failure(response: httpx.Response, error_prefix: str, api_key: str) -> AssistantLLMError | None:
    status = response.status_code
    if status < 400:
        return None
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error", {}) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    message = error.get("message", "")
    text = message.lower() if isinstance(message, str) else ""
    param = _safe_metadata(error.get("param"), api_key)
    # Only explicit unsupported protocol errors permit capability-time fallback.
    schema_rejected = status in {400, 422} and (param or "").startswith("response_format") and (
        "json_schema" in text or "strict" in text
    ) and any(term in text for term in ("not supported", "unsupported", "does not support"))
    if status == 408:
        code, label = AssistantFailureCode.UPSTREAM_TIMEOUT, "AI 请求超时"
    elif status == 429 or status >= 500:
        code, label = AssistantFailureCode.UPSTREAM_UNAVAILABLE, "AI 服务暂不可用"
    elif status in {401, 403}:
        code, label = AssistantFailureCode.AUTHENTICATION_ERROR, "AI 鉴权或权限失败"
    elif status in {400, 422}:
        code, label = AssistantFailureCode.REQUEST_PROTOCOL_ERROR, "AI 请求协议不兼容"
    else:
        code, label = AssistantFailureCode.CONFIGURATION_ERROR, "AI 配置无效"
    return AssistantLLMError(f"{error_prefix}：{label}", code=code, provider_status=status,
        provider_request_id=_safe_metadata(
            response.headers.get("x-request-id") or response.headers.get("request-id"), api_key,
        ),
        provider_error_type=_safe_metadata(error.get("type"), api_key), provider_error_param=param,
        schema_protocol_rejected=schema_rejected)


def _unwrap_json_fence(content: str) -> str:
    """Remove one exact outer JSON fence; leave all other validation to Pydantic."""
    candidate = content.strip()
    if not candidate.startswith("```") or not candidate.endswith("\n```"):
        return content
    opening_end = candidate.find("\n")
    if candidate[:opening_end] not in {"```", "```json", "```\r", "```json\r"}:
        return content
    return candidate[opening_end + 1:-4]


def _is_bounded_correction(error: AssistantLLMError) -> bool:
    if not isinstance(error.cause, ValidationError):
        return False
    return all(item.get("type") not in {"json_invalid", "json_type"} for item in error.cause.errors())


def _validate_content(content: object, response_model: type[ResultT], error_prefix: str) -> ResultT:
    if not isinstance(content, str) or not content.strip():
        raise AssistantLLMError(f"{error_prefix}：结构化输出无效", code=AssistantFailureCode.MODEL_OUTPUT_INVALID)
    try:
        return response_model.model_validate_json(_unwrap_json_fence(content))
    except ValidationError as exc:
        raise AssistantLLMError(f"{error_prefix}：结构化输出无效", code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
                                cause=exc) from exc

def _parse_structured(response: httpx.Response, response_model: type[ResultT], error_prefix: str) -> ResultT:
    try:
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") not in {None, "stop"} or choice["message"].get("refusal"):
            raise ValueError("incomplete or refused response")
        content = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AssistantLLMError(f"{error_prefix}：结构化输出无效", code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
                                cause=exc) from exc
    return _validate_content(content, response_model, error_prefix)


def team_model_credentials(db: Any, team_id: int) -> tuple[str, str, str]:  # noqa: ANN401
    """Resolve team-scoped credentials without falling back to another team."""
    config = ai_config_crud.get_config(db, team_id)
    if config is None:
        raise AssistantLLMError("AI 配置未设置", code=AssistantFailureCode.CONFIGURATION_ERROR)
    try:
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise AssistantLLMError("AI 配置无效", code=AssistantFailureCode.CONFIGURATION_ERROR, cause=exc) from exc
    host, model_name = config.api_host, config.model_name
    if not all(isinstance(item, str) and item for item in (api_key, host, model_name)):
        raise AssistantLLMError("AI 配置不完整", code=AssistantFailureCode.CONFIGURATION_ERROR)
    return host, api_key, model_name


def team_output_mode(db: Any, team_id: int) -> OutputMode:  # noqa: ANN401
    config = ai_config_crud.get_config(db, team_id)
    mode = getattr(config, "structured_output_mode", "json_object")
    if mode not in {"json_object", "json_schema"}:
        raise AssistantLLMError("结构化协议配置无效", code=AssistantFailureCode.CONFIGURATION_ERROR)
    return mode


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt typed object schemas to strict provider syntax, never erase open-map semantics."""
    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key in {"default", "title"}:
            continue
        if key in {"properties", "$defs"}:
            result[key] = {name: _strict_json_schema(child) for name, child in value.items()}
        elif isinstance(value, dict):
            result[key] = _strict_json_schema(value)
        elif isinstance(value, list):
            result[key] = [_strict_json_schema(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    if result.get("type") == "object":
        properties = result.get("properties")
        if not isinstance(properties, dict) or result.get("additionalProperties", False) is not False:
            raise AssistantLLMError("此输出契约含开放对象，无法使用严格 schema 协议",
                                    code=AssistantFailureCode.REQUEST_PROTOCOL_ERROR)
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


def _request_payload(*, model: str, temperature: float, system_prompt: str, user_prompt: str,
                     response_model: type[BaseModel], stream: bool,
                     output_mode: OutputMode = "json_object") -> dict[str, Any]:
    schema = response_model.model_json_schema()
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt + "\n仅输出符合 JSON schema 的 JSON 对象："
                + json.dumps(schema, ensure_ascii=False)},
            {"role": "user", "content": user_prompt},
            {"role": "user", "content": "请只返回符合系统 schema 的 JSON 对象。"},
        ],
        "temperature": temperature,
        "stream": stream,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": response_model.__name__, "strict": True, "schema": _strict_json_schema(schema),
        }} if output_mode == "json_schema" else {"type": "json_object"},
    }


async def _invoke_stream(*, api_host: str, api_key: str, payload: dict[str, Any],
                         response_model: type[ResultT], error_prefix: str, timeout_seconds: float) -> ResultT:
    from app.core.config import get_settings
    from app.services.ai_http_client import ai_httpx_streaming_timeout
    read_timeout = max(0.001, min(get_settings().AGENT_STRUCTURED_STREAM_CHUNK_TIMEOUT, timeout_seconds))
    chunks: list[str] = []
    finished = False
    try:
        async with asyncio.timeout(timeout_seconds):
            streaming_timeout = ai_httpx_streaming_timeout(read=read_timeout)
            async with httpx.AsyncClient(timeout=streaming_timeout, trust_env=False) as client, client.stream(
                "POST", f"{api_host.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    failure = _status_failure(response, error_prefix, api_key)
                    assert failure is not None
                    raise failure
                if response.headers.get("content-type", "").startswith("application/json"):
                    await response.aread()
                    return _parse_structured(response, response_model, error_prefix)
                async for line in response.aiter_lines():
                    if line.strip() == "data: [DONE]":
                        finished = True
                        continue
                    event = _stream_event(line)
                    if event is None:
                        continue
                    if event.get("error"):
                        raise AssistantLLMError(f"{error_prefix}：流式响应失败",
                                                code=AssistantFailureCode.UPSTREAM_UNAVAILABLE)
                    choices = event.get("choices")
                    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                        choice = choices[0]
                        delta = choice.get("delta", choice.get("message", {}))
                        finish_reason = choice.get("finish_reason")
                        refused = isinstance(delta, dict) and delta.get("refusal")
                        if finish_reason not in {None, "stop"} or refused:
                            raise AssistantLLMError(f"{error_prefix}：流式结果不完整或被拒绝",
                                                    code=AssistantFailureCode.MODEL_OUTPUT_INVALID)
                        if finish_reason == "stop":
                            finished = True
                    piece = _stream_piece(line)
                    if piece:
                        chunks.append(piece)
                if not finished:
                    raise AssistantLLMError(f"{error_prefix}：流式结果未正常结束",
                                            code=AssistantFailureCode.MODEL_OUTPUT_INVALID)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise AssistantLLMError(f"{error_prefix}：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT,
                                cause=exc) from exc
    except httpx.HTTPError as exc:
        raise AssistantLLMError(f"{error_prefix}：AI 请求失败", code=AssistantFailureCode.UPSTREAM_UNAVAILABLE,
                                cause=exc) from exc
    return _validate_content("".join(chunks), response_model, error_prefix)


def _stream_event(line: str) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw.startswith("data:") or raw[5:].strip() in {"", "[DONE]"}:
        return None
    try:
        data = json.loads(raw[5:].strip())
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _stream_piece(line: str) -> str:
    event = _stream_event(line)
    if event is None:
        return ""
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    choice = choices[0]
    for key in ("delta", "message"):
        part = choice.get(key)
        if isinstance(part, dict) and isinstance(part.get("content"), str):
            return part["content"]
    return ""
