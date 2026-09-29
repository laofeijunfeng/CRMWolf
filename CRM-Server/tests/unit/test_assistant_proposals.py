"""Behavioral contracts for evidence-bound, independently settled CRM proposals."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.customer_activity import CustomerActivity
from app.services.assistant.proposals import offer_next_proposal, settle_proposal


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters
    from app.models.opportunity import Opportunity

    Base.metadata.create_all(engine, tables=[AssistantTask.__table__, AssistantAction.__table__, CustomerActivity.__table__, Opportunity.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _task(db, *, candidates=(), content="客户确认预算80万；第一次任务完成；第二次任务完成；明年采购；风险在审批。"):
    activity = CustomerActivity(
        id=1, team_id=1, customer_id=7, activity_kind="FOLLOW_UP", source_content=content,
        content_json="{}", creator_id="2", owner_id="2", submission_source="AGENT",
    )
    task = AssistantTask(
        team_id=1, user_id=2, status=AssistantTaskStatus.ACTIVE, goal="记录跟进",
        draft_json={}, authority_json={"proposal_candidates": list(candidates)},
        committed_json=[{"kind": "customer_activity", "public_id": "1"}], version=0,
    )
    db.add_all([activity, task])
    db.commit()
    return task


async def test_no_evidence_means_no_proposal(db_session):
    task = _task(db_session)
    updated, message, offered = await offer_next_proposal(db_session, task)
    assert offered is False
    assert updated.waiting_field is None
    assert updated.status == AssistantTaskStatus.COMPLETED
    assert "商机" not in message


async def test_each_bound_task_and_fact_settles_independently(db_session, monkeypatch):
    from app.services.assistant import proposals

    candidates = [
        {"kind": "follow_up_task", "target_public_id": "fut_a", "evidence_quote": "第一次任务完成", "payload": {"action": "complete"}},
        {"kind": "follow_up_task", "target_public_id": "fut_b", "evidence_quote": "第二次任务完成", "payload": {"action": "complete"}},
        {"kind": "customer_fact", "evidence_quote": "客户确认预算80万", "payload": {"fact_type": "budget", "content": "预算80万", "subject": "预算"}},
        {"kind": "customer_fact", "evidence_quote": "风险在审批", "payload": {"fact_type": "risk", "content": "审批风险", "subject": "审批"}},
    ]
    task = _task(db_session, candidates=candidates)
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, active = await offer_next_proposal(db_session, task)
    assert active and offered.waiting_json["payload"]["confirmation_payload"]["target_public_id"] == "fut_a"
    first_key = offered.waiting_json["payload"]["confirmation_payload"]["key"]
    settled, receipt, followup = await settle_proposal(db_session, offered, accepted=False)
    assert followup and settled.status == AssistantTaskStatus.ACTIVE
    assert settled.waiting_field is None and settled.waiting_json == {}
    assert receipt and settled.committed_json[-1]["proposal_key"] == first_key
    assert settled.committed_json[-1]["kind"] == "refused:follow_up_task"
    for expected in ("fut_b", "customer_fact", "risk"):
        offered, _, active = await offer_next_proposal(db_session, settled)
        assert active
        proposal = offered.waiting_json["payload"]["confirmation_payload"]
        observed = (proposal["payload"]["fact_type"] if expected == "risk" else
                    proposal.get("target_public_id") or proposal.get("kind"))
        assert observed == expected
        settled, _, followup = await settle_proposal(db_session, offered, accepted=False)
        assert followup and settled.status == AssistantTaskStatus.ACTIVE
        assert settled.waiting_field is None and settled.waiting_json == {}
    finished, _, active = await offer_next_proposal(db_session, settled)
    assert not active and finished.status == AssistantTaskStatus.COMPLETED
    assert len({item["proposal_key"] for item in finished.committed_json[1:]}) == 4
    assert finished.committed_json[0]["kind"] == "customer_activity"


async def test_missing_executor_does_not_settle_as_success(db_session, monkeypatch):
    from app.services.assistant import proposals

    task = _task(db_session, candidates=[{"kind": "follow_up_task", "target_public_id": "fut_a", "evidence_quote": "第一次任务完成", "payload": {"action": "complete"}}])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    with pytest.raises(RuntimeError, match="executor"):
        await settle_proposal(db_session, offered, accepted=True)
    db_session.refresh(task)
    assert task.waiting_field == "proposal:follow_up_task"
    assert task.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_failed_command_keeps_activity_and_waiting(db_session, monkeypatch):
    from app.services.assistant import proposals

    task = _task(db_session, candidates=[{"kind": "customer_fact", "evidence_quote": "风险在审批", "payload": {"fact_type": "risk", "content": "审批风险"}}])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)

    async def reject(db, task, proposal):
        raise ValueError("CRM rejected")

    with pytest.raises(ValueError, match="CRM rejected"):
        await settle_proposal(db_session, offered, accepted=True, executor=reject)
    db_session.refresh(task)
    assert task.waiting_field == "proposal:customer_fact"
    assert task.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


@pytest.mark.parametrize("reply", [
    {"kind": "follow_up_task", "public_id": "fut_a", "status": "REJECTED"},
    {"kind": "follow_up_task", "public_id": "fut_a", "status": "UNKNOWN"},
    {"kind": "follow_up_task", "public_id": "fut_a", "success": False},
    {"kind": "follow_up_task", "status": "EXECUTED"},
])
async def test_non_success_response_does_not_settle(db_session, monkeypatch, reply):
    from app.services.assistant import proposals

    candidate = {"kind": "follow_up_task", "target_public_id": "fut_a",
                 "evidence_quote": "第一次任务完成", "payload": {"action": "complete"}}
    task = _task(db_session, candidates=[candidate])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)

    async def rejected(db, task, proposal):
        return reply

    with pytest.raises(RuntimeError, match="did not confirm"):
        await settle_proposal(db_session, offered, accepted=True, executor=rejected)
    db_session.refresh(task)
    assert task.status == AssistantTaskStatus.ACTIVE
    assert task.waiting_field == "proposal:follow_up_task"
    assert task.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


@pytest.fixture
def crm_session(db_session, monkeypatch):
    from app.models.customer import Customer, CustomerMember, CustomerProduct
    from app.models.customer_fact import CustomerFact, CustomerFactRevision, CustomerFactSource
    from app.models.customer_intelligence_run import CustomerIntelligenceRun
    from app.models.customer_vector_document import CustomerVectorDocument
    from app.models.opportunity import Opportunity, OpportunityProductModule
    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent, FollowUpTaskConfirmationCase
    from app.models.team import Team, UserTeam
    from app.models.user import User
    from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
    from app.models.operation_log import OperationLog
    from app.models.procurement import ProcurementMethod, ProcurementStageTemplate, OpportunityStageSnapshot
    Base.metadata.create_all(db_session.bind, tables=[
        User.__table__, Team.__table__, UserTeam.__table__, Customer.__table__, CustomerProduct.__table__, CustomerMember.__table__,
        FollowUpTask.__table__, FollowUpTaskEvent.__table__, FollowUpTaskConfirmationCase.__table__, CustomerFact.__table__,
        CustomerFactRevision.__table__, CustomerFactSource.__table__, CustomerVectorDocument.__table__,
        CustomerIntelligenceRun.__table__, Opportunity.__table__, OpportunityProductModule.__table__, ProcurementMethod.__table__,
        ProcurementStageTemplate.__table__, OpportunityStageSnapshot.__table__, CustomerDealJourney.__table__,
        CustomerDealJourneyEvent.__table__,
        OperationLog.__table__,
    ])
    db_session.add_all([
        User(id=2, name="小李", email="li@example.com"),
        Team(id=1, name="一队", code="A0001", owner_id=2),
        UserTeam(user_id=2, team_id=1),
        Customer(id=7, public_id="cus_7", team_id=1, account_name="北方科技", city="北京",
                 owner_id="2", creator_id="2"),
    ])
    db_session.commit()
    from app.crud.permission import permission_crud
    monkeypatch.setattr(permission_crud, "get_user_permissions", lambda db, user_id, team_id: [
        type("Permission", (), {"code": "customer:edit:own"})(),
    ])
    return db_session


async def test_meeting_actions_create_distinct_real_tasks_and_events(crm_session):
    import json
    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    action_a = "准备报价"
    action_b = "安排演示"
    task = _task(crm_session, content="小李准备报价，2026-10-01；小李安排演示，2026-10-02")
    activity = crm_session.query(CustomerActivity).one()
    activity.content_json = json.dumps({"action_items": [
        {"owner": "小李", "action": action_a, "due_date": "2026-10-01"},
        {"owner": "小李", "action": action_b, "due_date": "2026-10-02"},
    ]})
    crm_session.commit()
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active and offered.waiting_field == "proposal:follow_up_task_create"
    settled, _, followup = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert followup and settled.status == AssistantTaskStatus.ACTIVE and settled.waiting_field is None
    offered, _, active = await offer_next_proposal(crm_session, settled)
    assert active and offered.waiting_field == "proposal:follow_up_task_create"
    settled, _, followup = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert followup and settled.status == AssistantTaskStatus.ACTIVE and settled.waiting_field is None
    finished, _, active = await offer_next_proposal(crm_session, settled)
    assert not active
    tasks = crm_session.query(FollowUpTask).all()
    assert {row.title for row in tasks} == {action_a, action_b}
    assert {row.due_at_text for row in tasks} == {"2026-10-01", "2026-10-02"}
    assert len(crm_session.query(FollowUpTaskEvent).all()) == 2
    assert finished.committed_json[0] == {"kind": "customer_activity", "public_id": "1"}


async def test_real_fact_write_rechecks_revision_and_permission(crm_session):
    import json
    from app.models.customer_fact import CustomerFact
    from app.models.team import UserTeam
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    task = _task(crm_session, content="客户确认预算80万")
    activity = crm_session.query(CustomerActivity).one()
    activity.content_json = json.dumps({"customer_facts": [
        {"fact_type": "budget", "content": "预算80万", "evidence_quote": "客户确认预算80万"},
    ]})
    crm_session.commit()
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active
    activity.activity_revision += 1
    crm_session.commit()
    with pytest.raises(ValueError, match="状态已变化"):
        await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert crm_session.query(CustomerFact).count() == 0
    activity.activity_revision -= 1
    membership = crm_session.query(UserTeam).one()
    crm_session.delete(membership)
    crm_session.commit()
    with pytest.raises(ValueError, match="证据或操作权限"):
        await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert crm_session.query(CustomerFact).count() == 0
    crm_session.add(UserTeam(user_id=2, team_id=1))
    crm_session.commit()
    settled, _, followup = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert followup and settled.status == AssistantTaskStatus.ACTIVE and settled.waiting_field is None
    finished, _, active = await offer_next_proposal(crm_session, settled)
    assert not active and finished.status == AssistantTaskStatus.COMPLETED
    assert crm_session.query(CustomerFact).one().content == "预算80万"
    assert finished.committed_json[0]["kind"] == "customer_activity"


async def test_no_activity_cannot_complete(db_session):
    task = _task(db_session)
    db_session.delete(db_session.query(CustomerActivity).one())
    db_session.commit()
    with pytest.raises(ValueError, match="committed customer activity is missing"):
        await offer_next_proposal(db_session, task)
    db_session.refresh(task)
    assert task.status == AssistantTaskStatus.ACTIVE

async def test_ambiguous_opportunity_command_never_runs_twice(db_session, monkeypatch):
    from app.services.assistant import proposals

    candidate = {"kind": "opportunity_stage", "target_public_id": "opp_a",
                 "evidence_quote": "明年采购", "payload": {"stage_template_id": 3}}
    task = _task(db_session, candidates=[candidate])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    executions = []

    async def committed_then_failed(db, task, proposal):
        executions.append(proposal["key"])
        db.commit()  # Opportunity's existing API commits inside the command.
        raise RuntimeError("response lost after CRM commit")

    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=committed_then_failed)
    db_session.rollback()
    db_session.refresh(offered)
    assert offered.version == 2
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]
    assert offered.waiting_field == "proposal:opportunity_stage"
    with pytest.raises(RuntimeError, match="UNKNOWN_COMMIT_RESULT"):
        await settle_proposal(db_session, offered, accepted=True, executor=committed_then_failed)
    assert len(executions) == 1
    claims = db_session.query(AssistantAction).filter(AssistantAction.action == "proposal_command_claim").all()
    assert len(claims) == 1
    assert claims[0].result_json["proposal_key"] == executions[0]


async def test_unresolvable_readback_maps_to_unknown_commit_result_code(db_session, monkeypatch):
    """TRD §8: UNKNOWN_COMMIT_RESULT must be a typed, routable error code."""

    from app.services.assistant import proposals
    from app.services.assistant.proposals import settle_proposal

    candidate = {"kind": "opportunity_stage", "target_public_id": "opp_a",
                 "evidence_quote": "明年采购", "payload": {"stage_template_id": 3},
                 "prior_stage_snapshot_id": 1}
    task = _task(db_session, candidates=[candidate])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)

    async def commit_then_lose_response(db, task, proposal):
        db.commit()
        raise RuntimeError("response lost after CRM commit")

    async def readback(db, task, proposal):
        return None

    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    db_session.rollback()
    db_session.refresh(offered)
    monkeypatch.setattr(proposals, "readback_outcome", readback)

    from app.services.assistant.turns import classify_turn_error

    try:
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    except Exception as exc:
        assert classify_turn_error(exc) == "UNKNOWN_COMMIT_RESULT"
    else:
        pytest.fail("unresolved readback must raise a typed error")


async def test_unresolved_claim_is_queryable_for_operations(db_session, monkeypatch):
    """TRD §8: unresolved CRM commands must be queryable by operations staff."""

    from app.services.assistant import proposals
    from app.services.assistant.proposals import list_unresolved_command_claims

    candidate = {"kind": "opportunity_stage", "target_public_id": "opp_a",
                 "evidence_quote": "明年采购", "payload": {"stage_template_id": 3},
                 "prior_stage_snapshot_id": 1}
    task = _task(db_session, candidates=[candidate])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)

    async def commit_then_lose_response(db, task, proposal):
        db.commit()
        raise RuntimeError("response lost after CRM commit")

    async def readback(db, task, proposal):
        return None

    monkeypatch.setattr(proposals, "readback_outcome", readback)
    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    db_session.rollback()
    db_session.refresh(offered)

    # Retry hits the claim guard: readback cannot prove the outcome -> UNKNOWN.
    with pytest.raises(RuntimeError, match="UNKNOWN_COMMIT_RESULT"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    db_session.rollback()

    unresolved = list_unresolved_command_claims(db_session, team_id=1)
    assert len(unresolved) == 1
    entry = unresolved[0]
    payload = (offered.waiting_json or {}).get("payload")
    assert entry["proposal_key"] == payload["confirmation_payload"]["key"]
    assert entry["status"] == "UNKNOWN"
    assert entry["task_public_id"] == offered.public_id


async def test_stage_crash_after_crm_commit_reconciles_by_readback(db_session, monkeypatch):
    """D1/D2: retrying a crashed stage command must read back, not re-execute."""

    from app.services.assistant import proposals

    candidate = {"kind": "opportunity_stage", "target_public_id": "opp_a",
                 "evidence_quote": "明年采购", "payload": {"stage_template_id": 3},
                 "prior_stage_snapshot_id": 1}
    task = _task(db_session, candidates=[candidate])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    executions = []

    class FakeOpportunity:
        public_id = "opp_a"
        current_stage_snapshot_id = 1
        current_stage_name = "需求"

    fake = FakeOpportunity()

    async def commit_then_lose_response(db, task, proposal):
        executions.append(proposal["key"])
        db.commit()
        raise RuntimeError("response lost after CRM commit")

    async def readback(db, task, proposal):
        return {"kind": "opportunity_stage", "public_id": "opp_a"} if fake.current_stage_snapshot_id != 1 else None

    # First attempt crashes in the ambiguous window (CRM committed, receipt lost).
    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    db_session.rollback()
    db_session.refresh(offered)
    fake.current_stage_snapshot_id = 2  # CRM actually moved the stage.

    # Retry must reconcile by readback and settle without a second execution.
    monkeypatch.setattr(proposals, "readback_outcome", readback)
    settled, _, followup = await settle_proposal(db_session, offered, accepted=True,
                                                 executor=commit_then_lose_response)
    assert followup and settled.committed_json[-1]["public_id"] == "opp_a"
    assert len(executions) == 1


async def test_stage_unresolvable_readback_stays_unknown_without_reexecution(db_session, monkeypatch):
    """D1/D2: inconclusive readback must not re-execute or fake success."""

    from app.services.assistant import proposals

    candidate = {"kind": "opportunity_stage", "target_public_id": "opp_a",
                 "evidence_quote": "明年采购", "payload": {"stage_template_id": 3},
                 "prior_stage_snapshot_id": 1}
    task = _task(db_session, candidates=[candidate])
    monkeypatch.setattr(proposals, "validate_candidate", lambda db, task, candidate: candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    executions = []

    async def commit_then_lose_response(db, task, proposal):
        executions.append(proposal["hook_key"] if False else proposal["key"])
        db.commit()
        raise RuntimeError("response lost after CRM commit")

    async def readback(db, task, proposal):
        return None  # State unchanged or ambiguous: cannot prove the outcome.

    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    db_session.rollback()
    db_session.refresh(offered)
    monkeypatch.setattr(proposals, "readback_outcome", readback)
    with pytest.raises(RuntimeError, match="UNKNOWN_COMMIT_RESULT"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    assert len(executions) == 1
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_real_completion_targets_only_evidenced_open_task(crm_session):
    from datetime import datetime
    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent, FollowUpTaskStatus
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    task = _task(crm_session, candidates=[{"kind": "follow_up_task", "target_public_id": "fut_a",
        "evidence_quote": "小李准备报价任务完成", "payload": {"action": "complete"}}],
        content="小李准备报价任务完成")
    for public_id, title in (("fut_a", "准备报价"), ("fut_b", "安排演示")):
        crm_session.add(FollowUpTask(public_id=public_id, team_id=1, customer_id=7, owner_id="2", creator_id="2",
            title=title, status=FollowUpTaskStatus.OPEN, due_at=datetime(2026, 10, 1),
            source_type="CUSTOMER_ACTIVITY", source_key="fixture", task_hash=public_id))
    crm_session.commit()
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active and offered.waiting_field == "proposal:follow_up_task"
    result, _, followup = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert followup and result.status == AssistantTaskStatus.ACTIVE and result.waiting_field is None
    finished, _, active = await offer_next_proposal(crm_session, result)
    assert not active and finished.status == AssistantTaskStatus.COMPLETED
    assert crm_session.query(FollowUpTask).filter_by(public_id="fut_a").one().status == FollowUpTaskStatus.COMPLETED
    assert crm_session.query(FollowUpTask).filter_by(public_id="fut_b").one().status == FollowUpTaskStatus.OPEN
    assert crm_session.query(FollowUpTaskEvent).count() == 1


async def test_historical_task_actions_are_independent(crm_session):
    from datetime import datetime

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskStatus
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    content = "准备报价已完成；安排演示改到2026-10-15；内部评审取消；预算确认与本次无关"
    actions = (
        ("fut_done", "准备报价", "complete", None, FollowUpTaskStatus.COMPLETED),
        ("fut_later", "安排演示", "postpone", "2026-10-15", FollowUpTaskStatus.OPEN),
        ("fut_drop", "内部评审", "cancel", None, FollowUpTaskStatus.CANCELLED),
        ("fut_skip", "预算确认", "unrelated", None, FollowUpTaskStatus.OPEN),
    )
    for public_id, title, *_rest in actions:
        crm_session.add(FollowUpTask(
            public_id=public_id, team_id=1, customer_id=7, owner_id="2", creator_id="2",
            title=title, status=FollowUpTaskStatus.OPEN, due_at=datetime(2026, 10, 1),
            source_type="CUSTOMER_ACTIVITY", source_key="fixture", task_hash=public_id,
        ))
    task = _task(crm_session, candidates=[
        {"kind": "follow_up_task", "target_public_id": public_id, "evidence_quote": title,
         "payload": {"action": action, "due_date": due}}
        for public_id, title, action, due, _expected in actions
    ], content=content)
    current = task
    for _public_id, _title, _action, _due, _expected in actions:
        offered, _, active = await offer_next_proposal(crm_session, current)
        assert active and offered.waiting_field == "proposal:follow_up_task"
        current, _, _ = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    rows = {row.public_id: row for row in crm_session.query(FollowUpTask).all()}
    assert rows["fut_done"].status == FollowUpTaskStatus.COMPLETED
    assert rows["fut_later"].status == FollowUpTaskStatus.OPEN
    assert rows["fut_later"].due_at.date() == datetime(2026, 10, 15).date()
    assert rows["fut_drop"].status == FollowUpTaskStatus.CANCELLED
    assert rows["fut_skip"].status == FollowUpTaskStatus.OPEN
    assert rows["fut_skip"].due_at == datetime(2026, 10, 1)

async def test_real_stage_command_rejects_stale_snapshot_then_moves_exact_deal(crm_session, monkeypatch):
    from datetime import date, datetime
    from app.crud.permission import permission_crud
    from app.models.opportunity import Opportunity
    from app.models.procurement import ProcurementMethod, ProcurementStageTemplate, OpportunityStageSnapshot
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    monkeypatch.setattr(permission_crud, "get_user_permissions", lambda *args: [
        type("Permission", (), {"code": "opportunity:edit:own"})(),
    ])
    stages = [ProcurementStageTemplate(id=n, team_id=1, procurement_method_id=1, template_code=f"s{n}",
        stage_name=name, win_probability=n * 10, sort_order=n, is_default_start=int(n == 1), created_by="2")
        for n, name in ((1, "接触"), (2, "方案"))]
    crm_session.add(ProcurementMethod(id=1, team_id=1, code="test", name="标准", sort_order=1, created_by="2"))
    crm_session.add_all(stages)
    opportunity = Opportunity(id=1, public_id="opp_target", team_id=1, opportunity_number="T-1",
        opportunity_name="项目", customer_id=7, procurement_method_id=1, total_amount=1000,
        user_count=1, unit_price=1000, license_type="PERPETUAL", purchase_type="NEW",
        expected_closing_date=date(2026, 12, 31), owner_id="2", creator_id="2", approval_phase="approved")
    crm_session.add(opportunity)
    crm_session.flush()
    prior = OpportunityStageSnapshot(id=1, team_id=1, opportunity_id=1, procurement_stage_template_id=1,
        stage_name="接触", win_probability=10, template_sort_order=1, template_code="s1", snapshot_version=1,
        entered_at=datetime(2026, 9, 1))
    crm_session.add(prior)
    opportunity.current_stage_snapshot_id = prior.id
    opportunity.current_stage_name = prior.stage_name
    crm_session.commit()
    candidate = {"kind": "opportunity_stage", "target_public_id": "opp_target",
        "evidence_quote": "客户确认进入方案阶段", "payload": {"stage_template_id": 2}}
    task = _task(crm_session, candidates=[candidate], content="客户确认进入方案阶段")
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active and offered.waiting_field == "proposal:opportunity_stage"
    opportunity.version += 1
    crm_session.commit()
    with pytest.raises(ValueError, match="状态已变化"):
        await RealCRMProposalExecutor()(crm_session, offered, offered.waiting_json["payload"]["confirmation_payload"])
    assert opportunity.current_stage_snapshot_id == 1
    opportunity.version -= 1
    crm_session.commit()
    settled, _, followup = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert followup and settled.status == AssistantTaskStatus.ACTIVE and settled.waiting_field is None
    assert settled.committed_json[-1]["public_id"] == "opp_target"
    finished, _, active = await offer_next_proposal(crm_session, settled)
    assert not active and finished.status == AssistantTaskStatus.COMPLETED
    crm_session.refresh(opportunity)
    assert opportunity.current_stage_snapshot_id != 1 and opportunity.current_stage_name == "方案"