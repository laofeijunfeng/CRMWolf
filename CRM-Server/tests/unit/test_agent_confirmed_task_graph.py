"""Confirmed task LangGraph orchestration tests."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.exc import SQLAlchemyError

from app.services.agent.confirmed_application_step_projection import (
    ConfirmedApplicationStepProjectionResult,
)
from app.services.agent.confirmed_task_graph import (
    ConfirmedTaskGraphService,
    build_confirmed_task_graph_config,
    build_confirmed_task_thread_id,
)
from app.services.agent.state import ConfirmedTaskGraphSideEffects, ConfirmedTaskRuntimeContext


class FakeCheckpointFailingGraph:
    async def ainvoke(self, state, config, *, context):
        raise SQLAlchemyError("checkpoint write failed")


class FakeConfirmedApplicationProjector:
    def __init__(self, *, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def project(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return ConfirmedApplicationStepProjectionResult(
            status="COMPLETED",
            step_id=request.step["step_id"],
            result={
                "execution_status": "completed",
                "tool_result": {
                    "event": "tool_result",
                    "tool_name": "create_customer_activity",
                    "success": True,
                },
                "task_event": {
                    "event": "task_completed",
                    "task_id": request.task.id,
                    "content": "跟进记录已创建。",
                },
                "assistant_content": "跟进记录已创建。",
                "output_events": [
                    {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
                    {"event": "task_completed", "task_id": request.task.id, "content": "跟进记录已创建。"},
                    {"event": "final", "content": "跟进记录已创建。"},
                ],
                "executed_task_snapshot": {
                    "id": request.task.id,
                    "task_key": request.task.task_key,
                    "team_id": request.team_id,
                    "user_id": request.user_id,
                    "session_id": request.session_id,
                    "status": "COMPLETED",
                    "state_json": request.task.state_json,
                },
                "active_task_snapshot": {},
                "progress_events": [],
            },
        )


def _task():
    return SimpleNamespace(
        id=101,
        task_key="task-101",
        team_id=1,
        user_id=2,
        session_id=3,
        status="WAITING_USER",
        intent="CREATE_FOLLOW_UP",
        target_type="customer",
        target_id=17,
        state_json={"action": "create_customer_activity", "payload": {"customer_id": 17}},
    )


def _input_state(task):
    return {
        "db": object(),
        "session": SimpleNamespace(id=3),
        "task": task,
        "team_id": 1,
        "user_id": 2,
        "session_id": 3,
        "authorization": "Bearer test",
        "events": [],
    }


@pytest.mark.asyncio
async def test_confirmed_task_graph_checkpoints_execution_intent_and_hydrates_projected_result():
    task = _task()
    projector = FakeConfirmedApplicationProjector()
    service = ConfirmedTaskGraphService(
        application_projector=projector,
        checkpointer=InMemorySaver(),
    )

    result = await service.run(_input_state(task))
    snapshot = await service._graph.aget_state(build_confirmed_task_graph_config(
        team_id=1,
        user_id=2,
        session_id=3,
        task_id=101,
    ))

    assert build_confirmed_task_thread_id(team_id=1, user_id=2, session_id=3, task_id=101) == (
        "crm_agent_confirmed:1:2:3:101"
    )
    assert projector.calls[0].task is task
    assert projector.calls[0].authorization == "Bearer test"
    assert projector.calls[0].event_sink is None
    assert snapshot.values["task_projection"]["id"] == 101
    assert snapshot.values["application_step"]["step_type"] == "confirmed_task_execution"
    assert snapshot.values["application_step"]["action"] == "create_customer_activity"
    assert snapshot.values["application_step"]["task_snapshot"]["task_key"] == "task-101"
    assert snapshot.values["application_step_result"]["execution_status"] == "completed"
    assert snapshot.values["execution_status"] == "completed"
    assert result["output_events"] == [
        {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
        {"event": "task_completed", "task_id": 101, "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ]
    assert result["executed_task_snapshot"]["id"] == 101
    assert result["active_task_snapshot"] == {}


@pytest.mark.asyncio
async def test_confirmed_task_graph_keeps_runtime_objects_out_of_checkpoint_state():
    task = _task()
    projector = FakeConfirmedApplicationProjector()
    service = ConfirmedTaskGraphService(application_projector=projector)
    side_effects = ConfirmedTaskGraphSideEffects()

    state = await service._graph.ainvoke(
        {
            "team_id": 1,
            "user_id": 2,
            "session_id": 3,
            "task_projection": {},
            "events": [],
        },
        context=ConfirmedTaskRuntimeContext(
            db=object(),
            session=SimpleNamespace(id=3),
            task=task,
            team_id=1,
            user_id=2,
            session_id=3,
            authorization="Bearer test",
            side_effects=side_effects,
        ),
    )

    assert "db" not in state
    assert "session" not in state
    assert "task" not in state
    assert "authorization" not in state
    assert state["application_step"]["task_snapshot"]["id"] == 101
    assert side_effects.task_event == {"event": "task_completed", "task_id": 101, "content": "跟进记录已创建。"}
    assert side_effects.output_events[-1] == {"event": "final", "content": "跟进记录已创建。"}
    assert state["executed_task_snapshot"]["id"] == 101
    assert state["active_task_snapshot"] == {}


@pytest.mark.asyncio
async def test_confirmed_task_graph_does_not_fallback_for_business_sql_errors():
    service = ConfirmedTaskGraphService(
        application_projector=FakeConfirmedApplicationProjector(error=SQLAlchemyError("business db failed")),
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(SQLAlchemyError, match="business db failed"):
        await service.run(_input_state(_task()))


@pytest.mark.asyncio
async def test_confirmed_task_graph_propagates_checkpoint_errors_to_root_fail_closed_runtime():
    service = ConfirmedTaskGraphService(
        application_projector=FakeConfirmedApplicationProjector(),
        checkpointer=InMemorySaver(),
    )
    service._graph = FakeCheckpointFailingGraph()

    with pytest.raises(SQLAlchemyError, match="checkpoint write failed"):
        await service.run(_input_state(_task()))

    assert not hasattr(service, "_fallback_graph")
