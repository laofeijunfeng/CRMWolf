from datetime import datetime, timedelta

from app.schemas.agent_persistence import AgentUIActionRecord
from app.services.agent.ui.read_projection import project_interaction_action_states
from app.services.agent.ui.schemas import AgentUIEnvelope, AgentUIMetadata, InteractionBlock, InteractionOption


def test_consumed_action_projects_interaction_as_submitted_and_non_actionable() -> None:
    envelope = AgentUIEnvelope(
        schema_version="crm.agent.ui.v1",
        message_id=10,
        turn_id="turn_10",
        role="assistant",
        state="final",
        blocks=[InteractionBlock(
            id="b_interaction",
            type="interaction",
            interaction_id="int_1",
            interaction_type="confirmation",
            state="ACTIVE",
            prompt="确认创建吗？",
            options=[
                InteractionOption(value="confirm", label="确认创建"),
                InteractionOption(value="cancel", label="取消"),
            ],
            selection_mode="single",
            submit_action_id="act_1",
        )],
        suggested_actions=[],
        metadata=AgentUIMetadata(route="WORKFLOW"),
    )
    now = datetime(2026, 8, 24, 10, 0, 0)
    action = AgentUIActionRecord(
        public_id="act_1", team_id=1, user_id=2, session_id=3, message_id=10,
        action_type="submit_interaction", target={}, consumption_mode="ONE_SHOT",
        status="CONSUMED", expires_at=now, consumed_at=now,
        consumed_request_id="6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
        result_message_id=11, lock_version=1, created_time=now, last_modified_time=now,
    )

    block = project_interaction_action_states([envelope], [action])[0].blocks[0]

    assert block.type == "interaction"
    assert block.state == "SUBMITTED"
    assert block.submit_action_id is None


def test_elapsed_active_action_projects_interaction_as_expired_and_non_actionable() -> None:
    now = datetime(2026, 8, 24, 10, 0, 0)
    envelope = AgentUIEnvelope(
        schema_version="crm.agent.ui.v1",
        message_id=10,
        turn_id="turn_10",
        role="assistant",
        state="final",
        blocks=[InteractionBlock(
            id="b_interaction",
            type="interaction",
            interaction_id="int_1",
            interaction_type="confirmation",
            state="ACTIVE",
            prompt="确认创建吗？",
            options=[
                InteractionOption(value="confirm", label="确认创建"),
                InteractionOption(value="cancel", label="取消"),
            ],
            selection_mode="single",
            submit_action_id="act_1",
        )],
        suggested_actions=[],
        metadata=AgentUIMetadata(route="WORKFLOW"),
    )
    action = AgentUIActionRecord(
        public_id="act_1", team_id=1, user_id=2, session_id=3, message_id=10,
        action_type="submit_interaction", target={}, consumption_mode="ONE_SHOT",
        status="ACTIVE", expires_at=now - timedelta(seconds=1), consumed_at=None,
        consumed_request_id=None, result_message_id=None, lock_version=0,
        created_time=now - timedelta(hours=24), last_modified_time=now - timedelta(hours=24),
    )

    block = project_interaction_action_states([envelope], [action], now=now)[0].blocks[0]

    assert block.type == "interaction"
    assert block.state == "EXPIRED"
    assert block.submit_action_id is None


def test_grouped_interactions_project_each_action_state_independently() -> None:
    now = datetime(2026, 8, 25, 10, 0, 0)
    blocks = [
        InteractionBlock(
            id=f"b_task_{index}",
            type="interaction",
            interaction_id=f"int_{index}",
            interaction_type="choice",
            presentation="COMPACT_TASK_COMPLETION",
            state="ACTIVE",
            prompt=f"待办 {index}",
            options=[InteractionOption(value="已完成", label="标记完成")],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_on_select=True,
            submit_action_id=f"act_{index}",
        )
        for index in (1, 2)
    ]
    envelope = AgentUIEnvelope(
        schema_version="crm.agent.ui.v1",
        message_id=10,
        turn_id="turn_10",
        role="assistant",
        state="final",
        blocks=blocks,
        suggested_actions=[],
        metadata=AgentUIMetadata(route="WORKFLOW"),
    )
    actions = [
        AgentUIActionRecord(
            public_id=f"act_{index}", team_id=1, user_id=2, session_id=3, message_id=10,
            action_type="submit_interaction", target={}, consumption_mode="ONE_SHOT",
            status=status, expires_at=now + timedelta(days=1),
            consumed_at=now if status == "CONSUMED" else None,
            consumed_request_id=(
                "6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be" if status == "CONSUMED" else None
            ),
            result_message_id=11 if status == "CONSUMED" else None,
            lock_version=1 if status == "CONSUMED" else 0,
            created_time=now, last_modified_time=now,
        )
        for index, status in ((1, "CONSUMED"), (2, "ACTIVE"))
    ]

    projected = project_interaction_action_states([envelope], actions, now=now)[0]

    first, second = projected.blocks
    assert first.type == "interaction"
    assert first.state == "SUBMITTED"
    assert first.submit_action_id is None
    assert second.type == "interaction"
    assert second.state == "ACTIVE"
    assert second.submit_action_id == "act_2"


def test_cancelled_follow_up_confirmation_case_projects_active_card_as_cancelled() -> None:
    now = datetime(2026, 8, 26, 23, 8, 41)
    envelope = AgentUIEnvelope(
        schema_version="crm.agent.ui.v1",
        message_id=10,
        turn_id="turn_10",
        role="assistant",
        state="final",
        blocks=[InteractionBlock(
            id="b_interaction",
            type="interaction",
            interaction_id="int_follow_up_confirmation",
            interaction_type="choice",
            presentation="COMPACT_TASK_COMPLETION",
            state="ACTIVE",
            prompt="下周二打电话给 Rain 老师确认具体情况",
            options=[InteractionOption(value="已完成", label="标记完成")],
            selection_mode="single",
            min_selections=1,
            max_selections=1,
            submit_on_select=True,
            submit_action_id="act_old_case",
        )],
        suggested_actions=[],
        metadata=AgentUIMetadata(route="WORKFLOW"),
    )
    action = AgentUIActionRecord(
        public_id="act_old_case", team_id=1, user_id=2, session_id=3, message_id=10,
        action_type="submit_interaction",
        target={"follow_up_confirmation_case_public_id": "fuc_old_case"},
        consumption_mode="ONE_SHOT", status="ACTIVE", expires_at=now + timedelta(hours=1),
        consumed_at=None, consumed_request_id=None, result_message_id=None,
        lock_version=0, created_time=now, last_modified_time=now,
    )

    block = project_interaction_action_states(
        [envelope],
        [action],
        now=now,
        follow_up_confirmation_case_statuses_by_action={"act_old_case": "CANCELLED"},
    )[0].blocks[0]

    assert block.type == "interaction"
    assert block.state == "CANCELLED"
    assert block.submit_action_id is None
