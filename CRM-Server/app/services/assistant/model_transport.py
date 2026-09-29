"""Neutral OpenAI-compatible structured calls for the sales assistant."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ValidationError

from app.crud.ai_config import ai_config_crud


class AssistantLLMError(RuntimeError):
    """The configured AI service could not return a valid structured result."""


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
            raise AssistantLLMError(f"{error_prefix}：AI 配置不完整")
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    f"{api_host.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt + "\n仅输出符合 JSON schema 的 JSON 对象：" + json.dumps(response_model.model_json_schema(), ensure_ascii=False)},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "stream": False,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty model response")
                return response_model.model_validate_json(content)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise AssistantLLMError(f"{error_prefix}：AI 请求失败或结构化输出无效") from exc


def team_model_credentials(db: Any, team_id: int) -> tuple[str, str, str]:
    """Resolve team-scoped credentials without falling back to another team."""
    config = ai_config_crud.get_config(db, team_id)
    if config is None:
        raise AssistantLLMError("AI 配置未设置")
    try:
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise AssistantLLMError("AI 配置无效") from exc
    if not api_key or not config.api_host or not config.model_name:
        raise AssistantLLMError("AI 配置不完整")
    return config.api_host, api_key, config.model_name
