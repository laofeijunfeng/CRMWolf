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
from app.services.assistant.failure_contract import (
    ORGANIZE_FAILURE_MESSAGE,
    QUALITY_GATE_FAILURE_MESSAGE,
    AssistantFailureCode,
    AssistantStageFailure,
)
from app.services.assistant.intake_flow import apply_structured_draft, intake_step
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.llm_contracts import KindDecision, ModelDraftAction, StructureDraftResult
from app.services.assistant.quality_gate import QualityGateOutcome
from app.services.assistant.temporal_evidence import TemporalContractError


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



def _structure_failure(session, task_id: int) -> dict:
    action = (
        session.query(AssistantAction)
        .filter_by(task_id=task_id, action="structure_draft")
        .order_by(AssistantAction.id.desc())
        .first()
    )
    assert action is not None
    return action.result_json



async def _stage_failure(db_session, task, *args, **kwargs):
    with pytest.raises(AssistantStageFailure) as caught:
        await intake_step(db_session, task, *args, **kwargs)
    db_session.refresh(task)
    return task, caught.value


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

    updated, failure = await _stage_failure(db_session, task, "随便一句", structurer)

    assert failure.code is AssistantFailureCode.STRUCTURING_UNAVAILABLE
    assert failure.retryable is False
    assert failure.stage == "structure"
    assert "依赖暂不可用" in failure.user_message
    assert updated.status == AssistantTaskStatus.ACTIVE
    assert updated.waiting_type is None
    assert updated.last_error_code == "STRUCTURING_UNAVAILABLE"
    assert updated.committed_json == []
    assert TaskDraft.model_validate(updated.draft_json).source_segments == ["随便一句"]
    logged = _structure_failure(db_session, updated.id)
    assert logged["failure"] == "provider_schema"
    assert logged["code"] == "STRUCTURING_UNAVAILABLE"
    assert logged["retryable"] is False
    assert logged["error_type"] == "AssistantLLMError"
    assert "模型不可用" in logged["cause"]


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
    updated, failure = await _stage_failure(
        db_session, task, "验收通过", structurer, RecordingGate(TimeoutError())
    )
    assert failure.code is AssistantFailureCode.UPSTREAM_TIMEOUT
    assert failure.retryable is True
    assert failure.stage == "quality_gate"
    assert failure.user_message == QUALITY_GATE_FAILURE_MESSAGE
    assert updated.waiting_type is None
    assert updated.last_error_code == "UPSTREAM_TIMEOUT"
    assert updated.status == AssistantTaskStatus.ACTIVE
    assert updated.committed_json == []
    assert "验收通过" in TaskDraft.model_validate(updated.draft_json).source_segments


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
    updated, failure = await _stage_failure(db_session, task, "验收通过", structurer, RecordingGate(None))
    assert failure.code is AssistantFailureCode.MODEL_OUTPUT_INVALID and failure.retryable is True
    assert updated.waiting_type is None and updated.last_error_code == "MODEL_OUTPUT_INVALID"


async def test_invalid_gate_score_fails_technically(db_session):
    task = _make_task(db_session)
    structurer = FakeStructurer(
        KindDecision(kind="FOLLOW_UP"),
        StructureDraftResult(kind_confirmed="FOLLOW_UP", content="客户确认验收", next_action="周三回访"),
    )
    updated, failure = await _stage_failure(
        db_session, task, "确认验收", structurer, RecordingGate(_score(score=101))
    )
    assert failure.code is AssistantFailureCode.MODEL_OUTPUT_INVALID and failure.stage == "quality_gate"
    assert updated.waiting_type is None and updated.last_error_code == "MODEL_OUTPUT_INVALID"


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
    updated, failure = await _stage_failure(
        db_session, task, "补充：预算审批被驳回", structurer, RecordingGate(_score())
    )
    draft = TaskDraft.model_validate(updated.draft_json)
    assert failure.stage == "structure" and updated.waiting_type is None
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
    updated, failure = await _stage_failure(db_session, task, "讨论会议", structurer, RecordingGate(_score()))
    assert failure.code is AssistantFailureCode.MODEL_OUTPUT_INVALID and failure.retryable is True
    assert updated.waiting_type is None and updated.last_error_code == "MODEL_OUTPUT_INVALID"
    assert TaskDraft.model_validate(updated.draft_json).source_segments == ["讨论会议"]
    assert updated.committed_json == []
    logged = _structure_failure(db_session, updated.id)
    assert logged["failure"] == "draft_merge"
    assert logged["stage"] == "structure"
    assert logged["error_type"] == "ValidationError"


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
    if mode == "unavailable":
        updated, _failure = await _stage_failure(db_session, task, task.goal, structurer, accept_source=False)
    else:
        updated, _, _, _ = await intake_step(db_session, task, task.goal, structurer, accept_source=False)
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.source_segments == [original]
    assert draft.source_records == []


async def test_temporal_contract_failure_keeps_its_cause(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP")

    class MissingTime(FakeStructurer):
        async def structure(self, db, *, team_id, kind, user_text):
            raise TemporalContractError("temporal mentions do not cover the source")

    updated, failure = await _stage_failure(
        db_session, task, "我下周三联系叶老师", MissingTime(KindDecision(kind="FOLLOW_UP"))
    )
    assert failure.code is AssistantFailureCode.MODEL_OUTPUT_INVALID
    assert failure.user_message == "整理结果未通过校验，尚未写入客户活动。"
    assert updated.waiting_type is None
    assert updated.last_error_code == "MODEL_OUTPUT_INVALID"
    logged = _structure_failure(db_session, updated.id)
    assert logged["failure"] == "temporal_evidence"
    assert logged["retryable"] is True
    assert logged["error_type"] == "TemporalContractError"
    assert "temporal mentions do not cover the source" in logged["cause"]


async def test_action_contract_failure_is_not_a_draft_merge(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP")
    text = "叶老师会完成准备"
    structured = StructureDraftResult(
        kind_confirmed="FOLLOW_UP",
        content=text,
        actions=[
            ModelDraftAction(
                action_ref="a1",
                owner_role="CUSTOMER",
                owner_text="叶老师",
                action_text="完成准备",
                action_status="COMMITTED",
                evidence_quote="不在原文",
                quote_start=0,
                quote_end=4,
            )
        ],
    )
    updated, failure = await _stage_failure(
        db_session, task, text, FakeStructurer(KindDecision(kind="FOLLOW_UP"), structured)
    )
    assert failure.code is AssistantFailureCode.MODEL_OUTPUT_INVALID
    assert failure.user_message == "整理结果未通过校验，尚未写入客户活动。"
    assert updated.waiting_type is None
    logged = _structure_failure(db_session, updated.id)
    assert logged["failure"] == "action_evidence"
    assert logged["error_type"] == "ActionContractError"
    assert "action quote is not in the source" in logged["cause"]
    assert "model_type" not in logged["cause"]


async def test_structure_timeout_keeps_organize_message_and_labels_upstream_timeout(db_session):
    task = _make_task(db_session, activity_kind="FOLLOW_UP")

    class TimeoutStructurer(FakeStructurer):
        async def structure(self, db, *, team_id, kind, user_text):
            try:
                raise TimeoutError("read timed out")
            except TimeoutError as exc:
                raise AssistantLLMError(
                    "跟进整理：AI 请求超时",
                    code=AssistantFailureCode.UPSTREAM_TIMEOUT,
                    cause=exc,
                ) from exc

    updated, failure = await _stage_failure(
        db_session, task, "今天联系了客户", TimeoutStructurer(KindDecision(kind="FOLLOW_UP"))
    )
    assert failure.code is AssistantFailureCode.UPSTREAM_TIMEOUT
    assert failure.stage == "structure"
    assert failure.user_message == ORGANIZE_FAILURE_MESSAGE
    logged = _structure_failure(db_session, updated.id)
    assert logged["failure"] == "upstream_timeout"
    assert logged["code"] == "UPSTREAM_TIMEOUT"
    assert logged["error_type"] == "AssistantLLMError"
    assert "TimeoutError" in logged["cause"]
    assert "read timed out" in logged["cause"]


FUTURES_TEXT = (
    "今天微信联系了上海期货信息技术有限公司的代理商商务左总对齐合同和发票方面的情况，"
    "目前合同已经走完盖章流程，左总反馈发票今天可以开具，预计11月份可以完成付款；"
    "11月15号跟进付款方面的情况"
)


async def test_month_only_commitment_survives_structuring(db_session):
    from app.services.assistant.llm_contracts import ModelTemporalMention

    task = _make_task(db_session, activity_kind="FOLLOW_UP")

    def mention(raw, start, end, kind, role, ref, owner=""):
        return ModelTemporalMention(
            raw_text=raw,
            quote_start=start,
            quote_end=end,
            kind=kind,
            role=role,
            owner=owner,
            action_ref=ref,
            confidence=0.9,
        )

    def action(ref, role, text, status, start, end, owner=""):
        return ModelDraftAction(
            action_ref=ref,
            owner_role=role,
            owner_text=owner,
            action_text=text,
            action_status=status,
            evidence_quote=FUTURES_TEXT[start:end],
            quote_start=start,
            quote_end=end,
        )

    assert FUTURES_TEXT[68:72] == "11月份"
    structured = StructureDraftResult(
        kind_confirmed="FOLLOW_UP",
        content="合同已经走完盖章流程。左总反馈发票今天可以开具，预计11月份可以完成付款。11月15号跟进付款。",
        customer_name="上海期货信息技术有限公司",
        next_action="11月15号跟进付款方面的情况",
        next_follow_time_text="11月15号",
        temporal_mentions=[
            mention("今天", 0, 2, "RELATIVE_DAY", "SALES_FOLLOW_UP", "a1"),
            mention("今天", 59, 61, "RELATIVE_DAY", "CUSTOMER_COMMITMENT", "a3", "左总"),
            mention("11月份", 68, 72, "UNKNOWN", "CUSTOMER_COMMITMENT", "a4", "左总"),
            mention("11月15号", 79, 85, "MONTH_DAY", "SALES_FOLLOW_UP", "a5"),
        ],
        actions=[
            action("a1", "SALES", "微信联系对齐合同和发票", "COMPLETED", 0, 39),
            action("a3", "CUSTOMER", "发票今天可以开具", "COMMITTED", 53, 65, "左总"),
            action("a4", "CUSTOMER", "预计11月份可以完成付款", "PLANNED", 66, 78, "左总"),
            action("a5", "SALES", "11月15号跟进付款方面的情况", "PLANNED", 79, 94),
        ],
        content_json={
            "content": "合同已经走完盖章流程。左总反馈发票今天可以开具，预计11月份可以完成付款。",
            "customer_feedback": "左总反馈发票今天可以开具，预计11月份可以完成付款。",
            "current_progress": "目前合同已经走完盖章流程。",
            "next_action": "11月15号跟进付款方面的情况",
            "next_follow_time_text": "11月15号",
        },
    )
    updated, message, waiting, failed = await intake_step(
        db_session,
        task,
        FUTURES_TEXT,
        FakeStructurer(KindDecision(kind="FOLLOW_UP"), structured),
    )
    assert failed is False
    assert waiting is None
    assert message == "已整理完成。"
    draft = TaskDraft.model_validate(updated.draft_json)
    assert draft.customer.value == "上海期货信息技术有限公司"
    commitments = {item["text"] for item in draft.content_json["customer_commitments"]}
    assert "左总发票今天可以开具。" in commitments
    assert "左总预计11月份可以完成付款。" in commitments
    month = next(item for item in draft.content_json["temporal_evidence"]["mentions"] if item["raw_text"] == "11月份")
    assert month["role"] == "CUSTOMER_COMMITMENT"
    assert month["resolution_status"] == "RESOLVED"
    assert month["resolved_at"] is None
    assert draft.content_json["next_follow_time_text"] == "11月15号"
    assert "11月15号" in (draft.next_action.value or "")
    logged = _structure_failure(db_session, updated.id)
    assert logged["accepted"] is True


async def test_classify_timeout_keeps_saved_source_after_rollback(db_session):
    from app.services.assistant.failure_contract import CLASSIFY_TIMEOUT_MESSAGE

    task = _make_task(db_session)
    text = "今天下午和客户通了电话，下周三再确认。"

    class TimeoutClassifier:
        def __init__(self) -> None:
            self.calls = 0

        async def classify(self, db, *, team_id, user_text):
            self.calls += 1
            raise AssistantLLMError("活动类型判断：AI 请求超时", code=AssistantFailureCode.UPSTREAM_TIMEOUT)

        async def structure(self, db, *, team_id, kind, user_text):
            raise AssertionError("structure must not run")

    classifier = TimeoutClassifier()
    with pytest.raises(AssistantStageFailure) as caught:
        await intake_step(db_session, task, text, classifier)
    assert classifier.calls == 1
    assert caught.value.stage == "classify"
    assert caught.value.code is AssistantFailureCode.UPSTREAM_TIMEOUT
    assert caught.value.retryable is True
    assert caught.value.user_message == CLASSIFY_TIMEOUT_MESSAGE
    db_session.rollback()
    db_session.refresh(task)
    assert text in TaskDraft.model_validate(task.draft_json).source_segments
    assert task.committed_json == []


async def test_exhausted_attempt_budget_does_not_call_the_model(db_session):
    from datetime import timedelta

    from app.services.assistant.failure_contract import bind_attempt_deadline, reset_attempt_deadline
    from app.utils.time import business_now

    task = _make_task(db_session)

    class Guard:
        def __init__(self) -> None:
            self.calls = 0

        async def classify(self, db, *, team_id, user_text):
            self.calls += 1
            raise AssertionError("model must not be called")

        async def structure(self, db, *, team_id, kind, user_text):
            self.calls += 1
            raise AssertionError("model must not be called")

    guard = Guard()
    token = bind_attempt_deadline(business_now() - timedelta(seconds=180))
    try:
        with pytest.raises(AssistantStageFailure) as caught:
            await intake_step(db_session, task, "今天下午和客户通了电话", guard)
    finally:
        reset_attempt_deadline(token)
    assert guard.calls == 0
    assert caught.value.code is AssistantFailureCode.UPSTREAM_TIMEOUT
    assert caught.value.stage == "classify"
