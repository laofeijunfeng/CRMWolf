"""AI-backed business suggestion generator for CRM AI Agent."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.ai_service import ai_service
from app.services.agent.prompts import CRM_AGENT_SUGGESTION_SYSTEM_PROMPT, build_suggestion_messages
from app.services.agent.schemas import AgentSemanticParseResult, AgentSuggestionResult

try:
    from langchain.agents import create_agent
except Exception:  # pragma: no cover - keeps imports resilient in stripped envs
    create_agent = None  # type: ignore[assignment]

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional production dependency
    ChatOpenAI = None  # type: ignore[assignment]


class AgentSuggestionGeneratorError(Exception):
    """Raised when suggestion generation cannot call or validate AI output."""


@dataclass(frozen=True)
class AgentSuggestionEnvelope:
    result: AgentSuggestionResult
    suggestion_source: str
    model: str


class AgentSuggestionGenerator:
    def __init__(self, ai_client=ai_service, agent_factory=None, chat_model_factory=None) -> None:
        self.ai_client = ai_client
        self.agent_factory = agent_factory or create_agent
        self.chat_model_factory = chat_model_factory or ChatOpenAI

    async def generate_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        semantic_result: AgentSemanticParseResult,
        customer_context: dict[str, Any],
    ) -> AgentSuggestionEnvelope:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSuggestionGeneratorError("AI 配置未设置，无法生成业务建议。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSuggestionGeneratorError("AI API Key 未设置，无法生成业务建议。")

        semantic_json = semantic_result.model_dump_json(exclude_none=True)
        context_json = json.dumps(customer_context, ensure_ascii=False, default=str)
        langchain_result = await self._generate_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            semantic_json=semantic_json,
            customer_context_json=context_json,
            temperature=min(float(config.temperature or 0.1), 0.2),
        )
        if langchain_result is not None:
            return AgentSuggestionEnvelope(
                result=langchain_result,
                suggestion_source="langchain_structured_output",
                model=config.model_name,
            )

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_suggestion_messages(user_message, semantic_json, context_json),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=max(int(config.max_tokens or 1024), 1500),
            response_format={"type": "json_object"},
        )
        return AgentSuggestionEnvelope(
            result=self.parse_raw_response(raw),
            suggestion_source="system_ai_json_object",
            model=config.model_name,
        )

    async def _generate_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        semantic_json: str,
        customer_context_json: str,
        temperature: float,
    ) -> Optional[AgentSuggestionResult]:
        if self.agent_factory is None or self.chat_model_factory is None:
            return None

        system_prompt = f"{CRM_AGENT_SUGGESTION_SYSTEM_PROMPT}\n\n【当前日期】\n{date.today().isoformat()}"
        user_prompt = (
            "【用户输入】\n"
            f"{user_message}\n\n"
            "【语义解析结果】\n"
            f"{semantic_json}\n\n"
            "【客户上下文】\n"
            f"{customer_context_json}"
        )
        try:
            chat_model = self.chat_model_factory(
                model=model,
                api_key=api_key,
                base_url=api_host,
                temperature=temperature,
            )
            agent = self.agent_factory(
                model=chat_model,
                tools=[],
                system_prompt=system_prompt,
                response_format=AgentSuggestionResult,
                middleware=[],
            )
            response = await agent.ainvoke({"messages": [{"role": "user", "content": user_prompt}]})
        except Exception:
            return None

        structured_response = response.get("structured_response") if isinstance(response, dict) else None
        if isinstance(structured_response, AgentSuggestionResult):
            return structured_response
        if structured_response is not None:
            try:
                return AgentSuggestionResult.model_validate(structured_response)
            except ValidationError as exc:
                raise AgentSuggestionGeneratorError(f"LangChain suggestion structured output 无效：{str(exc)}") from exc
        raise AgentSuggestionGeneratorError("LangChain suggestion structured output 未返回结构化结果。")

    def parse_raw_response(self, raw: str) -> AgentSuggestionResult:
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentSuggestionResult.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSuggestionGeneratorError(f"AI 业务建议结果无效：{str(exc)}") from exc

    @staticmethod
    def _clean_json(raw: str) -> str:
        content = raw.strip()
        if content.startswith("```json"):
            content = content[7:].strip()
        elif content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end >= start:
            return content[start:end + 1]
        return content


agent_suggestion_generator = AgentSuggestionGenerator()
