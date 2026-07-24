"""AI-backed follow-up quality evaluator for CRM AI Agent."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.ai_service import ai_service
from app.services.agent.prompts import (
    build_follow_up_quality_system_prompt,
    build_follow_up_quality_messages,
)
from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentMemorySnapshot,
    AgentSemanticParseResult,
)
from app.services.follow_up_quality_principles import get_follow_up_quality_principles

try:
    from langchain.agents import create_agent
except Exception:  # pragma: no cover - keeps imports resilient in stripped envs
    create_agent = None  # type: ignore[assignment]

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional production dependency
    ChatOpenAI = None  # type: ignore[assignment]


class AgentFollowUpQualityEvaluatorError(Exception):
    """Raised when follow-up quality evaluation cannot call or validate AI output."""


@dataclass(frozen=True)
class AgentFollowUpQualityEnvelope:
    result: AgentFollowUpQualityResult
    quality_source: str
    model: str
    fallback_reason: Optional[str] = None
    fallback_error: Optional[str] = None


class AgentFollowUpQualityEvaluator:
    PASSING_SCORE = 60

    def __init__(self, ai_client=ai_service, agent_factory=None, chat_model_factory=None) -> None:
        self.ai_client = ai_client
        self.agent_factory = agent_factory or create_agent
        self.chat_model_factory = chat_model_factory or ChatOpenAI

    async def evaluate_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        semantic_result: AgentSemanticParseResult,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentFollowUpQualityEnvelope:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentFollowUpQualityEvaluatorError("AI 配置未设置，无法评估跟进质量。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentFollowUpQualityEvaluatorError("AI API Key 未设置，无法评估跟进质量。")

        semantic_json = semantic_result.model_dump_json(exclude_none=True)
        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        principles_text = get_follow_up_quality_principles()
        fallback_reason = None
        fallback_error = None
        try:
            langchain_result = await self._evaluate_with_langchain(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                user_message=user_message,
                semantic_json=semantic_json,
                memory_json=memory_json,
                principles_text=principles_text,
                temperature=min(float(config.temperature or 0.1), 0.2),
                current_date=current_date,
            )
        except AgentFollowUpQualityEvaluatorError:
            raise
        except Exception as exc:
            langchain_result = None
            fallback_reason = "langchain_structured_output_failed"
            fallback_error = exc.__class__.__name__
        if langchain_result is not None:
            return AgentFollowUpQualityEnvelope(
                result=self.normalize_result(langchain_result),
                quality_source="langchain_structured_output",
                model=config.model_name,
            )

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_follow_up_quality_messages(
                user_message,
                semantic_json,
                memory_json,
                current_date=current_date,
                principles_text=principles_text,
            ),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=max(int(config.max_tokens or 1024), 1400),
            response_format={"type": "json_object"},
        )
        return AgentFollowUpQualityEnvelope(
            result=self.normalize_result(self.parse_raw_response(raw)),
            quality_source="system_ai_json_object",
            model=config.model_name,
            fallback_reason=fallback_reason or "langchain_unavailable",
            fallback_error=fallback_error,
        )

    async def _evaluate_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        semantic_json: str,
        memory_json: str,
        principles_text: str,
        temperature: float,
        current_date: Optional[date] = None,
    ) -> Optional[AgentFollowUpQualityResult]:
        if self.agent_factory is None or self.chat_model_factory is None:
            return None

        system_prompt = build_follow_up_quality_system_prompt(
            current_date=current_date,
            principles_text=principles_text,
        )
        user_prompt = (
            "【用户原文】\n"
            f"{user_message}\n\n"
            "【语义解析结果】\n"
            f"{semantic_json}\n\n"
            "【会话记忆】\n"
            f"{memory_json}"
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
                response_format=AgentFollowUpQualityResult,
                middleware=[],
            )
            response = await agent.ainvoke({"messages": [{"role": "user", "content": user_prompt}]})
        except Exception as exc:
            raise RuntimeError(f"LangChain 跟进质量 structured output 调用失败：{exc.__class__.__name__}") from exc

        structured_response = response.get("structured_response") if isinstance(response, dict) else None
        if isinstance(structured_response, AgentFollowUpQualityResult):
            return structured_response
        if structured_response is not None:
            try:
                return AgentFollowUpQualityResult.model_validate(structured_response)
            except ValidationError as exc:
                raise AgentFollowUpQualityEvaluatorError(f"LangChain 跟进质量结果无效：{str(exc)}") from exc
        raise AgentFollowUpQualityEvaluatorError("LangChain 跟进质量 structured output 未返回结构化结果。")

    def parse_raw_response(self, raw: str) -> AgentFollowUpQualityResult:
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentFollowUpQualityResult.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentFollowUpQualityEvaluatorError(f"AI 跟进质量结果无效：{str(exc)}") from exc

    def normalize_result(self, result: AgentFollowUpQualityResult) -> AgentFollowUpQualityResult:
        score = max(0, min(100, int(result.score)))
        passed = score >= self.PASSING_SCORE
        supplement_question = result.supplement_question if not passed else None
        if not passed and not supplement_question:
            supplement_question = "这条跟进还差一点关键信息，请补充下一步由谁在什么时间做什么。"
        return result.model_copy(update={
            "score": score,
            "passed": passed,
            "supplement_question": supplement_question,
            "missing_aspects": result.missing_aspects[:3],
            "reason": (result.reason or "跟进记录信息还不够完整。")[:80],
        })

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


agent_follow_up_quality_evaluator = AgentFollowUpQualityEvaluator()
