"""Deterministic references into an authoritative query result set."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.orchestrator.contracts import ResultSetContext
    from app.services.agent.query import EntityRef

_ORDINAL_PATTERN = re.compile(r"第(?P<ordinal>[零〇一二两三四五六七八九十百\d]+)(?:个|位|条|家)")
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,  # noqa: RUF001
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


class ResultSetReferenceError(ValueError):
    """An explicit result-set reference cannot be resolved safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_result_set_entity(
    *,
    text: str,
    result_set: ResultSetContext,
) -> EntityRef | None:
    """Return one explicit ordinal selection; leave plural references as a result set."""

    match = _ORDINAL_PATTERN.search(text)
    if match is None:
        return None
    position = _ordinal_to_int(match.group("ordinal"))
    if position is None or position < 1:
        raise ResultSetReferenceError(
            "RESULT_SET_REFERENCE_AMBIGUOUS",
            "请使用明确的正序号选择查询结果。",
        )
    if position > len(result_set.ordered_entity_refs):
        raise ResultSetReferenceError(
            "RESULT_SET_REFERENCE_OUT_OF_RANGE",
            "所选序号超出当前查询结果范围。",
        )
    return result_set.ordered_entity_refs[position - 1]


def _ordinal_to_int(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value]
    if value == "十":
        return 10
    if "十" in value:
        tens, ones = value.split("十", maxsplit=1)
        tens_value = 1 if not tens else _CHINESE_DIGITS.get(tens)
        ones_value = 0 if not ones else _CHINESE_DIGITS.get(ones)
        if tens_value is None or ones_value is None:
            return None
        return tens_value * 10 + ones_value
    return None
