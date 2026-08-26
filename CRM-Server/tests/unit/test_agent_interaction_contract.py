"""Behavior tests for server-owned workflow interaction contracts."""

from app.services.agent.interaction_contract import (
    INTERACTION_TYPE_CHOICE,
    STATUS_WAITING_USER_INPUT,
    build_interaction,
)


def test_choice_interaction_declares_single_selection_contract_by_default() -> None:
    interaction = build_interaction(
        event_name="customer_selection_required",
        interaction_type=INTERACTION_TYPE_CHOICE,
        prompt="请选择客户。",
        status=STATUS_WAITING_USER_INPUT,
        choices=[
            {"label": "客户一", "value": "customer_1"},
            {"label": "客户二", "value": "customer_2"},
        ],
    )

    assert interaction["selection_mode"] == "single"
    assert interaction["min_selections"] == 1
    assert interaction["max_selections"] == 1


def test_choice_interaction_preserves_explicit_multiple_selection_contract() -> None:
    interaction = build_interaction(
        event_name="customer_selection_required",
        interaction_type=INTERACTION_TYPE_CHOICE,
        prompt="请选择客户。",
        status=STATUS_WAITING_USER_INPUT,
        choices=[
            {"label": "客户一", "value": "customer_1"},
            {"label": "客户二", "value": "customer_2"},
            {"label": "客户三", "value": "customer_3"},
        ],
        selection_mode="multiple",
        min_selections=1,
        max_selections=2,
    )

    assert interaction["selection_mode"] == "multiple"
    assert interaction["min_selections"] == 1
    assert interaction["max_selections"] == 2
