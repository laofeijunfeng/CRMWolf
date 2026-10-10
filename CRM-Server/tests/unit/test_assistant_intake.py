"""Intake contracts: kind pause, structuring failure, draft immutability."""
# ruff: noqa: RUF001

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
from app.models.assistant_turn import AssistantRequest, AssistantTurn, AssistantTurnEvent
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
    return QualityGateOutcome(
        passed,
        score,
        "业务信息完整" if passed else "缺乏事实",
        "content" if not passed else None,
        "请补充事实" if not passed else None,
        {"facts": score},
    )


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
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            AssistantRequest.__table__,
            AssistantTurn.__table__,
            AssistantTurnEvent.__table__,
        ],
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

    updated, message, waiting, failed = await intake_step(db_session, task, "今天和客户聊了很多", structurer)

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

    updated, _message, waiting, failed = await intake_step(db_session, task, "和睿狐聊了 POC", structurer)

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

    updated, message, _waiting, failed = await intake_step(db_session, task, "随便一句", structurer)

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
    first = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content="预算待批",
            customer_name="睿狐",
            next_action="周五回访",
            content_json={
                "content": "预算待批",
                "customer_feedback": "需要法务确认",
                "current_progress": "POC验收",
                "risks": ["预算延迟"],
                "next_action": "周五回访",
                "next_follow_time_text": "周五",
            },
        ),
    )
    initial = "周一客户说预算待批，POC验收，法务还在确认，周五回访"
    updated, _, _, _ = await intake_step(db_session, task, initial, first, gate)
    supplement = "补充：交付团队指出集成延期风险"
    second = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content="集成延期",
            content_json={"content": "集成延期", "risks": ["集成延期"]},
        ),
    )
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
    first = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="确认测试排期",
            customer_name="睿狐",
            next_action="李经理发方案",
            content_json={
                "meeting_subject": "季度评审",
                "key_minutes": ["确认测试排期"],
                "action_items": [
                    {"owner": "李经理", "action": "发方案", "due_date": "周三"},
                    {"owner": "王总", "action": "审预算", "due_date": "周五"},
                ],
            },
        ),
    )
    updated, _, _, _ = await intake_step(db_session, task, "会议决定李经理周三发方案，王总周五审预算", first)
    before = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert len(before) == 2
    assert all(item["item_id"] for item in before)
    assert [(item["owner"], item["action"], item["due_date"]) for item in before] == [
        ("李经理", "发方案", "周三"),
        ("王总", "审预算", "周五"),
    ]
    second = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="补充交付要求",
            content_json={
                "key_minutes": ["补充交付要求"],
                "action_items": [{"owner": "王总", "action": "审预算", "due_date": "周五"}],
            },
        ),
    )
    updated, _, _, _ = await intake_step(db_session, updated, "补充交付要求", second)
    after = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert len(after) == 2 and [item["item_id"] for item in after] == [item["item_id"] for item in before]
    assert "补充交付要求" in TaskDraft.model_validate(updated.draft_json).content_json["key_minutes"]


async def test_quality_gate_timeout_fails_closed_without_field_gap(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP", content="客户已通过验收", customer_name="睿狐", next_action="周三付款"
        ),
    )
    updated, message, waiting, failed = await intake_step(
        db_session, task, "验收通过", structurer, RecordingGate(TimeoutError())
    )
    assert failed is True and waiting is None
    assert updated.last_error_code == "QUALITY_GATE_UNAVAILABLE"
    assert updated.status == AssistantTaskStatus.ACTIVE
    assert "稍后重试" in message


async def test_supplement_low_score_clears_old_score_and_asks_new_gap(db_session):
    task = _make_task(db_session)
    first = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP", content="客户认可测试", customer_name="睿狐", next_action="周三回访"
        ),
    )
    updated, _, _, _ = await intake_step(db_session, task, "客户认可测试", first, RecordingGate(_score()))
    assert TaskDraft.model_validate(updated.draft_json).quality_score.value == "82"
    second = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="采购预算被撤销", next_action="重新讨论"),
    )
    low_gate = RecordingGate(_score(False, 42))
    updated, _, waiting, failed = await intake_step(db_session, updated, "补充：采购预算被撤销", second, low_gate)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert failed is False and waiting is not None and waiting.field == "content"
    assert draft.quality_score.status == "MISSING" and draft.score_reason == "缺乏事实"
    assert draft.score_detail["facts"] == 42
    assert low_gate.calls[0]["content_json"] == draft.content_json


async def test_high_gate_score_never_bypasses_missing_next_action(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="客户确认项目进度", customer_name="睿狐"),
    )
    updated, _, waiting, failed = await intake_step(
        db_session, task, "客户确认项目进度", structurer, RecordingGate(_score())
    )
    assert not failed and waiting is not None and waiting.field == "next_action"
    assert TaskDraft.model_validate(updated.draft_json).quality_score.status == "MISSING"


async def test_accepted_slots_keep_canonical_values_through_model_supplement(db_session):
    task = _make_task(
        db_session,
        activity_kind="FOLLOW_UP",
        draft_json=TaskDraft(
            content=DraftField(status="ACCEPTED", value="人工确认预算未批"),
            next_action=DraftField(status="EXPLICITLY_NONE"),
            content_json={"content": "人工确认预算未批", "next_action": ""},
        ).model_dump(mode="json"),
    )
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP",
            content="模型错误声称预算已批",
            next_action="模型凭空添加签合同",
            customer_name="睿狐",
            content_json={
                "content": "模型错误声称预算已批",
                "next_action": "模型凭空添加签合同",
                "risks": ["预算延迟"],
            },
        ),
    )
    updated, _, waiting, failed = await intake_step(
        db_session, task, "补充：预算延迟", structurer, RecordingGate(_score())
    )
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed and waiting is None
    assert draft.content.value == draft.content_json["content"] == "人工确认预算未批"
    assert draft.next_action.status == "EXPLICITLY_NONE"
    assert draft.content_json["next_action"] == ""
    assert draft.content_json["risks"] == ["预算延迟"]


async def test_invalid_gate_output_is_technical_failure(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="验收通过", next_action="周三回访"),
    )
    updated, _, waiting, failed = await intake_step(db_session, task, "验收通过", structurer, RecordingGate(None))
    assert failed and waiting is None and updated.last_error_code == "QUALITY_GATE_UNAVAILABLE"


async def test_invalid_gate_score_fails_technically(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="客户确认验收", next_action="周三回访"),
    )
    updated, _, waiting, failed = await intake_step(
        db_session, task, "确认验收", structurer, RecordingGate(_score(score=101))
    )
    assert failed and waiting is None and updated.last_error_code == "QUALITY_GATE_UNAVAILABLE"


async def test_explicit_none_reason_survives_restructuring_as_separate_field(db_session):
    task = _make_task(
        db_session,
        activity_kind="FOLLOW_UP",
        draft_json=TaskDraft(
            next_action=DraftField(status="EXPLICITLY_NONE", value="客户决定暂不安排下一步"),
        ).model_dump(mode="json"),
    )
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP", content="客户还在内部审核", customer_name="睿狐", next_action="模型建议马上签约"
        ),
    )
    updated, _, waiting, failed = await intake_step(
        db_session, task, "客户内部审核，明确暂无下一步", structurer, RecordingGate(_score())
    )
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed and waiting is None and draft.quality_score.value == "82"
    # The user's explicit "no next action" is stable; the reason lives in its own
    # canonical field and the model's competing suggestion never leaks into it.
    assert draft.content_json["next_action"] == ""
    assert draft.content_json["next_action_absence_reason"] == "客户决定暂不安排下一步"
    assert draft.next_action.status == "EXPLICITLY_NONE"


async def test_meeting_action_item_ids_survive_schema_roundtrip(db_session):
    from app.services.customer_activity_ai.schemas import MeetingContent

    content = MeetingContent.model_validate(
        {
            "meeting_subject": "评审",
            "action_items": [
                {"owner": "李经理", "action": "发方案", "due_date": "周三", "item_id": "act_stable_1"},
                {"owner": "王总", "action": "审预算", "due_date": "周五"},
            ],
        }
    )
    assert content.action_items[0].item_id == "act_stable_1"
    dumped = content.model_dump(mode="json")["action_items"]
    assert dumped[0]["item_id"] == "act_stable_1"
    assert dumped[1]["item_id"] is None


async def test_meeting_same_owner_action_with_distinct_deadlines_preserves_both(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="OFFLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="OFFLINE_MEETING",
            content="两次审阅",
            customer_name="睿狐",
            next_action="李经理分批审阅",
            content_json={
                "key_minutes": ["两次审阅"],
                "action_items": [
                    {"owner": "李经理", "action": "审阅报告", "due_date": "周三"},
                    {"owner": "李经理", "action": "审阅报告", "due_date": "周五"},
                ],
            },
        ),
    )
    updated, _, _, _ = await intake_step(db_session, task, "李经理周三周五分别审阅报告", structurer)
    actions = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert [(item["owner"], item["action"], item["due_date"]) for item in actions] == [
        ("李经理", "审阅报告", "周三"),
        ("李经理", "审阅报告", "周五"),
    ]
    assert actions[0]["item_id"] != actions[1]["item_id"]


async def test_unclear_kind_retains_initial_user_source_once(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(KindDecision(kind="UNCLEAR", reason="类型不清楚"))
    original = "与客户聊了预算及测试风险"
    updated, _, waiting, failed = await intake_step(db_session, task, original, structurer)
    assert not failed and waiting is not None
    assert TaskDraft.model_validate(updated.draft_json).source_segments == [original]


async def test_new_supplement_invalidates_old_pass_even_if_structuring_fails(db_session):
    task = _make_task(
        db_session,
        activity_kind="FOLLOW_UP",
        draft_json=TaskDraft(
            content=DraftField(status="CANDIDATE", value="预算已批准"),
            next_action=DraftField(status="CANDIDATE", value="周三签约"),
            quality_score=DraftField(status="CANDIDATE", value="89"),
            source_segments=["客户初步反馈预算已批"],
        ).model_dump(mode="json"),
    )
    structurer = FakeStructurer(KindDecision(kind="FOLLOW_UP"), fail=True)
    updated, _, waiting, failed = await intake_step(
        db_session, task, "补充：预算审批被驳回", structurer, RecordingGate(_score())
    )
    draft = TaskDraft.model_validate(updated.draft_json)
    assert failed and waiting is None
    assert draft.source_segments == ["客户初步反馈预算已批", "补充：预算审批被驳回"]
    assert draft.quality_score.status == "MISSING"


async def test_invalid_canonical_structuring_is_technical_failure(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING", content="会议讨论", content_json={"action_items": "not a list"}
        ),
    )
    updated, _, waiting, failed = await intake_step(db_session, task, "讨论会议", structurer, RecordingGate(_score()))
    assert failed and waiting is None and updated.last_error_code == "STRUCTURING_UNAVAILABLE"
    assert TaskDraft.model_validate(updated.draft_json).source_segments == ["讨论会议"]


async def test_follow_up_complete_revision_does_not_duplicate_prior_body(db_session):
    task = _make_task(db_session)
    first = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="客户认可POC", next_action="周五回访"),
    )
    updated, _, _, _ = await intake_step(db_session, task, "客户认可POC", first)
    second = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="客户认可POC，补充预算待批", next_action="周五回访"),
    )
    updated, _, _, _ = await intake_step(db_session, updated, "预算待批", second)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.content_json["content"] == "客户认可POC，补充预算待批"


async def test_meeting_explicit_none_removes_actions_and_dates_after_restructuring(db_session):
    reason = "等待客户内部盘点，批准前不安排新动作"
    task = _make_task(
        db_session,
        activity_kind="ONLINE_MEETING",
        draft_json=TaskDraft(
            next_action=DraftField(status="EXPLICITLY_NONE", value=reason),
            next_follow_time=DraftField(status="ACCEPTED", value="下周三"),
            content_json={
                "meeting_subject": "盘点评审",
                "next_step_summary": "我发方案",
                "action_items": [{"owner": "我", "action": "发方案", "due_date": "下周三"}],
            },
            source_segments=["我下周三发方案", reason],
        ).model_dump(mode="json"),
    )
    structurer = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="客户仍在内部盘点",
            next_action="我发方案",
            content_json={
                "key_minutes": ["客户仍在内部盘点"],
                "next_step_summary": "我发方案",
                "action_items": [{"owner": "我", "action": "发方案", "due_date": "下周三"}],
            },
        ),
    )
    updated, _, waiting, failed = await intake_step(db_session, task, reason, structurer, RecordingGate(_score()))
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed and waiting is None
    assert draft.content_json["action_items"] == []
    assert draft.content_json["next_step_summary"] == ""
    assert draft.content_json["next_action_absence_reason"] == reason
    assert draft.next_follow_time.value is None
    assert draft.source_segments == ["我下周三发方案", reason]


async def test_meeting_natural_deadline_is_anchored_to_accepted_source(db_session, monkeypatch):
    from datetime import datetime

    accepted_at = datetime(2026, 10, 8, 23, 59)
    monkeypatch.setattr("app.utils.time.business_now", lambda: accepted_at)
    source = "我下周三下午三点发方案"
    task = _make_task(db_session, activity_kind="ONLINE_MEETING")
    structurer = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="评审方案",
            next_action="我发方案",
            content_json={
                "key_minutes": ["评审方案"],
                "action_items": [{"owner": "我", "action": "发方案", "due_date": "下周三下午三点"}],
            },
        ),
    )
    updated, _, _, failed = await intake_step(db_session, task, source, structurer)
    draft = TaskDraft.model_validate(updated.draft_json)
    evidence = draft.content_json.get("action_evidence", [])
    assert not failed and evidence
    action = evidence[0]
    assert action["due_at"] == "2026-10-14T15:00:00"
    assert action["due_at_text"] == "下周三下午三点"
    assert action["granularity"] == "DATETIME"
    assert action["anchor_at"] == accepted_at.isoformat()
    assert action["evidence_quote"] == source
    monkeypatch.setattr("app.utils.time.business_now", lambda: datetime(2026, 10, 10, 8))
    updated, _, _, _ = await intake_step(
        db_session,
        updated,
        "补充客户认可方案",
        FakeStructurer(
            KindDecision(kind="ONLINE_MEETING"),
            StructureDraftResult(kind_confirmed="ONLINE_MEETING", content="客户认可方案"),
        ),
    )
    assert TaskDraft.model_validate(updated.draft_json).content_json["action_evidence"][0] == action


async def test_explicit_deadline_correction_revokes_old_action_eligibility(db_session):
    task = _make_task(db_session, activity_kind="ONLINE_MEETING")
    first = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="评审",
            next_action="我发方案",
            content_json={"action_items": [{"owner": "我", "action": "发方案", "due_date": "下周三"}]},
        ),
    )
    updated, _, _, _ = await intake_step(db_session, task, "我下周三发方案", first)
    before = TaskDraft.model_validate(updated.draft_json).content_json["action_items"][0]
    correction = "更正：我发方案不是下周三，改为下周五下午三点"
    second = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="修正时间",
            next_action="我发方案",
            content_json={"action_items": [{"owner": "我", "action": "发方案", "due_date": "下周五下午三点"}]},
        ),
    )
    updated, _, _, failed = await intake_step(db_session, updated, correction, second)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed
    assert [(item["item_id"], item["due_date"]) for item in draft.content_json["action_items"]] == [
        (before["item_id"], "下周五下午三点")
    ]
    assert draft.source_segments == ["我下周三发方案", correction]
    assert [item["state"] for item in draft.content_json["action_evidence"]] == ["SUPERSEDED", "ACTIVE"]


async def test_model_cannot_choose_new_action_identity(db_session):
    task = _make_task(db_session, activity_kind="ONLINE_MEETING")
    structurer = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="评审",
            next_action="我发方案",
            content_json={
                "action_items": [
                    {"item_id": "model_authority", "owner": "我", "action": "发方案", "due_date": "下周三"}
                ]
            },
        ),
    )
    updated, _, _, failed = await intake_step(db_session, task, "我下周三发方案", structurer)
    assert not failed
    action = TaskDraft.model_validate(updated.draft_json).content_json["action_items"][0]
    assert action["item_id"] != "model_authority"
    assert action["item_id"].startswith("act_")


async def test_unrelated_correction_does_not_replace_a_second_real_action(db_session):
    task = _make_task(db_session, activity_kind="ONLINE_MEETING")
    first = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="分批发方案",
            next_action="我发方案",
            content_json={"action_items": [{"owner": "我", "action": "发方案", "due_date": "下周三"}]},
        ),
    )
    updated, _, _, _ = await intake_step(db_session, task, "我下周三发方案", first)
    before = TaskDraft.model_validate(updated.draft_json).content_json["action_items"][0]
    second = FakeStructurer(
        KindDecision(kind="ONLINE_MEETING"),
        StructureDraftResult(
            kind_confirmed="ONLINE_MEETING",
            content="分批发方案",
            next_action="我发方案",
            content_json={"action_items": [{"owner": "我", "action": "发方案", "due_date": "下周五"}]},
        ),
    )
    updated, _, _, failed = await intake_step(db_session, updated, "预算不是20万，是30万；我下周五发方案", second)
    actions = TaskDraft.model_validate(updated.draft_json).content_json["action_items"]
    assert not failed
    assert (actions[0]["item_id"], actions[0]["due_date"]) == (before["item_id"], "下周三")
    assert [item["due_date"] for item in actions] == ["下周三", "下周五"]


async def test_same_source_in_new_accepted_turn_is_not_swallowed_as_a_retry(db_session):
    from datetime import datetime

    from app.services.assistant.turns import accept_submit

    source = "我下周三发方案"
    task = _make_task(db_session, activity_kind="FOLLOW_UP")
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(
            kind_confirmed="FOLLOW_UP", content=source, next_action="我发方案", next_follow_time_text="下周三"
        ),
    )
    gate = RecordingGate(_score())
    first, _ = accept_submit(
        db_session,
        task=task,
        key="source-event-first",
        input_data={"kind": "text", "text": source},
        action_id=None,
        expected_version=None,
    )
    first.created_time = datetime(2026, 10, 8, 23, 59)
    db_session.commit()
    db_session.refresh(task)
    updated, _, _, _ = await intake_step(db_session, task, source, structurer, gate)
    db_session.commit()
    await intake_step(db_session, updated, source, structurer, gate)
    assert len(gate.calls) == 1
    updated.active_turn_id = None
    first.status = "SUCCEEDED"
    db_session.commit()
    second, _ = accept_submit(
        db_session,
        task=updated,
        key="source-event-second",
        input_data={"kind": "text", "text": source},
        action_id=None,
        expected_version=None,
    )
    second.created_time = datetime(2026, 10, 10, 8)
    db_session.commit()
    db_session.refresh(updated)
    updated, _, _, failed = await intake_step(db_session, updated, source, structurer, gate)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert not failed
    assert [(record.turn_id, record.recorded_at) for record in draft.source_records] == [
        (first.public_id, first.created_time),
        (second.public_id, second.created_time),
    ]
    assert draft.source_segments == [source, source]
    assert len(gate.calls) == 2


@pytest.mark.parametrize("mode", ["success", "unavailable", "unclear"])
async def test_reorganization_cannot_accept_goal_as_new_source(db_session, mode):
    original = "已接受的虚构客户沟通"
    task = _make_task(
        db_session,
        activity_kind=None if mode == "unclear" else "FOLLOW_UP",
        goal="选择类型用的目标描述，不是新活动原话",
        draft_json=TaskDraft(source_segments=[original]).model_dump(mode="json"),
    )
    structured = StructureDraftResult(kind_confirmed="FOLLOW_UP", content="虚构客户沟通", next_action="继续沟通")
    structurer = FakeStructurer(
        KindDecision(kind="UNCLEAR" if mode == "unclear" else "FOLLOW_UP"), structured, fail=mode == "unavailable"
    )
    updated, _, _, _ = await intake_step(db_session, task, task.goal, structurer, accept_source=False)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.source_segments == [original]
    assert draft.source_records == []
