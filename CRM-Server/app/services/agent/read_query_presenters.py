"""Present read-tool results as user-facing Agent replies."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.agent.types import JSONDict, coerce_json_dict


def read_tool_error_response(tool_name: str | None, result: JSONDict) -> str:
    message = _display_text(result.get("error_message")) or "读取失败"
    if tool_name == "summarize_completed_work":
        return f"工作总结暂时生成失败，原因：{_truncate_sentence(message, 80)}。"
    if tool_name == "list_follow_up_tasks":
        return f"任务查询暂时失败，原因：{_truncate_sentence(message, 80)}。"
    return f"查询暂时失败，原因：{_truncate_sentence(message, 80)}。"


def work_summary_tool_response(data: object) -> str:
    payload = coerce_json_dict(data)
    narrative = coerce_json_dict(payload.get("narrative"))
    answer = _display_text(narrative.get("answer"))
    if answer:
        return answer
    coverage = coerce_json_dict(payload.get("coverage"))
    if not coverage:
        coverage = coerce_json_dict(narrative.get("coverage"))
    total = _int_json_value(coverage.get("available_total"))
    if total <= 0:
        return "当前时间范围内没有查询到可确认的工作事实。"
    return f"已查询到 {total} 条可确认工作事实，但暂时没有生成可展示的总结。"


def follow_up_tasks_tool_response(data: object, payload: JSONDict) -> str:
    result = coerce_json_dict(data)
    items = _json_dict_list(result.get("items"))
    if not items:
        return _empty_follow_up_tasks_response(payload)

    total = _int_json_value(result.get("total")) or len(items)
    title = _follow_up_tasks_response_title(payload, total, items)
    lines = [title, ""]
    for item in items[:10]:
        lines.append(_follow_up_task_line(item))
    if total > len(items[:10]):
        lines.append(f"- 还有 {total - len(items[:10])} 条未展示，可继续缩小时间或语义条件查询。")
    return "\n".join(lines)


def _follow_up_task_line(item: JSONDict) -> str:
    customer = coerce_json_dict(item.get("customer"))
    customer_name = (
        _display_text(customer.get("name"))
        or _display_text(customer.get("account_name"))
        or "未关联客户"
    )
    task_title = _display_text(item.get("title")) or _display_text(item.get("description")) or "未命名任务"
    due_at = _format_business_datetime(item.get("due_at"))
    overdue_days = _int_json_value(item.get("overdue_days"))
    suffix_parts = []
    if due_at:
        suffix_parts.append(f"到期：{due_at}")
    if overdue_days > 0:
        suffix_parts.append(f"逾期 {overdue_days} 天")
    suffix = f"（{'；'.join(suffix_parts)}）" if suffix_parts else ""
    return f"- **{customer_name}**：{task_title}{suffix}"


def _follow_up_tasks_response_title(payload: JSONDict, total: int, items: list[JSONDict]) -> str:
    due_window = _display_text(payload.get("due_window"))
    status = _display_text(payload.get("status")) or "open"
    window_label = {
        "today": "今天",
        "this_week": "本周",
        "next_week": "下周",
        "overdue": "逾期",
    }.get(due_window, "当前")
    status_label = "已完成" if status == "completed" else "待跟进"
    overdue_count = sum(1 for item in items if _int_json_value(item.get("overdue_days")) > 0)
    summary = f"{window_label}{status_label}任务，共 {total} 条"
    if status != "completed" and overdue_count > 0:
        summary += f"，其中 {overdue_count} 条已逾期"
    return f"### {summary}。"


def _empty_follow_up_tasks_response(payload: JSONDict) -> str:
    due_window = _display_text(payload.get("due_window"))
    status = _display_text(payload.get("status")) or "open"
    window_label = {
        "today": "今天",
        "this_week": "本周",
        "next_week": "下周",
        "overdue": "逾期",
    }.get(due_window, "当前")
    status_label = "已完成任务" if status == "completed" else "待跟进任务"
    return f"{window_label}没有查询到{status_label}。"


def _format_business_datetime(value: object) -> str:
    text = _display_text(value)
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
        return f"{parsed.year}年{parsed.month}月{parsed.day}日"
    return f"{parsed.year}年{parsed.month}月{parsed.day}日 {parsed.hour:02d}:{parsed.minute:02d}"


def _display_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _json_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [coerce_json_dict(item) for item in value if isinstance(item, dict)]


def _int_json_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _truncate_sentence(text: str, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."
