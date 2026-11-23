"""Centralized user-facing copy for CRM Agent responses."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def _clean_items(items: Iterable[object]) -> list[str]:
    return [str(item).strip() for item in items if str(item).strip()]


def generic_completed() -> str:
    return "好嘞\uff0c已处理完成。"


def customer_context_answer_unavailable() -> str:
    return "客户资料不足\uff0c暂时无法整理回答。"


def follow_up_created() -> str:
    return "好嘞\uff0c跟进已记录。"


def follow_up_created_with_next(next_prompt: str | None = None) -> str:
    if not next_prompt:
        return follow_up_created()
    return f"{follow_up_created()}{next_prompt.strip()}"


def customer_activity_created() -> str:
    return "好嘞\uff0c客户活动已记录。"


def customer_activity_created_with_next(next_prompt: str | None = None) -> str:
    if not next_prompt:
        return customer_activity_created()
    return f"{customer_activity_created()}{next_prompt.strip()}"


def no_pending_confirmation() -> str:
    return "好嘞\uff0c目前没有等待确认的操作。"


def service_error(message: str | None = None) -> str:
    """Return safe copy for an unexpected Agent exception.

    ``message`` is retained for call-site compatibility, but exception text
    can contain provider, SQL, or Python implementation details.  Those belong
    in server logs, never in the persisted Agent message shown to users.
    """
    del message
    return "这次没处理成，请稍后再试。"  # noqa: RUF001


def im_identity_missing(provider_label: str = "IM") -> str:
    return f"暂时没识别到你的{provider_label}身份\uff0c先处理不了。"


def im_account_not_bound(provider_label: str = "IM") -> str:
    return f"你还没绑定 CRM 账号\uff0c先去个人设置里绑定{provider_label}账号。"


def im_text_missing() -> str:
    return "我没识别到可处理的文本内容。"


def im_text_only() -> str:
    return "目前先支持文本消息\uff0c把要处理的内容用文字发给我。"


def confirm_prompt(action_label: str | None = None) -> str:
    if action_label:
        return f"确认后\uff0c我会继续执行「{action_label}」。"
    return "确认后\uff0c我会继续执行。"


def choose_customer() -> str:
    return "找到几个可能的客户\uff0c选一个我就继续。"


def choose_business_object() -> str:
    return "找到几个可用的业务对象\uff0c选一个我就继续。"


def fill_fields(kind_label: str, fields: Iterable[object] = ()) -> str:
    field_names = _clean_items(fields)
    if field_names:
        return f"还差{kind_label}的这些信息\uff1a{'、'.join(field_names)}。"
    return f"还差一点{kind_label}信息\uff0c补充后我继续。"


def opportunity_suggestion_needs_fields(title: str | None, fields: Iterable[object] = ()) -> str:
    action = f"「{title}」" if title else "一个新商机"
    field_names = _clean_items(fields)
    if field_names:
        return f"这条还像{action}\uff0c还差\uff1a{'、'.join(field_names)}。"
    return f"这条还像{action}\uff0c补一下商机信息我就继续。"


def opportunity_suggestion_needs_procurement(title: str | None) -> str:
    action = f"「{title}」" if title else "一个新商机"
    return f"这条还像{action}\uff0c还差采购方式。"


def opportunity_ready_to_confirm(customer_name: str | None = None) -> str:
    if customer_name:
        return f"商机信息齐了。要为「{customer_name}」创建商机吗\uff1f"
    return "商机信息齐了。要创建商机吗\uff1f"


def follow_up_quality_prompt() -> str:
    return "这条跟进还差一点关键信息\uff0c补充后我来记录。"


def pending_interruption_prompt() -> str:
    return "好嘞\uff0c这一步可以先放着。要切到新流程吗\uff1f"


def task_put_aside() -> str:
    return "好嘞\uff0c这一步先放着。"


def confirmation_unknown() -> str:
    return "你是要确认执行\uff0c还是先取消\uff1f也可以直接说新的需求。"


def pending_switch_notice(customer_name: str | None = None) -> str:
    if customer_name:
        return f"这条是在说「{customer_name}」。我先把刚才那一步放着\uff0c切过来处理。"
    return "这条像是新的流程。我先把刚才那一步放着\uff0c切过来处理。"


def pending_interruption_clarification() -> str:
    return "这句像是新流程\uff0c也可能是在补刚才的任务。你要切过去\uff0c还是继续刚才那步\uff1f"


def turn_relation_clarification(summaries: Iterable[object] = ()) -> str:
    items = _clean_items(summaries)[:2]
    if len(items) == 1:
        return f"这句是继续处理「{items[0]}」\uff0c还是作为新流程处理\uff1f"
    if len(items) >= 2:
        return f"这句是继续处理「{items[0]}」还是「{items[1]}」\uff0c还是作为新流程处理\uff1f"
    return "这句是在继续处理刚才放下的任务\uff0c还是作为新流程处理\uff1f"
