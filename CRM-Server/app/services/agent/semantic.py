"""AI-backed semantic parser for CRM AI Agent."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from app.crud.ai_config import ai_config_crud
from app.crud.product_intent import format_active_product_catalog
from app.services.acquisition_source_service import default_source_name, format_active_source_names
from app.services.agent.langchain_runtime import (
    AgentLangChainRuntime,
    AgentLangChainStructuredOutputError,
    agent_model_enable_thinking,
)
from app.services.agent.prompts import (
    CRM_AGENT_PENDING_INTERRUPTION_SYSTEM_PROMPT,
    CRM_AGENT_RESOURCE_RESOLUTION_SYSTEM_PROMPT,
    CRM_AGENT_TURN_INTENT_SYSTEM_PROMPT,
    CRM_AGENT_TURN_RELATION_SYSTEM_PROMPT,
    render_semantic_system_prompt,
)
from app.services.agent.schemas import (
    AgentMemorySnapshot,
    AgentPendingInterruptionDecision,
    AgentResourceResolutionResult,
    AgentSemanticParseResult,
    AgentTurnIntentDecision,
    AgentTurnRelationDecision,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.agent.types import JSONDict


class AgentSemanticParserError(Exception):
    """Raised when semantic parsing cannot call or validate AI output."""


@dataclass(frozen=True)
class AgentSemanticParseEnvelope:
    result: AgentSemanticParseResult
    parse_source: str
    model: str


StructuredDecisionT = TypeVar("StructuredDecisionT", bound=BaseModel)


class AgentSemanticParser:
    def __init__(self, agent_factory=None, chat_model_factory=None) -> None:
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
        memory: AgentMemorySnapshot | None = None,
        current_date: date | None = None,
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
        memory: AgentMemorySnapshot | None = None,
        current_date: date | None = None,
    ) -> AgentPendingInterruptionDecision:
        config, api_key = self._require_ai_config(
            db,
            team_id,
            missing_config_message="AI 配置未设置\uff0c无法判断挂起任务是否需要切换。",
            missing_key_message="AI API Key 未设置\uff0c无法判断挂起任务是否需要切换。",
        )
        result = await self._assess_pending_interruption_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            pending_task_json=json.dumps(pending_task, ensure_ascii=False, default=str),
            memory_json=(memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True),
            temperature=min(float(config.temperature or 0.1), 0.2),
            current_date=current_date,
        )
        return self._require_structured_result(result, "LangChain 挂起任务判断运行时不可用。")

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
        current_date: date | None = None,
    ) -> list[JSONDict]:
        config, api_key = self._require_ai_config(
            db,
            team_id,
            missing_config_message="AI 配置未设置\uff0c无法进行业务对象语义选择。",
            missing_key_message="AI API Key 未设置\uff0c无法进行业务对象语义选择。",
        )
        result = await self._rank_resource_candidates_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            action_json=json.dumps(
                {"resource_kind": resource_kind, "action_name": action_name},
                ensure_ascii=False,
                default=str,
            ),
            target_json=json.dumps(target, ensure_ascii=False, default=str),
            candidates_json=json.dumps(candidates, ensure_ascii=False, default=str),
            temperature=min(float(config.temperature or 0.1), 0.2),
            current_date=current_date,
        )
        resolved = self._require_structured_result(result, "LangChain 业务对象选择运行时不可用。")
        return [ranking.model_dump(exclude_none=True) for ranking in resolved.rankings]

    async def assess_turn_relation(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        active_task: dict | None = None,
        suspended_tasks: list[dict] | None = None,
        memory: AgentMemorySnapshot | None = None,
        current_date: date | None = None,
    ) -> AgentTurnRelationDecision:
        config, api_key = self._require_ai_config(
            db,
            team_id,
            missing_config_message="AI 配置未设置\uff0c无法判断本轮与业务状态的关系。",
            missing_key_message="AI API Key 未设置\uff0c无法判断本轮与业务状态的关系。",
        )
        result = await self._assess_turn_relation_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            active_task_json=json.dumps(active_task, ensure_ascii=False, default=str),
            suspended_tasks_json=json.dumps(suspended_tasks or [], ensure_ascii=False, default=str),
            memory_json=(memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True),
            temperature=min(float(config.temperature or 0.1), 0.2),
            current_date=current_date,
        )
        return self._require_structured_result(result, "LangChain 本轮关系判断运行时不可用。")

    async def assess_turn_intent(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        current_interrupt: dict | None = None,
        active_task: dict | None = None,
        suspended_tasks: list[dict] | None = None,
        memory: AgentMemorySnapshot | None = None,
        current_date: date | None = None,
    ) -> AgentTurnIntentDecision:
        config, api_key = self._require_ai_config(
            db,
            team_id,
            missing_config_message="AI 配置未设置\uff0c无法判断本轮意图。",
            missing_key_message="AI API Key 未设置\uff0c无法判断本轮意图。",
        )
        result = await self._assess_turn_intent_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            current_interrupt_json=json.dumps(current_interrupt or {}, ensure_ascii=False, default=str),
            active_task_json=json.dumps(active_task or {}, ensure_ascii=False, default=str),
            suspended_tasks_json=json.dumps(suspended_tasks or [], ensure_ascii=False, default=str),
            memory_json=(memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True),
            temperature=0.0,
            current_date=current_date,
        )
        return self._require_structured_result(result, "LangChain 本轮意图判断运行时不可用。")

    async def parse_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        memory: AgentMemorySnapshot | None = None,
        current_date: date | None = None,
    ) -> AgentSemanticParseEnvelope:
        config, api_key = self._require_ai_config(
            db,
            team_id,
            missing_config_message="AI 配置未设置\uff0c无法进行 Agent 语义理解。",
            missing_key_message="AI API Key 未设置\uff0c无法进行 Agent 语义理解。",
        )
        catalog_text, names_enum = format_active_product_catalog(db, team_id)
        result = await self._parse_with_langchain(
            api_host=config.api_host,
            api_key=api_key,
            model=config.model_name,
            user_message=user_message,
            memory_json=(memory or AgentMemorySnapshot()).model_dump_json(exclude_none=True),
            temperature=min(float(config.temperature or 0.1), 0.2),
            current_date=current_date,
            source_names=format_active_source_names(db, team_id),
            default_source_name=default_source_name(db, team_id),
            product_catalog_text=catalog_text,
            product_names_enum=names_enum,
        )
        return AgentSemanticParseEnvelope(
            result=self._require_structured_result(result, "LangChain structured output 运行时不可用。"),
            parse_source="langchain_structured_output",
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
        current_date: date | None = None,
        source_names: list[str] | None = None,
        default_source_name: str | None = None,
        product_catalog_text: str | None = None,
        product_names_enum: str | None = None,
    ) -> AgentSemanticParseResult | None:
        prompt_date = current_date or date.today()
        system_prompt = (
            f"{render_semantic_system_prompt(source_names, default_source_name, product_catalog_text, product_names_enum)}"
            f"\n\n【当前日期】\n{prompt_date.isoformat()}"
        )
        user_prompt = "【会话记忆】\n" f"{memory_json}\n\n" "【用户输入】\n" f"{user_message}"
        return await self._invoke_structured(
            api_host=api_host,
            api_key=api_key,
            model=model,
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=AgentSemanticParseResult,
            error_prefix="LangChain structured output",
        )

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
        current_date: date | None = None,
    ) -> AgentPendingInterruptionDecision | None:
        prompt_date = current_date or date.today()
        return await self._invoke_structured(
            api_host=api_host,
            api_key=api_key,
            model=model,
            temperature=temperature,
            system_prompt=(
                f"{CRM_AGENT_PENDING_INTERRUPTION_SYSTEM_PROMPT}\n\n"
                f"【当前日期】\n{prompt_date.isoformat()}"
            ),
            user_prompt=(
                "【当前挂起任务】\n"
                f"{pending_task_json}\n\n"
                "【会话记忆】\n"
                f"{memory_json}\n\n"
                "【用户本轮输入】\n"
                f"{user_message}"
            ),
            response_model=AgentPendingInterruptionDecision,
            error_prefix="LangChain 挂起任务判断",
        )

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
        current_date: date | None = None,
    ) -> AgentTurnRelationDecision | None:
        prompt_date = current_date or date.today()
        return await self._invoke_structured(
            api_host=api_host,
            api_key=api_key,
            model=model,
            temperature=temperature,
            system_prompt=(
                f"{CRM_AGENT_TURN_RELATION_SYSTEM_PROMPT}\n\n"
                f"【当前日期】\n{prompt_date.isoformat()}"
            ),
            user_prompt=(
                "【active_task】\n"
                f"{active_task_json}\n\n"
                "【suspended_tasks】\n"
                f"{suspended_tasks_json}\n\n"
                "【session_context】\n"
                f"{memory_json}\n\n"
                "【用户本轮输入】\n"
                f"{user_message}"
            ),
            response_model=AgentTurnRelationDecision,
            error_prefix="LangChain 本轮关系判断",
        )

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
        current_date: date | None = None,
    ) -> AgentResourceResolutionResult | None:
        prompt_date = current_date or date.today()
        return await self._invoke_structured(
            api_host=api_host,
            api_key=api_key,
            model=model,
            temperature=temperature,
            system_prompt=(
                f"{CRM_AGENT_RESOURCE_RESOLUTION_SYSTEM_PROMPT}\n\n"
                f"【当前日期】\n{prompt_date.isoformat()}"
            ),
            user_prompt=(
                "【待办动作】\n"
                f"{action_json}\n\n"
                "【目标/上下文】\n"
                f"{target_json}\n\n"
                "【候选资源】\n"
                f"{candidates_json}\n\n"
                "【用户本轮回复】\n"
                f"{user_message}"
            ),
            response_model=AgentResourceResolutionResult,
            error_prefix="LangChain 业务对象选择",
        )

    async def _assess_turn_intent_with_langchain(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        user_message: str,
        current_interrupt_json: str,
        active_task_json: str,
        suspended_tasks_json: str,
        memory_json: str,
        temperature: float,
        current_date: date | None = None,
    ) -> AgentTurnIntentDecision | None:
        prompt_date = current_date or date.today()
        return await self._invoke_structured(
            api_host=api_host,
            api_key=api_key,
            model=model,
            temperature=temperature,
            system_prompt=(
                f"{CRM_AGENT_TURN_INTENT_SYSTEM_PROMPT}\n\n"
                f"【当前日期】\n{prompt_date.isoformat()}"
            ),
            user_prompt=(
                "【current_interrupt】\n"
                f"{current_interrupt_json}\n\n"
                "【active_task】\n"
                f"{active_task_json}\n\n"
                "【suspended_tasks】\n"
                f"{suspended_tasks_json}\n\n"
                "【session_context】\n"
                f"{memory_json}\n\n"
                "【用户本轮输入】\n"
                f"{user_message}"
            ),
            response_model=AgentTurnIntentDecision,
            error_prefix="LangChain 本轮意图判断",
        )

    async def _invoke_structured(
        self,
        *,
        api_host: str,
        api_key: str,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredDecisionT],
        error_prefix: str,
    ) -> StructuredDecisionT | None:
        try:
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                enable_thinking=agent_model_enable_thinking(model),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                error_prefix=error_prefix,
            )
        except (AgentLangChainStructuredOutputError, RuntimeError) as exc:
            message = str(exc).replace(f"{error_prefix} 结果无效", f"{error_prefix} 无效")
            raise AgentSemanticParserError(message) from exc

    @staticmethod
    def _require_ai_config(
        db: Session,
        team_id: int,
        *,
        missing_config_message: str,
        missing_key_message: str,
    ) -> tuple[Any, str]:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSemanticParserError(missing_config_message)
        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSemanticParserError(missing_key_message)
        return config, api_key

    @staticmethod
    def _require_structured_result(
        result: StructuredDecisionT | None,
        unavailable_message: str,
    ) -> StructuredDecisionT:
        if result is None:
            raise AgentSemanticParserError(unavailable_message)
        return result


agent_semantic_parser = AgentSemanticParser()
