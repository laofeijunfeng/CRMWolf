"""Intake contracts: kind pause, structuring failure, draft immutability."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import (
    AssistantAction,
    AssistantTask,
    AssistantTaskStatus,
    AssistantWaitingType,
)
from app.services.assistant.contracts import DraftField, TaskDraft
from app.services.assistant.intake_flow import apply_structured_draft, intake_step
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.llm_contracts import KindDecision, StructureDraftResult
from app.services.assistant.quality_gate import QualityGateOutcome

class RecordingGate:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def evaluate(self, db, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _score(passed=True, score=82):
    return QualityGateOutcome(passed, score, "业务信息完整" if passed else "缺乏事实", "content" if not passed else None, "请补充事实" if not passed else None, {"facts": score})


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class FakeStructurer:
    def __init__(self, kind: KindDecision, structured=None, fail: bool = False):
        self.kind = kind
        self.structured = structured
        self.fail = fail
        self.calls: list[str] = []

    async def classify(self, db, *, team_id, user_text):
        self.calls.append("classify")
        return self.kind

    async def structure(self, db, *, team_id, kind, user_text):
        self.calls.append("structure")
        if self.fail:
            raise AssistantLLMError("模型不可用")
        return self.structured


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[AssistantTask.__table__, AssistantAction.__table__],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_task(session, **overrides):
    values = {
        "team_id": 1,
        "user_id": 2,
        "status": AssistantTaskStatus.ACTIVE,
        "goal": "记录跟进",
        "draft_json": TaskDraft().model_dump(mode="json"),
        "authority_json": {},
        "committed_json": [],
        "version": 0,
    }
    values.update(overrides)
    task = AssistantTask(**values)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


async def test_unclear_kind_pauses_with_kind_question(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="UNCLEAR", reason="线上线下不明"))

    updated, message, waiting, failed = await intake_step(
        db_session, task, "今天和客户聊了很多", structurer
    )

    assert failed is False
    assert waiting is not None
    assert waiting.type == AssistantWaitingType.ACTIVITY_KIND
    assert updated.activity_kind is None
    assert "会议" in message
    assert structurer.calls == ["classify"]


async def test_clear_kind_structures_and_fills_candidates(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content="客户反馈 POC 可行。",
            customer_name="睿狐科技",
            next_action="下周三确认批复",
            next_follow_time_text="下周三",
        ),
    )

    updated, _message, waiting, failed = await intake_step(
        db_session, task, "和睿狐聊了 POC", structurer
    )

    assert failed is False
    assert waiting is None
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.content.status == "CANDIDATE"
    assert draft.content.value == "客户反馈 POC 可行。"
    assert draft.customer.value == "睿狐科技"
    assert draft.next_action.value == "下周三确认批复"
    assert structurer.calls == ["classify", "structure"]


async def test_meeting_structure_fills_customer_candidate(db_session):
    """Meeting structuring must carry customer_name into the draft (2.0 parity

    with follow-up: the name is visible in the original text, so the user
    should never be asked for it afterwards)."""
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="客户方王总确认POC部署可行，预算下季度。",
            customer_name="广州睿狐科技有限公司",
            meeting_subject="与王总线上沟通POC部署",
            participants="我方张工；客户方王总、李经理",
            next_action="先交安全测评报告",
        ),
    )

    updated, _message, waiting, failed = await intake_step(
        db_session, task, "和广州睿狐科技有限公司的王总线上会", structurer
    )

    assert failed is False
    assert waiting is None
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.customer.status == "CANDIDATE"
    assert draft.customer.value == "广州睿狐科技有限公司"
    assert draft.meeting_subject.value == "与王总线上沟通POC部署"


async def test_structuring_failure_fails_closed(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), fail=True)

    updated, message, _waiting, failed = await intake_step(
        db_session, task, "随便一句", structurer
    )

    assert failed is True
    # Transient LLM failure keeps the task retryable, not terminal.
    assert updated.status == AssistantTaskStatus.ACTIVE
    assert updated.last_error_code == "STRUCTURING_UNAVAILABLE"
    assert "稍后重试" in message


async def test_structured_draft_never_overwrites_accepted_slot(db_session):
    task = _make_task(
        db_session,
        draft_json=TaskDraft(
            customer=DraftField(status="ACCEPTED", value="睿狐科技"),
            content=DraftField(status="ACCEPTED", value="已确认的正文"),
        ).model_dump(mode="json"),
    )

    structured = StructureDraftResult(
        kind_confirmed="FOLLOW_UP",
        content="模型想改写正文",
        customer_name="别的公司",
        next_action="新的下一步",
    )
    draft = apply_structured_draft(task, structured)

    # Accepted slots frozen; only the missing slot becomes a candidate.
    assert draft.customer.value == "睿狐科技"
    assert draft.customer.status == "ACCEPTED"
    assert draft.content.value == "已确认的正文"
    assert draft.next_action.status == "CANDIDATE"
    assert draft.next_action.value == "新的下一步"


async def test_follow_up_supplement_merges_canonical_facts_and_rescores_complete_source(db_session):
    task = _make_task(db_session)
    gate = RecordingGate(_score())
    first = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="预算待批", customer_name="睿狐", next_action="周五回访",
        content_json={"content": "预算待批", "customer_feedback": "需要法务确认", "current_progress": "POC验收",
                      "risks": ["预算延迟"], "next_action": "周五回访", "next_follow_time_text": "周五"},
    ))
    initial = "周一客户说预算待批，POC验收，法务还在确认，周五回访"
    updated, _, _, _ = await intake_step(db_session, task, initial, first, gate)
    supplement = "补充：交付团队指出集成延期风险"
    second = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="集成延期", content_json={"content": "集成延期", "risks": ["集成延期"]},
    ))
    updated, _, _, failed = await intake_step(db_session, updated, supplement, second, gate)
    assert not failed
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.source_segments == [initial, supplement]
    assert draft.content_json["customer_feedback"] == "需要法务确认"
    assert draft.content_json["current_progress"] == "POC验收"
    assert draft.content_json["risks"] == ["预算延迟", "集成延期"]
    assert "预算待批" in draft.content_json["content"] and "集成延期" in draft.content_json["content"]
    assert draft.content_json["next_action"] == "周五回访"
    assert second.calls == ["structure"]
    assert gate.calls[-1]["user_text"] == f"{initial}\n{supplement}"
    assert gate.calls[-1]["content_json"] == draft.content_json


async def test_meeting_keeps_two_actions_with_owner_due_date_and_stable_ids(db_session):
    task = _make_task(db_session)
    first = FakeStructurer(KindDecision(kind="ONLINE_MEETING"), StructureDraftResult(
        kind_confirmed="ONLINE_MEETING", content="确认测试排期", customer_name="睿狐", next_action="李经理发方案",
        content_json={"meeting_subject": "季度评审", "key_minutes": ["确认测试排期"],
                      "action_items": [{"owner": "李经理", "action": "发方案", "due_date": "周三"},
                                       {"owner": "王总", "action": "审预算", "due_date": "周五"}]},
    ))
    updated, _, _, _ = await intake_step(db_session, task, "会议决定李经理周三发方案，王总周五审预算", first)
    before = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert len(before) == 2
    assert all(item["item_id"] for item in before)
    assert [(item["owner"], item["action"], item["due_date"]) for item in before] == [
        ("李经理", "发方案", "周三"), ("王总", "审预算", "周五")]
    second = FakeStructurer(KindDecision(kind="ONLINE_MEETING"), StructureDraftResult(
        kind_confirmed="ONLINE_MEETING", content="补充交付要求", content_json={
            "key_minutes": ["补充交付要求"], "action_items": [{"owner": "王总", "action": "审预算", "due_date": "周五"}]},
    ))
    updated, _, _, _ = await intake_step(db_session, updated, "补充交付要求", second)
    after = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert len(after) == 2 and [item["item_id"] for item in after] == [item["item_id"] for item in before]
    assert "补充交付要求" in TaskDraft.model_validate(updated.draft_json).content_json["key_minutes"]


async def test_quality_gate_timeout_fails_closed_without_field_gap(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户已通过验收", customer_name="睿狐", next_action="周三付款"))
    updated, message, waiting, failed = await intake_step(db_session, task, "验收通过", structurer, RecordingGate(TimeoutError()))
    assert failed is True and waiting is None
    assert updated.last_error_code == "QUALITY_GATE_UNAVAILABLE"
    assert updated.status == AssistantTaskStatus.ACTIVE
    assert "稍后重试" in message


async def test_supplement_low_score_clears_old_score_and_asks_new_gap(db_session):
    task = _make_task(db_session)
    first = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户认可测试", customer_name="睿狐", next_action="周三回访"))
    updated, _, _, _ = await intake_step(db_session, task, "客户认可测试", first, RecordingGate(_score()))
    assert TaskDraft.model_validate(updated.draft_json).quality_score.value == "82"
    second = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="采购预算被撤销", next_action="重新讨论"))
    low_gate = RecordingGate(_score(False, 42))
    updated, _, waiting, failed = await intake_step(db_session, updated, "补充：采购预算被撤销", second, low_gate)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert failed is False and waiting is not None and waiting.field == "content"
    assert draft.quality_score.status == "MISSING" and draft.score_reason == "缺乏事实"
    assert draft.score_detail["facts"] == 42
    assert low_gate.calls[0]["content_json"] == draft.content_json


async def test_high_gate_score_never_bypasses_missing_next_action(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户确认项目进度", customer_name="睿狐"))
    updated, _, waiting, failed = await intake_step(db_session, task, "客户确认项目进度", structurer, RecordingGate(_score()))
    assert not failed and waiting is not None and waiting.field == "next_action"
    assert TaskDraft.model_validate(updated.draft_json).quality_score.status == "MISSING"


async def test_accepted_slots_keep_canonical_values_through_model_supplement(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP", draft_json=TaskDraft(
        content=DraftField(status="ACCEPTED", value="人工确认预算未批"),
        next_action=DraftField(status="EXPLICITLY_NONE"),
        content_json={"content": "人工确认预算未批", "next_action": ""},
    ).model_dump(mode="json"))
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="模型错误声称预算已批", next_action="模型凭空添加签合同",
        customer_name="睿狐", content_json={"content": "模型错误声称预算已批", "next_action": "模型凭空添加签合同", "risks": ["预算延迟"]},
    ))
    updated, _, waiting, failed = await intake_step(db_session, task, "补充：预算延迟", structurer, RecordingGate(_score()))
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed and waiting is None
    assert draft.content.value == draft.content_json["content"] == "人工确认预算未批"
    assert draft.next_action.status == "EXPLICITLY_NONE"
    assert draft.content_json["next_action"] == ""
    assert draft.content_json["risks"] == ["预算延迟"]


async def test_invalid_gate_output_is_technical_failure(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="验收通过", next_action="周三回访"))
    updated, _, waiting, failed = await intake_step(db_session, task, "验收通过", structurer, RecordingGate(None))
    assert failed and waiting is None and updated.last_error_code == "QUALITY_GATE_UNAVAILABLE"


async def test_invalid_gate_score_fails_technically(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户确认验收", next_action="周三回访"))
    updated, _, waiting, failed = await intake_step(db_session, task, "确认验收", structurer, RecordingGate(_score(score=101)))
    assert failed and waiting is None and updated.last_error_code == "QUALITY_GATE_UNAVAILABLE"


async def test_explicit_none_reason_survives_restructuring_as_separate_field(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP", draft_json=TaskDraft(
        next_action=DraftField(status="EXPLICITLY_NONE", value="客户决定暂不安排下一步"),
    ).model_dump(mode="json"))
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户还在内部审核", customer_name="睿狐", next_action="模型建议马上签约"))
    updated, _, waiting, failed = await intake_step(db_session, task, "客户内部审核，明确暂无下一步", structurer, RecordingGate(_score()))
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed and waiting is None and draft.quality_score.value == "82"
    # The user's explicit "no next action" is stable; the reason lives in its own
    # canonical field and the model's competing suggestion never leaks into it.
    assert draft.content_json["next_action"] == ""
    assert draft.content_json["next_action_absence_reason"] == "客户决定暂不安排下一步"
    assert draft.next_action.status == "EXPLICITLY_NONE"


async def test_meeting_action_item_ids_survive_schema_roundtrip(db_session):
    from app.services.customer_activity_ai.schemas import MeetingContent

    content = MeetingContent.model_validate({
        "meeting_subject": "评审",
        "action_items": [
            {"owner": "李经理", "action": "发方案", "due_date": "周三", "item_id": "act_stable_1"},
            {"owner": "王总", "action": "审预算", "due_date": "周五"},
        ],
    })
    assert content.action_items[0].item_id == "act_stable_1"
    dumped = content.model_dump(mode="json")["action_items"]
    assert dumped[0]["item_id"] == "act_stable_1"
    assert dumped[1]["item_id"] is None


async def test_meeting_same_owner_action_with_distinct_deadlines_preserves_both(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="OFFLINE_MEETING"), StructureDraftResult(
        kind_confirmed="OFFLINE_MEETING", content="两次审阅", customer_name="睿狐", next_action="李经理分批审阅",
        content_json={"key_minutes": ["两次审阅"], "action_items": [
            {"owner": "李经理", "action": "审阅报告", "due_date": "周三"},
            {"owner": "李经理", "action": "审阅报告", "due_date": "周五"},
        ]},
    ))
    updated, _, _, _ = await intake_step(db_session, task, "李经理周三周五分别审阅报告", structurer)
    actions = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert [(item["owner"], item["action"], item["due_date"]) for item in actions] == [
        ("李经理", "审阅报告", "周三"), ("李经理", "审阅报告", "周五")]
    assert actions[0]["item_id"] != actions[1]["item_id"]


async def test_unclear_kind_retains_initial_user_source_once(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="UNCLEAR", reason="类型不清楚"))
    original = "与客户聊了预算及测试风险"
    updated, _, waiting, failed = await intake_step(db_session, task, original, structurer)
    assert not failed and waiting is not None
    assert TaskDraft.model_validate(updated.draft_json).source_segments == [original]


async def test_new_supplement_invalidates_old_pass_even_if_structuring_fails(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP", draft_json=TaskDraft(
        content=DraftField(status="CANDIDATE", value="预算已批准"),
        next_action=DraftField(status="CANDIDATE", value="周三签约"),
        quality_score=DraftField(status="CANDIDATE", value="89"),
        source_segments=["客户初步反馈预算已批"],
    ).model_dump(mode="json"))
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), fail=True)
    updated, _, waiting, failed = await intake_step(db_session, task, "补充：预算审批被驳回", structurer, RecordingGate(_score()))
    draft = TaskDraft.model_validate(updated.draft_json)
    assert failed and waiting is None
    assert draft.source_segments == ["客户初步反馈预算已批", "补充：预算审批被驳回"]
    assert draft.quality_score.status == "MISSING"


async def test_invalid_canonical_structuring_is_technical_failure(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="ONLINE_MEETING"), StructureDraftResult(
        kind_confirmed="ONLINE_MEETING", content="会议讨论", content_json={"action_items": "not a list"}))
    updated, _, waiting, failed = await intake_step(db_session, task, "讨论会议", structurer, RecordingGate(_score()))
    assert failed and waiting is None and updated.last_error_code == "STRUCTURING_UNAVAILABLE"
    assert TaskDraft.model_validate(updated.draft_json).source_segments == ["讨论会议"]


async def test_follow_up_complete_revision_does_not_duplicate_prior_body(db_session):
    task = _make_task(db_session)
    first = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户认可POC", next_action="周五回访"))
    updated, _, _, _ = await intake_step(db_session, task, "客户认可POC", first)
    second = FakeStructurer(KindDecision(kind="FOLLOW_UP"), StructureDraftResult(
        kind_confirmed="FOLLOW_UP", content="客户认可POC，补充预算待批", next_action="周五回访"))
    updated, _, _, _ = await intake_step(db_session, updated, "预算待批", second)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.content_json["content"] == "客户认可POC，补充预算待批"
