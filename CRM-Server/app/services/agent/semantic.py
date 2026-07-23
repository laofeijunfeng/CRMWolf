"""AI-backed semantic parser for CRM AI Agent."""
from __future__ import annotations

import json
from datetime import date
from dataclasses import dataclass
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.ai_service import ai_service
from app.services.agent.prompts import CRM_AGENT_SEMANTIC_SYSTEM_PROMPT, build_semantic_messages
from app.services.agent.schemas import AgentMemorySnapshot, AgentSemanticParseResult

try:
    from langchain.agents import create_agent
except Exception:  # pragma: no cover - keeps imports resilient in stripped envs
    create_agent = None  # type: ignore[assignment]

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional production dependency
    ChatOpenAI = None  # type: ignore[assignment]


class AgentSemanticParserError(Exception):
    """Raised when semantic parsing cannot call or validate AI output."""


@dataclass(frozen=True)
class AgentSemanticParseEnvelope:
    result: AgentSemanticParseResult
    parse_source: str
    model: str


class AgentSemanticParser:
    def __init__(self, ai_client=ai_service, agent_factory=None, chat_model_factory=None) -> None:
        self.ai_client = ai_client
        self.agent_factory = agent_factory or create_agent
        self.chat_model_factory = chat_model_factory or ChatOpenAI

    async def parse(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        memory: Optional[AgentMemorySnapshot] = None,
    ) -> AgentSemanticParseResult:
        envelope = await self.parse_with_metadata(
            db,
            team_id=team_id,
            user_message=user_message,
            memory=memory,
        )
        return envelope.result

    async def parse_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        memory: Optional[AgentMemorySnapshot] = None,
    ) -> AgentSemanticParseEnvelope:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法进行 Agent 语义理解。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法进行 Agent 语义理解。")

        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        langchain_result = await self._parse_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            memory_json=memory_json,
            temperature=min(float(config.temperature or 0.1), 0.2),
        )
        if langchain_result is not None:
            return AgentSemanticParseEnvelope(
                result=langchain_result,
                parse_source="langchain_structured_output",
                model=config.model_name,
            )

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_semantic_messages(user_message, memory_json),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=max(int(config.max_tokens or 1024), 1500),
            response_format={"type": "json_object"},
        )
        return AgentSemanticParseEnvelope(
            result=self.parse_raw_response(raw),
            parse_source="system_ai_json_object",
            model=config.model_name,
        )

    async def _parse_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        memory_json: str,
        temperature: float,
    ) -> Optional[AgentSemanticParseResult]:
        if self.agent_factory is None or self.chat_model_factory is None:
            return None

        system_prompt = f"{CRM_AGENT_SEMANTIC_SYSTEM_PROMPT}\n\n【当前日期】\n{date.today().isoformat()}"
        user_prompt = "【会话记忆】\n" f"{memory_json}\n\n" "【用户输入】\n" f"{user_message}"
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
                response_format=AgentSemanticParseResult,
                middleware=[],
            )
            response = await agent.ainvoke({"messages": [{"role": "user", "content": user_prompt}]})
        except Exception:
            return None

        structured_response = response.get("structured_response") if isinstance(response, dict) else None
        if isinstance(structured_response, AgentSemanticParseResult):
            return structured_response
        if structured_response is not None:
            try:
                return AgentSemanticParseResult.model_validate(structured_response)
            except ValidationError as exc:
                raise AgentSemanticParserError(f"LangChain structured output 无效：{str(exc)}") from exc
        raise AgentSemanticParserError("LangChain structured output 未返回结构化结果。")

    def parse_raw_response(self, raw: str) -> AgentSemanticParseResult:
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentSemanticParseResult.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSemanticParserError(f"AI 语义解析结果无效：{str(exc)}") from exc

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


agent_semantic_parser = AgentSemanticParser()
