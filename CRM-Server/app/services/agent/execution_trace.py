"""User-facing execution trace projection for LangGraph runtimes."""
from __future__ import annotations

from app.services.agent import task_display
from app.services.agent.types import JSONDict, coerce_json_dict


def confirmed_task_execution_events(
    *,
    task: object,
    graph_events: object,
    output_events: object,
    include_graph_progress_events: bool = True,
) -> list[JSONDict]:
    """Project confirmed-task graph state into application-facing progress events."""

    internal_events = _events(graph_events)
    if not internal_events:
        return _with_readable_tool_events(output_events, task=task)

    existing_step_keys = _agent_step_keys(internal_events)
    action_label = _execution_action_label(_task_action(task))
    progress_events: list[JSONDict] = []
    for event in internal_events:
        event_name = event.get("event")
        if event_name == "confirmed_task_graph_started":
            progress_events.extend(_step_pair("confirmed_task_prepare", "读取待确认任务"))
        elif event_name == "agent_step" and include_graph_progress_events:
            progress_events.append(event)
        elif event_name == "confirmed_task_execution_completed":
            task_event = event.get("task_event")
            if task_event == "task_failed":
                progress_events.extend([
                    _step("confirmed_task_execute", "started", f"执行{action_label}"),
                    _step("confirmed_task_execute", "completed", f"{action_label}执行失败"),
                ])
            else:
                progress_events.extend(_step_pair("confirmed_task_execute", f"执行{action_label}"))
        elif event_name == "confirmed_task_effects_applied":
            progress_events.extend(_step_pair("confirmed_task_effects", "同步业务状态"))
        elif event_name == "confirmed_task_graph_finished":
            progress_events.extend(_step_pair("confirmed_task_finish", "整理执行结果"))

    return [
        *progress_events,
        *_with_readable_tool_events(output_events, task=task, existing_step_keys=existing_step_keys),
    ]


def pending_task_step_started(step_name: str) -> JSONDict | None:
    label = _pending_task_step_label(step_name)
    if not label:
        return None
    return _step(step_name, "started", label)


def pending_task_step_completed(step_name: str) -> JSONDict | None:
    label = _pending_task_step_label(step_name)
    if not label:
        return None
    return _step(step_name, "completed", label)


def _with_readable_tool_events(
    events: object,
    *,
    task: object,
    existing_step_keys: set[str] | None = None,
) -> list[JSONDict]:
    action_label = _execution_action_label(_task_action(task))
    readable_events: list[JSONDict] = []
    step_keys = existing_step_keys or set()
    for event in _events(events):
        if event.get("event") == "tool_result" and not isinstance(event.get("content"), str):
            success = event.get("success") is True
            event = {
                **event,
                "content": f"{action_label}已执行" if success else f"{action_label}执行失败",
            }
            readable_events.extend(_stage_move_step_events(event, existing_step_keys=step_keys))
        readable_events.append(event)
    return readable_events


def _step_pair(step: str, content: str) -> list[JSONDict]:
    return [
        _step(step, "started", content),
        _step(step, "completed", content),
    ]


def _step(step: str, status: str, content: str) -> JSONDict:
    return {
        "event": "agent_step",
        "step": step,
        "status": status,
        "content": content,
    }


def _stage_move_step_events(event: JSONDict, *, existing_step_keys: set[str]) -> list[JSONDict]:
    if event.get("tool_name") != "move_opportunity_stage" or event.get("success") is not True:
        return []
    data = event.get("data")
    if not isinstance(data, dict):
        return []
    raw_steps = data.get("stage_move_steps")
    if not isinstance(raw_steps, list) or len(raw_steps) <= 1:
        return []

    events: list[JSONDict] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            continue
        stage_name = raw_step.get("stage_name")
        if not isinstance(stage_name, str) or not stage_name.strip():
            continue
        step_key = f"opportunity_stage_move_{index}"
        if step_key in existing_step_keys:
            continue
        events.extend(_step_pair(step_key, f"推进到「{stage_name.strip()}」"))
    return events


def _agent_step_keys(events: list[JSONDict]) -> set[str]:
    keys: set[str] = set()
    for event in events:
        if event.get("event") != "agent_step":
            continue
        step = event.get("step")
        if isinstance(step, str):
            keys.add(step)
    return keys


def _execution_action_label(action: str | None) -> str:
    return task_display.readable_execution_label(action) or "业务操作"


def _task_action(task: object) -> str | None:
    state_json = getattr(task, "state_json", None)
    state = coerce_json_dict(state_json)
    action = state.get("action")
    return action if isinstance(action, str) else None


def _pending_task_step_label(step_name: str) -> str | None:
    labels = {
        "load_suspended_candidates": "读取待处理流程",
        "classify_turn_relation": "判断本次输入属于新流程还是待处理流程",
        "apply_turn_relation": "应用流程处理方式",
        "wait_turn_relation_clarification": "等待选择流程",
        "apply_resume_payload": "处理按钮选择",
        "apply_interaction_resume": "应用补充信息",
        "preflight": "识别确认或取消意图",
        "plan_interaction": "整理需要确认或补充的信息",
        "wait_interaction_interrupt": "等待确认或补充信息",
    }
    return labels.get(step_name)


def _events(events: object) -> list[JSONDict]:
    if not isinstance(events, list):
        return []
    return [coerce_json_dict(event) for event in events if isinstance(event, dict)]
