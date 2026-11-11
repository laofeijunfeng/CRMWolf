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
from app.services.assistant.contracts import ActivityPreview, DraftField, TaskDraft, TaskWaiting
from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
from app.services.assistant.follow_up_context import (
    RealFollowUpContext,
    ChangeCard,
    EvidenceItem,
    EvidencePack,
    OpportunityChoice,
    OpportunityOption,
    read_follow_up_evidence,
    select_opportunity,
)
from app.services.assistant.llm import AssistantLLMError
from app.services.assistant.llm_contracts import ChangeJudgment, KindDecision, StructureDraftResult
from app.services.assistant.quality_gate import QualityGateOutcome
from app.utils.time import business_now

# ruff: noqa: RUF001


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _comparison_input(*, role="CUSTOMER", reschedule=False):
    previous = "客户评审安排尚未明确" if not reschedule else "客户评审安排为2026年11月19日"
    current = "客户确认评审安排为2026年11月20日" if not reschedule else "客户将评审安排改至2026年11月20日"
    action = {
        "action_id": "act_review", "owner_role": role, "owner_text": "客户",
        "action_text": "评审安排", "action_status": "COMMITTED", "state": "ACTIVE",
        "source_segment_id": "seg_current", "evidence_quote": current,
        "quote_start": 0, "quote_end": len(current), "temporal_mention_id": "mention_review",
    }
    date_start = current.index("2026")
    mention = {
        "mention_id": "mention_review", "source_segment_id": "seg_current", "action_id": "act_review",
        "raw_text": "2026年11月20日", "quote_start": date_start, "quote_end": len(current),
        "kind": "EXPLICIT_DATE", "role": "CUSTOMER_COMMITMENT", "anchor_at": "2026-11-11T10:00:00",
        "resolution_status": "RESOLVED", "resolved_at": "2026-11-20T00:00:00", "granularity": "DATE",
    }
    candidate = {
        "subject": "评审安排", "action_id": "act_review",
        "increment": "DATE_CHANGED" if reschedule else "NEW_CUSTOMER_CONFIRMATION",
        "current": {"segment_id": "seg_current", "quote_start": 0, "quote_end": len(current), "quote": current},
        "previous": {"ref": "A1", "quote_start": 0, "quote_end": len(previous), "quote": previous},
        "previous_date": "2026年11月19日" if reschedule else None,
        "current_date": "2026年11月20日" if reschedule else None,
    }
    return {
        "pack": EvidencePack(activities_status="ready", activities=[EvidenceItem("A1", "电话跟进", "2026-11-10 09:00", previous)]),
        "source_records": [{"segment_id": "seg_current", "recorded_at": "2026-11-11T10:00:00", "text": current}],
        "content_json": {"temporal_evidence": {"version": "temporal-evidence-v1", "actions": [action], "mentions": [mention]}},
        "judgment": {"classification": "RESCHEDULE" if reschedule else "CUSTOMER_COMMITMENT", "candidate": candidate},
    }


async def _judge_comparison(inputs):
    class Model:
        async def judge_change(self, db, **kwargs):
            return ChangeJudgment.model_validate(inputs["judgment"])

    return await RealFollowUpContext(Model()).judge(
        None, team_id=1, pack=inputs["pack"],
        choice=OpportunityChoice("none"), source_records=inputs["source_records"], content_json=inputs["content_json"],
    )


async def test_verified_customer_confirmation_preserves_both_sources_without_repeating_commitment():
    inputs = _comparison_input()
    card = await _judge_comparison(inputs)
    assert card.comparison is not None
    assert card.comparison.previous.ref == "A1"
    assert card.comparison.current.quote == inputs["source_records"][0]["text"]
    assert card.comparison.current.quote not in card.comparison.summary
    assert card.comparison.previous.quote in card.comparison.summary
    assert card.context_evidence == ()
    assert "change_signal" not in card.as_command()
    assert "change_summary" not in card.as_command()


async def test_sales_action_cannot_be_promoted_to_customer_confirmation():
    inputs = _comparison_input(role="SALES")
    card = await _judge_comparison(inputs)
    assert card.comparison is None
    assert card.context_status


@pytest.mark.parametrize("corruption", ["no_history", "unknown_ref", "current_span", "history_span", "wrong_action", "superseded", "different_subject", "current_as_history"])
async def test_unverifiable_comparison_downgrades_without_blocking(corruption):
    inputs = _comparison_input()
    candidate = inputs["judgment"]["candidate"]
    if corruption == "no_history":
        inputs["pack"] = EvidencePack()
    elif corruption == "unknown_ref":
        candidate["previous"]["ref"] = "A999"
    elif corruption == "current_span":
        candidate["current"]["quote_start"] = 1
    elif corruption == "history_span":
        candidate["previous"]["quote_end"] -= 1
    elif corruption == "wrong_action":
        candidate["action_id"] = "invented"
    elif corruption == "superseded":
        inputs["content_json"]["temporal_evidence"]["actions"][0]["state"] = "SUPERSEDED"
    elif corruption == "different_subject":
        candidate["subject"] = "采购审批"
    else:
        text = inputs["source_records"][0]["text"]
        inputs["pack"].activities = [EvidenceItem("A1", "电话跟进", "2026-11-10 09:00", text)]
        candidate["previous"] = {"ref": "A1", "quote_start": 0, "quote_end": len(text), "quote": text}
    card = await _judge_comparison(inputs)
    assert card.comparison is None
    assert card.context_status


async def test_explicit_same_customer_matter_reschedule_requires_verified_dates():
    inputs = _comparison_input(reschedule=True)
    card = await _judge_comparison(inputs)
    assert card.comparison is not None
    assert card.comparison.kind == "RESCHEDULE"
    assert card.comparison.previous_date == "2026-11-19"
    assert card.comparison.current_date == "2026-11-20"
    inputs["judgment"]["candidate"]["previous_date"] = "2026年11月18日"
    assert (await _judge_comparison(inputs)).comparison is None


@pytest.mark.parametrize("reschedule,previous", [
    (False, "客户评审安排已确认2026年11月20日；采购预算尚未明确"),
    (True, "客户评审安排为2026年11月25日；培训安排为2026年11月19日"),
    (False, "客户评审安排已确认采购预算尚未明确"),
])
async def test_other_matter_history_cannot_supply_absence_or_previous_date(reschedule, previous):
    inputs = _comparison_input(reschedule=reschedule)
    inputs["pack"].activities = [EvidenceItem("A1", "电话跟进", "2026-11-10 09:00", previous)]
    inputs["judgment"]["candidate"]["previous"] = {
        "ref": "A1", "quote_start": 0, "quote_end": len(previous), "quote": previous,
    }
    assert (await _judge_comparison(inputs)).comparison is None


async def test_another_action_reschedule_marker_cannot_authorize_customer_date_change():
    inputs = _comparison_input(reschedule=True)
    current = "客户确认评审安排为2026年11月20日"
    inputs["source_records"][0]["text"] = current + "；培训安排延期"
    candidate = inputs["judgment"]["candidate"]
    candidate["current"] = {
        "segment_id": "seg_current", "quote_start": 0,
        "quote_end": len(inputs["source_records"][0]["text"]), "quote": inputs["source_records"][0]["text"],
    }
    action = inputs["content_json"]["temporal_evidence"]["actions"][0]
    action.update(evidence_quote=current, quote_end=len(current))
    mention = inputs["content_json"]["temporal_evidence"]["mentions"][0]
    mention.update(quote_start=current.index("2026"), quote_end=len(current))
    assert (await _judge_comparison(inputs)).comparison is None


async def test_same_day_explicit_time_reschedule_preserves_the_two_distinct_instants():
    inputs = _comparison_input(reschedule=True)
    previous = "客户评审安排为2026年11月20日09:00"
    current = "客户将评审安排改至2026年11月20日10:00"
    inputs["pack"].activities = [EvidenceItem("A1", "电话跟进", "2026-11-10 09:00", previous)]
    inputs["source_records"][0]["text"] = current
    candidate = inputs["judgment"]["candidate"]
    candidate.update(previous_date="2026年11月20日09:00", current_date="2026年11月20日10:00")
    candidate["current"].update(quote=current, quote_end=len(current))
    candidate["previous"].update(quote=previous, quote_end=len(previous))
    inputs["content_json"]["temporal_evidence"]["actions"][0].update(evidence_quote=current, quote_end=len(current))
    inputs["content_json"]["temporal_evidence"]["mentions"][0].update(
        raw_text=candidate["current_date"], quote_end=len(current), granularity="DATETIME", resolved_at="2026-11-20T10:00:00",
    )
    comparison = (await _judge_comparison(inputs)).comparison
    assert comparison is not None
    assert comparison.previous_date == "2026-11-20 09:00"
    assert comparison.current_date == "2026-11-20 10:00"
    assert comparison.previous_date in comparison.summary
    assert comparison.current_date in comparison.summary


async def test_same_customer_commitment_is_not_a_new_comparison():
    inputs = _comparison_input()
    inputs["judgment"]["candidate"]["increment"] = "NONE"
    assert (await _judge_comparison(inputs)).comparison is None


async def test_conflicting_model_shape_downgrades_instead_of_creating_multiple_comparisons():
    inputs = _comparison_input()
    inputs["judgment"]["candidates"] = [inputs["judgment"]["candidate"], inputs["judgment"]["candidate"]]
    card = await _judge_comparison(inputs)
    assert card.comparison is None
    assert card.context_status


async def test_model_failure_keeps_the_authorized_history_available_without_comparison():
    inputs = _comparison_input()

    class FailingModel:
        async def judge_change(self, db, **kwargs):
            raise AssistantLLMError("unavailable")

    card = await RealFollowUpContext(FailingModel()).judge(
        None, team_id=1, pack=inputs["pack"],
        choice=OpportunityChoice("none"), source_records=inputs["source_records"], content_json=inputs["content_json"],
    )
    assert card.comparison is None
    assert card.context_evidence[0]["summary"] == inputs["pack"].activities[0].summary


async def test_unavailable_history_is_not_given_to_the_model_or_exposed():
    inputs = _comparison_input()
    inputs["pack"].activities_status = "denied"

    class NeverModel:
        async def judge_change(self, db, **kwargs):
            raise AssertionError("unavailable evidence must not reach a model")

    card = await RealFollowUpContext(NeverModel()).judge(
        None, team_id=1, pack=inputs["pack"],
        choice=OpportunityChoice("none"), source_records=inputs["source_records"], content_json=inputs["content_json"],
    )
    assert card.comparison is None
    assert card.context_evidence == ()


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
            comparison=None,
            context_status="暂无可验证的历史对比",
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


async def test_bound_customer_freezes_context_without_adding_a_signal_or_mutating_content(db_session):
    context = Context("广州睿狐科技有限公司")
    coordinator = AssistantCoordinator(Chooser(), structurer=Structurer(), quality_gate=Gate(), follow_up=context)
    outcome = await coordinator.handle_task(
        db_session, _task(db_session), AssistantInput(kind="text", text="广州睿狐科技有限公司他说再考虑"),
    )
    waiting = outcome.reply.waiting
    assert waiting is not None and waiting.type == "CONFIRMATION"
    preview = waiting.confirmation_payload.preview
    assert preview.comparison is None
    assert preview.context_status
    assert preview.context_evidence[0].summary == "报价后说下周答复"
    command = outcome.task.authority_json["frozen_activity_command"]
    assert "change_signal" not in command
    assert "change_summary" not in command
    assert "comparison" not in command["content_json"]
    assert context.reads == 1


async def test_verified_comparison_survives_freeze_reload_revision_and_confirmation_without_models(db_session):
    from app.services.assistant.confirmation import (
        WriteActivityResult, command_fingerprint, execute_confirmation, freeze_confirmation, revise_frozen_activity_kind,
    )

    inputs = _comparison_input(reschedule=True)
    card = await _judge_comparison(inputs)
    task = _task(db_session)
    text = inputs["source_records"][0]["text"]
    task.activity_kind = "FOLLOW_UP"
    task.draft_json = TaskDraft(
        content=DraftField(status="CANDIDATE", value=text),
        content_json={"content": text, "next_action": "我发送评审材料", **inputs["content_json"]},
        source_segments=[text], source_records=inputs["source_records"],
        quality_score=DraftField(status="CANDIDATE", value="88"), score_reason="事实完整",
        channel_kind="PHONE_FOLLOW_UP", channel_status="recognized",
        channel_options=["PHONE_FOLLOW_UP", "WECHAT_FOLLOW_UP"],
    ).model_dump(mode="json")
    db_session.flush()
    task, waiting = freeze_confirmation(db_session, task, customer=_customer(db_session), context_card=card.as_command())
    command = task.authority_json["frozen_activity_command"]
    assert waiting.confirmation_payload.preview.comparison == card.comparison
    assert command_fingerprint(command) == command["fingerprint"]
    serialized = waiting.model_dump(mode="json")
    assert TaskWaiting.model_validate(serialized).confirmation_payload.preview.comparison == card.comparison
    task, revised = revise_frozen_activity_kind(db_session, task, "WECHAT_FOLLOW_UP")
    assert revised.confirmation_payload.preview.comparison == card.comparison

    class Writer:
        async def write_activity(self, db, *, task, command):
            assert command["comparison"] == card.as_command()["comparison"]
            return WriteActivityResult(True, "act_verified", None, _customer(db).id)

    confirmed, _message = await execute_confirmation(db_session, task, writer=Writer())
    assert confirmed.authority_json["frozen_activity_command"]["execution_status"] == "SUCCEEDED"


def test_strict_persisted_legacy_preview_remains_readable_without_mutating_its_command():
    from app.services.assistant.confirmation import command_fingerprint

    legacy = {
        "customer_name": "广州睿狐科技有限公司", "content_json": {"content": "旧活动"},
        "source_content": "旧活动", "score": 88, "score_reason": "完整",
        "change_signal": "推进", "change_summary": "这次出现了新的确认或下一步。",
    }
    command = {**legacy, "submission_id": "asub_old", "execution_status": "PENDING"}
    command["fingerprint"] = command_fingerprint(command)
    before = dict(command)
    preview = ActivityPreview.model_validate(legacy)
    assert preview.change_signal == "推进"
    assert preview.comparison is None
    assert command == before
    assert command_fingerprint(command) == command["fingerprint"]


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
    assert outcome.reply.waiting.confirmation_payload.preview.comparison is None


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
    assert preview.title == "电话跟进"
    assert preview.summary == "客户说再考虑。"
    assert "comparison" not in preview.content_json
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
    assert revised_preview.comparison == preview.comparison
    assert revised_preview.context_status == preview.context_status
    assert revised.authority_json["frozen_activity_command"]["submission_id"] == command["submission_id"]
    assert revised.authority_json["frozen_activity_command"]["fingerprint"] != command["fingerprint"]
    assert revised.activity_kind == "FOLLOW_UP"
