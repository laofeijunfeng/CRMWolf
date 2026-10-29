# ruff: noqa: RUF001
"""Stable Root model failure codes and the only user-facing copy for them."""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class AssistantFailureCode(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ROOT_RETRYABLE_FAILURE_CODES = frozenset(
    {
        AssistantFailureCode.UPSTREAM_UNAVAILABLE,
        AssistantFailureCode.UPSTREAM_TIMEOUT,
        AssistantFailureCode.MODEL_OUTPUT_INVALID,
    }
)


class RootFailurePresentation(NamedTuple):
    title: str
    message: str


_PRESENTATIONS: dict[AssistantFailureCode, RootFailurePresentation] = {
    AssistantFailureCode.CONFIGURATION_ERROR: RootFailurePresentation(
        "模型配置不可用",
        "模型配置暂不可用，本次没有写入客户活动，请联系管理员。",
    ),
    AssistantFailureCode.UPSTREAM_UNAVAILABLE: RootFailurePresentation(
        "模型服务不可达",
        "模型服务暂时不可达，本次没有写入客户活动。",
    ),
    AssistantFailureCode.UPSTREAM_TIMEOUT: RootFailurePresentation(
        "模型服务响应超时",
        "模型服务响应超时，本次没有写入客户活动。",
    ),
    AssistantFailureCode.MODEL_OUTPUT_INVALID: RootFailurePresentation(
        "模型返回格式异常",
        "模型返回结果格式异常，本次没有写入客户活动。",
    ),
    AssistantFailureCode.INTERNAL_ERROR: RootFailurePresentation(
        "处理失败",
        "处理失败，本次没有写入客户活动，请联系管理员。",
    ),
}


def is_root_failure_code(value: object) -> bool:
    return isinstance(value, str) and value in AssistantFailureCode.__members__.values()


def root_failure_code(value: object) -> AssistantFailureCode:
    if isinstance(value, AssistantFailureCode):
        return value
    if is_root_failure_code(value):
        return AssistantFailureCode(str(value))
    return AssistantFailureCode.INTERNAL_ERROR


def root_failure_presentation(code: AssistantFailureCode) -> RootFailurePresentation:
    return _PRESENTATIONS[code]


def root_failure_retryable(code: AssistantFailureCode) -> bool:
    return code in ROOT_RETRYABLE_FAILURE_CODES
