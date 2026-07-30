"""AI-backed follow-up quality evaluator for CRM AI Agent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.agent.prompts import build_follow_up_quality_system_prompt
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

    def __init__(self, agent_factory=None, chat_model_factory=None) -> None:
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
        return AgentFollowUpQualityEnvelope(
            result=self.normalize_result(langchain_result),
            quality_source="langchain_structured_output",
            model=config.model_name,
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

agent_follow_up_quality_evaluator = AgentFollowUpQualityEvaluator()
