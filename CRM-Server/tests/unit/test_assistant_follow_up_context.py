"""Follow-up context is read only after the customer is bound, and never writes CRM state."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.customer import Customer, CustomerMember, CustomerProduct
from app.models.customer_activity import CustomerActivity
from app.models.opportunity import Opportunity
from app.services.assistant.contracts import TaskDraft
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.follow_up_context import (
    SIGNAL_SUMMARY,
    ChangeCard,
    EvidenceItem,
    EvidencePack,
    OpportunityChoice,
    OpportunityOption,
    decide_signal,
    read_follow_up_evidence,
    select_opportunity,
)
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.llm_contracts import KindDecision, StructureDraftResult
from app.services.assistant.quality_gate import QualityGateOutcome
from app.utils.time import business_now

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def test_reconsider_without_prior_evidence_cannot_slow_down():
    signal, summary = decide_signal(
        proposed="放缓",
        uses=[],
        known_refs=set(),
        user_text="他说再考虑",
    )
    assert signal == "待确认"
    assert summary == SIGNAL_SUMMARY["待确认"]
    assert "输单" not in summary
    assert "回退" not in summary


def test_slowdown_requires_a_cited_in_window_source():
    signal, summary = decide_signal(
        proposed="放缓",
        uses=[("A1", "放缓")],
        known_refs={"A1"},
        user_text="他说再考虑",
    )
    assert signal == "放缓"
    assert summary == SIGNAL_SUMMARY["放缓"]


def test_conflicting_relations_stay_unresolved():
    signal, summary = decide_signal(
        proposed="推进",
        uses=[("A1", "推进"), ("A2", "放缓")],
        known_refs={"A1", "A2"},
        user_text="客户说可以继续，但另一个记录说先暂停",
    )
    assert (signal, summary) == ("待确认", "来源有冲突，先不判断变化。")


def test_unknown_evidence_ref_cannot_support_slowdown():
    signal, _summary = decide_signal(
        proposed="放缓",
        uses=[("A9", "放缓")],
        known_refs={"A1"},
        user_text="先暂停",
    )
    assert signal == "待确认"


def test_unique_full_name_binds_and_close_scores_ask():
    options = [
        OpportunityOption(0, "opp_a", "星河续费", "报价"),
        OpportunityOption(1, "opp_b", "星河扩容", "需求"),
    ]
    named = select_opportunity(options, "今天聊了星河续费，他说再考虑", None, rank_failed=False)
    assert named.kind == "bound" and named.public_id == "opp_a"

    both = select_opportunity(options, "星河续费和星河扩容都提到了", None, rank_failed=False)
    assert both.kind == "ask"

    close = select_opportunity(options, "他说再考虑", [(0, 0.9), (1, 0.7)], rank_failed=False)
    assert close.kind == "ask"
    ahead = select_opportunity(options, "他说再考虑", [(0, 0.9), (1, 0.6)], rank_failed=False)
    assert ahead.kind == "bound" and ahead.public_id == "opp_a"
    failed = select_opportunity(options, "他说再考虑", None, rank_failed=True)
    assert failed.kind == "ask"


def test_single_opportunity_binds_without_a_name():
    only = [OpportunityOption(0, "opp_a", "星河续费", "报价")]
    chosen = select_opportunity(only, "他说再考虑", None, rank_failed=True)
    assert chosen.public_id == "opp_a"


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            Customer.__table__,
            CustomerProduct.__table__,
            CustomerMember.__table__,
            CustomerActivity.__table__,
            Opportunity.__table__,
        ],
    )
    monkeypatch.setattr(
        "app.services.assistant.customer_resolution.permission_crud.get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code="customer:activity:create")],
    )
    monkeypatch.setattr(
        "app.crud.permission.permission_crud.get_user_permissions",
        lambda *args, **kwargs: [
            SimpleNamespace(code="customer:activity:create"),
            SimpleNamespace(code="customer:view:own"),
            SimpleNamespace(code="opportunity:view:own"),
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(Customer(
        team_id=1, account_name="广州睿狐科技有限公司", public_id="cus_ctx_1",
        city="广州", creator_id="2", owner_id="2",
    ))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _customer(session):
    return session.query(Customer).one()


def _activity(session, customer, *, source, status, when, summary):
    session.add(CustomerActivity(
        team_id=1,
        customer_id=customer.id,
        activity_kind="PHONE_FOLLOW_UP",
        source_content=summary,
        summary=summary,
        submission_source=source,
        submission_id=f"sub-{summary}",
        submission_fingerprint="a" * 64 if source == "ASSISTANT_2" else None,
        processing_status=status,
        occurred_at=when,
        creator_id="2",
        owner_id="2",
    ))


def test_evidence_window_includes_confirmed_assistant_rows_only(db_session):
    customer = _customer(db_session)
    now = business_now()
    _activity(db_session, customer, source="ASSISTANT_2", status="COMPLETED", when=now, summary="助手已确认的报价")
    _activity(db_session, customer, source="FORM", status="PENDING", when=now, summary="还没确认的草稿")
    _activity(
        db_session, customer, source="FORM", status="COMPLETED", when=now - timedelta(days=120),
        summary="窗口外的旧跟进",
    )
    for index in range(5):
        _activity(
            db_session, customer, source="FORM", status="COMPLETED", when=now - timedelta(days=index + 1),
            summary=f"近期跟进{index}",
        )
    db_session.commit()
    pack = read_follow_up_evidence(
        db_session,
        team_id=1,
        user_id=2,
        customer=customer,
        permission_codes={"customer:view:own", "opportunity:view:own"},
    )
    summaries = [item.summary for item in pack.activities]
    assert "助手已确认的报价" in summaries
    assert "还没确认的草稿" not in summaries
    assert "窗口外的旧跟进" not in summaries
    assert len(pack.activities) == 5
    assert "近期跟进4" not in summaries


def test_hidden_opportunity_is_not_counted(db_session):
    customer = _customer(db_session)
    db_session.add(Opportunity(
        team_id=1, public_id="opp_other", opportunity_number="OPP-CTX-1", opportunity_name="别人的商机",
        customer_id=customer.id, total_amount=1, user_count=1, unit_price=1, license_type="SUBSCRIPTION",
        purchase_type="NEW", expected_closing_date=business_now().date(), owner_id="9", creator_id="9",
        status=0, current_stage_name="报价",
    ))
    db_session.commit()
    pack = read_follow_up_evidence(
        db_session, team_id=1, user_id=2, customer=customer,
        permission_codes={"customer:view:own", "opportunity:view:own"},
    )
    assert pack.opportunities == []
    assert pack.opportunities_status == "empty"
    assert "别人的商机" not in " ".join(pack.notices)


class Structurer:
    def __init__(self, kind="FOLLOW_UP"):
        self.kind = kind
        self.structured = False

    async def classify(self, db, *, team_id, user_text):
        return KindDecision(kind=self.kind)

    async def structure(self, db, *, team_id, kind, user_text):
        self.structured = True
        return StructureDraftResult(
            kind_confirmed="FOLLOW_UP", content="客户说再考虑。", customer_name="", next_action="下周再问",
            content_json={"content": "客户说再考虑。", "next_action": "下周再问"},
        )


class Gate:
    async def evaluate(self, db, **kwargs):
        return QualityGateOutcome(True, 88, "事实清楚", None, None, {})


class Context:
    def __init__(self, name=""):
        self.name = name
        self.reads = 0

    async def locate_customer(self, db, *, team_id, user_text):
        if self.name == "boom":
            raise AssistantLLMError("down")
        return self.name

    def read_evidence(self, db, *, team_id, user_id, customer):
        self.reads += 1
        return EvidencePack(
            activities_status="ready",
            opportunities_status="empty",
            activities=[EvidenceItem("A1", "电话跟进", "2026-10-01 09:00", "报价后说下周答复")],
            notices=["暂无近期已确认跟进"] if False else [],
            as_of="2026-10-28 10:00",
        )

    async def choose_opportunity(self, db, **kwargs):
        return OpportunityChoice("none", notices=("没有进行中商机",))

    async def judge(self, db, **kwargs):
        return ChangeCard(
            change_signal="待确认",
            change_summary=SIGNAL_SUMMARY["待确认"],
            opportunity_name=None,
            opportunity_stage=None,
            context_as_of="2026-10-28 10:00",
            context_notices=("没有进行中商机",),
            context_evidence=(
                {
                    "source_type": "电话跟进",
                    "occurred_at": "2026-10-01 09:00",
                    "summary": "报价后说下周答复",
                    "relation": "背景",
                    "key": True,
                },
            ),
        )


class Chooser:
    async def choose(self, task):
        raise AssertionError("follow-up intake must not ask the chooser")


def _task(session):
    task = AssistantTask(
        team_id=1, user_id=2, status=AssistantTaskStatus.ACTIVE, goal="他说再考虑",
        draft_json=TaskDraft().model_dump(mode="json"), authority_json={}, committed_json=[], version=0,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


async def test_customer_is_required_before_any_evidence_read(db_session):
    context = Context("")
    structurer = Structurer()
    coordinator = AssistantCoordinator(
        Chooser(), structurer=structurer, quality_gate=Gate(), follow_up=context
    )
    outcome = await coordinator.handle_task(
        db_session, _task(db_session), AssistantInput(kind="text", text="他说再考虑"),
    )
    assert context.reads == 0
    assert structurer.structured is False
    assert outcome.reply.waiting is not None
    assert outcome.reply.waiting.field == "customer"
    assert outcome.reply.waiting.type == "FIELD"


async def test_bound_customer_confirmation_shows_signal_without_writing_it_into_content(db_session):
    context = Context("广州睿狐科技有限公司")
    coordinator = AssistantCoordinator(Chooser(), structurer=Structurer(), quality_gate=Gate(), follow_up=context)
    outcome = await coordinator.handle_task(
        db_session, _task(db_session), AssistantInput(kind="text", text="广州睿狐科技有限公司他说再考虑"),
    )
    waiting = outcome.reply.waiting
    assert waiting is not None and waiting.type == "CONFIRMATION"
    preview = waiting.confirmation_payload.preview
    assert preview.change_signal == "待确认"
    assert preview.change_summary == "现有依据不够，先不判断变化。"
    assert preview.context_evidence[0].summary == "报价后说下周答复"
    command = outcome.task.authority_json["frozen_activity_command"]
    assert command["change_signal"] == "待确认"
    assert "change_signal" not in command["content_json"]
    assert context.reads == 1


async def test_meeting_does_not_read_customer_history(db_session):
    context = Context("广州睿狐科技有限公司")

    class MeetingStructurer(Structurer):
        async def structure(self, db, *, team_id, kind, user_text):
            self.structured = True
            return StructureDraftResult(
                kind_confirmed="ONLINE_MEETING",
                content="会上确认了范围。",
                customer_name="广州睿狐科技有限公司",
                next_action="周五给纪要",
                content_json={
                    "meeting_subject": "范围",
                    "key_minutes": ["会上确认了范围。"],
                    "next_step_summary": "周五给纪要",
                },
            )

    structurer = MeetingStructurer("ONLINE_MEETING")
    outcome = await AssistantCoordinator(
        Chooser(), structurer=structurer, quality_gate=Gate(), follow_up=context
    ).handle_task(db_session, _task(db_session), AssistantInput(kind="text", text="今天开了线上会议"))
    assert context.reads == 0
    assert structurer.structured is True
    assert outcome.reply.waiting is not None
    assert outcome.reply.waiting.type == "CONFIRMATION"
    assert outcome.reply.waiting.confirmation_payload.preview.change_signal is None


class AskingContext(Context):
    def __init__(self):
        super().__init__("广州睿狐科技有限公司")
        self.judged = False

    async def choose_opportunity(self, db, **kwargs):
        return OpportunityChoice(
            "ask",
            candidates=({"id": "opp_a", "label": "星河续费 · 报价"}, {"id": "opp_b", "label": "星河扩容 · 需求"}),
        )

    async def judge(self, db, **kwargs):
        self.judged = True
        raise AssertionError("opportunity selection must not also ask for confirmation")


async def test_ambiguous_opportunity_is_the_only_action(db_session):
    context = AskingContext()
    outcome = await AssistantCoordinator(
        Chooser(), structurer=Structurer(), quality_gate=Gate(), follow_up=context
    ).handle_task(
        db_session, _task(db_session), AssistantInput(kind="text", text="广州睿狐科技有限公司他说再考虑")
    )
    waiting = outcome.reply.waiting
    assert waiting is not None
    assert waiting.type == "OBJECT_SELECTION"
    assert waiting.field == "opportunity"
    assert waiting.prompt == "请选择这次沟通对应的商机。"
    assert waiting.confirmation_payload is None
    assert context.judged is False
    assert [item["label"] for item in waiting.candidates] == ["星河续费 · 报价", "星河扩容 · 需求"]


async def test_high_confidence_phone_is_frozen_without_rewriting_follow_up_content(db_session):
    class PhoneStructurer(Structurer):
        async def classify(self, db, *, team_id, user_text):
            return KindDecision(
                kind="PHONE_FOLLOW_UP",
                confidence=0.91,
                evidence_quote="电话联系",
            )

    context = Context("广州睿狐科技有限公司")
    outcome = await AssistantCoordinator(
        Chooser(), structurer=PhoneStructurer(), quality_gate=Gate(), follow_up=context
    ).handle_task(
        db_session,
        _task(db_session),
        AssistantInput(kind="text", text="今天电话联系了广州睿狐科技有限公司，他说再考虑"),
    )
    waiting = outcome.reply.waiting
    assert waiting is not None and waiting.type == "CONFIRMATION"
    preview = waiting.confirmation_payload.preview
    assert preview.activity_kind == "PHONE_FOLLOW_UP"
    assert preview.channel_status == "recognized"
    assert preview.channel_status_label == "AI 已识别 · 高置信度"
    assert preview.title == "电话跟进"
    assert preview.summary == "客户说再考虑。"
    assert "change_signal" not in preview.content_json
    command = outcome.task.authority_json["frozen_activity_command"]
    assert command["activity_kind"] == "PHONE_FOLLOW_UP"
    assert outcome.task.activity_kind == "FOLLOW_UP"
    from app.services.assistant.confirmation import revise_frozen_activity_kind

    revised, revised_waiting = revise_frozen_activity_kind(db_session, outcome.task, "WECHAT_FOLLOW_UP")
    revised_preview = revised_waiting.confirmation_payload.preview
    assert revised_preview.activity_kind == "WECHAT_FOLLOW_UP"
    assert revised_preview.title == "微信跟进"
    assert revised_preview.summary == "客户说再考虑。"
    assert revised_preview.channel_status == "revised"
    assert revised_preview.channel_status_label == "已手动修正"
    assert revised_preview.score == preview.score
    assert revised_preview.change_signal == preview.change_signal
    assert revised.authority_json["frozen_activity_command"]["submission_id"] == command["submission_id"]
    assert revised.authority_json["frozen_activity_command"]["fingerprint"] != command["fingerprint"]
    assert revised.activity_kind == "FOLLOW_UP"
