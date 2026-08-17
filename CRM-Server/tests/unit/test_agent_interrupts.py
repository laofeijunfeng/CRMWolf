"""Tests for CRM Agent LangGraph interrupt payload adapters."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent import action_workflow, interactions, session_state
from app.services.agent.input import AgentTurnInput
from app.services.agent.interrupts import (
    allowed_resume_actions_for_interaction,
    interrupt_from_waiting_event,
    interrupt_from_waiting_task,
    interrupt_from_waiting_task_snapshot,
    resume_payload_from_turn_input,
    validate_resume_payload,
)
from app.services.agent.turn_intent import AgentTurnIntentRouter


def test_confirmation_waiting_task_projects_to_confirm_interrupt():
    task = SimpleNamespace(
        id=12,
        task_key="task_12",
        status="WAITING_USER",
        intent="CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=101,
        summary="等待确认执行：create_customer_activity",
        state_json={
            "action": "create_customer_activity",
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "payload": {"customer_id": 101, "content": "今天可以签合同了"},
        },
    )
    interaction = interactions._pending_task_interaction(task, task.summary)

    interrupt = interrupt_from_waiting_task(task, interaction=interaction)

    assert interrupt["schema_version"] == "agent.interrupt.v1"
    assert interrupt["type"] == "confirm"
    assert interrupt["reason"] == "write_confirmation"
    assert interrupt["business_action"] == "confirm_action"
    assert interrupt["allowed_resume_actions"] == ["approve", "edit", "reject", "cancel"]
    assert interrupt["task_projection_id"] == 12
    assert interrupt["task_projection_key"] == "task_12"
    assert interrupt["target_refs"] == [
        {"type": "customer", "id": 101},
    ]
    assert interrupt["interaction"]["prompt"] == "确认后，我会继续执行「确认记录跟进」。"
    assert "create_customer_activity" not in interrupt["interaction"]["prompt"]


def test_waiting_task_snapshot_projects_without_orm_hydration():
    task = SimpleNamespace(
        id=12,
        task_key="task_12",
        status="WAITING_USER",
        intent="CUSTOMER_ACTIVITY",
        target_type="customer",
        target_id=101,
        summary="等待确认执行：create_customer_activity",
        state_json={
            "action": "create_customer_activity",
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "payload": {"customer_id": 101, "content": "今天可以签合同了"},
        },
    )
    interaction = interactions._pending_task_interaction(task, task.summary)
    snapshot = {
        "id": task.id,
        "task_key": task.task_key,
        "status": task.status,
        "intent": task.intent,
        "target_type": task.target_type,
        "target_id": task.target_id,
        "summary": task.summary,
        "state_json": task.state_json,
    }

    assert interrupt_from_waiting_task_snapshot(snapshot, interaction=interaction) == (
        interrupt_from_waiting_task(task, interaction=interaction)
    )


def test_confirmation_event_prompt_hides_internal_action_key():
    event = {
        "event": "confirmation_required",
        "action": "create_customer_activity",
        "content": "确认后，我会继续执行「create_customer_activity」。",
    }

    interaction = interactions._with_interaction(event)["interaction"]

    assert interaction["prompt"] == "确认后，我会继续执行「确认记录跟进」。"
    assert "create_customer_activity" not in interaction["prompt"]


def test_form_waiting_task_projects_to_missing_fields_interrupt():
    task = SimpleNamespace(
        id=13,
        task_key="task_13",
        status="WAITING_USER",
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待补充商机信息",
        state_json={
            "action": "collect_opportunity_fields",
            "customer": {"id": 101, "account_name": "广州睿狐科技有限公司"},
            "payload": {
                "customer_id": 101,
                "missing_fields": ["total_amount", "license_type"],
                "interaction_fields": ["total_amount", "license_type"],
            },
        },
    )
    interaction = interactions._pending_task_interaction(task, task.summary)

    interrupt = interrupt_from_waiting_task(task, interaction=interaction)

    assert interrupt["type"] == "form"
    assert interrupt["reason"] == "missing_required_fields"
    assert interrupt["business_action"] == "create_opportunity"
    assert interrupt["allowed_resume_actions"] == ["submit_fields", "cancel"]
    assert interrupt["draft_payload"]["missing_fields"] == ["total_amount", "license_type"]
    assert interrupt["interaction"]["fields"]


def test_choice_waiting_event_projects_to_disambiguation_interrupt():
    interrupt = interrupt_from_waiting_event(
        {
            "event": "customer_selection_required",
            "action": "select_customer_for_activity",
            "customers": [
                {"id": 101, "account_name": "广州睿狐科技有限公司"},
                {"id": 102, "account_name": "深圳睿狐科技有限公司"},
            ],
        },
        interaction={
            "type": "choice",
            "status": "waiting_user_input",
            "business_action": "select_customer",
        },
    )

    assert interrupt["type"] == "choice"
    assert interrupt["reason"] == "business_object_disambiguation"
    assert interrupt["business_action"] == "select_customer"
    assert interrupt["allowed_resume_actions"] == ["select", "cancel"]
    assert interrupt["draft_payload"]["customers"][0]["id"] == 101


@pytest.mark.parametrize(
    ("action", "source_event", "business_action", "candidate_field"),
    [
        ("select_customer_for_activity", "customer_selection_required", "select_customer", "customers"),
        ("select_customer_for_opportunity", "customer_selection_required", "select_customer", "customers"),
        ("select_customer_for_contact", "customer_selection_required", "select_customer", "customers"),
        ("select_customer_for_invoice_title", "customer_selection_required", "select_customer", "customers"),
        ("select_customer_for_deployment_info", "customer_selection_required", "select_customer", "customers"),
        ("select_customer_for_customer_member", "customer_selection_required", "select_customer", "customers"),
        ("select_customer_for_payment_record", "customer_selection_required", "select_customer", "customers"),
        (
            "select_contract_for_payment_plan",
            "business_selection_required",
            "select_business_object",
            "contracts",
        ),
        (
            "select_payment_plan_for_record",
            "business_selection_required",
            "select_business_object",
            "payment_plans",
        ),
        (
            "select_opportunity_for_stage_move",
            "business_selection_required",
            "select_business_object",
            "opportunities",
        ),
    ],
)
def test_selection_waiting_task_snapshot_preserves_disambiguation_semantics(
    action: str,
    source_event: str,
    business_action: str,
    candidate_field: str,
):
    snapshot = {
        "id": 31,
        "task_key": "task_31",
        "status": "WAITING_USER",
        "target_type": "customer",
        "target_id": 101,
        "state_json": {
            "action": action,
            candidate_field: [{"id": 101, "name": "候选项"}],
            "payload": {},
        },
    }

    interrupt = interrupt_from_waiting_task_snapshot(
        snapshot,
        interaction={
            "type": "choice",
            "status": "waiting_user_input",
            "business_action": business_action,
        },
    )

    assert interrupt["type"] == "choice"
    assert interrupt["source_event"] == source_event
    assert interrupt["reason"] == "business_object_disambiguation"
    assert interrupt["business_action"] == business_action
    assert interrupt["allowed_resume_actions"] == ["select", "cancel"]


def test_allowed_resume_actions_has_status_fallback():
    assert allowed_resume_actions_for_interaction({"status": "waiting_user_input"}) == ["submit", "cancel"]


def test_resume_payload_maps_confirmation_text_to_edit_action():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.text("改成：客户今天可以签合同"),
        current_interrupt={
            "type": "confirm",
            "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
            "task_projection_id": 12,
            "task_projection_key": "task_12",
        },
    )

    assert payload["action"] == "edit"
    assert payload["task_projection_id"] == 12
    assert payload["task_projection_key"] == "task_12"


def test_resume_payload_maps_confirm_execute_text_to_approve_action():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.text("确认执行"),
        current_interrupt={
            "type": "confirm",
            "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
            "task_projection_id": 12,
            "task_projection_key": "task_12",
        },
    )

    assert payload["action"] == "approve"
    assert payload["task_projection_id"] == 12
    assert payload["task_projection_key"] == "task_12"


def test_resume_payload_maps_choice_rejection_text_to_cancel_action():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.text("先不处理"),
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
            "business_action": "select_suspended_task",
        },
    )

    assert payload["action"] == "cancel"


def test_resume_payload_maps_structured_reject_on_choice_to_cancel_action():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.reject(),
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
            "business_action": "select_suspended_task",
        },
    )

    assert payload["action"] == "cancel"


def test_resume_payload_maps_turn_relation_plain_business_text_to_new_flow():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.text("今天拜访了广州睿狐科技，张总说可以开始签合同了"),
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
            "business_action": "select_suspended_task",
            "source_event": "turn_relation_clarification_required",
        },
    )

    assert payload["action"] == "select"
    assert payload["metadata"]["turn_relation"] == "START_NEW_FLOW"


def test_resume_payload_maps_turn_relation_choice_label_to_selected_task():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.text("继续：确认记录跟进「广州睿狐科技有限公司」"),
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
            "business_action": "select_suspended_task",
            "source_event": "turn_relation_clarification_required",
            "interaction": {
                "type": "choice",
                "business_action": "select_suspended_task",
                "choices": [
                    {
                        "label": "继续处理：确认记录跟进｜广州睿狐科技有限公司",
                        "value": "继续处理：确认记录跟进｜广州睿狐科技有限公司",
                        "metadata": {"selected_task_id": 301},
                    },
                    {
                        "label": "作为新流程处理",
                        "value": "作为新流程处理",
                        "metadata": {"turn_relation": "START_NEW_FLOW"},
                    },
                ],
            },
        },
    )

    assert payload["action"] == "select"
    assert payload["metadata"]["selected_task_id"] == 301


async def test_turn_intent_router_cancels_required_form_interrupt_for_natural_language_skip():
    task = SimpleNamespace(
        id=13,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待补充商机信息",
        state_json={"action": "collect_opportunity_fields"},
        input_json={},
        status="WAITING_USER",
    )

    result = await AgentTurnIntentRouter().route_resume(
        None,
        team_id=1,
        user_id=2,
        session=None,
        turn_input=AgentTurnInput.text("暂不处理"),
        current_interrupt={
            "type": "form",
            "reason": "missing_required_fields",
            "allowed_resume_actions": ["submit_fields", "cancel"],
            "business_action": "create_opportunity",
            "task_projection_id": 13,
        },
        active_task=task,
    )

    assert result.resume_payload["action"] == "cancel"
    assert result.decision.intent == "CANCEL_CURRENT_TASK"
    assert result.resume_payload["metadata"]["turn_intent"]["intent"] == "CANCEL_CURRENT_TASK"


async def test_turn_intent_router_skips_optional_suggestion_form_interrupt_for_natural_language_skip():
    workflow = action_workflow.optional_suggestion_contract(action="collect_opportunity_fields")
    task = SimpleNamespace(
        id=13,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待补充商机信息",
        state_json={"action": "collect_opportunity_fields", "workflow": workflow},
        input_json={},
        status="WAITING_USER",
    )

    result = await AgentTurnIntentRouter().route_resume(
        None,
        team_id=1,
        user_id=2,
        session=None,
        turn_input=AgentTurnInput.text("暂不处理"),
        current_interrupt={
            "type": "form",
            "reason": "missing_required_fields",
            "allowed_resume_actions": ["submit_fields", "skip_current_action", "cancel"],
            "business_action": "create_opportunity",
            "task_projection_id": 13,
            "workflow": workflow,
        },
        active_task=task,
    )

    assert result.resume_payload["action"] == "skip_current_action"
    assert result.decision.intent == "DISMISS_CURRENT_SUGGESTION"
    assert result.resume_payload["metadata"]["turn_intent"]["intent"] == "DISMISS_CURRENT_SUGGESTION"


async def test_turn_intent_router_keeps_field_supplement_on_form_interrupt():
    task = SimpleNamespace(
        id=13,
        intent="CREATE_OPPORTUNITY",
        target_type="customer",
        target_id=101,
        summary="等待补充商机信息",
        state_json={"action": "collect_opportunity_fields"},
        input_json={},
        status="WAITING_USER",
    )

    result = await AgentTurnIntentRouter().route_resume(
        None,
        team_id=1,
        user_id=2,
        session=None,
        turn_input=AgentTurnInput.text("金额 48450，120 人，续购"),
        current_interrupt={
            "type": "form",
            "reason": "missing_required_fields",
            "allowed_resume_actions": ["submit_fields", "cancel"],
            "business_action": "create_opportunity",
            "task_projection_id": 13,
        },
        active_task=task,
    )

    assert result.resume_payload["action"] == "submit_fields"
    assert result.decision.intent == "SUBMIT_FIELDS"


def test_dismissed_suspended_task_is_not_resumable():
    task = SimpleNamespace(
        status="SUSPENDED",
        state_json={
            "action": "collect_opportunity_fields",
            "suspension_kind": "dismissed",
            "dismissed": True,
        },
    )

    assert session_state._is_resumable_task(task) is False


def test_legacy_suspended_task_without_suspension_kind_stays_resumable():
    task = SimpleNamespace(
        status="SUSPENDED",
        state_json={"action": "collect_opportunity_fields"},
    )

    assert session_state._is_resumable_task(task) is True


def test_resume_payload_maps_turn_relation_choice_number_to_selected_task():
    payload = resume_payload_from_turn_input(
        AgentTurnInput.text("1"),
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
            "business_action": "select_suspended_task",
            "source_event": "turn_relation_clarification_required",
            "interaction": {
                "type": "choice",
                "business_action": "select_suspended_task",
                "choices": [
                    {
                        "label": "继续处理：确认记录跟进｜广州睿狐科技有限公司",
                        "value": "继续处理：确认记录跟进｜广州睿狐科技有限公司",
                        "metadata": {"selected_task_id": 301},
                    },
                    {
                        "label": "作为新流程处理",
                        "value": "作为新流程处理",
                        "metadata": {"turn_relation": "START_NEW_FLOW"},
                    },
                ],
            },
        },
    )

    assert payload["action"] == "select"
    assert payload["metadata"]["selected_task_id"] == 301


def test_resume_payload_keeps_generic_choice_selection_strict_for_plain_text():
    try:
        resume_payload_from_turn_input(
            AgentTurnInput.text("今天拜访了广州睿狐科技，张总说可以开始签合同了"),
            current_interrupt={
                "type": "choice",
                "allowed_resume_actions": ["select", "cancel"],
                "business_action": "select_customer",
                "source_event": "customer_selection_required",
            },
        )
    except ValueError as exc:
        assert "selected id" in str(exc)
    else:
        raise AssertionError("expected generic choice resume without selected id to be rejected")


def test_validate_resume_payload_rejects_disallowed_action():
    try:
        validate_resume_payload(
            {"action": "submit"},
            current_interrupt={
                "type": "confirm",
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
            },
        )
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("expected invalid resume action to be rejected")


def test_validate_resume_payload_rejects_skip_current_action_for_required_workflow():
    workflow = action_workflow.required_write_contract(action="create_opportunity")

    try:
        validate_resume_payload(
            {"action": "skip_current_action", "content": "先不管"},
            current_interrupt={
                "type": "confirm",
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel", "skip_current_action"],
                "workflow": workflow,
            },
        )
    except ValueError as exc:
        assert "optional non-blocking" in str(exc)
    else:
        raise AssertionError("expected required workflow skip to be rejected")


def test_workflow_from_mapping_rejects_malformed_contract():
    workflow = action_workflow.optional_suggestion_contract(action="collect_opportunity_fields")
    workflow["policy"]["scope"] = "optional"

    assert action_workflow.workflow_from_mapping(workflow) == {}


def test_validate_resume_payload_rejects_stale_task_projection():
    try:
        validate_resume_payload(
            {"action": "approve", "task_projection_id": 99},
            current_interrupt={
                "type": "confirm",
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
                "task_projection_id": 12,
            },
        )
    except ValueError as exc:
        assert "task_projection_id" in str(exc)
    else:
        raise AssertionError("expected stale task projection to be rejected")


def test_validate_choice_resume_requires_selected_id():
    try:
        validate_resume_payload(
            {"action": "select", "content": "", "source": "web", "metadata": {}},
            current_interrupt={
                "type": "choice",
                "allowed_resume_actions": ["select", "cancel"],
            },
        )
    except ValueError as exc:
        assert "selected id" in str(exc)
    else:
        raise AssertionError("expected choice resume without selected id to be rejected")


def test_validate_choice_resume_accepts_selected_id_metadata():
    validate_resume_payload(
        {"action": "select", "content": "", "source": "web", "metadata": {"selected_customer_id": 101}},
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
        },
    )


def test_validate_choice_resume_accepts_turn_relation_metadata():
    validate_resume_payload(
        {
            "action": "select",
            "content": "作为新流程处理",
            "source": "web",
            "metadata": {"turn_relation": "START_NEW_FLOW"},
        },
        current_interrupt={
            "type": "choice",
            "allowed_resume_actions": ["select", "cancel"],
            "business_action": "select_suspended_task",
        },
    )


def test_validate_form_resume_requires_fields_or_content():
    try:
        validate_resume_payload(
            {"action": "submit_fields", "content": "", "source": "web", "metadata": {}},
            current_interrupt={
                "type": "form",
                "allowed_resume_actions": ["submit_fields", "cancel"],
            },
        )
    except ValueError as exc:
        assert "submitted fields" in str(exc)
    else:
        raise AssertionError("expected form resume without fields or content to be rejected")


def test_validate_text_resume_requires_content():
    try:
        validate_resume_payload(
            {"action": "submit_text", "content": "", "source": "web", "metadata": {}},
            current_interrupt={
                "type": "text",
                "allowed_resume_actions": ["submit_text", "cancel"],
            },
        )
    except ValueError as exc:
        assert "non-empty content" in str(exc)
    else:
        raise AssertionError("expected text resume without content to be rejected")


def test_validate_resume_payload_rejects_stale_business_action():
    try:
        validate_resume_payload(
            {"action": "approve", "business_action": "create_opportunity"},
            current_interrupt={
                "type": "confirm",
                "allowed_resume_actions": ["approve", "edit", "reject", "cancel"],
                "business_action": "create_customer_activity",
            },
        )
    except ValueError as exc:
        assert "business_action" in str(exc)
    else:
        raise AssertionError("expected stale business action to be rejected")


def test_interrupt_payload_json_marks_legacy_pending_checkpoint_continuation_invalid():
    from app.services.agent.interrupts import interrupt_payload_from_json

    payload = interrupt_payload_from_json({
        "schema_version": "agent.interrupt.v1",
        "type": "confirm",
        "reason": "write_confirmation",
        "business_action": "create_opportunity",
        "checkpoint_ref": {
            "runtime": "crm_agent_pending_task",
            "thread_id": "crm_agent_pending:2:3:4:101",
            "checkpoint_ns": "pending_task_subgraph:checkpoint-1",
            "team_id": 2,
            "user_id": 3,
            "session_id": 4,
            "task_id": 101,
        },
    })

    assert payload is not None
    assert "checkpoint_ref" not in payload
    assert payload["checkpoint_ref_error"] == "invalid_continuation"


def test_interrupt_payload_json_preserves_root_owned_checkpoint_locator_for_later_authentication():
    from app.services.agent.interrupts import interrupt_payload_from_json
    from app.services.agent.pending_continuation import new_pending_task_continuation

    continuation = new_pending_task_continuation(
        team_id=2,
        user_id=3,
        session_id=4,
        task_id=101,
        root_thread_id="crm_agent:2:3:4:abc",
        checkpoint_ns="pending_task_subgraph:checkpoint-1",
    )

    payload = interrupt_payload_from_json({
        "schema_version": "agent.interrupt.v1",
        "type": "confirm",
        "reason": "write_confirmation",
        "business_action": "create_opportunity",
        "checkpoint_ref": continuation,
    })

    assert payload is not None
    assert payload["checkpoint_ref"] == continuation
