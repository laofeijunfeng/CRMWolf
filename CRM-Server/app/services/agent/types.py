"""Shared serializable type aliases for CRM Agent runtime contracts."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import TypeAlias


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]
JSONList: TypeAlias = list[JSONValue]
AgentRuntimeEventSink: TypeAlias = Callable[[JSONDict], Awaitable[None]]


def coerce_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [coerce_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return coerce_json_dict(value)
    return str(value)


def coerce_json_dict(value: object) -> JSONDict:
    if not isinstance(value, Mapping):
        return {}
    result: JSONDict = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = coerce_json_value(item)
    return result
