"""LLM-backed narrative generation for structured work summary facts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.crud.ai_config import ai_config_crud
from app.services.agent.langchain_runtime import AgentLangChainRuntime, AgentLangChainStructuredOutputError
from app.services.agent.schemas import WorkSummaryNarrativeItem, WorkSummaryNarrativeResult
from app.services.work_summary_grounding import CitationResolver
from app.services.work_summary_models import DEFAULT_WORK_SUMMARY_SYNTHESIS_CHUNK_BUDGET

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_SYNTHESIS_HIGHLIGHTS_PER_CHUNK = 2
_SYNTHESIS_CUSTOMERS_PER_CHUNK = 1
_SYNTHESIS_FACT_IDS_PER_ITEM = 1
_SYNTHESIS_TITLE_CHARS = 64
_SYNTHESIS_SUMMARY_CHARS = 140
_SYNTHESIS_QUESTION_CHARS = 1000


class AIConfigLike(Protocol):
    api_host: str
    model_name: str
    temperature: float | None


class AIConfigCrudProtocol(Protocol):
    def get_config(self, db: Session, team_id: int) -> AIConfigLike | None: ...

    def get_decrypted_api_key(self, db: Session, team_id: int) -> str | None: ...


@dataclass(frozen=True)
class WorkSummaryNarrativeEnvelope:
    result: WorkSummaryNarrativeResult
    summary_source: str
    model: str | None = None
    fallback_reason: str | None = None
    fallback_error: str | None = None


class WorkSummaryNarrativeService:
    """Generate grounded summaries from structured MySQL-backed work facts."""

    def __init__(
        self,
        *,
        runtime: AgentLangChainRuntime | None = None,
        config_crud: AIConfigCrudProtocol = ai_config_crud,
        citation_resolver: CitationResolver | None = None,
    ) -> None:
        self.runtime = runtime or AgentLangChainRuntime()
        self.config_crud = config_crud
        self.citation_resolver = citation_resolver or CitationResolver()

    async def summarize_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        question: str,
        work_facts: dict[str, Any],
    ) -> WorkSummaryNarrativeEnvelope:
        fallback = self.fallback_summary(question=question, work_facts=work_facts)
        if not work_facts.get("items"):
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                fallback_reason="empty_facts",
            )

        config = self.config_crud.get_config(db, team_id)
        if not config:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                fallback_reason="ai_config_missing",
            )

        api_key = self.config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                model=config.model_name,
                fallback_reason="ai_api_key_missing",
            )

        fallback_error: str | None = None
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                temperature=min(float(config.temperature or 0.1), 0.2),
                system_prompt=_WORK_SUMMARY_SYSTEM_PROMPT,
                user_prompt=self._build_user_prompt(question=question, work_facts=work_facts),
                response_model=WorkSummaryNarrativeResult,
                structured_output_strategy="tool",
                error_prefix="工作总结 structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            result = None
            fallback_error = str(exc)
        except RuntimeError as exc:
            result = None
            fallback_error = f"{exc.__class__.__name__}: {exc!s}"

        if result is None:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                model=config.model_name,
                fallback_reason="llm_summary_failed",
                fallback_error=fallback_error,
            )

        grounded = self._ground_result(result, work_facts)
        if work_facts.get("items") and not grounded.highlights and not grounded.customer_summaries:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                model=config.model_name,
                fallback_reason="llm_summary_ungrounded",
            )
        return WorkSummaryNarrativeEnvelope(
            result=grounded.model_copy(update={"narrative_mode": "langchain_structured_output"}),
            summary_source="langchain_structured_output",
            model=config.model_name,
        )

    async def synthesize_chunks_with_metadata(
        self,
        db: Session,
        *,
        team_id: int,
        question: str,
        chunk_results: list[WorkSummaryNarrativeResult],
        work_facts: dict[str, Any],
    ) -> WorkSummaryNarrativeEnvelope:
        """Reduce bounded chunk narratives into one grounded final narrative."""
        fallback = self._fallback_from_chunk_results(
            question=question,
            chunk_results=chunk_results,
            work_facts=work_facts,
        )
        if not work_facts.get("items"):
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                fallback_reason="empty_facts",
            )

        config = self.config_crud.get_config(db, team_id)
        if not config:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                fallback_reason="ai_config_missing",
            )
        api_key = self.config_crud.get_decrypted_api_key(db, team_id)
        if not api_key:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                model=config.model_name,
                fallback_reason="ai_api_key_missing",
            )

        fallback_error: str | None = None
        try:
            result = await self.runtime.ainvoke_structured(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                temperature=min(float(config.temperature or 0.1), 0.2),
                system_prompt=_WORK_SUMMARY_SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=self._build_synthesis_prompt(
                    question=question,
                    chunk_results=chunk_results,
                    work_facts=work_facts,
                ),
                response_model=WorkSummaryNarrativeResult,
                structured_output_strategy="tool",
                error_prefix="工作总结 synthesis structured output",
            )
        except AgentLangChainStructuredOutputError as exc:
            result = None
            fallback_error = str(exc)
        except RuntimeError as exc:
            result = None
            fallback_error = f"{exc.__class__.__name__}: {exc!s}"

        if result is None:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                model=config.model_name,
                fallback_reason="llm_synthesis_failed",
                fallback_error=fallback_error,
            )
        grounded = self._ground_result(result, work_facts)
        if work_facts.get("items") and not grounded.highlights and not grounded.customer_summaries:
            return WorkSummaryNarrativeEnvelope(
                result=fallback,
                summary_source="deterministic_work_summary_fallback",
                model=config.model_name,
                fallback_reason="llm_synthesis_ungrounded",
            )
        return WorkSummaryNarrativeEnvelope(
            result=WorkSummaryNarrativeResult.model_validate({
                **grounded.model_dump(),
                "narrative_mode": "langchain_structured_output",
            }),
            summary_source="langchain_structured_output",
            model=config.model_name,
        )

    def fallback_summary(self, *, question: str, work_facts: dict[str, Any]) -> WorkSummaryNarrativeResult:
        items = _fact_items(work_facts)
        if not items:
            return WorkSummaryNarrativeResult(
                answer="当前时间范围内没有查询到可确认的工作事实。",
                highlights=[],
                customer_summaries=[],
                confidence=0.6,
                narrative_mode="insufficient",
                missing_context=["当前时间范围内的任务、客户活动或业务推进事实"],
                citations=[],
            )

        highlights = self._fact_type_summary_items(items)
        customer_summaries = self._customer_summary_items(items)
        resolved = self.citation_resolver.resolve(
            highlights=highlights,
            customer_summaries=customer_summaries,
            facts=items,
        )
        lines = [
            f"### 工作总结\n围绕“{question or '当前工作'}”，系统查询到 "
            f"{work_facts.get('available_total', len(items))} 条可确认事实。"
        ]
        for item in resolved.highlights[:8]:
            lines.append(f"- **{item.title}**：{item.summary}")
        return WorkSummaryNarrativeResult(
            answer="\n".join(lines),
            highlights=resolved.highlights,
            customer_summaries=resolved.customer_summaries,
            confidence=0.78 if not work_facts.get("truncated") else 0.64,
            narrative_mode="fallback",
            missing_context=["后续分页事实"] if work_facts.get("truncated") else [],
            citations=[citation.model_dump() for citation in resolved.citations],
        )

    def _fallback_from_chunk_results(
        self,
        *,
        question: str,
        chunk_results: list[WorkSummaryNarrativeResult],
        work_facts: dict[str, Any],
    ) -> WorkSummaryNarrativeResult:
        if not chunk_results:
            return self.fallback_summary(question=question, work_facts=work_facts)
        facts = _fact_items(work_facts)
        highlights = self._fact_type_summary_items(facts)
        customer_summaries = self._customer_summary_items(facts)
        resolved = self.citation_resolver.resolve(
            highlights=highlights,
            customer_summaries=customer_summaries,
            facts=facts,
        )
        lines = [
            f"### 工作总结\n围绕“{question or '当前工作'}”，系统已汇总 "
            f"{len(facts)} 条可确认事实。"
        ]
        for item in resolved.highlights[:8]:
            lines.append(f"- **{item.title}**：{item.summary}")
        confidences = [result.confidence for result in chunk_results]
        return WorkSummaryNarrativeResult(
            answer="\n".join(lines),
            highlights=resolved.highlights,
            customer_summaries=resolved.customer_summaries,
            confidence=min(confidences) if confidences else 0.6,
            narrative_mode="fallback",
            missing_context=["未覆盖的后续工作事实"] if work_facts.get("truncated") else [],
            citations=[citation.model_dump() for citation in resolved.citations],
        )

    def _ground_result(
        self,
        result: WorkSummaryNarrativeResult,
        work_facts: dict[str, Any],
    ) -> WorkSummaryNarrativeResult:
        resolved = self.citation_resolver.resolve(
            highlights=list(result.highlights),
            customer_summaries=list(result.customer_summaries),
            facts=_fact_items(work_facts),
        )
        missing_context = list(result.missing_context or [])
        if work_facts.get("truncated"):
            missing_context = _unique_texts([*missing_context, "后续分页事实"])
        return WorkSummaryNarrativeResult.model_validate({
            **result.model_dump(),
            "highlights": [item.model_dump() for item in resolved.highlights],
            "customer_summaries": [item.model_dump() for item in resolved.customer_summaries],
            "citations": [citation.model_dump() for citation in resolved.citations],
            "missing_context": missing_context,
            "confidence": min(result.confidence, 0.72) if work_facts.get("truncated") else result.confidence,
        })

    @staticmethod
    def _customer_summary_items(items: list[dict[str, Any]]) -> list[WorkSummaryNarrativeItem]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            customer = item.get("customer") if isinstance(item.get("customer"), dict) else {}
            customer_name = str(customer.get("name") or customer.get("account_name") or "未关联客户")
            grouped.setdefault(customer_name, []).append(item)
        summaries: list[WorkSummaryNarrativeItem] = []
        ordered_groups = sorted(grouped.items(), key=lambda pair: -len(pair[1]))
        for customer_name, customer_items in ordered_groups[:12]:
            fact_ids = [str(item.get("fact_id")) for item in customer_items[:2] if item.get("fact_id")]
            if not fact_ids:
                continue
            type_counts = _fact_type_counts(customer_items)
            type_summary = "、".join(
                f"{_fact_type_label_for_name(fact_type)} {count} 条"
                for fact_type, count in type_counts.items()
            )
            summaries.append(
                WorkSummaryNarrativeItem(
                    category="business_progress",
                    title=customer_name,
                    summary=f"{customer_name} 共 {len(customer_items)} 条工作事实，包括 {type_summary}。",
                    fact_ids=fact_ids,
                )
            )
        return summaries

    @staticmethod
    def _fact_type_summary_items(items: list[dict[str, Any]]) -> list[WorkSummaryNarrativeItem]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            fact_type = str(item.get("fact_type") or "unknown")
            grouped.setdefault(fact_type, []).append(item)
        ordered_groups = sorted(grouped.items(), key=lambda pair: -len(pair[1]))
        summaries: list[WorkSummaryNarrativeItem] = []
        for fact_type, fact_items in ordered_groups[:12]:
            representative_ids = [
                str(item.get("fact_id"))
                for item in fact_items[:2]
                if item.get("fact_id")
            ]
            if not representative_ids:
                continue
            label = _fact_type_label_for_name(fact_type)
            examples = "、".join(
                str(item.get("title") or label)
                for item in fact_items[:3]
            )
            summaries.append(
                WorkSummaryNarrativeItem(
                    category=_fact_category(fact_items[0]),
                    title=label,
                    summary=f"{label} {len(fact_items)} 条，代表事项包括 {examples}。",
                    fact_ids=representative_ids,
                )
            )
        return summaries

    @staticmethod
    def _build_user_prompt(*, question: str, work_facts: dict[str, Any]) -> str:
        prompt_payload = {
            "question": question,
            "filters": work_facts.get("filters"),
            "pagination": work_facts.get("pagination"),
            "source_counts": work_facts.get("source_counts"),
            "source_total_counts": work_facts.get("source_total_counts"),
            "items": work_facts.get("items"),
        }
        return json.dumps(prompt_payload, ensure_ascii=False, default=str)

    @staticmethod
    def _build_synthesis_prompt(
        *,
        question: str,
        chunk_results: list[WorkSummaryNarrativeResult],
        work_facts: dict[str, Any],
    ) -> str:
        if len(chunk_results) > DEFAULT_WORK_SUMMARY_SYNTHESIS_CHUNK_BUDGET:
            raise ValueError(
                "work summary synthesis chunk budget exceeded: "
                f"received {len(chunk_results)}, "
                f"maximum {DEFAULT_WORK_SUMMARY_SYNTHESIS_CHUNK_BUDGET}"
            )
        bounded_chunks = chunk_results
        prompt_payload = {
            "question": _clip_text(question, _SYNTHESIS_QUESTION_CHARS),
            "coverage": {
                "available_total": work_facts.get("available_total"),
                "summarized_total": len(_fact_items(work_facts)),
                "truncated": work_facts.get("truncated"),
                "input_chunk_count": len(chunk_results),
                "included_chunk_count": len(bounded_chunks),
            },
            "chunks": [
                {
                    "highlights": [
                        _bounded_synthesis_item(item)
                        for item in result.highlights[:_SYNTHESIS_HIGHLIGHTS_PER_CHUNK]
                    ],
                    "customer_summaries": [
                        _bounded_synthesis_item(item)
                        for item in result.customer_summaries[:_SYNTHESIS_CUSTOMERS_PER_CHUNK]
                    ],
                    "confidence": result.confidence,
                }
                for result in bounded_chunks
            ],
        }
        return json.dumps(prompt_payload, ensure_ascii=False, default=str)


_WORK_SUMMARY_SYNTHESIS_SYSTEM_PROMPT = """你是 CRMWolf 的销售工作总结归并器。

输入是多个已经基于真实工作事实生成的分块总结。你必须：
1. 只使用 chunks 中出现的 fact_id，不得创造新引用。
2. 合并重复内容，形成一份完整、清晰的销售工作总结。
3. 每个输出项至少引用一个 fact_id。
4. coverage.truncated=true 时必须明确说明结果不完整。
5. 不输出数据库内部字段或技术实现细节。
"""


_WORK_SUMMARY_SYSTEM_PROMPT = """你是 CRMWolf 的销售工作总结助手。

你只能基于用户消息中 items 列出的 structured facts 生成工作总结，不能补充、猜测或使用外部知识。

必须遵守：
1. 每个 highlights 和 customer_summaries 项必须引用至少一个真实存在的 fact_id。
2. completed_follow_up_task 可以归为 completed_work。
3. customer_activity 只能归为 process_record，不能写成“任务已完成”。
4. 商机阶段、合同、回款、开票、License 等业务事件归为 business_progress。
5. 如果 pagination.truncated=true，必须在 answer 或 missing_context 中说明还需要后续分页事实，不能声称总结完整。
6. 不输出内部数据库主键、表名、source_key、source_activity_id。
"""


def _fact_items(work_facts: dict[str, Any]) -> list[dict[str, Any]]:
    items = work_facts.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _fact_category(item: dict[str, Any]) -> str:
    fact_type = str(item.get("fact_type") or "")
    if fact_type == "completed_follow_up_task":
        return "completed_work"
    if fact_type == "customer_activity":
        return "process_record"
    return "business_progress"


def _fact_type_label(item: dict[str, Any]) -> str:
    return _fact_type_label_for_name(str(item.get("fact_type") or ""))


def _fact_type_label_for_name(fact_type: str) -> str:
    labels = {
        "completed_follow_up_task": "已完成跟进任务",
        "customer_activity": "客户活动",
        "opportunity_stage_entered": "商机阶段推进",
        "contract_signed": "合同签署",
        "contract_created": "合同创建",
        "payment_recorded": "回款记录",
        "invoice_application": "开票申请",
        "license_application": "License 申请",
    }
    return labels.get(fact_type, "工作事实")


def _fact_type_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        fact_type = str(item.get("fact_type") or "unknown")
        counts[fact_type] = counts.get(fact_type, 0) + 1
    return counts


def _bounded_synthesis_item(item: WorkSummaryNarrativeItem) -> dict[str, object]:
    return {
        "category": item.category,
        "title": _clip_text(item.title, _SYNTHESIS_TITLE_CHARS),
        "summary": _clip_text(item.summary, _SYNTHESIS_SUMMARY_CHARS),
        # Fact IDs are opaque identities. Never truncate them: a shortened ID
        # cannot be resolved back to the authoritative snapshot.
        "fact_ids": list(item.fact_ids[:_SYNTHESIS_FACT_IDS_PER_ITEM]),
    }


def _clip_text(value: object, max_chars: int) -> str:
    return str(value or "")[:max_chars]


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
