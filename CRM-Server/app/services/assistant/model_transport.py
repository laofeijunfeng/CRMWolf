# ruff: noqa: RUF001
"""Neutral OpenAI-compatible structured calls for the sales assistant."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError

from app.crud.ai_config import ai_config_crud
from app.services.assistant.failure_contract import (
    AssistantFailureCode,
    root_failure_retryable,
)


class AssistantLLMError(RuntimeError):
    """The configured AI service could not return a valid structured result."""

    def __init__(
        self,
        message: str,
        *,
        code: AssistantFailureCode = AssistantFailureCode.INTERNAL_ERROR,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = root_failure_retryable(code)
        self.cause = cause


ResultT = TypeVar("ResultT", bound=BaseModel)


class AssistantModelTransport:
    """One bounded request against the team's OpenAI-compatible endpoint."""

    async def ainvoke_structured(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResultT],
        error_prefix: str,
        timeout_seconds: float = 120,
    ) -> ResultT:
        if not api_host or not api_key or not model:
            raise AssistantLLMError(
                f"{error_prefix}：AI 配置不完整",
                code=AssistantFailureCode.CONFIGURATION_ERROR,
            )
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    f"{api_host.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": system_prompt
                                + "\n仅输出符合 JSON schema 的 JSON 对象："
                                + json.dumps(response_model.model_json_schema(), ensure_ascii=False),
                            },
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "stream": False,
                        "response_format": {"type": "json_object"},
                    },
                )
        except httpx.TimeoutException as exc:
            raise AssistantLLMError(
                f"{error_prefix}：AI 请求超时",
                code=AssistantFailureCode.UPSTREAM_TIMEOUT,
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise AssistantLLMError(
                f"{error_prefix}：AI 请求失败",
                code=AssistantFailureCode.UPSTREAM_UNAVAILABLE,
                cause=exc,
            ) from exc
        status_error = _status_failure(response.status_code, error_prefix)
        if status_error is not None:
            raise status_error
        return _parse_structured(response, response_model, error_prefix)


def _status_failure(status_code: int, error_prefix: str) -> AssistantLLMError | None:
    if status_code < 400:
        return None
    if status_code == 408:
        return AssistantLLMError(f"{error_prefix}：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)
    if status_code == 429 or status_code >= 500:
        return AssistantLLMError(f"{error_prefix}：AI 请求失败", code=AssistantFailureCode.UPSTREAM_UNAVAILABLE)
    return AssistantLLMError(f"{error_prefix}：AI 配置无效", code=AssistantFailureCode.CONFIGURATION_ERROR)


def _parse_structured(response: httpx.Response, response_model: type[ResultT], error_prefix: str) -> ResultT:
    try:
        data = response.json()
    except ValueError as exc:
        raise AssistantLLMError(
            f"{error_prefix}：结构化输出无效",
            code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
            cause=exc,
        ) from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AssistantLLMError(
            f"{error_prefix}：结构化输出无效",
            code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
            cause=exc,
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise AssistantLLMError(
            f"{error_prefix}：结构化输出无效",
            code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
        )
    try:
        return response_model.model_validate_json(content)
    except ValidationError as exc:
        raise AssistantLLMError(
            f"{error_prefix}：结构化输出无效",
            code=AssistantFailureCode.MODEL_OUTPUT_INVALID,
            cause=exc,
        ) from exc


def team_model_credentials(db: Any, team_id: int) -> tuple[str, str, str]:  # noqa: ANN401
    """Resolve team-scoped credentials without falling back to another team."""
    config = ai_config_crud.get_config(db, team_id)
    if config is None:
        raise AssistantLLMError("AI 配置未设置", code=AssistantFailureCode.CONFIGURATION_ERROR)
    try:
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise AssistantLLMError("AI 配置无效", code=AssistantFailureCode.CONFIGURATION_ERROR, cause=exc) from exc
    host = config.api_host
    model_name = config.model_name
    if not isinstance(api_key, str) or not isinstance(host, str) or not isinstance(model_name, str):
        raise AssistantLLMError("AI 配置不完整", code=AssistantFailureCode.CONFIGURATION_ERROR)
    if not api_key or not host or not model_name:
        raise AssistantLLMError("AI 配置不完整", code=AssistantFailureCode.CONFIGURATION_ERROR)
    return host, api_key, model_name
