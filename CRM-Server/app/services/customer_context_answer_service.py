"""Customer context answer generation for CRM Agent."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import ValidationError

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.agent.prompts import build_customer_context_answer_messages
from app.services.agent.schemas import CustomerContextAnswerResult
from app.services.agent.types import coerce_json_dict
from app.services.ai_service import ai_service

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.orm import Session

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
AgentFactory = Callable[..., object]
ChatModelFactory = Callable[..., object]
MessageList = list[dict[str, str]]


class CustomerAnswerAIClient(Protocol):
    async def _stream_chat_collect(
        self,
        api_host: str,
        api_key: str,
        model: str,
        messages: MessageList,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        response_format: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> str: ...

_TECHNICAL_TOKEN_RE = re.compile(
    r"\b("
    r"source_type|source_object_id|business_object_id|business_object_type|"
    r"tool|payload|procurement_method_id|customer_id|opportunity_id|contract_id|"
    r"payment_plan_id|payment_record_id|evidence_id|document_key"
    r")\b",
    re.IGNORECASE,
)


class CustomerContextAnswerError(Exception):
    """Raised when a customer context answer cannot be generated."""


@dataclass(frozen=True)
class CustomerContextAnswerEnvelope:
    result: CustomerContextAnswerResult
    answer_source: str
    model: str | None = None
    fallback_reason: str | None = None
    fallback_error: str | None = None


class CustomerContextAnswerService:
    """Generate user-facing answers from unified customer intelligence context."""

    def __init__(
        self,
        ai_client: CustomerAnswerAIClient = ai_service,
        agent_factory: AgentFactory | None = None,
        chat_model_factory: ChatModelFactory | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.langchain_runtime = AgentLangChainRuntime(
            agent_factory=agent_factory,
            chat_model_factory=chat_model_factory,
        )

    async def answer_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        question: str,
        customer_context: JsonObject,
        customer_memory: JsonObject,
        current_date: date | None = None,
    ) -> CustomerContextAnswerEnvelope:
        fallback = self.fallback_answer(
            question=question,
            customer_context=customer_context,
            customer_memory=customer_memory,
        )
        config = ai_config_crud.get_config(db, team_id)
        if not config:
            return CustomerContextAnswerEnvelope(
                result=fallback,
                answer_source="deterministic_context_fallback",
                fallback_reason="ai_config_missing",
            )

        api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return CustomerContextAnswerEnvelope(
                result=fallback,
                answer_source="deterministic_context_fallback",
                model=config.model_name,
                fallback_reason="ai_api_key_missing",
            )

        customer_context_json = json.dumps(_sanitize_context(customer_context), ensure_ascii=False, default=str)
        customer_memory_json = json.dumps(_sanitize_memory(customer_memory), ensure_ascii=False, default=str)
        messages = build_customer_context_answer_messages(
            question,
            customer_context_json,
            customer_memory_json,
            current_date=current_date,
        )
        temperature = min(float(config.temperature or 0.1), 0.2)
        fallback_error: str | None = None
        try:
            result = await self.langchain_runtime.ainvoke_structured(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                temperature=temperature,
                system_prompt=messages[0]["content"],
                user_prompt=messages[1]["content"],
                response_model=CustomerContextAnswerResult,
                structured_output_strategy="tool",
                error_prefix="LangChain customer context answer structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            result = None
            fallback_error = str(exc)
        except RuntimeError as exc:
            result = None
            fallback_error = f"{exc.__class__.__name__}: {exc!s}"

        if result is not None:
            cleaned = self._clean_result(result)
            if cleaned.answer:
                return CustomerContextAnswerEnvelope(
                    result=cleaned,
                    answer_source="langchain_structured_output",
                    model=config.model_name,
                )

        try:
            raw = await self.ai_client._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max(int(config.max_tokens or 1024), 1200),
                response_format={"type": "json_object"},
            )
            parsed = CustomerContextAnswerResult.model_validate(json.loads(_clean_json(raw)))
            cleaned = self._clean_result(parsed)
            if cleaned.answer:
                return CustomerContextAnswerEnvelope(
                    result=cleaned,
                    answer_source="system_ai_json_object",
                    model=config.model_name,
                    fallback_reason="langchain_unavailable",
                    fallback_error=fallback_error,
                )
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:
            return CustomerContextAnswerEnvelope(
                result=fallback,
                answer_source="deterministic_context_fallback",
                model=config.model_name,
                fallback_reason="ai_answer_failed",
                fallback_error=f"{exc.__class__.__name__}: {exc!s}",
            )

        return CustomerContextAnswerEnvelope(
            result=fallback,
            answer_source="deterministic_context_fallback",
            model=config.model_name,
            fallback_reason="empty_ai_answer",
            fallback_error=fallback_error,
        )

    @classmethod
    def fallback_answer(
        cls,
        *,
        question: str,
        customer_context: JsonObject,
        customer_memory: JsonObject,
    ) -> CustomerContextAnswerResult:
        strong_context = coerce_json_dict(customer_context.get("strong_context"))
        customer = coerce_json_dict(strong_context.get("customer"))
        customer_name = _text(customer.get("account_name")) or "该客户"
        question_text = _text(question)
        parts: list[str] = [
            f"### {customer_name}客户现状"
            if not question_text
            else f"### {customer_name}客户现状\n围绕“{question_text}”，当前可确认的信息如下："
        ]
        used_sections: list[str] = ["customer"]

        profile_parts = [
            _label_value("行业", customer.get("industry_name") or customer.get("industry_code")),
            _label_value("城市", customer.get("city")),
            _label_value("规模", customer.get("company_scale")),
        ]
        profile_line = ", ".join(item for item in profile_parts if item)
        if profile_line:
            parts.append(f"- **基础信息**：{profile_line}。")

        facts = _object_list(strong_context.get("customer_facts"))
        if facts:
            used_sections.append("facts")
            fact_texts = [_text(item.get("content")) for item in facts[:3]]
            fact_line = "; ".join(item for item in fact_texts if item)
            if fact_line:
                parts.append(f"- **客户事实**：{fact_line}。")

        opportunities = _object_list(strong_context.get("opportunities"))
        if opportunities:
            used_sections.append("opportunities")
            parts.append("- **推进中的商机**：" + "; ".join(_opportunity_line(item) for item in opportunities[:3]) + "。")

        contracts = _object_list(strong_context.get("contracts"))
        if contracts:
            used_sections.append("contracts")
            parts.append("- **相关合同**：" + "; ".join(_contract_line(item) for item in contracts[:3]) + "。")

        payments = _object_list(strong_context.get("payment_plans"))
        if payments:
            used_sections.append("payments")
            parts.append("- **回款计划**：" + "; ".join(_payment_plan_line(item) for item in payments[:3]) + "。")

        activities = _object_list(strong_context.get("recent_activities"))
        if activities:
            used_sections.append("activities")
            parts.append("- **近期动态**：" + "; ".join(_activity_line(item) for item in activities[:3]) + "。")

        memory_summaries = _object_list(customer_memory.get("summaries"))
        if memory_summaries:
            used_sections.append("memory")
            memory_text = _memory_line(memory_summaries[0])
            if memory_text:
                parts.append(f"- **长期记忆**：{memory_text}。")

        evidence_items = _object_list(customer_context.get("semantic_evidence"))
        if evidence_items:
            used_sections.append("evidence")
            evidence_text = _text(evidence_items[0].get("text"))
            if evidence_text:
                parts.append(f"- **相关证据**：{evidence_text}。")

        if len(parts) == 1:
            parts.append("- 目前系统里还没有足够的客户业务资料。")

        answer = cls._normalize_markdown_answer(cls._remove_technical_tokens("\n".join(parts)))
        missing_context = [] if len(parts) > 2 else ["客户近期跟进、商机、合同或回款资料"]
        confidence = 0.82 if len(parts) > 2 else 0.45
        return CustomerContextAnswerResult(
            answer=answer,
            confidence=confidence,
            used_sections=_unique_texts(used_sections),
            missing_context=missing_context,
        )

    @classmethod
    def _clean_result(cls, result: CustomerContextAnswerResult) -> CustomerContextAnswerResult:
        answer = cls._normalize_markdown_answer(cls._remove_technical_tokens(result.answer))
        return result.model_copy(update={"answer": answer})

    @staticmethod
    def _remove_technical_tokens(text: str) -> str:
        cleaned = _TECHNICAL_TOKEN_RE.sub("", text)
        cleaned = re.sub(r"\([^)]*=\s*\d+[^)]*\)", "", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _normalize_markdown_answer(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+\n", "\n", normalized)
        normalized = re.sub(r"\n[ \t]+", "\n", normalized)
        normalized = re.sub(r"([^\n])\s+(#{1,6}\s+\d+[.、]\s+)", r"\1\n\n\2", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()


def _sanitize_context(customer_context: JsonObject) -> JsonObject:
    return _sanitize_json(customer_context, drop_keys={
        "id",
        "source_type",
        "source_object_id",
        "business_object_type",
        "business_object_id",
        "evidence_id",
        "document_key",
        "procurement_method_id",
        "usage_policy",
        "retrieval",
    })


def _sanitize_memory(customer_memory: JsonObject) -> JsonObject:
    return _sanitize_json(customer_memory, drop_keys={"namespace_prefix", "source", "id", "tool"})


def _sanitize_json(value: JsonValue | object, *, drop_keys: set[str]) -> JsonValue:
    if isinstance(value, dict):
        sanitized: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in drop_keys or key.endswith("_id"):
                continue
            sanitized[key] = _sanitize_json(item, drop_keys=drop_keys)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_json(item, drop_keys=drop_keys) for item in value[:20]]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


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


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _label_value(label: str, value: object) -> str:
    text = _text(value)
    return f"{label}: {text}" if text else ""


def _object_list(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, dict)]


def _opportunity_line(item: JsonObject) -> str:
    name = _text(item.get("name")) or "未命名商机"
    stage = _text(item.get("stage"))
    amount = _text(item.get("amount"))
    closing_date = _text(item.get("expected_closing_date"))
    fields = [name]
    if stage:
        fields.append(f"阶段 {stage}")
    if amount:
        fields.append(f"预计金额 {amount}")
    if closing_date:
        fields.append(f"预计成交 {closing_date}")
    return ", ".join(fields)


def _contract_line(item: JsonObject) -> str:
    name = _text(item.get("contract_name")) or _text(item.get("contract_number")) or "未命名合同"
    amount = _text(item.get("amount"))
    status = _text(item.get("status"))
    fields = [name]
    if amount:
        fields.append(f"金额 {amount}")
    if status:
        fields.append(f"状态 {status}")
    return ", ".join(fields)


def _payment_plan_line(item: JsonObject) -> str:
    name = _text(item.get("stage_name")) or "未命名回款"
    amount = _text(item.get("planned_amount"))
    due_date = _text(item.get("due_date"))
    status = _text(item.get("status"))
    fields = [name]
    if amount:
        fields.append(f"计划 {amount}")
    if due_date:
        fields.append(f"到期 {due_date}")
    if status:
        fields.append(f"状态 {status}")
    return ", ".join(fields)


def _activity_line(item: JsonObject) -> str:
    occurred_at = _text(item.get("occurred_at"))
    content = _text(item.get("content")) or _text(item.get("title"))
    if occurred_at and content:
        return f"{occurred_at} {content}"
    return content or occurred_at or "有一条跟进记录"


def _memory_line(item: JsonObject) -> str:
    value = item.get("value")
    if isinstance(value, dict):
        summary = value.get("summary")
        if isinstance(summary, str):
            return summary.strip()
        return json.dumps(value, ensure_ascii=False, default=str)
    return _text(value)


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


customer_context_answer_service = CustomerContextAnswerService()
