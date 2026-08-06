"""Trace event helpers for CRM Agent LangGraph runtimes."""
from __future__ import annotations

from app.services.agent.schemas import (
    AgentFollowUpQualityResult,
    AgentSemanticParseResult,
    AgentSuggestionResult,
)
from app.services.agent.state import AgentGraphState
from app.services.agent.types import JSONDict, coerce_json_dict


def build_semantic_trace_events(state: AgentGraphState) -> list[JSONDict]:
    semantic_result = _semantic_result(state)
    if not semantic_result:
        return []
    semantic_metadata = state.get("semantic_metadata") or {}
    intent_label = _intent_display_label(semantic_result)
    return [
        {
            "event": "intent",
            "intent": semantic_result.intent,
            "technical_intent": semantic_result.intent,
            "intent_label": intent_label,
        },
        {
            "event": "semantic_parsed",
            "intent": semantic_result.intent,
            "technical_intent": semantic_result.intent,
            "intent_label": intent_label,
            "confidence": semantic_result.intent_confidence,
            "parse_source": semantic_metadata.get("parse_source"),
            "model": semantic_metadata.get("model"),
            "fallback_reason": semantic_metadata.get("fallback_reason"),
            "fallback_error": semantic_metadata.get("fallback_error"),
            "need_clarification": semantic_result.need_clarification,
            "parsed": state.get("parsed") or {},
        },
    ]


def build_suggestion_trace_events(state: AgentGraphState) -> list[JSONDict]:
    suggestion_result = _suggestion_result(state)
    if suggestion_result:
        suggestion_metadata = state.get("suggestion_metadata") or {}
        return [{
            "event": "business_suggestions",
            "summary": suggestion_result.summary,
            "suggestions": [
                coerce_json_dict(suggestion.model_dump(exclude_none=True))
                for suggestion in suggestion_result.suggestions
            ],
            "need_user_choice": suggestion_result.need_user_choice,
            "clarification_question": suggestion_result.clarification_question,
            "suggestion_source": suggestion_metadata.get("suggestion_source"),
            "model": suggestion_metadata.get("model"),
            "structured_output_strategy": suggestion_metadata.get("structured_output_strategy"),
            "fallback_reason": suggestion_metadata.get("fallback_reason"),
            "fallback_error": suggestion_metadata.get("fallback_error"),
            "fallback_error_message": suggestion_metadata.get("fallback_error_message"),
        }]
    suggestion_error = state.get("suggestion_error")
    return [{"event": "suggestion_failed", "message": suggestion_error}] if isinstance(suggestion_error, str) else []


def build_follow_up_quality_trace_events(state: AgentGraphState) -> list[JSONDict]:
    quality = _follow_up_quality_result(state)
    if quality:
        metadata = state.get("follow_up_quality_metadata") or {}
        return [{
            "event": "follow_up_quality_evaluated",
            "score": quality.score,
            "passed": quality.passed,
            "reason": quality.reason,
            "missing_aspects": quality.missing_aspects,
            "quality_source": metadata.get("quality_source"),
            "model": metadata.get("model"),
            "fallback_reason": metadata.get("fallback_reason"),
            "fallback_error": metadata.get("fallback_error"),
        }]
    quality_error = state.get("follow_up_quality_error")
    return [{"event": "follow_up_quality_failed", "message": quality_error}] if isinstance(quality_error, str) else []


def _semantic_result(state: AgentGraphState) -> AgentSemanticParseResult | None:
    value = state.get("semantic_result")
    return value if isinstance(value, AgentSemanticParseResult) else None


def _suggestion_result(state: AgentGraphState) -> AgentSuggestionResult | None:
    value = state.get("suggestion_result")
    return value if isinstance(value, AgentSuggestionResult) else None


def _follow_up_quality_result(state: AgentGraphState) -> AgentFollowUpQualityResult | None:
    value = state.get("follow_up_quality_result")
    return value if isinstance(value, AgentFollowUpQualityResult) else None


def _intent_display_label(semantic_result: AgentSemanticParseResult) -> str:
    if semantic_result.intent == "CRM_READ_QUERY":
        return {
            "FOLLOW_UP_TASKS": "任务查询",
            "WORK_SUMMARY": "工作总结",
            "CUSTOMER_PROFILE": "客户查询",
            "OPPORTUNITY": "商机查询",
            "CONTRACT": "合同查询",
            "PAYMENT": "回款查询",
            "INVOICE": "发票查询",
            "LICENSE": "License 查询",
        }.get(semantic_result.read_query.type, "业务查询")
    return {
        "CUSTOMER_ACTIVITY": "客户跟进记录",
        "PAYMENT_RECORD": "回款记录",
        "CREATE_LEAD": "创建线索",
        "CREATE_CUSTOMER": "创建客户",
        "CREATE_OPPORTUNITY": "创建商机",
        "CREATE_CONTACT": "创建联系人",
        "CREATE_INVOICE_TITLE": "创建发票抬头",
        "CREATE_DEPLOYMENT_INFO": "创建部署信息",
        "CREATE_CUSTOMER_MEMBER": "添加客户团队成员",
        "UNKNOWN": "无法识别",
    }.get(semantic_result.intent, semantic_result.intent)
