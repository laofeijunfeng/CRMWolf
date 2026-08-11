"""Action planning primitives for Agent auto execution.

This module keeps DAG readiness and blocking rules outside the LangGraph root
runtime. The runtime should execute ready nodes; this planner decides which
nodes are ready and why others are not.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.agent import AgentTaskStatus
from app.services.agent import action_workflow
from app.services.agent.types import JSONDict, coerce_json_dict


TASK_TERMINAL_STATUSES = frozenset({
    AgentTaskStatus.COMPLETED,
    AgentTaskStatus.FAILED,
    AgentTaskStatus.CANCELLED,
})


@dataclass(frozen=True)
class ActionPlanItem:
    action_id: str
    action_type: str
    workflow: JSONDict = field(default_factory=dict)
    payload: JSONDict = field(default_factory=dict)
    task: object | None = None
    task_id: int | None = None
    target_type: str | None = None
    target_id: int | None = None
    depends_on: tuple[str, ...] = ()
    parallel_group: str | None = None
    terminal: bool = False


@dataclass(frozen=True)
class ActionPlanNode:
    action_id: str
    action_type: str
    workflow: JSONDict
    payload: JSONDict
    task: object | None
    task_id: int | None
    target_type: str | None = None
    target_id: int | None = None
    depends_on: tuple[str, ...] = ()
    parallel_group: str | None = None
    terminal: bool = False
    blocked_reason: str | None = None


@dataclass(frozen=True)
class ActionExecutionPlan:
    nodes: tuple[ActionPlanNode, ...] = ()
    ready_nodes: tuple[ActionPlanNode, ...] = ()
    blocked_nodes: tuple[ActionPlanNode, ...] = ()
    active_nodes: tuple[ActionPlanNode, ...] = ()
    terminal_nodes: tuple[ActionPlanNode, ...] = ()
    satisfied_action_ids: frozenset[str] = field(default_factory=frozenset)
    running_action_ids: frozenset[str] = field(default_factory=frozenset)
    terminal_action_ids: frozenset[str] = field(default_factory=frozenset)

    def summary(self) -> JSONDict:
        parallel_groups = sorted({
            node.parallel_group
            for node in self.ready_nodes
            if isinstance(node.parallel_group, str) and node.parallel_group
        })
        return {
            "total_nodes": len(self.nodes),
            "ready_count": len(self.ready_nodes),
            "blocked_count": len(self.blocked_nodes),
            "active_count": len(self.active_nodes),
            "terminal_count": len(self.terminal_nodes),
            "satisfied_action_count": len(self.satisfied_action_ids),
            "running_action_count": len(self.running_action_ids),
            "terminal_action_count": len(self.terminal_action_ids),
            "parallel_groups": parallel_groups,
        }


def build_auto_execute_plan_from_tasks(
    tasks: list[object],
    *,
    completed_action_ids: set[str] | frozenset[str] | None = None,
    satisfied_action_ids: set[str] | frozenset[str] | None = None,
    running_action_ids: set[str] | frozenset[str] | None = None,
    terminal_action_ids: set[str] | frozenset[str] | None = None,
) -> ActionExecutionPlan:
    """Build one executable DAG snapshot for auto-executable Agent tasks."""

    return build_action_execution_plan(
        items_from_tasks(tasks),
        completed_action_ids=completed_action_ids,
        satisfied_action_ids=satisfied_action_ids,
        running_action_ids=running_action_ids,
        terminal_action_ids=terminal_action_ids,
    )


def items_from_tasks(tasks: list[object]) -> list[ActionPlanItem]:
    """Adapt legacy AgentTask projections into action-level plan items."""

    return [_item_from_task(task) for task in tasks]


def build_action_execution_plan(
    items: list[ActionPlanItem],
    *,
    completed_action_ids: set[str] | frozenset[str] | None = None,
    satisfied_action_ids: set[str] | frozenset[str] | None = None,
    running_action_ids: set[str] | frozenset[str] | None = None,
    terminal_action_ids: set[str] | frozenset[str] | None = None,
) -> ActionExecutionPlan:
    """Build one executable DAG snapshot from action-level plan items."""

    satisfied = frozenset(satisfied_action_ids or completed_action_ids or set())
    running = frozenset(running_action_ids or set())
    terminal = frozenset(terminal_action_ids or set())
    nodes = tuple(_node_from_item(item) for item in items)
    known_action_ids = {node.action_id for node in nodes}
    terminal_nodes: list[ActionPlanNode] = []
    active_nodes: list[ActionPlanNode] = []
    ready_nodes: list[ActionPlanNode] = []
    blocked_nodes: list[ActionPlanNode] = []

    for node in nodes:
        if node.terminal or node.action_id in satisfied or node.action_id in terminal:
            terminal_nodes.append(node)
            continue
        if node.action_id in running:
            active_nodes.append(node)
            continue
        missing_dependencies = [
            dependency
            for dependency in node.depends_on
            if dependency not in satisfied and dependency not in known_action_ids
        ]
        if missing_dependencies:
            blocked_nodes.append(_replace_blocked_reason(
                node,
                f"missing_dependencies:{','.join(missing_dependencies)}",
            ))
            continue
        terminal_dependencies = [
            dependency
            for dependency in node.depends_on
            if dependency not in satisfied and dependency in terminal
        ]
        if terminal_dependencies:
            blocked_nodes.append(_replace_blocked_reason(
                node,
                f"terminal_dependencies:{','.join(terminal_dependencies)}",
            ))
            continue
        pending_dependencies = [
            dependency
            for dependency in node.depends_on
            if dependency not in satisfied
        ]
        if pending_dependencies:
            blocked_nodes.append(_replace_blocked_reason(
                node,
                f"waiting_dependencies:{','.join(pending_dependencies)}",
            ))
            continue
        ready_nodes.append(node)

    return ActionExecutionPlan(
        nodes=nodes,
        ready_nodes=tuple(ready_nodes),
        blocked_nodes=tuple(blocked_nodes),
        active_nodes=tuple(active_nodes),
        terminal_nodes=tuple(terminal_nodes),
        satisfied_action_ids=satisfied,
        running_action_ids=running,
        terminal_action_ids=terminal,
    )


def item_from_workflow(
    workflow: object,
    *,
    payload: object | None = None,
    task: object | None = None,
    task_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    terminal: bool = False,
) -> ActionPlanItem | None:
    workflow_json = action_workflow.workflow_from_mapping(workflow)
    if not workflow_json:
        return None
    dependency = coerce_json_dict(workflow_json.get("dependency_json"))
    return ActionPlanItem(
        action_id=str(workflow_json["action_id"]),
        action_type=str(workflow_json["action_type"]),
        workflow=workflow_json,
        payload=coerce_json_dict(payload),
        task=task,
        task_id=task_id,
        target_type=target_type,
        target_id=target_id,
        depends_on=tuple(_dependency_action_ids(dependency)),
        parallel_group=_optional_str(dependency.get("parallel_group")),
        terminal=terminal or _is_terminal_workflow_status(workflow_json.get("status")),
    )


def item_from_ledger_action(action: object) -> ActionPlanItem | None:
    workflow = _workflow_from_ledger_action(action)
    if not workflow:
        return None
    return ActionPlanItem(
        action_id=str(workflow["action_id"]),
        action_type=str(workflow["action_type"]),
        workflow=workflow,
        payload=coerce_json_dict(getattr(action, "payload_json", None)),
        task=None,
        task_id=_optional_int(getattr(action, "task_id", None)),
        target_type=_optional_str(getattr(action, "target_type", None)),
        target_id=_optional_int(getattr(action, "target_id", None)),
        depends_on=tuple(_dependency_action_ids(coerce_json_dict(getattr(action, "dependency_json", None)))),
        parallel_group=_optional_str(coerce_json_dict(getattr(action, "dependency_json", None)).get("parallel_group")),
        terminal=_ledger_action_is_terminal(action),
    )


def _item_from_task(task: object) -> ActionPlanItem:
    state = coerce_json_dict(getattr(task, "state_json", None))
    workflow = action_workflow.workflow_from_task_state(state)
    dependency = coerce_json_dict(workflow.get("dependency_json") or state.get("dependency_json"))
    task_id = _optional_int(getattr(task, "id", None))
    action = _action_type_from_state_or_workflow(state, workflow)
    action_id = _action_id_from_task_or_workflow(task_id=task_id, workflow=workflow)
    payload = _payload_from_task(task=task, state=state)
    return ActionPlanItem(
        action_id=action_id,
        action_type=action,
        workflow=workflow,
        payload=payload,
        task=task,
        task_id=task_id,
        target_type=_optional_str(getattr(task, "target_type", None)),
        target_id=_optional_int(getattr(task, "target_id", None)),
        depends_on=tuple(_dependency_action_ids(dependency)),
        parallel_group=_optional_str(dependency.get("parallel_group")),
        terminal=_is_task_terminal(task) or _is_terminal_workflow_status(workflow.get("status")),
    )


def _node_from_item(item: ActionPlanItem) -> ActionPlanNode:
    return ActionPlanNode(
        action_id=item.action_id,
        action_type=item.action_type,
        workflow=item.workflow,
        payload=item.payload,
        task=item.task,
        task_id=item.task_id,
        target_type=item.target_type,
        target_id=item.target_id,
        depends_on=item.depends_on,
        parallel_group=item.parallel_group,
        terminal=item.terminal,
    )


def _is_terminal_workflow_status(value: object) -> bool:
    return value in {
        action_workflow.STATUS_EXECUTED,
        action_workflow.STATUS_SKIPPED,
        action_workflow.STATUS_CANCELLED,
        action_workflow.STATUS_FAILED,
    }


def _replace_blocked_reason(node: ActionPlanNode, reason: str) -> ActionPlanNode:
    return ActionPlanNode(
        action_id=node.action_id,
        action_type=node.action_type,
        workflow=node.workflow,
        payload=node.payload,
        task=node.task,
        task_id=node.task_id,
        target_type=node.target_type,
        target_id=node.target_id,
        depends_on=node.depends_on,
        parallel_group=node.parallel_group,
        terminal=node.terminal,
        blocked_reason=reason,
    )


def _action_type_from_state_or_workflow(state: JSONDict, workflow: JSONDict) -> str:
    action_type = workflow.get("action_type")
    if isinstance(action_type, str) and action_type.strip():
        return action_type.strip()
    action = state.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip()
    return "unknown"


def _action_id_from_task_or_workflow(*, task_id: int | None, workflow: JSONDict) -> str:
    action_id = workflow.get("action_id")
    if isinstance(action_id, str) and action_id.strip():
        return action_id.strip()
    if task_id is not None:
        return f"task:{task_id}"
    return "task:unknown"


def _dependency_action_ids(value: JSONDict) -> list[str]:
    raw_depends_on = value.get("depends_on")
    if not isinstance(raw_depends_on, list):
        return []
    return [item.strip() for item in raw_depends_on if isinstance(item, str) and item.strip()]


def _is_task_terminal(task: object) -> bool:
    status = getattr(task, "status", None)
    return isinstance(status, str) and status in TASK_TERMINAL_STATUSES


def _workflow_from_ledger_action(action: object) -> JSONDict:
    workflow = {
        "schema_version": action_workflow.WORKFLOW_SCHEMA_VERSION,
        "workflow_id": _optional_str(getattr(action, "workflow_id", None)) or "",
        "action_id": _optional_str(getattr(action, "action_id", None)) or "",
        "action_type": _optional_str(getattr(action, "action_type", None)) or "unknown",
        "status": _workflow_status_from_ledger_status(getattr(action, "status", None)),
        "policy": {
            "scope": _optional_str(getattr(action, "scope", None)) or action_workflow.SCOPE_REQUIRED_WRITE,
            "source": _optional_str(getattr(action, "source", None)) or action_workflow.SOURCE_EXPLICIT_USER_REQUEST,
            "execution_policy": (
                _optional_str(getattr(action, "execution_policy", None))
                or action_workflow.EXECUTION_REQUIRES_CONFIRMATION
            ),
            "on_reject": _optional_str(getattr(action, "on_reject", None)) or action_workflow.ON_REJECT_CANCEL_ACTION,
            "blocking": bool(getattr(action, "blocking", True)),
        },
    }
    parent_action_id = _optional_str(getattr(action, "parent_action_id", None))
    if parent_action_id:
        workflow["parent_action_id"] = parent_action_id
    dependency = coerce_json_dict(getattr(action, "dependency_json", None))
    if dependency:
        workflow["dependency_json"] = dependency
    return action_workflow.workflow_from_mapping(workflow)


def _workflow_status_from_ledger_status(status: object) -> str:
    status_value = _optional_str(status)
    if not status_value:
        return action_workflow.STATUS_WAITING_USER
    mapping = {
        "PLANNED": action_workflow.STATUS_PLANNED,
        "WAITING_USER": action_workflow.STATUS_WAITING_USER,
        "RUNNING": action_workflow.STATUS_RUNNING,
        "EXECUTED": action_workflow.STATUS_EXECUTED,
        "SKIPPED": action_workflow.STATUS_SKIPPED,
        "CANCELLED": action_workflow.STATUS_CANCELLED,
        "FAILED": action_workflow.STATUS_FAILED,
        "BLOCKED": action_workflow.STATUS_BLOCKED,
    }
    return mapping.get(status_value.upper(), status_value)


def _ledger_action_is_terminal(action: object) -> bool:
    return _workflow_status_from_ledger_status(getattr(action, "status", None)) in {
        action_workflow.STATUS_EXECUTED,
        action_workflow.STATUS_SKIPPED,
        action_workflow.STATUS_CANCELLED,
        action_workflow.STATUS_FAILED,
    }


def _payload_from_task(*, task: object, state: JSONDict) -> JSONDict:
    state_payload = coerce_json_dict(state.get("payload"))
    if state_payload:
        return state_payload
    task_input = coerce_json_dict(getattr(task, "input_json", None))
    input_payload = coerce_json_dict(task_input.get("payload"))
    if input_payload:
        return input_payload
    input_business_payload = _strip_internal_payload_keys(task_input)
    if input_business_payload:
        return input_business_payload
    return _strip_internal_payload_keys(state)


def _strip_internal_payload_keys(value: JSONDict) -> JSONDict:
    return {
        key: item
        for key, item in value.items()
        if key not in {"action", "workflow", "dependency_json"}
    }


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
