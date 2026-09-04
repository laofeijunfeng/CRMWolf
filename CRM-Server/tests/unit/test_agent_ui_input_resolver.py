"""Signed Agent UI interaction values resolve into Workflow resume input."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app.services.agent.ui.input_resolver import (
    AgentUIInputResolutionError,
    InteractionInputResolver,
)
from app.services.agent.workflow import WorkflowResumeInput


def _choice_target(*, selection_mode: str = "single") -> dict:
    return {
        "interaction_type": "choice",
        "business_action": "select_customer",
        "selection_mode": selection_mode,
        "min_selections": 1,
        "max_selections": 1 if selection_mode == "single" else 2,
        "choices": [
            {
                "value": "customer_shanghai",
                "label": "上海星云科技",
                "disabled": False,
                "metadata": {"customer_public_id": "cus_1"},
            },
            {
                "value": "customer_beijing",
                "label": "北京北辰科技",
                "disabled": False,
                "metadata": {"customer_public_id": "cus_2"},
            },
            {
                "value": "customer_disabled",
                "label": "不可选择客户",
                "disabled": True,
            },
        ],
    }


def _confirmation_target() -> dict:
    return {
        "interaction_type": "confirmation",
        "business_action": "confirm_follow_up",
        "payload": {"task_id": 91},
        "selection_mode": "single",
        "choices": [
            {"value": "confirm", "label": "确认", "disabled": False},
            {"value": "cancel", "label": "取消", "disabled": False},
        ],
    }


def _legacy_workflow_choice_target() -> dict:
    return {
        "interaction_type": "choice",
        "workflow_trigger": {
            "type": "workflow_trigger",
            "workflow": "customer_opportunity_suggestion",
            "job_public_id": "cosj_legacy_1",
            "action": "MOVE_OPPORTUNITY_STAGE",
        },
        "selection_mode": "single",
        "min_selections": 1,
        "max_selections": 1,
        "choices": [
            {"value": "confirm", "label": "是", "disabled": False},
            {"value": "cancel", "label": "否", "disabled": False},
        ],
    }


def _form_target() -> dict:
    return {
        "interaction_type": "form",
        "business_action": "collect_customer_profile",
        "fields": [
            {
                "key": "summary",
                "label": "客户情况",
                "field_type": "textarea",
                "required": True,
                "min_length": 2,
                "max_length": 50,
            },
            {
                "key": "employee_count",
                "label": "员工数",
                "field_type": "number",
                "required": True,
                "minimum": 1,
                "maximum": 100000,
            },
            {
                "key": "stage",
                "label": "阶段",
                "field_type": "select",
                "required": True,
                "options": [
                    {"value": "lead", "label": "线索", "disabled": False},
                    {"value": "customer", "label": "客户", "disabled": False},
                    {"value": "closed", "label": "已关闭", "disabled": True},
                ],
            },
            {
                "key": "tags",
                "label": "标签",
                "field_type": "multi_select",
                "required": False,
                "options": [
                    {"value": "key", "label": "重点", "disabled": False},
                    {"value": "renewal", "label": "续费", "disabled": False},
                ],
            },
            {
                "key": "approved",
                "label": "已确认",
                "field_type": "boolean",
                "required": True,
            },
            {
                "key": "next_date",
                "label": "下次联系日期",
                "field_type": "date",
                "required": True,
            },
            {
                "key": "meeting_at",
                "label": "会议时间",
                "field_type": "datetime",
                "required": True,
            },
        ],
    }


def _text_target(*, allow_blank: bool = False) -> dict:
    return {
        "interaction_type": "text_input",
        "business_action": "collect_supplement",
        "allow_blank": allow_blank,
        "fields": [
            {
                "key": "text",
                "label": "补充信息",
                "field_type": "textarea",
                "required": not allow_blank,
                "min_length": 0 if allow_blank else 2,
                "max_length": 20,
            }
        ],
    }


def test_single_choice_returns_canonical_workflow_resume_input() -> None:
    resolved = InteractionInputResolver().resolve_interaction_values(
        _choice_target(),
        {"choice": "customer_shanghai"},
    )

    assert resolved == WorkflowResumeInput(
        kind="text",
        content="customer_shanghai",
        source="web",
        metadata={
            "business_action": "select_customer",
            "customer_public_id": "cus_1",
        },
    )


@pytest.mark.parametrize(
    ("choice", "kind", "content"),
    [("confirm", "confirm", "确认"), ("cancel", "reject", "取消")],
)
def test_legacy_binary_workflow_choice_uses_typed_confirmation_protocol(
    choice: str,
    kind: str,
    content: str,
) -> None:
    resolved = InteractionInputResolver().resolve_interaction_values(
        _legacy_workflow_choice_target(),
        {"choice": choice},
    )

    assert resolved.kind == kind
    assert resolved.content == content


def test_general_choice_with_confirmation_values_stays_text_without_workflow_trigger() -> None:
    target = _choice_target()
    target["choices"] = [
        {"value": "confirm", "label": "确认客户", "disabled": False},
        {"value": "cancel", "label": "取消选择", "disabled": False},
    ]

    resolved = InteractionInputResolver().resolve_interaction_values(
        target,
        {"choice": "confirm"},
    )

    assert resolved.kind == "text"
    assert resolved.content == "confirm"


def test_multiple_choice_preserves_authorized_selection_order_and_metadata() -> None:
    resolved = InteractionInputResolver().resolve_interaction_values(
        _choice_target(selection_mode="multiple"),
        {"choices": ["customer_beijing", "customer_shanghai"]},
    )

    assert resolved.kind == "text"
    assert resolved.content == "customer_beijing、customer_shanghai"
    assert resolved.metadata == {
        "business_action": "select_customer",
        "selected_values": ["customer_beijing", "customer_shanghai"],
        "selected_choices": [
            {"value": "customer_beijing", "metadata": {"customer_public_id": "cus_2"}},
            {"value": "customer_shanghai", "metadata": {"customer_public_id": "cus_1"}},
        ],
    }


@pytest.mark.parametrize(
    ("values", "target_change"),
    [
        ({"choice": "not_signed"}, None),
        ({"choice": "customer_disabled"}, None),
        ({"choices": ["customer_shanghai", "customer_shanghai"]}, {"selection_mode": "multiple"}),
        ({"choices": []}, {"selection_mode": "multiple"}),
        ({"choice": "customer_shanghai"}, {"min_selections": 0}),
    ],
)
def test_choice_rejects_values_outside_the_signed_contract(values: dict, target_change: dict | None) -> None:
    target = _choice_target(selection_mode=(target_change or {}).get("selection_mode", "single"))
    if target_change:
        target.update(target_change)

    with pytest.raises(AgentUIInputResolutionError):
        InteractionInputResolver().resolve_interaction_values(target, values)


def test_confirmation_maps_only_signed_decisions_to_workflow_kinds() -> None:
    resolver = InteractionInputResolver()

    confirmed = resolver.resolve_interaction_values(_confirmation_target(), {"choice": "confirm", "task_id": 999})
    cancelled = resolver.resolve_interaction_values(_confirmation_target(), {"choice": "cancel"})

    assert confirmed == WorkflowResumeInput(
        kind="confirm",
        content="确认",
        source="web",
        metadata={
            "business_action": "confirm_follow_up",
            "payload": {"task_id": 91},
        },
    )
    assert cancelled == WorkflowResumeInput(
        kind="reject",
        content="取消",
        source="web",
        metadata=confirmed.metadata,
    )


@pytest.mark.parametrize(
    "mutate_target",
    [
        lambda target: target.update(selection_mode="multiple"),
        lambda target: target.update(choices=[{"value": "yes", "label": "是", "disabled": False}]),
        lambda target: target["choices"].append(
            {"value": "confirm", "label": "重复确认", "disabled": False}
        ),
        lambda target: target["choices"][0].update(disabled=True),
    ],
)
def test_confirmation_rejects_noncanonical_or_disabled_choices(mutate_target) -> None:
    target = _confirmation_target()
    mutate_target(target)

    with pytest.raises(AgentUIInputResolutionError):
        InteractionInputResolver().resolve_interaction_values(target, {"choice": "confirm"})


def test_form_validates_all_supported_field_types_and_returns_canonical_json() -> None:
    values = {
        "summary": "准备签约",
        "employee_count": 800,
        "stage": "customer",
        "tags": ["key", "renewal"],
        "approved": True,
        "next_date": "2026-08-24",
        "meeting_at": "2026-08-24T10:30:00+08:00",
    }

    resolved = InteractionInputResolver().resolve_interaction_values(_form_target(), values)

    assert resolved.kind == "text"
    assert resolved.source == "web"
    assert resolved.content == json.dumps(values, ensure_ascii=False, sort_keys=True)
    assert resolved.metadata == {
        "business_action": "collect_customer_profile",
        "form_values": values,
    }


@pytest.mark.parametrize(
    "values",
    [
        {
            "summary": "准备签约",
            "employee_count": 800,
            "stage": "customer",
            "tags": ["key"],
            "approved": True,
            "next_date": "2026-08-24",
            "meeting_at": "2026-08-24T10:30:00+08:00",
            "unknown": "must fail",
        },
        {
            "employee_count": 800,
            "stage": "customer",
            "approved": True,
            "next_date": "2026-08-24",
            "meeting_at": "2026-08-24T10:30:00+08:00",
        },
        {
            "summary": "准备签约",
            "employee_count": 0,
            "stage": "customer",
            "approved": True,
            "next_date": "2026-08-24",
            "meeting_at": "2026-08-24T10:30:00+08:00",
        },
        {
            "summary": "准备签约",
            "employee_count": 800,
            "stage": "closed",
            "approved": True,
            "next_date": "2026-08-24",
            "meeting_at": "2026-08-24T10:30:00+08:00",
        },
        {
            "summary": "准备签约",
            "employee_count": 800,
            "stage": "customer",
            "approved": False,
            "next_date": "not-a-date",
            "meeting_at": "2026-08-24T10:30:00+08:00",
        },
    ],
)
def test_form_rejects_unknown_missing_or_invalid_values(values: dict) -> None:
    with pytest.raises(AgentUIInputResolutionError):
        InteractionInputResolver().resolve_interaction_values(_form_target(), values)


def test_text_input_applies_signed_blank_and_length_policy() -> None:
    resolver = InteractionInputResolver()

    resolved = resolver.resolve_interaction_values(_text_target(), {"text": "需要补充联系人"})
    blank = resolver.resolve_interaction_values(_text_target(allow_blank=True), {"text": ""})

    assert resolved == WorkflowResumeInput(
        kind="text",
        content="需要补充联系人",
        source="web",
        metadata={"business_action": "collect_supplement"},
    )
    assert blank.content == ""


@pytest.mark.parametrize("text", ["", "a", "x" * 21])
def test_text_input_rejects_values_outside_signed_bounds(text: str) -> None:
    with pytest.raises(AgentUIInputResolutionError):
        InteractionInputResolver().resolve_interaction_values(_text_target(), {"text": text})


def test_resolver_rejects_unsupported_or_legacy_interaction_type() -> None:
    resolver = InteractionInputResolver()
    legacy_target = deepcopy(_confirmation_target())
    legacy_target["type"] = legacy_target.pop("interaction_type")

    with pytest.raises(AgentUIInputResolutionError):
        resolver.resolve_interaction_values(legacy_target, {"choice": "confirm"})
    with pytest.raises(AgentUIInputResolutionError):
        resolver.resolve_interaction_values({"interaction_type": "upload"}, {})


def test_text_input_preserves_server_signed_interaction_identity() -> None:
    target = _text_target()
    target.update(
        interaction_id="int_workflow_follow_up_confirmation_case",
        business_action="resolve_follow_up_task_confirmation_case",
    )

    resolved = InteractionInputResolver().resolve_interaction_values(
        target,
        {"text": "已完成"},
    )

    assert resolved.metadata == {
        "business_action": "resolve_follow_up_task_confirmation_case",
        "interaction_id": "int_workflow_follow_up_confirmation_case",
    }
