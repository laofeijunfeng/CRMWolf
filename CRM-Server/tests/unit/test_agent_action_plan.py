from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from app.models.agent import AgentTaskStatus
from app.services.agent import action_plan, action_workflow


def test_action_workflow_capabilities_declare_user_authorized_write_actions():
    assert action_workflow.action_requires_user_authorization("create_customer_activity") is True
    assert action_workflow.action_requires_user_authorization("transition_follow_up_task") is True
    assert action_workflow.action_requires_user_authorization("refresh_customer_profile") is False
    assert action_workflow.action_requires_user_authorization(None) is False
    activity_capability = action_workflow.action_capability("create_customer_activity")
    assert activity_capability.tool_name == "create_customer_activity"
    assert activity_capability.is_write is True
    assert activity_capability.requires_confirmation is True
    assert action_workflow.ACTION_CAPABILITY_CRM_WRITE in activity_capability.flags
    assert action_workflow.ACTION_CAPABILITY_REQUIRES_USER_AUTHORIZATION in activity_capability.flags
    assert action_workflow.action_capability("refresh_customer_profile").tool_name is None


def test_action_workflow_capabilities_declare_recovery_parallel_and_idempotency_policy():
    activity_capability = action_workflow.action_capability("create_customer_activity")
    assert activity_capability.requires_idempotency_key is True
    assert activity_capability.allows_background_recovery is False
    assert activity_capability.parallel_safe is False
    assert action_workflow.ACTION_CAPABILITY_REQUIRES_IDEMPOTENCY_KEY in activity_capability.flags
    assert action_workflow.action_requires_idempotency_key("create_customer_activity") is True
    assert action_workflow.action_allows_background_recovery("create_customer_activity") is False
    assert action_workflow.action_is_parallel_safe("create_customer_activity") is False

    refresh_capability = action_workflow.action_capability("refresh_customer_profile")
    assert refresh_capability.is_write is False
    assert refresh_capability.requires_idempotency_key is False
    assert refresh_capability.allows_background_recovery is True
    assert refresh_capability.parallel_safe is True
    assert action_workflow.ACTION_CAPABILITY_BACKGROUND_RECOVERABLE in refresh_capability.flags
    assert action_workflow.ACTION_CAPABILITY_PARALLEL_SAFE in refresh_capability.flags

    unknown_capability = action_workflow.action_capability("unknown_action")
    assert unknown_capability.allows_background_recovery is False
    assert unknown_capability.parallel_safe is False


def test_action_workflow_auto_execute_contract_has_non_waiting_status():
    workflow = action_workflow.required_write_contract(action="create_customer_activity")

    auto_workflow = action_workflow.mark_auto_executable(
        workflow,
        reason="low_risk_high_confidence",
        source="action_review",
    )

    assert auto_workflow["workflow_id"] == workflow["workflow_id"]
    assert auto_workflow["action_id"] == workflow["action_id"]
    assert auto_workflow["status"] == action_workflow.STATUS_PLANNED
    assert auto_workflow["status_reason"] == "low_risk_high_confidence"
    assert auto_workflow["status_source"] == "action_review"
    assert auto_workflow["policy"]["execution_policy"] == action_workflow.EXECUTION_AUTO_EXECUTE
    assert action_workflow.is_auto_execute_workflow(auto_workflow) is True
    assert action_workflow.is_auto_execute_workflow(workflow) is False


def test_auto_execute_plan_marks_independent_tasks_ready_in_one_batch():
    task_1 = SimpleNamespace(
        id=501,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"action": "create_customer_activity"},
    )
    task_2 = SimpleNamespace(
        id=502,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"action": "transition_follow_up_task"},
    )

    plan = action_plan.build_auto_execute_plan_from_tasks([task_1, task_2])

    assert [node.task_id for node in plan.ready_nodes] == [501, 502]
    assert plan.blocked_nodes == ()
    assert plan.summary()["ready_count"] == 2


def test_auto_execute_plan_blocks_task_until_dependency_completed():
    upstream_workflow = _workflow("act_upstream", action_type="create_customer_activity")
    downstream_workflow = _workflow(
        "act_downstream",
        action_type="transition_follow_up_task",
        dependency_json={"depends_on": ["act_upstream"], "parallel_group": "post_commit"},
    )
    upstream = SimpleNamespace(
        id=501,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"action": "create_customer_activity", "workflow": upstream_workflow},
    )
    downstream = SimpleNamespace(
        id=502,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"action": "transition_follow_up_task", "workflow": downstream_workflow},
    )

    plan = action_plan.build_auto_execute_plan_from_tasks([upstream, downstream])

    assert [node.action_id for node in plan.ready_nodes] == ["act_upstream"]
    assert [node.action_id for node in plan.blocked_nodes] == ["act_downstream"]
    assert plan.blocked_nodes[0].blocked_reason == "waiting_dependencies:act_upstream"

    next_plan = action_plan.build_auto_execute_plan_from_tasks(
        [upstream, downstream],
        completed_action_ids={"act_upstream"},
    )

    assert [node.action_id for node in next_plan.ready_nodes] == ["act_downstream"]
    assert [node.action_id for node in next_plan.terminal_nodes] == ["act_upstream"]


def test_auto_execute_plan_blocks_missing_dependencies_and_skips_terminal_tasks():
    skipped_workflow = _workflow("act_skipped", action_type="create_opportunity")
    skipped_workflow["status"] = action_workflow.STATUS_SKIPPED
    cancelled_workflow = _workflow("act_cancelled", action_type="collect_opportunity_fields")
    cancelled_workflow["status"] = action_workflow.STATUS_CANCELLED
    blocked_workflow = _workflow(
        "act_blocked",
        action_type="transition_follow_up_task",
        dependency_json={"depends_on": ["act_missing"]},
    )
    skipped = SimpleNamespace(
        id=501,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"workflow": skipped_workflow},
    )
    cancelled = SimpleNamespace(
        id=504,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"workflow": cancelled_workflow},
    )
    blocked = SimpleNamespace(
        id=502,
        status=AgentTaskStatus.WAITING_USER,
        state_json={"workflow": blocked_workflow},
    )
    completed = SimpleNamespace(
        id=503,
        status=AgentTaskStatus.COMPLETED,
        state_json={"action": "create_customer_activity"},
    )

    plan = action_plan.build_auto_execute_plan_from_tasks([skipped, cancelled, blocked, completed])

    assert [node.action_id for node in plan.terminal_nodes] == ["act_skipped", "act_cancelled", "task:503"]
    assert [node.action_id for node in plan.blocked_nodes] == ["act_blocked"]
    assert plan.blocked_nodes[0].blocked_reason == "missing_dependencies:act_missing"
    assert plan.ready_nodes == ()


def test_auto_execute_plan_terminal_action_does_not_satisfy_downstream_dependency():
    upstream = SimpleNamespace(
        id=501,
        status=AgentTaskStatus.WAITING_USER,
        state_json={
            "workflow": _workflow("act_failed", action_type="create_customer_activity"),
        },
    )
    downstream = SimpleNamespace(
        id=502,
        status=AgentTaskStatus.WAITING_USER,
        state_json={
            "workflow": _workflow(
                "act_downstream",
                action_type="transition_follow_up_task",
                dependency_json={"depends_on": ["act_failed"]},
            ),
        },
    )

    plan = action_plan.build_auto_execute_plan_from_tasks(
        [upstream, downstream],
        terminal_action_ids={"act_failed"},
    )

    assert [node.action_id for node in plan.terminal_nodes] == ["act_failed"]
    assert [node.action_id for node in plan.blocked_nodes] == ["act_downstream"]
    assert plan.blocked_nodes[0].blocked_reason == "terminal_dependencies:act_failed"


def test_action_execution_plan_builds_from_action_level_items_without_agent_tasks():
    upstream = action_plan.item_from_workflow(
        _workflow("act_upstream", action_type="create_customer_activity"),
    )
    downstream = action_plan.item_from_workflow(
        _workflow(
            "act_downstream",
            action_type="transition_follow_up_task",
            dependency_json={"depends_on": ["act_upstream"], "parallel_group": "post_commit"},
        ),
    )

    assert upstream is not None
    assert downstream is not None
    plan = action_plan.build_action_execution_plan([upstream, downstream])

    assert [node.action_id for node in plan.ready_nodes] == ["act_upstream"]
    assert [node.action_id for node in plan.blocked_nodes] == ["act_downstream"]
    assert plan.blocked_nodes[0].blocked_reason == "waiting_dependencies:act_upstream"
    assert plan.blocked_nodes[0].task is None
    assert plan.blocked_nodes[0].parallel_group == "post_commit"

    next_plan = action_plan.build_action_execution_plan(
        [upstream, downstream],
        satisfied_action_ids={"act_upstream"},
    )

    assert [node.action_id for node in next_plan.ready_nodes] == ["act_downstream"]


def test_action_execution_plan_treats_running_action_as_active_without_satisfying_dependencies():
    upstream = action_plan.item_from_workflow(
        _workflow("act_upstream", action_type="create_customer_activity"),
    )
    downstream = action_plan.item_from_workflow(
        _workflow(
            "act_downstream",
            action_type="transition_follow_up_task",
            dependency_json={"depends_on": ["act_upstream"]},
        ),
    )

    assert upstream is not None
    assert downstream is not None
    plan = action_plan.build_action_execution_plan(
        [upstream, downstream],
        running_action_ids={"act_upstream"},
    )

    assert [node.action_id for node in plan.active_nodes] == ["act_upstream"]
    assert [node.action_id for node in plan.blocked_nodes] == ["act_downstream"]
    assert plan.blocked_nodes[0].blocked_reason == "waiting_dependencies:act_upstream"
    assert plan.ready_nodes == ()
    assert plan.summary()["active_count"] == 1
    assert plan.summary()["running_action_count"] == 1


def test_derived_automation_contract_is_valid_action_workflow():
    workflow = action_workflow.derived_automation_contract(action="project_next_follow_up_tasks")

    parsed = action_workflow.workflow_from_mapping(workflow)

    assert parsed["action_type"] == "project_next_follow_up_tasks"
    assert parsed["policy"]["scope"] == action_workflow.SCOPE_DERIVED_AUTOMATION
    assert parsed["policy"]["source"] == action_workflow.SOURCE_SYSTEM_AUTOMATION
    assert parsed["policy"]["execution_policy"] == action_workflow.EXECUTION_AUTO_EXECUTE
    assert parsed["policy"]["blocking"] is False


def test_action_plan_item_can_be_rebuilt_from_ledger_action():
    ledger_action = SimpleNamespace(
        workflow_id="wf_ledger",
        action_id="act_projection",
        parent_action_id="act_activity",
        action_type="project_next_follow_up_tasks",
        status="PLANNED",
        scope=action_workflow.SCOPE_DERIVED_AUTOMATION,
        source=action_workflow.SOURCE_SYSTEM_AUTOMATION,
        execution_policy=action_workflow.EXECUTION_AUTO_EXECUTE,
        on_reject=action_workflow.ON_REJECT_ASK_CLARIFICATION,
        blocking=False,
        task_id=None,
        target_type="customer",
        target_id=101,
        dependency_json={"depends_on": ["act_activity"], "parallel_group": "post_commit_activity_analysis"},
        payload_json={"activity_id": 205, "customer_id": 101},
    )

    item = action_plan.item_from_ledger_action(ledger_action)

    assert item is not None
    assert item.action_id == "act_projection"
    assert item.action_type == "project_next_follow_up_tasks"
    assert item.depends_on == ("act_activity",)
    assert item.parallel_group == "post_commit_activity_analysis"
    assert item.payload == {"activity_id": 205, "customer_id": 101}
    assert item.target_type == "customer"
    assert item.target_id == 101
    assert item.terminal is False
    assert item.workflow["policy"]["execution_policy"] == action_workflow.EXECUTION_AUTO_EXECUTE


def test_action_plan_item_from_ledger_marks_failed_action_terminal():
    ledger_action = SimpleNamespace(
        workflow_id="wf_ledger",
        action_id="act_failed",
        parent_action_id=None,
        action_type="create_customer_activity",
        status="FAILED",
        scope=action_workflow.SCOPE_REQUIRED_WRITE,
        source=action_workflow.SOURCE_EXPLICIT_USER_REQUEST,
        execution_policy=action_workflow.EXECUTION_REQUIRES_CONFIRMATION,
        on_reject=action_workflow.ON_REJECT_CANCEL_ACTION,
        blocking=True,
        task_id=501,
        target_type="customer",
        target_id=101,
        dependency_json=None,
        payload_json={"customer_id": 101},
    )

    item = action_plan.item_from_ledger_action(ledger_action)

    assert item is not None
    assert item.terminal is True


def test_items_from_tasks_keeps_workflow_metadata_out_of_business_payload():
    task = SimpleNamespace(
        id=501,
        status=AgentTaskStatus.WAITING_USER,
        target_type="customer",
        target_id=101,
        input_json={"action": "legacy_wrapper"},
        state_json={
            "action": "transition_follow_up_task",
            "workflow": _workflow(
                "act_task",
                action_type="transition_follow_up_task",
                dependency_json={"depends_on": ["act_activity"]},
            ),
        },
    )

    [item] = action_plan.items_from_tasks([task])

    assert item.payload == {}
    assert item.target_type == "customer"
    assert item.target_id == 101


def test_items_from_tasks_uses_explicit_business_payload_from_state_or_input():
    state_payload_task = SimpleNamespace(
        id=501,
        status=AgentTaskStatus.WAITING_USER,
        state_json={
            "action": "create_customer_activity",
            "payload": {"content": "今天拜访客户"},
            "workflow": _workflow("act_state", action_type="create_customer_activity"),
        },
    )
    input_payload_task = SimpleNamespace(
        id=502,
        status=AgentTaskStatus.WAITING_USER,
        input_json={"payload": {"customer_id": 101}},
        state_json={
            "action": "transition_follow_up_task",
            "workflow": _workflow("act_input", action_type="transition_follow_up_task"),
        },
    )

    state_item, input_item = action_plan.items_from_tasks([state_payload_task, input_payload_task])

    assert state_item.payload == {"content": "今天拜访客户"}
    assert input_item.payload == {"customer_id": 101}


def _workflow(action_id: str, *, action_type: str, dependency_json: dict | None = None) -> dict:
    workflow = action_workflow.required_write_contract(action=action_type)
    copied = deepcopy(workflow)
    copied["workflow_id"] = "wf_test"
    copied["action_id"] = action_id
    copied["action_type"] = action_type
    if dependency_json:
        copied["dependency_json"] = dependency_json
    return copied
