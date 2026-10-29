# ruff: noqa: RUF001, E501
"""Assistant conversation messages project to one crm.agent.ui.v1 carrier."""

from __future__ import annotations

from app.schemas.assistant import AssistantTaskView
from app.schemas.assistant_conversation import ConversationBoundary, ConversationMessage
from app.services.assistant.contracts import (
    ActivityPreview,
    ActivityWriteConfirmation,
    DraftField,
    ProposalCandidate,
    ProposalConfirmation,
    TaskDraft,
    TaskWaiting,
)
from app.services.assistant.ui_projection import finalize_assistant_ui, project_assistant_message


def _task(**overrides: object) -> AssistantTaskView:
    payload = {
        "public_id": "ast_one",
        "status": "ACTIVE",
        "goal": "客户沟通",
        "activity_kind": "FOLLOW_UP",
        "draft": TaskDraft(),
        "waiting": None,
        "committed": [],
        "budget_steps": 0,
        "budget_max_steps": 50,
        "version": 1,
    }
    payload.update(overrides)
    return AssistantTaskView.model_validate(payload)


def _message(message_id: str, text: str, task: AssistantTaskView | None = None, **overrides: object) -> ConversationMessage:
    payload = {
        "id": message_id,
        "role": "assistant",
        "text": text,
        "at": "2026-10-28T10:00:00",
        "task": task,
        "boundary": None,
        "outcome": None,
    }
    payload.update(overrides)
    return ConversationMessage.model_validate(payload)


def _preview(**overrides: object) -> ActivityPreview:
    payload = {
        "customer_name": "原客户",
        "activity_kind": "ONLINE_MEETING",
        "title": "原会议主题",
        "summary": "原会议讨论",
        "content_json": {"participants": {"internal": ["虚构同事甲"], "customer": ["虚构客户乙"]}},
        "source_content": "原文",
        "score": 88,
        "score_reason": "原评分",
        "next_action": "原行动",
    }
    payload.update(overrides)
    return ActivityPreview.model_validate(payload)


def _confirmation(preview: ActivityPreview | None = None, **overrides: object) -> TaskWaiting:
    payload = {
        "type": "CONFIRMATION",
        "field": "activity_write",
        "question_id": "q1",
        "prompt": "确认后写入这条客户活动？",
        "action_id": "act_1",
        "expected_version": 1,
        "confirmation_payload": ActivityWriteConfirmation(kind="activity_write", preview=preview or _preview()),
    }
    payload.update(overrides)
    return TaskWaiting.model_validate(payload)


def test_plain_reply_is_only_a_text_block() -> None:
    message = _message("m1", "今天先记到这里。")
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    assert [block.type for block in envelope.blocks] == ["text"]
    assert envelope.blocks[0].text == "今天先记到这里。"
    assert envelope.schema_version == "crm.agent.ui.v1"


def test_field_gap_does_not_repeat_the_prompt_as_text() -> None:
    waiting = TaskWaiting(type="FIELD", field="customer", question_id="q1", prompt="请补充客户名称", action_id="act_1", expected_version=1)
    draft = TaskDraft(customer=DraftField(status="ACCEPTED", value="旧客户"))
    task = _task(draft=draft, waiting=waiting)
    message = _message("m1", "请补充客户名称", task)
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    assert [block.type for block in envelope.blocks] == ["notice", "interaction"]
    interaction = envelope.blocks[1]
    assert interaction.interaction_type == "text_input"
    assert interaction.prompt == "请补充客户名称"
    assert interaction.state == "ACTIVE"
    assert interaction.submit_action_id == "act_1"
    assert envelope.blocks[0].text == "客户：旧客户"
    assert not any(block.type == "text" for block in envelope.blocks)


def test_temporal_choice_uses_signed_candidate_ids() -> None:
    waiting = TaskWaiting(
        type="FIELD",
        field="temporal_choice",
        question_id="q1",
        prompt="30 号是指哪个月？",
        action_id="act_time",
        expected_version=2,
        candidates=[{"id": "month_this", "label": "本月 30 号"}, {"id": "month_next", "label": "下月 30 号"}],
    )
    message = _message("m1", waiting.prompt, _task(waiting=waiting))
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    interaction = envelope.blocks[0]
    assert interaction.interaction_type == "choice"
    assert interaction.business_action == "resolve_temporal_choice"
    assert [option.value for option in interaction.options] == ["month_this", "month_next"]
    assert not any(block.type == "text" for block in envelope.blocks)


def test_confirmation_uses_frozen_preview_not_the_later_draft() -> None:
    preview = _preview()
    waiting = _confirmation(preview)
    draft = TaskDraft(
        customer=DraftField(status="ACCEPTED", value="新客户"),
        content=DraftField(status="CANDIDATE", value="新摘要"),
        next_action=DraftField(status="CANDIDATE", value="新行动"),
    )
    message = _message("m1", "会议确认", _task(draft=draft, waiting=waiting, activity_kind="ONLINE_MEETING"))
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    interaction = next(block for block in envelope.blocks if block.type == "interaction")
    values = {fact.key: fact.value for fact in interaction.facts}
    assert values["customer"] == "原客户"
    assert values["title"] == "原会议主题"
    assert values["summary"] == "原会议讨论"
    assert values["participants"] == "我方：虚构同事甲；客户方：虚构客户乙"
    assert values["next_action"] == "原行动"
    assert values["score"] == "88 / 100"
    assert "新客户" not in " ".join(values.values())
    assert [option.value for option in interaction.options] == ["confirm", "cancel"]


def test_missing_meeting_action_does_not_fall_back_to_the_draft() -> None:
    waiting = _confirmation(_preview(summary=None, next_action=None, content_json={}))
    draft = TaskDraft(
        content=DraftField(status="CANDIDATE", value="后来讨论"),
        next_action=DraftField(status="CANDIDATE", value="后来行动"),
    )
    message = _message("m1", "确认？", _task(draft=draft, waiting=waiting))
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    interaction = next(block for block in envelope.blocks if block.type == "interaction")
    values = {fact.key: fact.value for fact in interaction.facts}
    assert values["next_action"] == "未提供行动项"
    assert "后来讨论" not in values.values()
    assert "后来行动" not in values.values()
    assert interaction.state == "READ_ONLY"
    assert interaction.submit_action_id is None


def test_only_the_latest_matching_wait_stays_active() -> None:
    waiting = _confirmation()
    task = _task(waiting=waiting)
    older = _message("old", "旧提示", task)
    newer = _message("new", "当前提示", task)
    user = ConversationMessage(id="user", role="user", text="你好", at="2026-10-28T10:00:00")
    finalize_assistant_ui([older, user, newer], focused_task=task, pending_choice=None)
    older_block = next(block for block in older.ui.blocks if block.type == "interaction")
    newer_block = next(block for block in newer.ui.blocks if block.type == "interaction")
    assert older.ui is not None and older_block.state == "READ_ONLY"
    assert older_block.submit_action_id is None
    assert newer.ui is not None and newer_block.state == "ACTIVE"
    assert user.ui is None


def test_failure_uses_the_event_code_instead_of_the_sentence() -> None:
    message = _message("m1", "没有找到客户「拒绝」", outcome="failure", error_code="CUSTOMER_NOT_FOUND", retryable=False)
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    error = envelope.blocks[0]
    assert error.type == "error"
    assert error.code == "CUSTOMER_NOT_FOUND"
    assert error.title == "尚未写入"
    assert error.retryable is False


def test_unknown_commit_is_a_notice_and_not_a_retryable_error() -> None:
    message = _message(
        "m1",
        "处理未完成，结果待核对，请查看最新任务状态。",
        outcome="failure",
        error_code="UNKNOWN_COMMIT_RESULT",
        retryable=True,
    )
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    notice = envelope.blocks[0]
    assert notice.type == "notice"
    assert notice.tone == "warning"
    assert notice.title == "结果待核对"
    assert envelope.state == "final"


def test_written_activity_is_a_result_block() -> None:
    message = _message("m1", "已记录这条客户活动。", outcome="activity_written")
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    result = envelope.blocks[0]
    assert result.type == "action_result"
    assert result.status == "SUCCESS"
    assert result.title == "已写入"
    assert result.message == "已记录这条客户活动。"


def test_boundary_choice_is_active_only_while_pending() -> None:
    boundary = ConversationBoundary(entry_id="entry_1", prompt="是接着刚才，还是另记一件？")
    message = _message("m1", boundary.prompt, boundary=boundary)
    active = project_assistant_message(message, active_waiting=False, active_boundary=True)
    historical = project_assistant_message(message, active_waiting=False, active_boundary=False)
    assert active.blocks[0].state == "ACTIVE"
    assert [option.value for option in active.blocks[0].options] == ["CONTINUE", "NEW"]
    assert historical.blocks[0].submit_action_id is None


def test_customer_choice_does_not_accept_a_raw_name_as_the_option_value() -> None:
    waiting = TaskWaiting(
        type="OBJECT_SELECTION",
        field="customer",
        question_id="q1",
        prompt="请选择客户",
        action_id="act_customer",
        expected_version=1,
        candidates=[{"id": "cus_b", "account_name": "睿狐集团"}],
    )
    message = _message("m1", waiting.prompt, _task(waiting=waiting))
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    assert envelope.blocks[0].options[0].value == "cus_b"
    assert envelope.blocks[0].options[0].label == "睿狐集团"


def test_proposal_confirmation_is_its_own_interaction() -> None:
    candidate = ProposalCandidate(
        kind="opportunity_create",
        key="proposal-1",
        payload={"name": "年度合同"},
        evidence_quote="客户提到了年度合同",
        activity_id=1,
        customer_id=2,
        source_revision=1,
    )
    waiting = TaskWaiting(
        type="CONFIRMATION",
        field="proposal:opportunity_create",
        question_id="q1",
        prompt="要不要创建这条商机？",
        action_id="act_proposal",
        expected_version=3,
        confirmation_payload=ProposalConfirmation(
            kind="proposal",
            proposal_kind="opportunity_create",
            candidate=candidate,
        ),
    )
    message = _message("m1", waiting.prompt, _task(waiting=waiting))
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    interaction = envelope.blocks[0]
    assert interaction.business_action == "confirm_proposal"
    assert interaction.facts[0].value == "创建商机"
    assert [block.type for block in envelope.blocks] == ["interaction"]


def test_different_prose_stays_beside_the_field_prompt() -> None:
    waiting = TaskWaiting(type="FIELD", field="customer", question_id="q1", prompt="请补充客户名称", action_id="act_1", expected_version=1)
    message = _message("m1", "整理暂时没有完成，请稍后重试。", _task(waiting=waiting))
    envelope = project_assistant_message(message, active_waiting=True, active_boundary=False)
    assert [block.type for block in envelope.blocks] == ["text", "interaction"]
    assert envelope.blocks[0].text == "整理暂时没有完成，请稍后重试。"
    assert envelope.blocks[1].prompt == "请补充客户名称"


def test_root_model_failures_use_fixed_copy_and_retry_only_three_codes() -> None:
    cases = {
        "CONFIGURATION_ERROR": (False, "模型配置不可用"),
        "UPSTREAM_UNAVAILABLE": (True, "模型服务不可达"),
        "UPSTREAM_TIMEOUT": (True, "模型服务响应超时"),
        "MODEL_OUTPUT_INVALID": (True, "模型返回格式异常"),
        "INTERNAL_ERROR": (False, "处理失败"),
    }
    for code, (retryable, title) in cases.items():
        message = _message(
            "acm_123:reply",
            "供应商原文 https://secret.example",
            outcome="failure",
            error_code=code,
            retryable=retryable,
        )
        envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
        error = envelope.blocks[0]
        assert error.type == "error"
        assert error.code == code
        assert error.title == title
        assert "secret.example" not in error.message
        assert "本次没有写入客户活动" in error.message
        assert error.trace_id == "acm_123"
        if retryable:
            assert envelope.suggested_actions[0].action_id == "retry:acm_123"
            assert envelope.suggested_actions[0].label == "重试"
        else:
            assert envelope.suggested_actions == []


def test_organize_failure_keeps_saved_content_sentence_and_skips_root_retry() -> None:
    from app.services.assistant.failure_contract import ORGANIZE_FAILURE_MESSAGE

    message = _message(
        "acm_123:atn_1:4",
        ORGANIZE_FAILURE_MESSAGE,
        outcome="failure",
        error_code="UPSTREAM_TIMEOUT",
        retryable=True,
    )
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    error = envelope.blocks[0]
    assert error.type == "error"
    assert error.code == "UPSTREAM_TIMEOUT"
    assert error.title == "整理未完成"
    assert error.message == ORGANIZE_FAILURE_MESSAGE
    assert error.retryable is True
    assert error.trace_id is None
    assert envelope.suggested_actions == []

    hidden = _message(
        "acm_123:atn_1:5",
        ORGANIZE_FAILURE_MESSAGE,
        outcome="failure",
        error_code="CONFIGURATION_ERROR",
        retryable=False,
    )
    denied = project_assistant_message(hidden, active_waiting=False, active_boundary=False)
    assert denied.blocks[0].retryable is False
    assert denied.suggested_actions == []


def test_downstream_failure_does_not_gain_a_root_retry_action() -> None:
    message = _message(
        "entry:turn:1",
        "处理未完成请重试",
        outcome="failure",
        error_code="RETRYABLE_DEPENDENCY_FAILURE",
        retryable=True,
    )
    envelope = project_assistant_message(message, active_waiting=False, active_boundary=False)
    assert envelope.blocks[0].type == "error"
    assert envelope.blocks[0].message == "处理未完成请重试"
    assert envelope.blocks[0].retryable is False
    assert envelope.suggested_actions == []
    assert envelope.blocks[0].trace_id is None
