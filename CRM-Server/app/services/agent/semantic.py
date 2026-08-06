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
from app.services.agent.prompts import (
    build_confirmation_intent_messages,
    build_resource_resolution_messages,
    build_turn_intent_messages,
    CRM_AGENT_PENDING_INTERRUPTION_SYSTEM_PROMPT,
    CRM_AGENT_RESOURCE_RESOLUTION_SYSTEM_PROMPT,
    CRM_AGENT_SEMANTIC_SYSTEM_PROMPT,
    CRM_AGENT_TURN_RELATION_SYSTEM_PROMPT,
    build_pending_interruption_messages,
    build_semantic_messages,
    build_turn_relation_messages,
)
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.agent.schemas import (
    AgentConfirmationIntentDecision,
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentResourceResolutionResult,
    AgentSemanticParseResult,
    AgentTurnIntentDecision,
    AgentTurnRelationDecision,
)
from app.services.agent.types import JSONDict


class AgentSemanticParserError(Exception):
    """Raised when semantic parsing cannot call or validate AI output."""


@dataclass(frozen=True)
class AgentSemanticParseEnvelope:
    result: AgentSemanticParseResult
    parse_source: str
    model: str
    fallback_reason: Optional[str] = None
    fallback_error: Optional[str] = None


class AgentSemanticParser:
    def __init__(self, ai_client=ai_service, agent_factory=None, chat_model_factory=None) -> None:
        self.ai_client = ai_client
        self.langchain_runtime = AgentLangChainRuntime(
            agent_factory=agent_factory,
            chat_model_factory=chat_model_factory,
        )

    async def parse(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentSemanticParseResult:
        envelope = await self.parse_with_metadata(
            db,
            team_id=team_id,
            user_message=user_message,
            memory=memory,
            current_date=current_date,
        )
        return envelope.result

    async def assess_pending_interruption(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        pending_task: dict,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentPendingInterruptionDecision:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法判断挂起任务是否需要切换。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法判断挂起任务是否需要切换。")

        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        pending_task_json = json.dumps(pending_task, ensure_ascii=False, default=str)
        try:
            langchain_result = await self._assess_pending_interruption_with_langchain(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                user_message=user_message,
                pending_task_json=pending_task_json,
                memory_json=memory_json,
                temperature=min(float(config.temperature or 0.1), 0.2),
                current_date=current_date,
            )
        except AgentSemanticParserError:
            raise
        except Exception:
            langchain_result = None
        if langchain_result is not None:
            return langchain_result

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_pending_interruption_messages(
                user_message,
                pending_task_json,
                memory_json,
                current_date=current_date,
            ),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentPendingInterruptionDecision.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSemanticParserError(f"AI 挂起任务判断结果无效：{str(exc)}") from exc

    async def assess_confirmation_intent(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        pending_task: dict,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentConfirmationIntentDecision:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法判断确认意图。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法判断确认意图。")

        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        pending_task_json = json.dumps(pending_task, ensure_ascii=False, default=str)
        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_confirmation_intent_messages(
                user_message,
                pending_task_json,
                memory_json,
                current_date=current_date,
            ),
            temperature=0.0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentConfirmationIntentDecision.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSemanticParserError(f"AI 确认意图判断结果无效：{str(exc)}") from exc

    async def rank_resource_candidates(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        resource_kind: str,
        action_name: str,
        target: JSONDict,
        candidates: list[JSONDict],
        current_date: Optional[date] = None,
    ) -> list[JSONDict]:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法进行业务对象语义选择。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法进行业务对象语义选择。")

        action = {
            "resource_kind": resource_kind,
            "action_name": action_name,
        }
        target_json = json.dumps(target, ensure_ascii=False, default=str)
        candidates_json = json.dumps(candidates, ensure_ascii=False, default=str)
        action_json = json.dumps(action, ensure_ascii=False, default=str)
        try:
            langchain_result = await self._rank_resource_candidates_with_langchain(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                user_message=user_message,
                action_json=action_json,
                target_json=target_json,
                candidates_json=candidates_json,
                temperature=min(float(config.temperature or 0.1), 0.2),
                current_date=current_date,
            )
        except AgentSemanticParserError:
            raise
        except Exception:
            langchain_result = None
        if langchain_result is not None:
            return [ranking.model_dump(exclude_none=True) for ranking in langchain_result.rankings]

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_resource_resolution_messages(
                user_message,
                action_json,
                target_json,
                candidates_json,
                current_date=current_date,
            ),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(self._clean_json(raw))
            result = AgentResourceResolutionResult.model_validate(parsed)
            return [ranking.model_dump(exclude_none=True) for ranking in result.rankings]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSemanticParserError(f"AI 业务对象选择结果无效：{str(exc)}") from exc

    async def assess_turn_relation(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        active_task: Optional[dict] = None,
        suspended_tasks: Optional[list[dict]] = None,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentTurnRelationDecision:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法判断本轮与业务状态的关系。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法判断本轮与业务状态的关系。")

        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        active_task_json = json.dumps(active_task, ensure_ascii=False, default=str)
        suspended_tasks_json = json.dumps(suspended_tasks or [], ensure_ascii=False, default=str)
        try:
            langchain_result = await self._assess_turn_relation_with_langchain(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                user_message=user_message,
                active_task_json=active_task_json,
                suspended_tasks_json=suspended_tasks_json,
                memory_json=memory_json,
                temperature=min(float(config.temperature or 0.1), 0.2),
                current_date=current_date,
            )
        except AgentSemanticParserError:
            raise
        except Exception:
            langchain_result = None
        if langchain_result is not None:
            return langchain_result

        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_turn_relation_messages(
                user_message,
                active_task_json,
                suspended_tasks_json,
                memory_json,
                current_date=current_date,
            ),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentTurnRelationDecision.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSemanticParserError(f"AI 本轮关系判断结果无效：{str(exc)}") from exc

    async def assess_turn_intent(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        current_interrupt: Optional[dict] = None,
        active_task: Optional[dict] = None,
        suspended_tasks: Optional[list[dict]] = None,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentTurnIntentDecision:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法判断本轮意图。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法判断本轮意图。")

        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        current_interrupt_json = json.dumps(current_interrupt or {}, ensure_ascii=False, default=str)
        active_task_json = json.dumps(active_task or {}, ensure_ascii=False, default=str)
        suspended_tasks_json = json.dumps(suspended_tasks or [], ensure_ascii=False, default=str)
        raw = await self.ai_client._stream_chat_collect(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            messages=build_turn_intent_messages(
                user_message,
                current_interrupt_json,
                active_task_json,
                suspended_tasks_json,
                memory_json,
                current_date=current_date,
            ),
            temperature=0.0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(self._clean_json(raw))
            return AgentTurnIntentDecision.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentSemanticParserError(f"AI 本轮意图判断结果无效：{str(exc)}") from exc

    async def parse_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        memory: Optional[AgentMemorySnapshot] = None,
        current_date: Optional[date] = None,
    ) -> AgentSemanticParseEnvelope:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError("AI 配置未设置，无法进行 Agent 语义理解。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError("AI API Key 未设置，无法进行 Agent 语义理解。")

        memory_json = (memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True)
        fallback_reason = None
        fallback_error = None
        try:
            langchain_result = await self._parse_with_langchain(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                user_message=user_message,
                memory_json=memory_json,
                temperature=min(float(config.temperature or 0.1), 0.2),
                current_date=current_date,
            )
        except AgentSemanticParserError:
            raise
        except Exception as exc:
            langchain_result = None
            fallback_reason = "langchain_structured_output_failed"
            fallback_error = exc.__class__.__name__
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
            messages=build_semantic_messages(user_message, memory_json, current_date=current_date),
            temperature=min(float(config.temperature or 0.1), 0.2),
            max_tokens=max(int(config.max_tokens or 1024), 1500),
            response_format={"type": "json_object"},
        )
        return AgentSemanticParseEnvelope(
            result=self.parse_raw_response(raw),
            parse_source="system_ai_json_object",
            model=config.model_name,
            fallback_reason=fallback_reason or "langchain_unavailable",
            fallback_error=fallback_error,
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
        current_date: Optional[date] = None,
    ) -> Optional[AgentSemanticParseResult]:
        prompt_date = current_date or date.today()
        system_prompt = f"{CRM_AGENT_SEMANTIC_SYSTEM_PROMPT}\n\n【当前日期】\n{prompt_date.isoformat()}"
        user_prompt = "【会话记忆】\n" f"{memory_json}\n\n" "【用户输入】\n" f"{user_message}"
        try:
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=AgentSemanticParseResult,
                error_prefix="LangChain structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            message = str(exc).replace("LangChain structured output 结果无效", "LangChain structured output 无效")
            raise AgentSemanticParserError(message) from exc

    async def _assess_pending_interruption_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        pending_task_json: str,
        memory_json: str,
        temperature: float,
        current_date: Optional[date] = None,
    ) -> Optional[AgentPendingInterruptionDecision]:
        prompt_date = current_date or date.today()
        system_prompt = f"{CRM_AGENT_PENDING_INTERRUPTION_SYSTEM_PROMPT}\n\n【当前日期】\n{prompt_date.isoformat()}"
        user_prompt = (
            "【当前挂起任务】\n"
            f"{pending_task_json}\n\n"
            "【会话记忆】\n"
            f"{memory_json}\n\n"
            "【用户本轮输入】\n"
            f"{user_message}"
        )
        try:
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=AgentPendingInterruptionDecision,
                error_prefix="LangChain 挂起任务判断",
            )
        except AgentLangChainStructuredOutputError as exc:
            raise AgentSemanticParserError(str(exc)) from exc

    async def _assess_turn_relation_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        active_task_json: str,
        suspended_tasks_json: str,
        memory_json: str,
        temperature: float,
        current_date: Optional[date] = None,
    ) -> Optional[AgentTurnRelationDecision]:
        prompt_date = current_date or date.today()
        system_prompt = f"{CRM_AGENT_TURN_RELATION_SYSTEM_PROMPT}\n\n【当前日期】\n{prompt_date.isoformat()}"
        user_prompt = (
            "【active_task】\n"
            f"{active_task_json}\n\n"
            "【suspended_tasks】\n"
            f"{suspended_tasks_json}\n\n"
            "【session_context】\n"
            f"{memory_json}\n\n"
            "【用户本轮输入】\n"
            f"{user_message}"
        )
        try:
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=AgentTurnRelationDecision,
                error_prefix="LangChain 本轮关系判断",
            )
        except AgentLangChainStructuredOutputError as exc:
            raise AgentSemanticParserError(str(exc)) from exc

    async def _rank_resource_candidates_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        action_json: str,
        target_json: str,
        candidates_json: str,
        temperature: float,
        current_date: Optional[date] = None,
    ) -> Optional[AgentResourceResolutionResult]:
        prompt_date = current_date or date.today()
        system_prompt = f"{CRM_AGENT_RESOURCE_RESOLUTION_SYSTEM_PROMPT}\n\n【当前日期】\n{prompt_date.isoformat()}"
        user_prompt = (
            "【待办动作】\n"
            f"{action_json}\n\n"
            "【目标/上下文】\n"
            f"{target_json}\n\n"
            "【候选资源】\n"
            f"{candidates_json}\n\n"
            "【用户本轮回复】\n"
            f"{user_message}"
        )
        try:
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=AgentResourceResolutionResult,
                error_prefix="LangChain 业务对象选择",
            )
        except AgentLangChainStructuredOutputError as exc:
            raise AgentSemanticParserError(str(exc)) from exc

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
