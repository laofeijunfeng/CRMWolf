from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import follow_up_task_confirmation_case_crud, follow_up_task_crud
from app.models.agent import AgentWorkflowAction
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskProjectionStatus,
    FollowUpTaskReconciliationRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    FollowUpTaskTransitionPolicyDecisionLog,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.customer_activity_post_commit_workflow import CustomerActivityPostCommitWorkflow
from app.services.follow_up_task_projection_service import FollowUpTaskProjectionResult
from app.services.follow_up_task_reconciliation_evaluation_service import FollowUpTaskReconciliationDecision
from app.services.task_reconciliation_semantic_matcher import TaskReconciliationSemanticMatchResult
from app.services.task_reconciliation_service import TaskReconciliationCandidate, TaskReconciliationCandidateSet


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerVectorDocument.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskTransitionPolicyDecisionLog.__table__,
            FollowUpTaskReconciliationRun.__table__,
            AgentWorkflowAction.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("app.services.customer_activity_post_commit_workflow.SessionLocal", Session)
    session = Session()
    _seed_customer_and_activities(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_customer_and_activities(db_session) -> None:
    db_session.add_all(
        [
            Customer(
                id=1,
                public_id="cus_11111111111111111111111111111111",
                team_id=1,
                account_name="测试客户",
                city="上海",
                owner_id="9",
                creator_id="9",
            ),
            CustomerActivity(
                id=77,
                team_id=1,
                customer_id=1,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="客户说本周确认付款流程。",
                summary="客户本周确认付款流程。",
                next_action="跟进付款流程的进度",
                occurred_at=datetime(2026, 8, 1, 10, 0, 0),
                owner_id="2",
                creator_id="2",
            ),
            CustomerActivity(
                id=190,
                team_id=1,
                customer_id=1,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="已与客户采购埋铭老师完成回款确认。",
                summary="已完成回款确认。",
                occurred_at=datetime(2026, 8, 6, 10, 0, 0),
                owner_id="2",
                creator_id="2",
            ),
        ]
    )


def _create_open_task(db_session) -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title="跟进付款流程的进度",
            description="客户说本周确认付款流程。",
            status=FollowUpTaskStatus.OPEN,
            due_at=datetime(2026, 8, 5, 10, 0, 0),
            due_at_text="本周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=77,
            confidence=0.91,
            evidence_json={"quote": "客户说本周确认付款流程"},
            task_hash="payment-flow-task",
        ),
    )


def _candidate(task: FollowUpTask) -> TaskReconciliationCandidate:
    return TaskReconciliationCandidate(
        public_id=task.public_id,
        owner_id=task.owner_id,
        title=task.title,
        description=task.description,
        due_at=task.due_at.isoformat(),
        due_at_text=task.due_at_text,
        due_at_granularity=task.due_at_granularity,
        due_at_timezone=task.due_at_timezone,
        source_type=task.source_type,
        source_public_id=task.source_public_id,
        confidence=task.confidence,
        candidate_reasons=("same_customer", "open_task", "due_window", "same_owner"),
        auto_transition_eligible=True,
        confirmation_required_reason=None,
    )


def _candidate_set(task: FollowUpTask) -> TaskReconciliationCandidateSet:
    return TaskReconciliationCandidateSet(
        items=[_candidate(task)],
        total=1,
        filters={"activity_owner_id": task.owner_id},
        usage_policy={
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        },
    )


def _match_result(task: FollowUpTask, *, confidence: float = 0.94) -> TaskReconciliationSemanticMatchResult:
    return TaskReconciliationSemanticMatchResult(
        decision=FollowUpTaskReconciliationDecision(
            decision="COMPLETE",
            task_public_id=task.public_id,
            candidate_public_ids=(task.public_id,),
            confidence=confidence,
            needs_confirmation=confidence < 0.85,
            forbid_auto_reasons=("LOW_CONFIDENCE",) if confidence < 0.85 else (),
            evidence_terms=("完成回款确认", "付款流程"),
        ),
        candidate_set=_candidate_set(task),
        source="unit_test_matcher",
    )


class FakeProjectionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_activity_projection(self, db, *, activity_id, team_id, trigger_type, actor_id=None):
        self.calls.append(
            {
                "activity_id": activity_id,
                "team_id": team_id,
                "trigger_type": trigger_type,
                "actor_id": actor_id,
            }
        )
        return FollowUpTaskProjectionResult(
            trigger_type=trigger_type,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=f"activity:{activity_id}",
            input_snapshot_hash="input-hash",
            projection_hash="projection-hash",
            projection_run_id=1,
            projection_run_status=FollowUpTaskProjectionStatus.SKIPPED,
            skip_reason="NO_NEXT_STEP",
        )


class FakeMatcher:
    def __init__(self, result: TaskReconciliationSemanticMatchResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def match_activity(self, db, *, team_id, activity_id, include_cross_owner=False):
        self.calls.append(
            {
                "team_id": team_id,
                "activity_id": activity_id,
                "include_cross_owner": include_cross_owner,
            }
        )
        return self.result


@dataclass(frozen=True)
class FakePolicyResult:
    allowed: bool
    reason: str
    team_id: int
    action: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "team_id": self.team_id,
            "action": self.action,
            "enabled": True,
            "owner_allowlist_configured": False,
            "allowed_actions": ["COMPLETE", "DELAY", "CANCEL"],
            "config_errors": [],
        }


class FakePolicyService:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed

    def is_auto_transition_allowed(self, db, *, team_id, owner_id, action):
        return FakePolicyResult(
            allowed=self.allowed,
            reason="ALLOWED" if self.allowed else "TEAM_DISABLED",
            team_id=team_id,
            action=action,
        )


def _workflow(
    *,
    projection_service: FakeProjectionService,
    matcher: FakeMatcher,
    policy_service: FakePolicyService,
) -> CustomerActivityPostCommitWorkflow:
    return CustomerActivityPostCommitWorkflow(
        projection_service=projection_service,
        matcher=matcher,
        policy_service=policy_service,
        checkpointer=None,
    )


@pytest.mark.asyncio
async def test_post_commit_workflow_completes_old_same_owner_task_without_next_step(db_session):
    task = _create_open_task(db_session)
    projection_service = FakeProjectionService()
    matcher = FakeMatcher(_match_result(task))
    workflow = _workflow(
        projection_service=projection_service,
        matcher=matcher,
        policy_service=FakePolicyService(allowed=True),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.refresh(task)
    assert projection_service.calls[0]["activity_id"] == 190
    assert matcher.calls[0]["activity_id"] == 190
    assert matcher.calls[0]["include_cross_owner"] is False
    assert task.status == FollowUpTaskStatus.COMPLETED
    assert state["execution_results"][0]["status"] == "EXECUTED"
    assert db_session.query(FollowUpTaskTransitionPolicyDecisionLog).count() == 1
    event_names = [event["event"] for event in state["events"]]
    assert event_names[:2] == ["post_commit_workflow_started", "activity_loaded"]
    assert "next_step_projected" in event_names
    assert "historical_tasks_matched" in event_names
    assert event_names.index("transition_policy_applied") > event_names.index("historical_tasks_matched")
    assert event_names.index("transition_execution_finished") > event_names.index("transition_policy_applied")
    assert event_names.index("confirmation_cases_created") > event_names.index("transition_execution_finished")
    assert event_names[-1] == "post_commit_outcome_built"
    ledger_actions = _post_commit_ledger_actions(db_session)
    assert {action.action_type for action in ledger_actions} == {
        "project_next_follow_up_tasks",
        "reconcile_historical_follow_up_tasks",
    }
    assert {action.workflow_id for action in ledger_actions} == {"wf_pc_190_activity_created_deterministic"}
    assert {action.action_id for action in ledger_actions} == {
        "act_pc_proj_190_activity_created_deterministic",
        "act_pc_recon_190_activity_created_deterministic",
    }
    assert all(action.status == "EXECUTED" for action in ledger_actions)
    assert all(
        action.dependency_json == {
            "depends_on": [],
            "parallel_group": "post_commit_activity_analysis",
            "join": "apply_transition_policy",
        }
        for action in ledger_actions
    )


@pytest.mark.asyncio
async def test_post_commit_workflow_creates_confirmation_case_when_policy_blocks_auto_transition(db_session):
    task = _create_open_task(db_session)
    projection_service = FakeProjectionService()
    matcher = FakeMatcher(_match_result(task))
    workflow = _workflow(
        projection_service=projection_service,
        matcher=matcher,
        policy_service=FakePolicyService(allowed=False),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.refresh(task)
    cases, total = follow_up_task_confirmation_case_crud.list_pending_by_task(
        db_session,
        team_id=1,
        task_id=task.id,
    )
    assert task.status == FollowUpTaskStatus.OPEN
    assert state["execution_results"][0]["status"] == "DISABLED"
    assert total == 1
    assert cases[0].status == FollowUpTaskConfirmationStatus.PENDING
    assert cases[0].source_activity_id == 190
    assert cases[0].source_plan_json["confirmation_source"]["source_activity_id"] == 190
    assert state["confirmation_cases"][0]["case_public_id"] == cases[0].public_id
    assert state["post_commit"]["needs_user_confirmation"] is True
    assert state["post_commit"]["confirmation_case_public_ids"] == [cases[0].public_id]
    assert state["post_commit"]["confirmation_cases"][0]["task_public_id"] == task.public_id
    ledger_actions = _post_commit_ledger_actions(db_session)
    assert {action.action_type for action in ledger_actions} == {
        "project_next_follow_up_tasks",
        "reconcile_historical_follow_up_tasks",
    }
    assert all(action.status == "EXECUTED" for action in ledger_actions)


def _post_commit_ledger_actions(db_session) -> list[AgentWorkflowAction]:
    return (
        db_session.query(AgentWorkflowAction)
        .filter(AgentWorkflowAction.workflow_id.like("wf_pc_%"))
        .order_by(AgentWorkflowAction.action_type.asc())
        .all()
    )
