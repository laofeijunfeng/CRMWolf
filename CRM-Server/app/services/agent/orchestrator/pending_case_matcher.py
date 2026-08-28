"""Explicit pending confirmation Case matching for the Root Orchestrator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.orchestrator.contracts import PendingCaseContext

_PENDING_ACTION_REFERENCE = re.compile(
    r"(?:完成|标记完成|确认完成|处理|延期|推迟|保留|取消|忽略|关闭|恢复)"
    r".{0,12}(?:待办|确认事项|确认卡片)"
    r"|(?:待办|确认事项|确认卡片).{0,12}"
    r"(?:完成|标记完成|确认完成|处理|延期|推迟|保留|取消|忽略|关闭|恢复)"
)

_CASE_ID_PATTERN = re.compile(r"fuc_[0-9a-f]{32}", re.IGNORECASE)
_GENERIC_PENDING_REFERENCE = re.compile(
    r"(?:完成|标记完成|确认完成|处理|延期|推迟|保留|取消|忽略|关闭|恢复)"
    r".{0,12}(?:上面|上一个|之前|历史)的?(?:待办|跟进任务|任务|确认事项|确认卡片)"
    r"|(?:上面|上一个|之前|历史)的?(?:待办|跟进任务|任务|确认事项|确认卡片)"
    r".{0,12}(?:完成|标记完成|确认完成|处理|延期|推迟|保留|取消|忽略|关闭|恢复)"
)


def _normalize(value: str) -> str:
    # This is a conservative candidate scorer, not a general Chinese tokenizer.
    normalized = re.sub(r"[\W_]", "", value, flags=re.UNICODE).lower()
    for glue in ("的", "那个", "这", "该", "当前", "上面", "之前", "历史"):
        normalized = normalized.replace(glue, "")
    return normalized


def is_explicit_pending_case_reference(text: str) -> bool:
    """Require both a Case noun and an action/reference marker.

    A normal activity such as "今天联系了凡亚信息" must not enter the pending
    Case flow merely because pending Cases exist in the same session.
    """

    normalized = text.strip()
    if not normalized:
        return False
    if _CASE_ID_PATTERN.search(normalized) is not None:
        return True
    return (
        _PENDING_ACTION_REFERENCE.search(normalized) is not None
        or _GENERIC_PENDING_REFERENCE.search(normalized) is not None
    )


@dataclass(frozen=True)
class PendingCaseMatch:
    status: str
    case: PendingCaseContext | None = None
    candidates: tuple[PendingCaseContext, ...] = ()
    reference: str | None = None


def match_pending_case(text: str, cases: list[PendingCaseContext]) -> PendingCaseMatch:
    """Match only an explicit user reference against server-provided candidates."""

    if not is_explicit_pending_case_reference(text):
        return PendingCaseMatch(status="NONE")

    normalized_text = _normalize(text)
    explicit_id = _CASE_ID_PATTERN.search(text)
    if explicit_id is not None:
        case_id = explicit_id.group(0).lower()
        exact = tuple(case for case in cases if case.case_public_id.lower() == case_id)
        if len(exact) == 1:
            return PendingCaseMatch(status="MATCHED", case=exact[0], reference=explicit_id.group(0))
        return PendingCaseMatch(status="AMBIGUOUS" if len(exact) > 1 else "NOT_FOUND", reference=explicit_id.group(0))

    if _GENERIC_PENDING_REFERENCE.search(text):
        if len(cases) == 1:
            return PendingCaseMatch(status="MATCHED", case=cases[0], reference=text.strip()[:255])
        if len(cases) > 1:
            return PendingCaseMatch(
                status="AMBIGUOUS",
                candidates=tuple(cases),
                reference=text.strip()[:255],
            )
        return PendingCaseMatch(status="NOT_FOUND", reference=text.strip()[:255])

    scored: list[tuple[int, PendingCaseContext]] = []
    for case in cases:
        customer = _normalize(case.customer_name)
        aliases = [_normalize(alias) for alias in case.customer_aliases]
        title = _normalize(case.task_title)
        description = _normalize(case.task_description or "")
        score = 0
        if customer and customer in normalized_text:
            score += 100
        if any(alias and alias in normalized_text for alias in aliases):
            score = max(score, 100)
        if title and title in normalized_text:
            score += 50
        if description and len(description) >= 8 and description in normalized_text:
            score += 25
        if score:
            scored.append((score, case))

    if not scored:
        return PendingCaseMatch(status="NOT_FOUND", reference=text.strip()[:255])
    highest = max(score for score, _ in scored)
    matches = tuple(case for score, case in scored if score == highest)
    if len(matches) == 1:
        return PendingCaseMatch(status="MATCHED", case=matches[0], reference=text.strip()[:255])
    return PendingCaseMatch(status="AMBIGUOUS", candidates=matches, reference=text.strip()[:255])
