"""Tests for the canonical activity-kind and legacy import boundaries."""

from app.models.lead import FollowUpMethod
from app.services.customer_activity_kinds import (
    CustomerActivityKind,
    infer_activity_kind,
    normalize_activity_kind,
)
from app.services.legacy_customer_activity_adapter import (
    activity_kind_from_legacy_lead_method,
)


def test_canonical_normalizer_does_not_translate_legacy_lead_method_values() -> None:
    """Persisted customer-activity inputs must use canonical activity_kind values."""

    assert normalize_activity_kind("PHONE_FOLLOW_UP") == CustomerActivityKind.PHONE_FOLLOW_UP
    assert normalize_activity_kind("电话") == CustomerActivityKind.OTHER_FOLLOW_UP


def test_agent_semantic_method_hint_is_still_supported_before_canonical_write() -> None:
    """Agent language parsing can resolve a user hint without making it a DB alias."""

    assert infer_activity_kind("电话", "客户确认了采购计划") == CustomerActivityKind.PHONE_FOLLOW_UP
    assert infer_activity_kind("线上会议", "讨论项目范围") == CustomerActivityKind.ONLINE_MEETING


def test_legacy_lead_method_is_converted_only_by_explicit_adapter() -> None:
    assert activity_kind_from_legacy_lead_method(FollowUpMethod.PHONE) == CustomerActivityKind.PHONE_FOLLOW_UP
    assert activity_kind_from_legacy_lead_method("线下会议") == CustomerActivityKind.OFFLINE_MEETING
    assert activity_kind_from_legacy_lead_method("未知历史方式") == CustomerActivityKind.OTHER_FOLLOW_UP
