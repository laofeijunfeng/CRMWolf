"""Regression tests for assistant user reply bubble labels (command_label and conversation claim)."""
# ruff: noqa: RUF001 -- Tests assert exact Chinese UI copy.

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask
from app.models.assistant_conversation import AssistantConversation, AssistantConversationEntry
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
from app.schemas.assistant import SubmitInputRequest
from app.schemas.assistant_conversation import ConversationCommandRequest, ConversationDecision
from app.services.assistant import conversation as conversation_module
from app.services.assistant.contracts import (
    ActivityPreview,
    ActivityWriteConfirmation,
    ProfileProposalItem,
    ProposalCandidate,
    ProposalConfirmation,
    TaskDraft,
    TaskWaiting,
)
from app.services.assistant.conversation import ConversationService
from app.services.assistant.history import command_label


@compiles(BigInteger, "sqlite")
def _sqlite_integer(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                AssistantTask,
                AssistantAction,
                AssistantRequest,
                AssistantTurn,
                AssistantTurnEvent,
                AssistantConversation,
                AssistantConversationEntry,
            )
        ],
    )
    monkeypatch.setattr(conversation_module, "schedule_turn", lambda turn_id: None)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


class _StubClassifier:
    async def classify(self, db, **kwargs):
        return ConversationDecision(
            semantic_plan={
                "speech_act": "ASSERT_EVENT",
                "business_object": "CUSTOMER_ACTIVITY",
                "operation": "CREATE",
                "confidence": 0.95,
            },
            task_relation="NEW_TASK",
            route="WORKFLOW",
            boundary="NEW",
            target_task_public_id=None,
            confidence=0.95,
        )


def _req(**kwargs) -> SubmitInputRequest:
    return SubmitInputRequest(
        client_request_id=kwargs.pop("client_request_id", "req-label-1"),
        **kwargs,
    )


def _waiting(wait_type: str, **kwargs) -> TaskWaiting:
    if wait_type == "CONFIRMATION" and "confirmation_payload" not in kwargs:
        kwargs["confirmation_payload"] = ActivityWriteConfirmation(kind="activity_write", preview=_activity_preview())
    return TaskWaiting(
        type=wait_type,
        question_id=kwargs.pop("question_id", "q_1"),
        prompt=kwargs.pop("prompt", "请选择"),
        **kwargs,
    )


def _activity_preview() -> ActivityPreview:
    return ActivityPreview(
        activity_kind="PHONE_FOLLOW_UP",
        customer_name="睿狐科技",
        summary="确认下周部署计划",
        content_json={"summary": "确认下周部署计划"},
        source_content="电话沟通确认下周部署计划",
        score=80,
        score_reason="内容完整",
    )


@pytest.mark.parametrize(
    ("payload", "waiting", "expected"),
    [
        (
            _req(kind="submit_field", choice="cus_1"),
            _waiting(
                "OBJECT_SELECTION",
                field="customer",
                candidates=[{"id": "cus_1", "account_name": "睿狐科技"}],
            ),
            "睿狐科技",
        ),
        (
            _req(kind="submit_field", choice="__new_customer__"),
            _waiting(
                "OBJECT_SELECTION",
                field="customer",
                candidates=[
                    {"id": "cus_1", "label": "睿狐科技"},
                    {"id": "__new_customer__", "label": "新建客户"},
                ],
            ),
            "新建客户",
        ),
        (
            _req(kind="submit_field", choice="opp_1"),
            _waiting(
                "OBJECT_SELECTION",
                field="opportunity",
                candidates=[{"id": "opp_1", "label": "二期扩容项目"}],
            ),
            "二期扩容项目",
        ),
        (
            _req(kind="submit_field", choice="missing_opp"),
            _waiting("OBJECT_SELECTION", field="opportunity", candidates=[]),
            "选择商机",
        ),
        (
            _req(kind="submit_field", choice="missing_intent"),
            _waiting("OBJECT_SELECTION", field="intent", candidates=[]),
            "选择意图",
        ),
        (
            _req(kind="submit_field", choice="missing_customer"),
            _waiting("OBJECT_SELECTION", field="customer", candidates=[]),
            "选择客户",
        ),
        (
            _req(kind="submit_field", choice="resume"),
            _waiting(
                "ENTITY_DEFERRED",
                field="resume",
                candidates=[{"id": "resume", "label": "继续填写"}, {"id": "cancel", "label": "不要了"}],
            ),
            "继续填写",
        ),
        (
            _req(kind="submit_field", choice="cancel"),
            _waiting(
                "ENTITY_DEFERRED",
                field="resume",
                candidates=[{"id": "resume", "label": "继续填写"}, {"id": "cancel", "label": "不要了"}],
            ),
            "不要了",
        ),
        (
            _req(kind="submit_field", choice="FOLLOW_UP"),
            _waiting("ACTIVITY_KIND", field="activity_kind"),
            "普通跟进",
        ),
        (
            _req(kind="submit_field", choice="PHONE_FOLLOW_UP"),
            _waiting("ACTIVITY_KIND", field="activity_kind"),
            "电话跟进",
        ),
        (
            _req(kind="revise_activity_kind", choice="FOLLOW_UP"),
            _waiting("CONFIRMATION", field="activity_write"),
            "改为普通跟进",
        ),
        (
            _req(kind="revise_activity_kind", choice="ONLINE_MEETING"),
            _waiting("CONFIRMATION", field="activity_write"),
            "改为线上会议",
        ),
        (
            _req(kind="revise_activity_kind", choice="UNKNOWN_KIND"),
            _waiting("CONFIRMATION", field="activity_write"),
            "修改活动类型",
        ),
        (
            _req(kind="confirm", choice="confirm"),
            _waiting(
                "CONFIRMATION",
                field="activity_write",
                confirmation_payload=ActivityWriteConfirmation(kind="activity_write", preview=_activity_preview()),
            ),
            "确认写入",
        ),
        (
            _req(kind="confirm", choice="confirm"),
            _waiting(
                "CONFIRMATION",
                field="proposal:customer_fact",
                confirmation_payload=ProposalConfirmation(
                    kind="proposal",
                    proposal_kind="customer_fact",
                    candidate=ProposalCandidate(
                        kind="customer_fact",
                        key="fact:company_size",
                        payload={"fact_type": "company_size", "value": "200人"},
                        evidence_quote="客户约 200 人",
                        activity_id=1,
                        customer_id=10,
                        source_revision=1,
                    ),
                ),
            ),
            "确认",
        ),
        (
            _req(kind="confirm", choice="reject"),
            _waiting("CONFIRMATION", field="activity_write"),
            "取消",
        ),
        (
            _req(kind="confirm", choice="reject", reason="wrong_customer"),
            _waiting("CONFIRMATION", field="activity_write"),
            "取消（客户不对）",
        ),
        (
            _req(kind="confirm", choice="reject", reason="wrong_content"),
            _waiting("CONFIRMATION", field="activity_write"),
            "取消（内容不对）",
        ),
        (
            _req(kind="confirm", choice="reject", reason="should_not_record"),
            _waiting("CONFIRMATION", field="activity_write"),
            "取消（不该记录）",
        ),
        (
            _req(kind="confirm", choice="reject", reason="other"),
            _waiting("CONFIRMATION", field="activity_write"),
            "取消（其他）",
        ),
        (
            _req(kind="request_edit"),
            _waiting("CONFIRMATION", field="activity_write"),
            "修改内容",
        ),
        (
            _req(kind="cancel"),
            _waiting("FIELD", field="content"),
            "算了，不记了",
        ),
        (
            _req(kind="submit_form", form_revision=1, values={"name": "王敏"}),
            _waiting("ENTITY_FORM", field="contact_create", form_revision=1),
            "提交",
        ),
        (
            _req(kind="submit_form", form_revision=1, choice="defer"),
            _waiting("ENTITY_FORM", field="contact_create", form_revision=1),
            "稍后补充",
        ),
        (
            _req(kind="submit_form", form_revision=1, choice="cancel"),
            _waiting("ENTITY_FORM", field="contact_create", form_revision=1),
            "取消",
        ),
        (
            _req(kind="submit_form", form_revision=1, choice="cancel"),
            _waiting("CONFIRMATION_EDIT", field="activity_write", form_revision=1),
            "取消修改",
        ),
        (
            _req(kind="submit_field", choice="2026-11-26"),
            _waiting(
                "FIELD",
                field="temporal_choice",
                candidates=[{"id": "2026-11-26", "label": "昨天（11月26日）"}],
            ),
            "昨天（11月26日）",
        ),
        (
            _req(kind="submit_field", choice="EXPLICITLY_NONE", text="这次暂不约定下一步"),
            _waiting("FIELD", field="next_action"),
            "这次暂不约定下一步",
        ),
        (
            _req(kind="submit_field", choice="EXPLICITLY_NONE"),
            _waiting("FIELD", field="next_action"),
            "暂无下一步行动",
        ),
    ],
)
def test_command_label_matrix(payload, waiting, expected):
    assert command_label(payload, waiting) == expected


@pytest.mark.parametrize(
    ("choices", "suppress_week", "expected"),
    [
        (["item_1"], False, "标记完成：发送报价单"),
        (["item_1"], True, "标记完成：发送报价单 · 本周不再提示"),
        (["item_1", "item_2"], False, "标记完成 2 项：发送报价单 等"),
        (["item_1", "item_2"], True, "标记完成 2 项：发送报价单 等 · 本周不再提示"),
        ([], False, "暂不标记完成"),
        ([], True, "本周不再提示"),
    ],
)
def test_command_label_follow_up_disposition(choices, suppress_week, expected):
    waiting = _waiting(
        "FOLLOW_UP_DISPOSITION",
        field="open_follow_up",
        candidates=[
            {"id": "item_1", "label": "发送报价单"},
            {"id": "item_2", "label": "约技术评审"},
        ],
    )
    payload = _req(kind="submit_field", choices=choices, suppress_week=suppress_week)
    assert command_label(payload, waiting) == expected


def test_command_label_profile_proposals_with_prefix_dedup_and_clipping():
    long_summary = "开票抬头：" + "这是一段超过四十个字的开票抬头详情描述用于验证截断行为是否与卡片选项完全一致"
    proposals = [
        ProfileProposalItem(kind="contact_create", summary="联系人：王敏 13800138000", quote="王敏负责对接"),
        ProfileProposalItem(kind="invoice_title_create", summary=long_summary, quote="开票信息如下"),
        ProfileProposalItem(kind="contact_supplement", summary="补充 孙自豪（邮箱、备注）", quote="孙自豪邮箱换了"),
    ]
    waiting = _waiting(
        "PROFILE_PROPOSALS",
        field="profile_proposals",
        candidates=[
            {"id": "go:0", "label": "打开建档表单"},
            {"id": "skip:0", "label": "不保存"},
            {"id": "go:1", "label": "打开建档表单"},
            {"id": "skip:1", "label": "不保存"},
            {"id": "go:2", "label": "打开补充表单"},
            {"id": "skip:2", "label": "不保存"},
            {"id": "none", "label": "全部不保存"},
        ],
    )

    assert (
        command_label(_req(kind="submit_field", choice="go:0"), waiting, profile_proposals=proposals)
        == "打开建档表单：新建联系人：王敏 13800138000"
    )
    assert (
        command_label(_req(kind="submit_field", choice="skip:0"), waiting, profile_proposals=proposals)
        == "不保存：新建联系人：王敏 13800138000"
    )
    assert (
        command_label(_req(kind="submit_field", choice="go:2"), waiting, profile_proposals=proposals)
        == "打开补充表单：更新已有联系人：孙自豪（邮箱、备注）"
    )
    clipped = command_label(
        _req(kind="submit_field", choice="go:1"),
        waiting,
        profile_proposals=proposals,
    )
    assert clipped.startswith("打开建档表单：新建开票抬头：这是一段")
    assert len(clipped.removeprefix("打开建档表单：")) == 40
    assert (
        command_label(_req(kind="submit_field", choice="none"), waiting, profile_proposals=proposals)
        == "全部不保存"
    )
    # Without profile_proposals context, falls back cleanly to candidate label.
    assert command_label(_req(kind="submit_field", choice="go:0"), waiting) == "打开建档表单"


async def test_conversation_command_persists_profile_proposal_and_disposition_labels(db):
    proposals = [
        ProfileProposalItem(kind="contact_create", summary="王敏（采购总监）", quote="联系王敏").model_dump(mode="json")
    ]
    proposal_task = AssistantTask(
        team_id=1,
        user_id=2,
        goal="补充客户资料",
        status="ACTIVE",
        version=2,
        waiting_type="PROFILE_PROPOSALS",
        waiting_field="profile_proposals",
        waiting_json={
            "action_id": "act-profile",
            "payload": {
                "question_id": "q_profile",
                "prompt": "以下客户资料是否需要保存？",
                "candidates": [
                    {"id": "go:0", "label": "去补充"},
                    {"id": "skip:0", "label": "不保存"},
                    {"id": "none", "label": "都不需要"},
                ],
            },
        },
        draft_json=TaskDraft().model_dump(mode="json"),
        authority_json={"profile_proposals": proposals},
        committed_json=[],
    )
    db.add(proposal_task)
    db.commit()

    service = ConversationService(classifier=_StubClassifier())
    state = service.open(db, team_id=1, user_id=2)
    reply = await service.command(
        db,
        team_id=1,
        user_id=2,
        request=ConversationCommandRequest(
            task_public_id=proposal_task.public_id,
            expected_version=state.version,
            input=SubmitInputRequest(
                kind="submit_field",
                choice="go:0",
                action_id="act-profile",
                expected_version=2,
                client_request_id="profile-go-0",
            ),
        ),
    )
    assert any(
        m.role == "user" and m.text == "去补充：新建联系人：王敏（采购总监）"
        for m in reply.conversation.messages
    )
