"""Plan CRM read-query tool calls for the Agent graph."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.services.agent.schemas import AgentSemanticParseResult
from app.services.agent.types import JSONDict
from app.services.follow_up_task_query_intent import extract_follow_up_task_semantic_query_text


@dataclass(frozen=True)
class AgentReadQueryPlan:
    query_type: str
    tool_name: str
    payload: JSONDict
    requires_customer_resolution: bool
    trace_label: str


_WORK_SUMMARY_PHRASES = (
    "完成了什么",
    "完成什么",
    "做了什么",
    "工作总结",
    "周报",
    "月报",
    "本周总结",
    "这周总结",
    "本月总结",
    "这个月总结",
)
_WORK_SUMMARY_TASK_EXCLUSION_PHRASES = (
    "任务",
    "待办",
    "安排",
    "要跟进",
    "需要跟进",
    "客户要跟进",
    "要做",
    "未完成",
    "没完成",
    "逾期",
    "延期",
)
_FOLLOW_UP_TASK_QUERY_PHRASES = (
    "任务",
    "待办",
    "安排",
    "要跟进",
    "需要跟进",
    "客户要跟进",
    "还有哪些客户",
    "未完成",
    "没完成",
    "逾期",
    "延期",
    "过期",
)


class AgentReadQueryPlanner:
    """Convert a normalized CRM read intent into one deterministic read tool call."""

    def plan(
        self,
        *,
        semantic_result: AgentSemanticParseResult | None,
        content: str,
        parsed: Mapping[str, object],
        selected_customer: Mapping[str, object] | None = None,
    ) -> AgentReadQueryPlan | None:
        if not semantic_result or semantic_result.intent != "CRM_READ_QUERY":
            return None
        text = "".join(str(content or "").split())
        if not text:
            return None

        customer_id = _selected_customer_id(selected_customer)
        if _has_explicit_customer_scope(parsed, semantic_result=semantic_result) and not customer_id:
            return AgentReadQueryPlan(
                query_type="CUSTOMER_SCOPED_READ",
                tool_name="",
                payload={},
                requires_customer_resolution=True,
                trace_label="客户范围查询",
            )

        query_type = semantic_result.read_query.type
        if query_type == "UNKNOWN_READ":
            query_type = _infer_query_type(text)
        if query_type == "WORK_SUMMARY" and not _is_work_summary_query(text):
            query_type = _infer_query_type(text)
        if query_type == "FOLLOW_UP_TASKS":
            return self._follow_up_tasks_plan(
                content=content,
                text=text,
                parsed=parsed,
                semantic_result=semantic_result,
                customer_id=customer_id,
            )
        if query_type == "WORK_SUMMARY":
            return self._work_summary_plan(
                content=content,
                text=text,
                semantic_result=semantic_result,
                customer_id=customer_id,
            )
        return None

    def _follow_up_tasks_plan(
        self,
        *,
        content: str,
        text: str,
        parsed: Mapping[str, object],
        semantic_result: AgentSemanticParseResult,
        customer_id: str | None,
    ) -> AgentReadQueryPlan:
        read_query = semantic_result.read_query
        payload: JSONDict = {
            "status": read_query.status or _follow_up_task_status(text),
            "owner_scope": read_query.owner_scope or "mine",
            "retrieval_mode": "structured",
            "limit": 50,
        }
        due_window = read_query.due_window or _follow_up_task_due_window(text)
        if due_window:
            payload["due_window"] = due_window
        if customer_id:
            payload["customer_id"] = customer_id
        query_text = _follow_up_task_semantic_query_text(
            read_query.query_text,
            content=content,
            customer_name=_query_customer_name(parsed, semantic_result=semantic_result),
        )
        if query_text:
            payload["retrieval_mode"] = "semantic_filter"
            payload["query_text"] = query_text
        return AgentReadQueryPlan(
            query_type="FOLLOW_UP_TASKS",
            tool_name="list_follow_up_tasks",
            payload=payload,
            requires_customer_resolution=False,
            trace_label="任务查询",
        )

    def _work_summary_plan(
        self,
        *,
        content: str,
        text: str,
        semantic_result: AgentSemanticParseResult,
        customer_id: str | None,
    ) -> AgentReadQueryPlan:
        payload: JSONDict = {
            "window": semantic_result.read_query.work_window or _work_summary_window(text),
            "question": str(content or "").strip(),
            "limit": 50,
        }
        if customer_id:
            payload["customer_id"] = customer_id
        return AgentReadQueryPlan(
            query_type="WORK_SUMMARY",
            tool_name="summarize_completed_work",
            payload=payload,
            requires_customer_resolution=False,
            trace_label="工作总结",
        )


def _infer_query_type(text: str) -> str:
    if _is_work_summary_query(text):
        return "WORK_SUMMARY"
    if _is_follow_up_task_query(text):
        return "FOLLOW_UP_TASKS"
    return "UNKNOWN_READ"


def _selected_customer_id(selected_customer: Mapping[str, object] | None) -> str | None:
    if not isinstance(selected_customer, Mapping):
        return None
    customer_id = selected_customer.get("id")
    if customer_id is None:
        return None
    value = str(customer_id).strip()
    return value or None


def _has_explicit_customer_scope(
    parsed: Mapping[str, object],
    *,
    semantic_result: AgentSemanticParseResult,
) -> bool:
    customer_name = parsed.get("customer_name") or semantic_result.read_query.customer_name_text
    if not isinstance(customer_name, str):
        return False
    stripped = customer_name.strip()
    if _looks_like_query_fragment_customer_name(stripped):
        return False
    return bool(stripped) and stripped not in {"客户", "哪些客户", "所有客户"}


def _query_customer_name(
    parsed: Mapping[str, object],
    *,
    semantic_result: AgentSemanticParseResult,
) -> str | None:
    customer_name = parsed.get("customer_name") or semantic_result.read_query.customer_name_text
    if not isinstance(customer_name, str):
        return None
    stripped = customer_name.strip()
    return stripped or None


def _looks_like_query_fragment_customer_name(value: str) -> bool:
    if not value:
        return False
    return (
        "哪些客户" in value
        or value.endswith("客户要")
        or any(value.startswith(prefix) for prefix in ("今天", "今日", "本周", "这周", "下周"))
        and any(marker in value for marker in ("任务", "待办", "安排", "客户"))
    )


def _is_work_summary_query(text: str) -> bool:
    if not any(phrase in text for phrase in _WORK_SUMMARY_PHRASES):
        return False
    return not any(phrase in text for phrase in _WORK_SUMMARY_TASK_EXCLUSION_PHRASES)


def _is_follow_up_task_query(text: str) -> bool:
    return any(phrase in text for phrase in _FOLLOW_UP_TASK_QUERY_PHRASES)


def _work_summary_window(text: str) -> str:
    if "今天" in text or "今日" in text:
        return "today"
    if "上周" in text:
        return "last_week"
    if "本月" in text or "这个月" in text or "月报" in text:
        return "this_month"
    return "this_week"


def _follow_up_task_due_window(text: str) -> str | None:
    if "逾期" in text or "延期" in text or "过期" in text:
        return "overdue"
    if "今天" in text or "今日" in text:
        return "today"
    if "下周" in text:
        return "next_week"
    if "本周" in text or "这周" in text:
        return "this_week"
    return None


def _follow_up_task_status(text: str) -> str:
    if ("已完成" in text or "完成了" in text) and ("任务" in text or "待办" in text):
        return "completed"
    return "open"


def _follow_up_task_semantic_query_text(
    llm_query_text: object,
    *,
    content: str,
    customer_name: str | None = None,
) -> str | None:
    llm_text = extract_follow_up_task_semantic_query_text(llm_query_text, customer_name=customer_name)
    if llm_text:
        return llm_text
    return extract_follow_up_task_semantic_query_text(content, customer_name=customer_name)


agent_read_query_planner = AgentReadQueryPlanner()
