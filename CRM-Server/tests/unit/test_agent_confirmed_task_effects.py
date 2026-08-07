from types import SimpleNamespace

from app.services.agent.confirmed_task_effects import (
    ConfirmedTaskSideEffectContext,
    confirmed_task_side_effect_handler,
)
from app.services.agent.state import ConfirmedTaskExecutionResult


def test_confirmed_task_effects_clear_completed_task_and_offer_next(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "create_customer_activity"})
    next_task = SimpleNamespace(id=12, state_json={"action": "collect_opportunity_fields"})
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_effects.interactions._should_offer_next_pending_task",
        lambda action: action == "create_customer_activity",
    )
    monkeypatch.setattr(
        "app.services.agent.confirmed_task_effects.interactions._pending_task_interaction",
        lambda task_arg, content, **kwargs: {"type": "form", "prompt": content, "task_id": task_arg.id},
    )

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            execution=ConfirmedTaskExecutionResult(
                tool_event={"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
                task_event={"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
                assistant_content="跟进记录已创建。",
                next_task=next_task,
            ),
        )
    )

    assert result.task_event == {
        "event": "task_completed",
        "task_id": 11,
        "content": "跟进记录已创建。",
        "next_task_id": 12,
        "interaction": {
            "type": "form",
            "prompt": "跟进记录已创建。",
            "task_id": 12,
        },
    }
    assert result.output_events == [
        {"event": "tool_result", "tool_name": "create_customer_activity", "success": True},
        result.task_event,
        {"event": "final", "content": "跟进记录已创建。"},
    ]


def test_confirmed_task_effects_do_not_clear_failed_task(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "unsupported"})

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            execution=ConfirmedTaskExecutionResult(
                tool_event=None,
                task_event={"event": "task_failed", "task_id": 11, "content": "执行失败"},
                assistant_content="执行失败",
            ),
        )
    )

    assert result.output_events == [
        {"event": "task_failed", "task_id": 11, "content": "执行失败"},
        {"event": "final", "content": "执行失败"},
    ]


def test_confirmed_task_effects_prompt_current_activity_confirmation_cases(monkeypatch):
    db = object()
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "create_customer_activity"})
    prompt_calls = []

    def fake_prompt_cases_by_public_ids(
        db_arg,
        *,
        team_id,
        user_id,
        case_public_ids,
        channel,
        provider,
        agent_session_id,
    ):
        prompt_calls.append(
            {
                "db": db_arg,
                "team_id": team_id,
                "user_id": user_id,
                "case_public_ids": case_public_ids,
                "channel": channel,
                "provider": provider,
                "agent_session_id": agent_session_id,
            }
        )
        return [
            {
                "event": "follow_up_task_confirmation_case_prompt",
                "content": "你有一项上次跟进需要确认: 测试客户 - 确认预算. 是否已完成?",
                "case_public_id": "fuc_11111111111111111111111111111111",
                "interaction": {"business_action": "resolve_follow_up_task_confirmation_case"},
            }
        ]

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_effects.follow_up_task_confirmation_channel_service.prompt_cases_by_public_ids",
        fake_prompt_cases_by_public_ids,
    )

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            channel="im",
            provider="feishu",
            execution=ConfirmedTaskExecutionResult(
                tool_event={
                    "event": "tool_result",
                    "tool_name": "create_customer_activity",
                    "success": True,
                    "data": {
                        "id": 190,
                        "post_commit": {
                            "needs_user_confirmation": True,
                            "confirmation_case_public_ids": ["fuc_11111111111111111111111111111111"],
                        },
                    },
                },
                task_event={"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
                assistant_content="跟进记录已创建。",
            ),
        )
    )

    assert prompt_calls == [
        {
            "db": db,
            "team_id": 1,
            "user_id": 2,
            "case_public_ids": ["fuc_11111111111111111111111111111111"],
            "channel": "im",
            "provider": "feishu",
            "agent_session_id": 3,
        }
    ]
    assert result.output_events == [
        {
            "event": "tool_result",
            "tool_name": "create_customer_activity",
            "success": True,
            "data": {
                "id": 190,
                "post_commit": {
                    "needs_user_confirmation": True,
                    "confirmation_case_public_ids": ["fuc_11111111111111111111111111111111"],
                },
            },
        },
        {"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
        {
            "event": "follow_up_task_confirmation_case_prompt",
            "content": "你有一项上次跟进需要确认: 测试客户 - 确认预算. 是否已完成?",
            "case_public_id": "fuc_11111111111111111111111111111111",
            "interaction": {"business_action": "resolve_follow_up_task_confirmation_case"},
        },
        {
            "event": "final",
            "content": (
                "跟进记录已创建。\n\n"
                "你有一项上次跟进需要确认: 测试客户 - 确认预算. 是否已完成?"
            ),
        },
    ]
    assert result.assistant_content == (
        "跟进记录已创建。\n\n"
        "你有一项上次跟进需要确认: 测试客户 - 确认预算. 是否已完成?"
    )


def test_confirmed_task_effects_isolate_current_activity_prompt_failure(monkeypatch):
    rollback_calls = []
    db = SimpleNamespace(rollback=lambda: rollback_calls.append("rollback"))
    session = SimpleNamespace(id=3)
    task = SimpleNamespace(id=11, state_json={"action": "create_customer_activity"})

    def fake_prompt_cases_by_public_ids(*args, **kwargs):
        raise RuntimeError("prompt delivery failed")

    monkeypatch.setattr(
        "app.services.agent.confirmed_task_effects.follow_up_task_confirmation_channel_service.prompt_cases_by_public_ids",
        fake_prompt_cases_by_public_ids,
    )

    result = confirmed_task_side_effect_handler.apply(
        ConfirmedTaskSideEffectContext(
            db=db,
            session=session,
            task=task,
            team_id=1,
            user_id=2,
            execution=ConfirmedTaskExecutionResult(
                tool_event={
                    "event": "tool_result",
                    "tool_name": "create_customer_activity",
                    "success": True,
                    "data": {
                        "id": 190,
                        "post_commit": {
                            "needs_user_confirmation": True,
                            "confirmation_case_public_ids": ["fuc_11111111111111111111111111111111"],
                        },
                    },
                },
                task_event={"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
                assistant_content="跟进记录已创建。",
            ),
        )
    )

    assert rollback_calls == ["rollback"]
    assert result.output_events == [
        {
            "event": "tool_result",
            "tool_name": "create_customer_activity",
            "success": True,
            "data": {
                "id": 190,
                "post_commit": {
                    "needs_user_confirmation": True,
                    "confirmation_case_public_ids": ["fuc_11111111111111111111111111111111"],
                },
            },
        },
        {"event": "task_completed", "task_id": 11, "content": "跟进记录已创建。"},
        {"event": "final", "content": "跟进记录已创建。"},
    ]
    assert result.assistant_content == "跟进记录已创建。"
