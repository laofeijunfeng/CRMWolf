"""AI-backed business suggestion generator for CRM AI Agent."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.ai_config import ai_config_crud
from app.services.ai_service import ai_service
from app.services.agent import business_rules
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.agent.prompts import CRM_AGENT_SUGGESTION_SYSTEM_PROMPT, build_suggestion_messages
from app.services.agent.schemas import AgentBusinessSuggestion, AgentSemanticParseResult, AgentSuggestionResult
from app.utils.public_id import is_opportunity_public_id


class AgentSuggestionGeneratorError(Exception):
    """Raised when suggestion generation cannot call or validate AI output."""


@dataclass(frozen=True)
class AgentSuggestionEnvelope:
    result: AgentSuggestionResult
    suggestion_source: str
    model: str
    structured_output_strategy: Optional[str] = None
    fallback_reason: Optional[str] = None
    fallback_error: Optional[str] = None
    fallback_error_message: Optional[str] = None


class AgentSuggestionGenerator:
    SUPPORTED_ACTIONS = {
        "CREATE_OPPORTUNITY",
        "MOVE_OPPORTUNITY_STAGE",
        "CREATE_CONTACT",
        "CREATE_PAYMENT_PLAN",
        "CREATE_PAYMENT_RECORD",
        "CREATE_INVOICE_TITLE",
        "CREATE_DEPLOYMENT_INFO",
        "CREATE_LICENSE_APPLICATION",
        "CUSTOMER_QUERY_SUMMARY",
        "NO_ACTION",
    }

    def __init__(self, ai_client=ai_service, agent_factory=None, chat_model_factory=None) -> None:
        self.ai_client = ai_client
        self.langchain_runtime = AgentLangChainRuntime(
            agent_factory=agent_factory,
            chat_model_factory=chat_model_factory,
        )

    async def generate_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        user_message: str,
        semantic_result: AgentSemanticParseResult,
        customer_context: dict[str, object],
        current_date: Optional[date] = None,
    ) -> AgentSuggestionEnvelope:
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            raise AgentSuggestionGeneratorError("AI 配置未设置，无法生成业务建议。")

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            raise AgentSuggestionGeneratorError("AI API Key 未设置，无法生成业务建议。")

        semantic_json = semantic_result.model_dump_json(exclude_none=True)
        context_json = json.dumps(customer_context, ensure_ascii=False, default=str)
        fallback_reason = None
        fallback_error = None
        fallback_error_message = None
        structured_output_strategy = "tool"
        try:
            langchain_result = await self._generate_with_langchain(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                user_message=user_message,
                semantic_json=semantic_json,
                customer_context_json=context_json,
                temperature=min(float(config.temperature or 0.1), 0.2),
                current_date=current_date,
            )
        except AgentSuggestionGeneratorError:
            raise
        except Exception as exc:
            langchain_result = None
            fallback_reason = "langchain_structured_output_failed"
            fallback_error = exc.__class__.__name__
            fallback_error_message = str(exc)
        if langchain_result is not None:
            return AgentSuggestionEnvelope(
                result=self.apply_business_guardrails(langchain_result, semantic_result, customer_context),
                suggestion_source="langchain_structured_output",
                model=config.model_name,
                structured_output_strategy=structured_output_strategy,
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
            result=self.apply_business_guardrails(self.parse_raw_response(raw), semantic_result, customer_context),
            suggestion_source="system_ai_json_object",
            model=config.model_name,
            structured_output_strategy=structured_output_strategy,
            fallback_reason=fallback_reason or "langchain_unavailable",
            fallback_error=fallback_error,
            fallback_error_message=fallback_error_message,
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
        current_date: Optional[date] = None,
    ) -> Optional[AgentSuggestionResult]:
        prompt_date = current_date or date.today()
        system_prompt = f"{CRM_AGENT_SUGGESTION_SYSTEM_PROMPT}\n\n【当前日期】\n{prompt_date.isoformat()}"
        user_prompt = (
            "【用户输入】\n"
            f"{user_message}\n\n"
            "【语义解析结果】\n"
            f"{semantic_json}\n\n"
            "【客户上下文】\n"
            f"{customer_context_json}"
        )
        try:
            return await self.langchain_runtime.ainvoke_structured(
                api_host=api_host,
                api_key=api_key,
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=AgentSuggestionResult,
                structured_output_strategy="tool",
                error_prefix="LangChain suggestion structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            message = str(exc).replace(
                "LangChain suggestion structured output 结果无效",
                "LangChain suggestion structured output 无效",
            )
            raise AgentSuggestionGeneratorError(message) from exc

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

    @classmethod
    def apply_business_guardrails(
        cls,
        result: AgentSuggestionResult,
        semantic_result: AgentSemanticParseResult,
        customer_context: dict[str, object],
    ) -> AgentSuggestionResult:
        valid_suggestions: list[AgentBusinessSuggestion] = []
        contracts = cls._context_items(customer_context.get("contracts"))
        opportunities = cls._context_items(customer_context.get("opportunities"))
        deployment_infos = cls._context_items(customer_context.get("deployment_infos"))
        open_payment_plans = [
            plan
            for plan in cls._context_items(customer_context.get("payment_plans"))
            if cls._is_open_payment_plan(plan)
        ]
        contract_ids = {int(item["id"]) for item in contracts if item.get("id") is not None}
        payment_plan_ids = {int(item["id"]) for item in open_payment_plans if item.get("id") is not None}
        approved_opportunities = [item for item in opportunities if cls._is_approved_opportunity(item)]
        approved_contracts = [item for item in contracts if cls._is_approved_contract(item)]
        approved_opportunity_ids = {str(item["id"]) for item in approved_opportunities if item.get("id") is not None}
        approved_contract_ids = {int(item["id"]) for item in approved_contracts if item.get("id") is not None}
        active_stage_context = cls._context_items(customer_context.get("active_opportunity_stage_context"))

        for suggestion in result.suggestions:
            action = suggestion.action
            if action not in cls.SUPPORTED_ACTIONS:
                continue
            if action == "MOVE_OPPORTUNITY_STAGE":
                guarded = cls._guard_move_opportunity_stage_suggestion(suggestion, active_stage_context)
                if guarded is not None:
                    valid_suggestions.append(guarded)
                continue
            if action == "CREATE_PAYMENT_PLAN":
                guarded = cls._guard_payment_plan_suggestion(suggestion, contract_ids, contracts)
                if guarded is not None:
                    valid_suggestions.append(guarded)
                continue
            if action == "CREATE_PAYMENT_RECORD":
                guarded = cls._guard_payment_record_suggestion(suggestion, payment_plan_ids, open_payment_plans)
                if guarded is not None:
                    valid_suggestions.append(guarded)
                continue
            if action == "CREATE_LICENSE_APPLICATION":
                guarded = cls._guard_license_application_suggestion(
                    suggestion,
                    approved_opportunity_ids,
                    approved_contract_ids,
                    approved_opportunities,
                    approved_contracts,
                    deployment_infos,
                )
                if guarded is not None:
                    valid_suggestions.append(guarded)
                continue
            valid_suggestions.append(suggestion)

        if semantic_result.intent == "PAYMENT_RECORD":
            valid_suggestions = cls._repair_payment_suggestions(
                result.summary,
                valid_suggestions,
                opportunities,
                contracts,
                open_payment_plans,
            )

        return result.model_copy(
            update={
                "suggestions": valid_suggestions[:3],
                "need_user_choice": any(
                    suggestion.action != "NO_ACTION" and suggestion.confidence >= 0.7
                    for suggestion in valid_suggestions[:3]
                ),
            }
        )

    @classmethod
    def _guard_move_opportunity_stage_suggestion(
        cls,
        suggestion: AgentBusinessSuggestion,
        active_stage_context: list[dict[str, object]],
    ) -> Optional[AgentBusinessSuggestion]:
        target_stage_id = (suggestion.execution_payload or {}).get("stage_template_id")
        if not target_stage_id:
            return None
        try:
            target_stage_id = int(target_stage_id)
        except (TypeError, ValueError):
            return None

        valid_contexts = [
            item
            for item in active_stage_context
            if isinstance(item.get("opportunity"), dict)
            and cls._is_active_opportunity(item["opportunity"])
            and cls._is_approved_opportunity(item["opportunity"])
            and is_opportunity_public_id(item["opportunity"].get("id"))
            and isinstance(item.get("procurement_stages"), list)
        ]
        related_id = suggestion.related_object_id
        if related_id is not None:
            if not is_opportunity_public_id(related_id):
                return None
            valid_contexts = [
                item
                for item in valid_contexts
                if cls._opportunity_public_ids_match(item["opportunity"].get("id"), related_id)
            ]
        elif len(valid_contexts) == 1:
            related_id = valid_contexts[0]["opportunity"].get("id")
            if not is_opportunity_public_id(related_id):
                return None
        else:
            candidate_contexts = [
                item
                for item in valid_contexts
                if cls._stage_move_target(item, target_stage_id) is not None
            ]
            if len(candidate_contexts) >= 2:
                target_stage = cls._stage_move_target(candidate_contexts[0], target_stage_id)
                return suggestion.model_copy(update={
                    "related_object_type": "opportunity",
                    "related_object_id": None,
                    "missing_fields": list(dict.fromkeys([*suggestion.missing_fields, "opportunity_id"])),
                    "execution_payload": {
                        **(suggestion.execution_payload or {}),
                        "stage_template_id": target_stage_id,
                        "target_stage_name": target_stage.get("stage_name") if target_stage else None,
                        "stage_move_steps": target_stage.get("stage_move_steps") if target_stage else [],
                    },
                })
            if len(candidate_contexts) == 1:
                valid_contexts = candidate_contexts
                related_id = candidate_contexts[0]["opportunity"].get("id")
            else:
                return None

        if related_id is None or len(valid_contexts) != 1:
            return None

        stage_context = valid_contexts[0]
        stages = [stage for stage in stage_context.get("procurement_stages") or [] if isinstance(stage, dict)]
        requested_stage = next((stage for stage in stages if stage.get("id") is not None and int(stage["id"]) == target_stage_id), None)
        target_stage = cls._stage_move_target(stage_context, target_stage_id)
        if not target_stage or target_stage.get("is_current"):
            return None

        return suggestion.model_copy(update={
            "related_object_type": "opportunity",
            "related_object_id": str(related_id),
            "execution_payload": {
                **(suggestion.execution_payload or {}),
                "stage_template_id": target_stage_id,
                "target_stage_name": target_stage.get("stage_name"),
                "stage_move_steps": target_stage.get("stage_move_steps"),
            },
        })

    @staticmethod
    def _opportunity_public_ids_match(left: object, right: object) -> bool:
        return is_opportunity_public_id(left) and is_opportunity_public_id(right) and str(left) == str(right)

    @staticmethod
    def _stage_move_target(
        stage_context: dict[str, object],
        target_stage_id: int,
    ) -> Optional[dict[str, object]]:
        stages = [stage for stage in stage_context.get("procurement_stages") or [] if isinstance(stage, dict)]
        requested_stage = next(
            (
                stage
                for stage in stages
                if stage.get("id") is not None and int(stage["id"]) == int(target_stage_id)
            ),
            None,
        )
        if not requested_stage or requested_stage.get("is_current"):
            return None
        current_stage = next((stage for stage in stages if stage.get("is_current")), None)
        if current_stage and requested_stage.get("sort_order") is not None and current_stage.get("sort_order") is not None:
            try:
                if int(requested_stage["sort_order"]) < int(current_stage["sort_order"]):
                    return None
            except (TypeError, ValueError):
                return None
        stage_plan = AgentSuggestionGenerator._forward_stage_move_plan(stages, current_stage, requested_stage)
        if not stage_plan:
            return None
        return {
            **requested_stage,
            "stage_move_steps": stage_plan,
        }

    @staticmethod
    def _forward_stage_move_plan(
        stages: list[dict[str, object]],
        current_stage: object,
        target_stage: dict[str, object],
    ) -> list[dict[str, object]]:
        target_order = AgentSuggestionGenerator._stage_sort_order(target_stage)
        if target_stage.get("id") is None or target_order is None:
            return []
        if not isinstance(current_stage, dict):
            start_order = None
        else:
            start_order = AgentSuggestionGenerator._stage_sort_order(current_stage)
            if start_order is None or target_order <= start_order:
                return []
        candidates = [
            stage
            for stage in stages
            if stage.get("id") is not None
            and AgentSuggestionGenerator._stage_sort_order(stage) is not None
            and int(AgentSuggestionGenerator._stage_sort_order(stage) or 0) <= target_order
            and (start_order is None or int(AgentSuggestionGenerator._stage_sort_order(stage) or 0) > start_order)
        ]
        return [
            {
                "stage_template_id": int(stage["id"]),
                "stage_name": stage.get("stage_name"),
            }
            for stage in sorted(candidates, key=lambda stage: int(AgentSuggestionGenerator._stage_sort_order(stage) or 0))
        ]

    @staticmethod
    def _next_stage_after_current(
        stages: list[dict[str, object]],
        current_stage: object,
    ) -> Optional[dict[str, object]]:
        if not isinstance(current_stage, dict):
            default_stage = next((stage for stage in stages if stage.get("is_default_start")), None)
            if default_stage:
                return default_stage
            sortable = [stage for stage in stages if AgentSuggestionGenerator._stage_sort_order(stage) is not None]
            return min(sortable, key=lambda stage: int(AgentSuggestionGenerator._stage_sort_order(stage) or 0)) if sortable else None
        current_order = AgentSuggestionGenerator._stage_sort_order(current_stage)
        if current_order is None:
            return None
        forward_stages = [
            stage
            for stage in stages
            if not stage.get("is_current")
            and AgentSuggestionGenerator._stage_sort_order(stage) is not None
            and int(AgentSuggestionGenerator._stage_sort_order(stage) or 0) > current_order
        ]
        return min(forward_stages, key=lambda stage: int(AgentSuggestionGenerator._stage_sort_order(stage) or 0)) if forward_stages else None

    @staticmethod
    def _stage_sort_order(stage: dict[str, object]) -> Optional[int]:
        if stage.get("sort_order") is None:
            return None
        try:
            return int(stage["sort_order"])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _guard_payment_plan_suggestion(
        suggestion: AgentBusinessSuggestion,
        contract_ids: set[int],
        contracts: list[dict[str, object]],
    ) -> Optional[AgentBusinessSuggestion]:
        related_id = suggestion.related_object_id
        if related_id is not None and int(related_id) in contract_ids:
            return suggestion.model_copy(update={"related_object_type": "contract"})
        if related_id is None and len(contracts) == 1 and contracts[0].get("id") is not None:
            return suggestion.model_copy(
                update={
                    "related_object_type": "contract",
                    "related_object_id": int(contracts[0]["id"]),
                }
            )
        return None

    @staticmethod
    def _guard_payment_record_suggestion(
        suggestion: AgentBusinessSuggestion,
        payment_plan_ids: set[int],
        open_payment_plans: list[dict[str, object]],
    ) -> Optional[AgentBusinessSuggestion]:
        related_id = suggestion.related_object_id
        if related_id is not None and int(related_id) in payment_plan_ids:
            return suggestion.model_copy(update={"related_object_type": "payment_plan"})
        if related_id is None and len(open_payment_plans) == 1 and open_payment_plans[0].get("id") is not None:
            return suggestion.model_copy(
                update={
                    "related_object_type": "payment_plan",
                    "related_object_id": int(open_payment_plans[0]["id"]),
                }
            )
        return None

    @staticmethod
    def _guard_license_application_suggestion(
        suggestion: AgentBusinessSuggestion,
        approved_opportunity_ids: set[str],
        approved_contract_ids: set[int],
        approved_opportunities: list[dict[str, object]],
        approved_contracts: list[dict[str, object]],
        deployment_infos: list[dict[str, object]],
    ) -> Optional[AgentBusinessSuggestion]:
        if not deployment_infos:
            return None
        related_type = suggestion.related_object_type
        related_id = suggestion.related_object_id
        if related_type == "opportunity":
            if related_id is not None and str(related_id) in approved_opportunity_ids:
                return suggestion
            if related_id is None and len(approved_opportunities) == 1 and approved_opportunities[0].get("id") is not None:
                return suggestion.model_copy(update={"related_object_id": approved_opportunities[0]["id"]})
            return None
        if related_type == "contract":
            if related_id is not None and int(related_id) in approved_contract_ids:
                return suggestion
            if related_id is None and len(approved_contracts) == 1 and approved_contracts[0].get("id") is not None:
                return suggestion.model_copy(update={"related_object_id": int(approved_contracts[0]["id"])})
            return None
        return None

    @classmethod
    def _repair_payment_suggestions(
        cls,
        summary: str,
        suggestions: list[AgentBusinessSuggestion],
        opportunities: list[dict[str, object]],
        contracts: list[dict[str, object]],
        open_payment_plans: list[dict[str, object]],
    ) -> list[AgentBusinessSuggestion]:
        if contracts and open_payment_plans:
            return suggestions
        if any(suggestion.action in {"CREATE_PAYMENT_PLAN", "CREATE_PAYMENT_RECORD"} for suggestion in suggestions):
            return suggestions
        if not contracts and not opportunities:
            base_suggestions = [
                suggestion
                for suggestion in suggestions
                if suggestion.action not in {"CREATE_PAYMENT_PLAN", "CREATE_PAYMENT_RECORD"}
            ]
            if any(suggestion.action == "CREATE_OPPORTUNITY" for suggestion in base_suggestions):
                return base_suggestions
            return base_suggestions + [AgentBusinessSuggestion(
                action="CREATE_OPPORTUNITY",
                title="先补充商机",
                reason="用户输入体现已回款，但该客户上下文中没有商机和合同；按 CRM 业务链路应先补齐商机，再处理合同和回款。",
                priority="high",
                requires_confirmation=True,
                missing_fields=["预计成交金额", "采购用户数", "授权模式", "采购类型", "预计成交日期"],
                related_object_type=None,
                related_object_id=None,
                risk_notes=["当前 Agent 暂不支持创建合同，回款计划和回款登记都需要已有合同链路。"],
                confidence=0.86,
            )]
        if not contracts:
            return [
                suggestion
                for suggestion in suggestions
                if suggestion.action in {"NO_ACTION", "CUSTOMER_QUERY_SUMMARY"}
            ] + [AgentBusinessSuggestion(
                action="NO_ACTION",
                title="合同环节缺失",
                reason="用户输入体现已回款，但该客户已有商机却没有可用于回款的合同；创建合同需要附件，当前 Agent 不执行合同创建。",
                priority="high",
                requires_confirmation=False,
                missing_fields=[],
                related_object_type=None,
                related_object_id=None,
                risk_notes=["请先在合同模块完成人工合同创建后，再由 Agent 继续创建回款计划或登记回款。"],
                confidence=0.9,
            )]
        return suggestions

    @staticmethod
    def _context_items(value: object) -> list[dict[str, object]]:
        return business_rules.context_items(value)

    @staticmethod
    def _is_open_payment_plan(plan: dict[str, object]) -> bool:
        return business_rules.is_open_payment_plan(plan)

    @staticmethod
    def _is_approved_opportunity(opportunity: dict[str, object]) -> bool:
        return str(opportunity.get("approval_phase") or "").lower() == "approved"

    @staticmethod
    def _is_active_opportunity(opportunity: dict[str, object]) -> bool:
        return str(opportunity.get("status")) == "0"

    @staticmethod
    def _is_approved_contract(contract: dict[str, object]) -> bool:
        status = str(contract.get("status") or "").upper()
        approval_phase = str(contract.get("approval_phase") or "").lower()
        return status == "SIGNED" or approval_phase == "approved"


agent_suggestion_generator = AgentSuggestionGenerator()
