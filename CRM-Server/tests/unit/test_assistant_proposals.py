"""Behavioral contracts for evidence-bound, independently settled CRM proposals."""
# ruff: noqa: RUF001

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.assistant import AssistantAction, AssistantTask, AssistantTaskStatus
from app.models.assistant_turn import AssistantRequest, AssistantTurn
from app.models.customer_activity import CustomerActivity
from app.services.assistant.proposals import offer_next_proposal, settle_proposal
from app.services.assistant.opportunity_nominator import OpportunityNominator
from app.services.assistant.turns import AssistantUnknownCommitResultError


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

    from app.models.assistant_crm_effect import AssistantCRMEffect
    from app.models.opportunity import Opportunity

    Base.metadata.create_all(
        engine,
        tables=[
            AssistantTask.__table__,
            AssistantAction.__table__,
            CustomerActivity.__table__,
            Opportunity.__table__,
            AssistantCRMEffect.__table__,
            AssistantTurn.__table__,
            AssistantRequest.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def nominate(monkeypatch):
    candidates = []
    calls = []

    async def nominate(self, db, task, activity):
        calls.append(activity.id)
        return list(candidates)

    monkeypatch.setattr(OpportunityNominator, "nominate", nominate)
    return candidates, calls


def _task(db, *, content="客户确认预算80万；第一次任务完成；第二次任务完成；明年采购；风险在审批。"):
    activity = CustomerActivity(
        id=1,
        team_id=1,
        customer_id=7,
        activity_kind="FOLLOW_UP",
        source_content=content,
        content_json="{}",
        creator_id="2",
        owner_id="2",
        submission_source="AGENT",
    )
    task = AssistantTask(
        team_id=1,
        user_id=2,
        status=AssistantTaskStatus.ACTIVE,
        goal="记录跟进",
        draft_json={},
        authority_json={},
        committed_json=[{"kind": "customer_activity", "public_id": "1"}],
        version=0,
    )
    db.add_all([activity, task])
    db.commit()
    return task


def _bound_candidate(db, task, candidate, *, on_reject=None):
    return {**candidate, "activity_id": 1, "customer_id": 7, "source_revision": 1}


def _open_create_form(db, task, monkeypatch):
    from app.services.assistant import opportunity_form, proposals
    from app.services.assistant.task_state import load_waiting

    # Catalog permissions and field validation are covered in the form tests.
    monkeypatch.setattr(opportunity_form, "prepare_opportunity_form", lambda db, task, candidate: {
        "task_public_id": task.public_id, "customer_name": "客户", "fields": [],
    })
    return proposals.open_opportunity_proposal_form(db, task, load_waiting(task))


def _submit_create_form(db, task, monkeypatch):
    from app.schemas.opportunity import OpportunityCreate
    from app.services.assistant import opportunity_form, proposals
    from app.services.assistant.task_state import load_waiting

    def canonicalize(db, task, candidate, spec, values):
        return OpportunityCreate.model_validate(values).model_dump(mode="json")

    monkeypatch.setattr(opportunity_form, "validate_opportunity_form", canonicalize)
    submitted, invalid = proposals.validate_proposal_form_submission(db, task, load_waiting(task), values={
        "customer_id": "cus_7",
        "opportunity_name": "项目",
        "product_public_id": "prd_1",
        "product_module_public_ids": ["prm_1"],
        "total_amount": 1000,
        "user_count": 1,
        "license_type": "PERPETUAL",
        "purchase_type": "NEW",
        "expected_closing_date": "2026-12-31",
    })
    assert invalid is None
    return submitted


async def test_no_evidence_means_no_proposal(db_session, monkeypatch):
    from app.services.assistant.events import SSEProgressReporter
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    async def nominate(*args):
        return []

    monkeypatch.setattr(OpportunityNominator, "nominate", nominate)
    task = _task(db_session)
    reporter = SSEProgressReporter()
    updated, message, offered = await offer_next_proposal(db_session, task, reporter=reporter)
    assert [(payload["stage"], payload["phase"]) for _, payload in reporter.drain()] == [
        ("propose", "start"), ("propose", "done"),
    ]
    assert offered is False
    assert updated.waiting_field is None
    assert updated.status == AssistantTaskStatus.COMPLETED
    assert "商机" not in message
    assert db_session.query(AssistantAction).one().action == "proposal_none"


@pytest.mark.parametrize("reason", ["llm_error", "timeout", "db_error", "queue_error"])
async def test_proposal_failure_keeps_activity_and_records_reason(db_session, monkeypatch, reason):
    from sqlalchemy import text

    from app.services.assistant import proposals
    from app.services.assistant.events import SSEProgressReporter
    from app.services.assistant.model_transport import AssistantLLMError
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    async def nominate(self, db, task, activity):
        if reason == "db_error":
            db.execute(text("SELECT * FROM missing_proposal_table"))
        if reason == "timeout":
            raise TimeoutError
        raise AssistantLLMError("provider details not for audit")

    monkeypatch.setattr(OpportunityNominator, "nominate", nominate)
    if reason == "queue_error":
        async def nominate_empty(*args):
            return []

        def fail_to_read_queue(db, *_args):
            db.execute(text("SELECT * FROM missing_proposal_table"))

        monkeypatch.setattr(OpportunityNominator, "nominate", nominate_empty)
        monkeypatch.setattr(proposals, "_take_queued_candidate", fail_to_read_queue)
    task = _task(db_session)
    reporter = SSEProgressReporter()
    updated, message, offered = await offer_next_proposal(db_session, task, reporter=reporter)
    assert [(payload["stage"], payload["phase"]) for _, payload in reporter.drain()] == [
        ("propose", "start"), ("propose", "failed"),
    ]
    db_session.commit()
    action = db_session.query(AssistantAction).one()
    assert (action.action, action.result_json) == (
        "proposal_failed", {"reason": "db_error" if reason == "queue_error" else reason},
    )
    assert not offered and updated.status == AssistantTaskStatus.COMPLETED
    assert updated.committed_json == [{"kind": "customer_activity", "public_id": "1"}]
    assert db_session.query(CustomerActivity).one().id == 1
    assert message == "活动已记录。本次没能生成后续建议，可在客户页手动处理。"


async def test_rejected_nominations_audit_each_reason(crm_session, monkeypatch):
    from app.services.assistant.events import SSEProgressReporter
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    async def nominate(*args):
        return [
            {"kind": "opportunity_stage", "evidence_quote": "捏造的引用", "target_public_id": "opp_missing"},
            {"kind": "opportunity_stage", "evidence_quote": "明年采购", "target_public_id": "opp_missing",
             "payload": {"stage_template_id": 5}},
            {"kind": "opportunity_stage", "evidence_quote": "明年采购"},
            {"kind": "opportunity_create", "evidence_quote": "明年采购"},
        ]

    monkeypatch.setattr(OpportunityNominator, "nominate", nominate)
    reporter = SSEProgressReporter()
    updated, _, offered = await offer_next_proposal(crm_session, _task(crm_session), reporter=reporter)
    assert [(payload["stage"], payload["phase"]) for _, payload in reporter.drain()] == [
        ("propose", "start"), ("propose", "failed"),
    ]
    assert not offered and updated.status == AssistantTaskStatus.COMPLETED
    action = crm_session.query(AssistantAction).one()
    assert action.action == "proposal_rejected"
    assert action.result_json == {"rejected": [
        {"kind": "opportunity_stage", "reason": "literal"},
        {"kind": "opportunity_stage", "reason": "target"},
        {"kind": "opportunity_stage", "reason": "schema"},
        {"kind": "opportunity_create", "reason": "permission"},
    ]}


async def test_queue_prioritizes_advancement_and_does_not_nominate_again(db_session, monkeypatch, nominate):
    from app.services.assistant import proposals

    candidates, calls = nominate
    candidates.extend([
        {"kind": "follow_up_task_create", "evidence_quote": "明年采购", "payload": {}},
        {"kind": "opportunity_create", "evidence_quote": "明年采购", "payload": {"opportunity_name": "项目"}},
        {"kind": "opportunity_stage", "target_public_id": "opp_a", "evidence_quote": "明年采购", "payload": {}},
        {"kind": "opportunity_stage", "target_public_id": "opp_b", "evidence_quote": "明年采购", "payload": {}},
    ])
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, active = await offer_next_proposal(db_session, _task(db_session))
    assert active and offered.waiting_field == "proposal:opportunity_stage"
    db_session.commit()
    for kind in ("opportunity_stage", "opportunity_stage", "opportunity_create", "follow_up_task_create"):
        assert offered.waiting_field == f"proposal:{kind}"
        offered, _, _ = await settle_proposal(db_session, offered, accepted=False)
    assert offered.status == AssistantTaskStatus.COMPLETED and offered.waiting_field is None
    assert [item["kind"] for item in offered.committed_json[1:]] == [
        "refused:opportunity_stage", "refused:opportunity_stage", "refused:opportunity_create",
        "refused:follow_up_task_create",
    ]
    assert len({item["proposal_key"] for item in offered.committed_json[1:]}) == 4
    assert calls == [1]


async def test_missing_executor_does_not_settle_as_success(db_session, monkeypatch, nominate):
    from app.services.assistant import proposals

    nominate[0].append({"kind": "follow_up_task_create", "evidence_quote": "明年采购", "payload": {}})
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    with pytest.raises(RuntimeError, match="executor"):
        await settle_proposal(db_session, offered, accepted=True)
    db_session.refresh(task)
    assert task.waiting_field == "proposal:follow_up_task_create"
    assert task.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_failed_command_keeps_activity_and_waiting(db_session, monkeypatch, nominate):
    from app.services.assistant import proposals

    nominate[0].append({"kind": "follow_up_task_create", "evidence_quote": "明年采购", "payload": {}})
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)

    async def reject(db, task, proposal):
        raise ValueError("CRM rejected")

    with pytest.raises(ValueError, match="CRM rejected"):
        await settle_proposal(db_session, offered, accepted=True, executor=reject)
    db_session.refresh(task)
    assert task.waiting_field == "proposal:follow_up_task_create"
    assert task.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


@pytest.mark.parametrize(
    "reply",
    [
        {"kind": "follow_up_task_create", "public_id": "fut_a", "status": "REJECTED"},
        {"kind": "follow_up_task_create", "public_id": "fut_a", "status": "UNKNOWN"},
        {"kind": "follow_up_task_create", "public_id": "fut_a", "success": False},
        {"kind": "follow_up_task_create", "status": "EXECUTED"},
    ],
)
async def test_non_success_response_does_not_settle(db_session, monkeypatch, reply, nominate):
    from app.services.assistant import proposals

    nominate[0].append({"kind": "follow_up_task_create", "evidence_quote": "明年采购", "payload": {}})
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)

    async def rejected(db, task, proposal):
        return reply

    with pytest.raises(RuntimeError, match="did not confirm"):
        await settle_proposal(db_session, offered, accepted=True, executor=rejected)
    db_session.refresh(task)
    assert task.status == AssistantTaskStatus.ACTIVE
    assert task.waiting_field == "proposal:follow_up_task_create"
    assert task.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


@pytest.fixture
def crm_session(db_session, monkeypatch):
    from app.models.customer import Customer, CustomerMember, CustomerProduct
    from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
    from app.models.customer_fact import CustomerFact, CustomerFactRevision, CustomerFactSource
    from app.models.customer_intelligence_run import CustomerIntelligenceRun
    from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
    from app.models.customer_vector_document import CustomerVectorDocument
    from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
    from app.models.operation_log import OperationLog
    from app.models.opportunity import Opportunity, OpportunityProductModule
    from app.models.procurement import OpportunityStageSnapshot, ProcurementMethod, ProcurementStageTemplate
    from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase, FollowUpTaskEvent
    from app.models.team import Team, UserTeam
    from app.models.user import User

    Base.metadata.create_all(
        db_session.bind,
        tables=[
            User.__table__,
            Team.__table__,
            UserTeam.__table__,
            Customer.__table__,
            CustomerProduct.__table__,
            CustomerMember.__table__,
            CustomerActivityDeletionTombstone.__table__,
            CustomerLegacySourceProgress.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskConfirmationCase.__table__,
            CustomerFact.__table__,
            CustomerFactRevision.__table__,
            CustomerFactSource.__table__,
            CustomerVectorDocument.__table__,
            CustomerIntelligenceRun.__table__,
            Opportunity.__table__,
            OpportunityProductModule.__table__,
            ProcurementMethod.__table__,
            ProcurementStageTemplate.__table__,
            OpportunityStageSnapshot.__table__,
            CustomerDealJourney.__table__,
            CustomerDealJourneyEvent.__table__,
            OperationLog.__table__,
        ],
    )
    db_session.add_all(
        [
            User(id=2, name="小李", email="li@example.com"),
            Team(id=1, name="一队", code="A0001", owner_id=2),
            UserTeam(user_id=2, team_id=1),
            Customer(
                id=7, public_id="cus_7", team_id=1, account_name="北方科技", city="北京", owner_id="2", creator_id="2"
            ),
        ]
    )
    db_session.commit()
    from app.crud.permission import permission_crud

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda db, user_id, team_id: [
            type("Permission", (), {"code": "customer:edit:own"})(),
        ],
    )
    return db_session


async def test_meeting_actions_create_distinct_real_tasks_and_events(crm_session):
    import json
    from datetime import datetime

    from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent
    from app.services.assistant.action_evidence import SourceSegment, reconcile_action_evidence
    from app.services.assistant.contracts import DraftField, TaskDraft
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    action_a = "准备报价"
    action_b = "安排演示"
    source = "小李准备报价，2026-10-01；小李安排演示，2026-10-02"
    task = _task(crm_session, content=source)
    draft = TaskDraft(
        next_action=DraftField(status="CANDIDATE", value="准备报价；安排演示"),
        content_json={
            "action_items": [
                {"item_id": "act_quote", "owner": "小李", "action": action_a, "due_date": "2026-10-01"},
                {"item_id": "act_demo", "owner": "小李", "action": action_b, "due_date": "2026-10-02"},
            ]
        },
        source_segments=[source],
        source_records=[SourceSegment(segment_id="seg_meeting", text=source, recorded_at=datetime(2026, 9, 30, 10))],
    )
    reconcile_action_evidence(draft, "ONLINE_MEETING")
    activity = crm_session.query(CustomerActivity).one()
    activity.content_json = json.dumps(draft.content_json)
    crm_session.commit()
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active and offered.waiting_field == "proposal:follow_up_task_create"
    settled, _, _ = await settle_proposal(
        crm_session, offered, accepted=True, executor=RealCRMProposalExecutor()
    )
    assert settled.status == AssistantTaskStatus.ACTIVE and settled.waiting_field == "proposal:follow_up_task_create"
    settled, _, _ = await settle_proposal(
        crm_session, settled, accepted=True, executor=RealCRMProposalExecutor()
    )
    assert settled.status == AssistantTaskStatus.COMPLETED and settled.waiting_field is None
    tasks = crm_session.query(FollowUpTask).all()
    assert {row.title for row in tasks} == {action_a, action_b}
    assert {row.due_at_text for row in tasks} == {"2026-10-01", "2026-10-02"}
    assert len(crm_session.query(FollowUpTaskEvent).all()) == 2
    assert settled.committed_json[0] == {"kind": "customer_activity", "public_id": "1"}


async def test_no_activity_cannot_complete(db_session):
    task = _task(db_session)
    db_session.delete(db_session.query(CustomerActivity).one())
    db_session.commit()
    with pytest.raises(ValueError, match="committed customer activity is missing"):
        await offer_next_proposal(db_session, task)
    db_session.refresh(task)
    assert task.status == AssistantTaskStatus.ACTIVE


async def test_ambiguous_opportunity_command_never_runs_twice(db_session, monkeypatch, nominate):
    from app.services.assistant import proposals

    candidate = {
        "kind": "opportunity_stage",
        "target_public_id": "opp_a",
        "evidence_quote": "明年采购",
        "payload": {"stage_template_id": 3},
    }
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
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
    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=committed_then_failed)
    assert len(executions) == 1
    claims = db_session.query(AssistantAction).filter(AssistantAction.action == "proposal_command_claim").all()
    assert len(claims) == 1
    assert claims[0].result_json["proposal_key"] == executions[0]

async def test_lost_claim_acknowledgement_never_enters_executor(db_session, monkeypatch, nominate):
    from sqlalchemy.exc import OperationalError

    from app.services.assistant import proposals
    from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
    from app.services.assistant.turns import AssistantStateConflict, accept_submit

    nominate[0].append({
        "kind": "opportunity_stage", "target_public_id": "opp_a", "evidence_quote": "明年采购",
        "payload": {"stage_template_id": 3}, "prior_stage_snapshot_id": 1, "prior_version": 4,
    })
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, _task(db_session))
    db_session.commit()
    commit = db_session.commit

    def lose_ack():
        commit()
        monkeypatch.setattr(db_session, "commit", commit)
        raise OperationalError(None, None, OSError("claim acknowledgement lost"))

    async def execute(*_args):
        pytest.fail("an ambiguous durable claim must not enter the executor")

    monkeypatch.setattr(db_session, "commit", lose_ack)
    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=execute)
    assert db_session.query(AssistantAction).filter_by(action="proposal_command_claim").one().result_json["status"] == "UNKNOWN"
    from app.services.assistant.presentation import task_view

    view = task_view(offered, db_session)
    assert view.waiting is None and view.reconciliation_required
    with pytest.raises(AssistantStateConflict):
        accept_submit(db_session, task=offered, key="late-cancel", input_data={"kind": "cancel"},
                      action_id=None, expected_version=None)
    with pytest.raises(AssistantStateConflict):
        await AssistantCoordinator(next_action_chooser=None).handle_task(db_session, offered, AssistantInput(kind="cancel"))
    assert offered.status == "ACTIVE" and offered.waiting_field == "proposal:opportunity_stage"



async def test_unresolvable_readback_maps_to_unknown_commit_result_code(db_session, monkeypatch, nominate):
    """TRD §8: UNKNOWN_COMMIT_RESULT must be a typed, routable error code."""

    from app.services.assistant import proposals
    from app.services.assistant.proposals import settle_proposal

    candidate = {
        "kind": "opportunity_stage",
        "target_public_id": "opp_a",
        "evidence_quote": "明年采购",
        "payload": {"stage_template_id": 3},
        "prior_stage_snapshot_id": 1,
    }
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
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


async def test_unresolved_claim_is_queryable_for_operations(db_session, monkeypatch, nominate):
    """TRD §8: unresolved CRM commands must be queryable by operations staff."""

    from app.services.assistant import proposals
    from app.services.assistant.proposals import list_unresolved_command_claims

    candidate = {
        "kind": "opportunity_stage",
        "target_public_id": "opp_a",
        "evidence_quote": "明年采购",
        "payload": {"stage_template_id": 3},
        "prior_stage_snapshot_id": 1,
    }
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
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
    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    db_session.rollback()

    unresolved = list_unresolved_command_claims(db_session, team_id=1)
    assert len(unresolved) == 1
    entry = unresolved[0]
    payload = (offered.waiting_json or {}).get("payload")
    assert entry["proposal_key"] == payload["confirmation_payload"]["candidate"]["key"]
    assert entry["status"] == "UNKNOWN"
    assert entry["task_public_id"] == offered.public_id


@pytest.mark.parametrize(("kind", "legacy"), [
    ("opportunity_stage", False), ("opportunity_create", False),
    ("opportunity_stage", True), ("opportunity_create", True),
])
async def test_crashed_command_reconciles_only_exact_effect(db_session, monkeypatch, kind, legacy, nominate):
    from app.services.assistant import proposals
    from app.services.assistant.coordinator import AssistantCoordinator, AssistantInput
    from app.services.assistant.crm_effects import record_effect
    from app.services.assistant.crm_proposal_commands import build_proposal_command

    candidate = {
        "kind": kind,
        "evidence_quote": "明年采购",
        "payload": {"opportunity_name": "项目"},
    }
    if kind == "opportunity_stage":
        candidate.update(target_public_id="opp_a", prior_stage_snapshot_id=1, prior_version=4)
        candidate["payload"].update(stage_template_id=3, current_stage_name="接触", stage_name="方案")
        if legacy:
            candidate["payload"] = {"stage_template_id": 3}
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    submitted = None
    if kind == "opportunity_create" and not legacy:
        offered = _open_create_form(db_session, offered, monkeypatch)
        submitted = _submit_create_form(db_session, offered, monkeypatch)
    executions = []

    async def commit_then_lose_response(db, task, proposal):
        executions.append(proposal["key"])
        command = build_proposal_command(task, proposal)
        record_effect(
            db,
            command,
            kind,
            target_public_id="opp_a",
            approval_id=42 if kind == "opportunity_create" else None,
            stage_snapshot_id=2 if kind == "opportunity_stage" else None,
            previous_snapshot_id=command.expected_snapshot_id,
            previous_version=command.expected_version,
            resulting_version=5 if kind == "opportunity_stage" else None,
        )
        db.commit()
        raise RuntimeError("response lost after CRM commit")

    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(
            db_session, offered, accepted=True, executor=commit_then_lose_response, form_proposal=submitted,
        )
    db_session.rollback()
    db_session.refresh(offered)
    if submitted is not None:
        submitted = _submit_create_form(db_session, offered, monkeypatch)
    if kind == "opportunity_create" and legacy:
        from app.services.assistant import opportunity_form

        def reject_form(*args):
            pytest.fail("the original command must be read back before opening any form")

        monkeypatch.setattr(opportunity_form, "prepare_opportunity_form", reject_form)
        coordinator = AssistantCoordinator(None, proposal_executor=commit_then_lose_response)
        outcome = await coordinator.handle_task(db_session, offered, AssistantInput(kind="confirm", choice="confirm"))
        settled = outcome.task
    else:
        settled, _, _ = await settle_proposal(
            db_session, offered, accepted=True, executor=commit_then_lose_response, form_proposal=submitted,
        )
    assert settled.status == AssistantTaskStatus.COMPLETED and settled.waiting_field is None
    receipt = settled.committed_json[-1]
    assert (receipt["kind"], receipt["public_id"]) == (kind, "opp_a")
    if kind == "opportunity_create":
        assert (receipt["approval_phase"], receipt["approval_id"]) == ("pending_review", 42)
    elif legacy:
        assert "detail" not in receipt
    else:
        assert receipt["detail"] == "项目：接触 → 方案"
    assert len(executions) == 1
    claim = db_session.query(AssistantAction).filter_by(action="proposal_command_claim").one()
    assert claim.result_json["status"] == "RECONCILED"


@pytest.mark.parametrize("kind", ["opportunity_stage", "opportunity_create"])
async def test_success_response_without_exact_effect_stays_unknown(db_session, monkeypatch, kind, nominate):
    from app.services.assistant import proposals

    candidate = {"kind": kind, "evidence_quote": "明年采购", "payload": {"opportunity_name": "项目"}}
    if kind == "opportunity_stage":
        candidate.update(target_public_id="opp_a", prior_stage_snapshot_id=1, prior_version=4)
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    submitted = None
    if kind == "opportunity_create":
        offered = _open_create_form(db_session, offered, monkeypatch)
        submitted = _submit_create_form(db_session, offered, monkeypatch)
    executions = []

    async def unproven_success(db, task, proposal):
        executions.append(proposal["key"])
        db.get(CustomerActivity, 1).source_content = "uncommitted side effect"
        return {"kind": kind, "public_id": "opp_a"}

    for _ in range(2):
        with pytest.raises(AssistantUnknownCommitResultError):
            await settle_proposal(
                db_session, offered, accepted=True, executor=unproven_success, form_proposal=submitted,
            )
    assert len(executions) == 1
    assert offered.waiting_field == f"proposal:{kind}"
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]
    assert db_session.get(CustomerActivity, 1).source_content != "uncommitted side effect"


@pytest.mark.parametrize("kind", ["opportunity_stage", "opportunity_create"])
async def test_unrelated_same_name_or_snapshot_change_cannot_settle_claim(db_session, monkeypatch, kind, nominate):
    from datetime import date

    from app.models.opportunity import Opportunity
    from app.services.assistant import proposals

    candidate = {"kind": kind, "evidence_quote": "明年采购", "payload": {"opportunity_name": "项目"}}
    if kind == "opportunity_stage":
        candidate.update(target_public_id="opp_a", prior_stage_snapshot_id=1, prior_version=4)
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    submitted = None
    if kind == "opportunity_create":
        offered = _open_create_form(db_session, offered, monkeypatch)
        submitted = _submit_create_form(db_session, offered, monkeypatch)
    executions = []

    async def lose_response(db, task, proposal):
        executions.append(proposal["key"])
        db.commit()
        raise RuntimeError("response lost")

    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=lose_response, form_proposal=submitted)
    db_session.add(
        Opportunity(
            public_id="opp_a",
            team_id=1,
            opportunity_number="T-1",
            opportunity_name="项目",
            customer_id=7,
            procurement_method_id=1,
            total_amount=1000,
            user_count=1,
            unit_price=1000,
            license_type="PERPETUAL",
            purchase_type="NEW",
            expected_closing_date=date(2026, 12, 31),
            owner_id="2",
            creator_id="2",
            current_stage_snapshot_id=2,
            version=5,
        )
    )
    db_session.commit()
    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=lose_response, form_proposal=submitted)
    assert len(executions) == 1
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_success_response_target_must_match_exact_effect(db_session, monkeypatch, nominate):
    from app.services.assistant import proposals
    from app.services.assistant.crm_effects import record_effect
    from app.services.assistant.crm_proposal_commands import build_proposal_command

    nominate[0].append({"kind": "opportunity_create", "evidence_quote": "明年采购", "payload": {"opportunity_name": "项目"}})
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    offered = _open_create_form(db_session, offered, monkeypatch)
    submitted = _submit_create_form(db_session, offered, monkeypatch)

    async def mismatched_receipt(db, task, proposal):
        record_effect(
            db,
            build_proposal_command(task, proposal),
            "opportunity_create",
            target_public_id="opp_actual",
            approval_id=42,
        )
        db.commit()
        return {"kind": "opportunity_create", "public_id": "opp_unrelated"}

    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=mismatched_receipt, form_proposal=submitted)
    assert await proposals.readback_outcome(db_session, offered, submitted) == {
        "kind": "opportunity_create", "public_id": "opp_actual",
        "approval_phase": "pending_review", "approval_id": 42,
    }
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


@pytest.mark.parametrize(
    "conflict",
    ["actor", "fingerprint", "effect_kind", "target", "snapshot", "version", "legacy", "claim_id", "claim_fingerprint"],
)
async def test_claim_recovery_conflicts_fail_closed(db_session, monkeypatch, conflict, nominate):
    from hashlib import sha256

    from app.services.assistant import proposals
    from app.services.assistant.crm_effects import AssistantCRMCommand, record_effect

    nominate[0].append({
        "kind": "opportunity_stage", "target_public_id": "opp_a", "evidence_quote": "明年采购",
        "payload": {"stage_template_id": 3}, "prior_stage_snapshot_id": 1, "prior_version": 4,
    })
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    executions = []

    async def commit_then_lose_response(db, task, proposal):
        executions.append(proposal["key"])
        command = AssistantCRMCommand(
            command_id=sha256(f"assistant:{task.team_id}:{task.public_id}:{proposal['key']}".encode()).hexdigest(),
            team_id=task.team_id,
            actor_id=3 if conflict == "actor" else task.user_id,
            fingerprint="wrong" if conflict == "fingerprint" else proposal["key"],
        )
        record_effect(
            db,
            command,
            "opportunity_create" if conflict == "effect_kind" else "opportunity_stage",
            target_public_id="opp_other" if conflict == "target" else "opp_a",
            stage_snapshot_id=2,
            previous_snapshot_id=9 if conflict == "snapshot" else 1,
            previous_version=9 if conflict == "version" else 4,
            resulting_version=5,
        )
        db.commit()
        raise RuntimeError("response lost")

    with pytest.raises(RuntimeError, match="response lost"):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    if conflict in {"legacy", "claim_id", "claim_fingerprint"}:
        claim = db_session.query(AssistantAction).filter_by(action="proposal_command_claim").one()
        result = dict(claim.result_json)
        if conflict == "legacy":
            result = {"proposal_key": executions[0], "status": "CLAIMED"}
        else:
            result["command_id" if conflict == "claim_id" else "fingerprint"] = "wrong"
        claim.result_json = result
        db_session.commit()
    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    assert len(executions) == 1
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_proposal_envelope_kind_mismatch_cannot_settle(db_session, monkeypatch, nominate):
    from copy import deepcopy

    from app.services.assistant import proposals

    nominate[0].append({"kind": "follow_up_task_create", "evidence_quote": "明年采购", "payload": {}})
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
    offered, _, _ = await offer_next_proposal(db_session, task)
    waiting = deepcopy(offered.waiting_json)
    waiting["payload"]["confirmation_payload"]["proposal_kind"] = "opportunity_create"
    offered.waiting_json = waiting
    db_session.commit()
    with pytest.raises(ValueError):
        await settle_proposal(db_session, offered, accepted=False)
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_stage_unresolvable_readback_stays_unknown_without_reexecution(db_session, monkeypatch, nominate):
    """D1/D2: inconclusive readback must not re-execute or fake success."""

    from app.services.assistant import proposals

    candidate = {
        "kind": "opportunity_stage",
        "target_public_id": "opp_a",
        "evidence_quote": "明年采购",
        "payload": {"stage_template_id": 3},
        "prior_stage_snapshot_id": 1,
    }
    nominate[0].append(candidate)
    task = _task(db_session)
    monkeypatch.setattr(proposals, "validate_candidate", _bound_candidate)
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
    with pytest.raises(AssistantUnknownCommitResultError):
        await settle_proposal(db_session, offered, accepted=True, executor=commit_then_lose_response)
    assert len(executions) == 1
    assert offered.committed_json == [{"kind": "customer_activity", "public_id": "1"}]


async def test_real_stage_command_rejects_stale_snapshot_then_moves_exact_deal(crm_session, monkeypatch, nominate):
    from datetime import date, datetime

    from app.crud.permission import permission_crud
    from app.models.opportunity import Opportunity
    from app.models.procurement import OpportunityStageSnapshot, ProcurementMethod, ProcurementStageTemplate
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda *args: [
            type("Permission", (), {"code": "opportunity:edit:own"})(),
        ],
    )
    stages = [
        ProcurementStageTemplate(
            id=n,
            team_id=1,
            procurement_method_id=1,
            template_code=f"s{n}",
            stage_name=name,
            win_probability=n * 10,
            sort_order=n,
            is_default_start=int(n == 1),
            created_by="2",
        )
        for n, name in ((1, "接触"), (2, "方案"))
    ]
    crm_session.add(ProcurementMethod(id=1, team_id=1, code="test", name="标准", sort_order=1, created_by="2"))
    crm_session.add_all(stages)
    opportunity = Opportunity(
        id=1,
        public_id="opp_target",
        team_id=1,
        opportunity_number="T-1",
        opportunity_name="项目",
        customer_id=7,
        procurement_method_id=1,
        total_amount=1000,
        user_count=1,
        unit_price=1000,
        license_type="PERPETUAL",
        purchase_type="NEW",
        expected_closing_date=date(2026, 12, 31),
        owner_id="2",
        creator_id="2",
        approval_phase="approved",
    )
    crm_session.add(opportunity)
    crm_session.flush()
    prior = OpportunityStageSnapshot(
        id=1,
        team_id=1,
        opportunity_id=1,
        procurement_stage_template_id=1,
        stage_name="接触",
        win_probability=10,
        template_sort_order=1,
        template_code="s1",
        snapshot_version=1,
        entered_at=datetime(2026, 9, 1),
    )
    crm_session.add(prior)
    opportunity.current_stage_snapshot_id = prior.id
    opportunity.current_stage_name = prior.stage_name
    crm_session.commit()
    candidate = {
        "kind": "opportunity_stage",
        "target_public_id": "opp_target",
        "evidence_quote": "客户确认进入方案阶段",
        "payload": {"stage_template_id": 2},
    }
    nominate[0].append(candidate)
    task = _task(crm_session, content="客户确认进入方案阶段")
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active and offered.waiting_field == "proposal:opportunity_stage"
    proposal = offered.waiting_json["payload"]["confirmation_payload"]["candidate"]
    opportunity.version += 1
    crm_session.commit()
    with pytest.raises(ValueError, match="状态已变化"):
        await RealCRMProposalExecutor()(crm_session, offered, proposal)
    assert opportunity.current_stage_snapshot_id == 1
    opportunity.version -= 1
    crm_session.commit()
    settled, _, _ = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    assert settled.status == AssistantTaskStatus.COMPLETED and settled.waiting_field is None
    assert settled.committed_json[-1]["public_id"] == "opp_target"
    crm_session.refresh(opportunity)
    assert opportunity.current_stage_snapshot_id != 1 and opportunity.current_stage_name == "方案"
    from app.services.assistant.crm_effects import checked_effect
    from app.services.assistant.crm_proposal_commands import build_proposal_command

    effect = checked_effect(crm_session, build_proposal_command(offered, proposal), "opportunity_stage")
    assert effect is not None and effect.target_public_id == "opp_target"
    assert effect.previous_snapshot_id == proposal["prior_stage_snapshot_id"]
    assert effect.previous_version == proposal["prior_version"]
    assert effect.stage_snapshot_id == opportunity.current_stage_snapshot_id
    assert effect.resulting_version == opportunity.version


async def test_natural_date_source_reaches_real_task_with_fixed_evidence(crm_session):
    import json
    from datetime import datetime

    from app.models.sales_commitment import FollowUpTask
    from app.services.assistant.action_evidence import SourceSegment, reconcile_action_evidence
    from app.services.assistant.contracts import DraftField, TaskDraft
    from app.services.assistant.crm_proposal_commands import RealCRMProposalExecutor

    source = "小李下周三下午三点发方案"
    task = _task(crm_session, content=source)
    draft = TaskDraft(
        next_action=DraftField(status="CANDIDATE", value="小李发方案"),
        content_json={
            "action_items": [
                {"item_id": "act_send", "owner": "小李", "action": "发方案", "due_date": "2026-10-14T15:00:00"}
            ]
        },
        source_segments=[source],
        source_records=[SourceSegment(segment_id="seg_send", text=source, recorded_at=datetime(2026, 10, 8, 23, 59))],
    )
    reconcile_action_evidence(draft, "ONLINE_MEETING")
    activity = crm_session.query(CustomerActivity).one()
    activity.content_json = json.dumps(draft.content_json)
    crm_session.commit()
    offered, _, active = await offer_next_proposal(crm_session, task)
    assert active
    proposal = offered.waiting_json["payload"]["confirmation_payload"]["candidate"]
    assert proposal["action_id"] == "act_send"
    settled, _, _ = await settle_proposal(crm_session, offered, accepted=True, executor=RealCRMProposalExecutor())
    crm_session.commit()
    row = crm_session.query(FollowUpTask).one()
    assert row.title == "发方案" and row.due_at == datetime(2026, 10, 14, 15)
    assert (row.due_at_text, row.due_at_granularity, row.due_at_timezone) == (
        "下周三下午三点",
        "DATETIME",
        "Asia/Shanghai",
    )
    assert row.evidence_json["anchor_at"] == "2026-10-08T23:59:00"
    assert row.evidence_json["evidence_quote"] == source
    assert settled.committed_json[0]["kind"] == "customer_activity"
