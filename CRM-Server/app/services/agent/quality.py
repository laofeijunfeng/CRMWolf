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
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
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
        self.langchain_runtime = AgentLangChainRuntime(
            agent_factory=agent_factory,
            chat_model_factory=chat_model_factory,
        )

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
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=AgentFollowUpQualityResult,
                error_prefix="LangChain 跟进质量 structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            message = str(exc).replace(
                "LangChain 跟进质量 structured output 结果无效",
                "LangChain 跟进质量结果无效",
            )
            raise AgentFollowUpQualityEvaluatorError(message) from exc

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
