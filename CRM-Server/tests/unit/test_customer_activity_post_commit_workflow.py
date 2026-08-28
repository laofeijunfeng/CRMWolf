from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.crud.sales_commitment import follow_up_task_confirmation_case_crud, follow_up_task_crud
from app.models.agent import AgentMessage, AgentSession, AgentWorkflowAction
from app.models.agent_persistence import AgentUIAction
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskConfirmationPromptStatus,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEvent,
    FollowUpTaskProjectionRun,
    FollowUpTaskProjectionStatus,
    FollowUpTaskReconciliationRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitment,
)
from app.schemas.sales_commitment import FollowUpTaskInternalCreate
from app.services.customer_activity_post_commit_workflow import CustomerActivityPostCommitWorkflow
from app.services.follow_up_task_confirmation_service import (
    FollowUpTaskConfirmationService,
    follow_up_task_confirmation_service,
)
from app.services.follow_up_task_projection_service import (
    FollowUpTaskProjectionResult,
    follow_up_task_projection_service,
)
from app.services.follow_up_task_reconciliation_evaluation_service import (
    FollowUpTaskReconciliationDecision,
    FollowUpTaskReconciliationTaskDecision,
)
from app.services.follow_up_task_transition_execution_service import (
    FollowUpTaskTransitionExecutionResult,
)
from app.services.task_reconciliation_semantic_matcher import (
    TaskReconciliationSemanticMatchResult,
    TaskReconciliationUnavailableError,
)
from app.services.task_reconciliation_service import (
    TaskReconciliationCandidate,
    TaskReconciliationCandidateSet,
    task_reconciliation_service,
)
from tests.unit.support.reconciliation_decisions import (
    empty_reconciliation_decision,
    single_task_reconciliation_decision,
)


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
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskConfirmationPromptDelivery.__table__,
            FollowUpTaskReconciliationRun.__table__,
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentWorkflowAction.__table__,
            AgentUIAction.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("app.services.customer_activity_post_commit_workflow.SessionLocal", Session)
    from app.services.follow_up_confirmation_delivery_workflow import follow_up_confirmation_delivery_workflow

    monkeypatch.setattr(follow_up_confirmation_delivery_workflow.projection, "_session_factory", Session)
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


def _create_open_task(
    db_session,
    *,
    title: str = "跟进付款流程的进度",
    task_hash: str = "payment-flow-task",
) -> FollowUpTask:
    return follow_up_task_crud.create(
        db_session,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=1,
            owner_id="2",
            creator_id="2",
            title=title,
            description="客户说本周确认付款流程。",
            status=FollowUpTaskStatus.OPEN,
            due_at=datetime(2026, 8, 5, 10, 0, 0),
            due_at_text="本周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=77,
            confidence=0.91,
            evidence_json={"quote": "客户说本周确认付款流程"},
            task_hash=task_hash,
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


def _candidate_set(*tasks: FollowUpTask) -> TaskReconciliationCandidateSet:
    first = tasks[0]
    return TaskReconciliationCandidateSet(
        items=[_candidate(task) for task in tasks],
        total=len(tasks),
        filters={"activity_owner_id": first.owner_id},
        usage_policy={
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        },
    )


def _empty_candidate_set() -> TaskReconciliationCandidateSet:
    return TaskReconciliationCandidateSet(
        items=[],
        total=0,
        filters={"activity_owner_id": "2"},
        usage_policy={
            "state_source": "mysql.crm_follow_up_tasks",
            "mutation": "forbidden",
            "cross_owner": "confirmation_only",
        },
    )


def _no_match_result() -> TaskReconciliationSemanticMatchResult:
    return TaskReconciliationSemanticMatchResult(
        decision=empty_reconciliation_decision(reason="NO_OPEN_CANDIDATES"),
        candidate_set=_empty_candidate_set(),
        source="unit_test_no_candidates",
    )


def _match_result(task: FollowUpTask, *, confidence: float = 0.94) -> TaskReconciliationSemanticMatchResult:
    return TaskReconciliationSemanticMatchResult(
        decision=single_task_reconciliation_decision(
            decision="COMPLETE",
            task_public_id=task.public_id,
            confidence=confidence,
            needs_confirmation=confidence < 0.85,
            forbid_auto_reasons=("LOW_CONFIDENCE",) if confidence < 0.85 else (),
            evidence_terms=("完成回款确认", "付款流程"),
        ),
        candidate_set=_candidate_set(task),
        source="unit_test_matcher",
    )


def _batch_match_result(
    *tasks: FollowUpTask,
    decisions: tuple[FollowUpTaskReconciliationTaskDecision, ...],
) -> TaskReconciliationSemanticMatchResult:
    return TaskReconciliationSemanticMatchResult(
        decision=FollowUpTaskReconciliationDecision(
            candidate_public_ids=tuple(task.public_id for task in tasks),
            task_decisions=decisions,
        ),
        candidate_set=_candidate_set(*tasks),
        source="unit_test_batch_matcher",
    )


class FakeProjectionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_activity_projection(
        self,
        db,
        *,
        activity_id,
        team_id,
        trigger_type,
        actor_id=None,
        activity_snapshot=None,
        commit=True,
    ):
        self.calls.append(
            {
                "activity_id": activity_id,
                "team_id": team_id,
                "trigger_type": trigger_type,
                "actor_id": actor_id,
                "activity_snapshot": activity_snapshot,
                "commit": commit,
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


def _workflow(
    *,
    projection_service: FakeProjectionService,
    matcher: FakeMatcher,
    execution_service=None,
    confirmation_service=None,
) -> CustomerActivityPostCommitWorkflow:
    kwargs = {}
    if execution_service is not None:
        kwargs["execution_service"] = execution_service
    if confirmation_service is not None:
        kwargs["confirmation_service"] = confirmation_service
    return CustomerActivityPostCommitWorkflow(
        projection_service=projection_service,
        matcher=matcher,
        checkpointer=None,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_post_commit_workflow_finishes_without_task_results_when_customer_has_no_open_tasks(db_session):
    matcher = FakeMatcher(_no_match_result())
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=matcher,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    assert state["post_commit"]["automatic_task_transitions"] == []
    assert state["post_commit"]["confirmation_cases"] == []
    assert state["post_commit"]["confirmation_case_public_ids"] == []
    assert state["post_commit"]["needs_user_confirmation"] is False
    assert matcher.calls == [
        {
            "team_id": 1,
            "activity_id": 190,
            "include_cross_owner": True,
        }
    ]


@pytest.mark.asyncio
async def test_post_commit_workflow_completes_old_same_owner_task_without_next_step(db_session):
    task = _create_open_task(db_session)
    projection_service = FakeProjectionService()
    matcher = FakeMatcher(_match_result(task))
    workflow = _workflow(
        projection_service=projection_service,
        matcher=matcher,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.refresh(task)
    assert projection_service.calls[0]["activity_id"] == 190
    assert matcher.calls[0]["activity_id"] == 190
    assert matcher.calls[0]["include_cross_owner"] is True
    assert task.status == FollowUpTaskStatus.COMPLETED
    assert state["execution_results"][0]["status"] == "EXECUTED"
    event_names = [event["event"] for event in state["events"]]
    assert event_names[:2] == ["post_commit_workflow_started", "activity_loaded"]
    assert "next_step_projected" in event_names
    assert "historical_tasks_matched" in event_names
    assert event_names.index("transition_execution_finished") > event_names.index("historical_tasks_matched")
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
        action.dependency_json
        == {
            "depends_on": [],
            "parallel_group": "post_commit_activity_analysis",
            "join": "execute_transition",
        }
        for action in ledger_actions
    )


@pytest.mark.asyncio
async def test_post_commit_workflow_handles_each_historical_task_independently_and_projects_results(db_session):
    completed_task = _create_open_task(
        db_session,
        title="提供私有环境安装包和试用方案",
        task_hash="private-deployment-package-task",
    )
    confirmation_task = _create_open_task(
        db_session,
        title="确认客户 POC 环境部署情况",
        task_hash="poc-deployment-follow-up-task",
    )
    matcher = FakeMatcher(
        _batch_match_result(
            completed_task,
            confirmation_task,
            decisions=(
                FollowUpTaskReconciliationTaskDecision(
                    decision="COMPLETE",
                    task_public_id=completed_task.public_id,
                    confidence=0.96,
                    evidence_terms=("已经给客户反馈了部署相关的内容", "安装包和试用方案"),
                ),
                FollowUpTaskReconciliationTaskDecision(
                    decision="ASK_CONFIRMATION",
                    task_public_id=confirmation_task.public_id,
                    confidence=0.72,
                    needs_confirmation=True,
                    forbid_auto_reasons=("LOW_CONFIDENCE",),
                    evidence_terms=("周四跟进客户 POC 环境部署情况",),
                ),
            ),
        )
    )
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=matcher,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.expire_all()
    assert db_session.get(FollowUpTask, completed_task.id).status == FollowUpTaskStatus.COMPLETED
    assert db_session.get(FollowUpTask, confirmation_task.id).status == FollowUpTaskStatus.OPEN
    assert {item["task_public_id"]: item["status"] for item in state["execution_results"]} == {
        completed_task.public_id: "EXECUTED",
        confirmation_task.public_id: "SKIPPED",
    }
    assert [case["task_public_id"] for case in state["confirmation_cases"]] == [confirmation_task.public_id]
    assert state["post_commit"]["automatic_task_transitions"] == [
        {
            "task_public_id": completed_task.public_id,
            "title": "提供私有环境安装包和试用方案",
            "action": "COMPLETE",
            "previous_status": "OPEN",
            "new_status": "COMPLETED",
        }
    ]
    assert state["post_commit"]["needs_user_confirmation"] is True


@pytest.mark.asyncio
async def test_post_commit_workflow_requests_confirmation_for_single_low_confidence_task(db_session):
    task = _create_open_task(db_session)
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(_match_result(task, confidence=0.72)),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.refresh(task)
    assert task.status == FollowUpTaskStatus.OPEN
    assert state["post_commit"]["automatic_task_transitions"] == []
    assert [case["task_public_id"] for case in state["post_commit"]["confirmation_cases"]] == [task.public_id]
    assert state["post_commit"]["needs_user_confirmation"] is True


@pytest.mark.asyncio
async def test_post_commit_workflow_requests_confirmation_when_related_task_is_kept_open(db_session):
    task = _create_open_task(
        db_session,
        title="等领导回来后继续推进",
        task_hash="related-keep-open-task",
    )
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(
            _batch_match_result(
                task,
                decisions=(
                    FollowUpTaskReconciliationTaskDecision(
                        decision="KEEP_OPEN",
                        task_public_id=task.public_id,
                        confidence=0.88,
                        evidence_terms=("重新评估私有化部署方案", "继续推进"),
                    ),
                ),
            )
        ),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.refresh(task)
    assert task.status == FollowUpTaskStatus.OPEN
    assert state["post_commit"]["automatic_task_transitions"] == []
    assert [case["task_public_id"] for case in state["post_commit"]["confirmation_cases"]] == [task.public_id]
    assert state["post_commit"]["confirmation_cases"][0]["suggested_action"] == "KEEP_OPEN"
    assert state["post_commit"]["needs_user_confirmation"] is True


@pytest.mark.asyncio
async def test_post_commit_workflow_supersedes_stale_confirmation_cases_after_reconciliation(db_session):
    retained_task = _create_open_task(
        db_session,
        title="确认客户 POC 环境部署情况",
        task_hash="retained-poc-confirmation-task",
    )
    stale_task = _create_open_task(
        db_session,
        title="继续跟进立项流程",
        task_hash="stale-project-confirmation-task",
    )
    first_workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(
            _batch_match_result(
                retained_task,
                stale_task,
                decisions=(
                    FollowUpTaskReconciliationTaskDecision(
                        decision="ASK_CONFIRMATION",
                        task_public_id=retained_task.public_id,
                        confidence=0.72,
                        needs_confirmation=True,
                        evidence_terms=("POC 环境部署",),
                    ),
                    FollowUpTaskReconciliationTaskDecision(
                        decision="ASK_CONFIRMATION",
                        task_public_id=stale_task.public_id,
                        confidence=0.68,
                        needs_confirmation=True,
                        evidence_terms=("立项流程",),
                    ),
                ),
            )
        ),
    )

    first_state = await first_workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    assert {case["task_public_id"] for case in first_state["confirmation_cases"]} == {
        retained_task.public_id,
        stale_task.public_id,
    }

    second_workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(
            _batch_match_result(
                retained_task,
                decisions=(
                    FollowUpTaskReconciliationTaskDecision(
                        decision="ASK_CONFIRMATION",
                        task_public_id=retained_task.public_id,
                        confidence=0.72,
                        needs_confirmation=True,
                        evidence_terms=("POC 环境部署",),
                    ),
                ),
            )
        ),
    )

    second_state = await second_workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    pending_cases, total = follow_up_task_confirmation_case_crud.list_pending_by_source_activity(
        db_session,
        team_id=1,
        source_activity_id=190,
    )
    stale_case = (
        db_session.query(FollowUpTaskConfirmationCase)
        .filter(FollowUpTaskConfirmationCase.task_id == stale_task.id)
        .one()
    )

    assert [case["task_public_id"] for case in second_state["confirmation_cases"]] == [retained_task.public_id]
    assert total == 1
    assert [case.task_id for case in pending_cases] == [retained_task.id]
    assert stale_case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert stale_case.cancelled_reason == "SOURCE_RECONCILIATION_SUPERSEDED"


@pytest.mark.asyncio
async def test_post_commit_workflow_auto_completes_high_confidence_task_without_runtime_feature_gate(db_session):
    task = _create_open_task(db_session)
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(_match_result(task)),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.refresh(task)
    cases, total = follow_up_task_confirmation_case_crud.list_pending_by_task(
        db_session,
        team_id=1,
        task_id=task.id,
    )
    assert task.status == FollowUpTaskStatus.COMPLETED
    assert state["execution_results"][0]["status"] == "EXECUTED"
    assert cases == []
    assert total == 0
    assert state["confirmation_cases"] == []
    assert state["post_commit"]["needs_user_confirmation"] is False
    assert state["post_commit"]["confirmation_case_public_ids"] == []
    assert state["post_commit"]["automatic_task_transitions"] == [
        {
            "task_public_id": task.public_id,
            "title": task.title,
            "action": "COMPLETE",
            "previous_status": "OPEN",
            "new_status": "COMPLETED",
        }
    ]


@pytest.mark.asyncio
async def test_post_commit_delivery_uses_confirmation_case_owner_not_activity_owner(db_session):
    task = _create_open_task(db_session)
    task.owner_id = "3"
    db_session.commit()
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(_match_result(task)),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.expire_all()
    case = db_session.query(FollowUpTaskConfirmationCase).one()
    delivery = db_session.query(FollowUpTaskConfirmationPromptDelivery).one()
    assert case.owner_id == "3"
    assert delivery.owner_id == "3"
    assert delivery.status == FollowUpTaskConfirmationPromptStatus.SENT
    assert state["confirmation_deliveries"][0]["status"] == FollowUpTaskConfirmationPromptStatus.SENT


@pytest.mark.asyncio
async def test_post_commit_workflow_fences_stale_revision_before_task_transition(db_session):
    task = _create_open_task(db_session)
    projection_service = FakeProjectionService()

    class RevisionAdvancingMatcher(FakeMatcher):
        async def match_activity(self, db, *, team_id, activity_id, include_cross_owner=False):
            result = await super().match_activity(
                db,
                team_id=team_id,
                activity_id=activity_id,
                include_cross_owner=include_cross_owner,
            )
            activity = db.query(CustomerActivity).filter_by(id=activity_id, team_id=team_id).one()
            activity.post_commit_revision = 2
            db.commit()
            return result

    workflow = _workflow(
        projection_service=projection_service,
        matcher=RevisionAdvancingMatcher(_match_result(task)),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.expire_all()
    assert db_session.get(FollowUpTask, task.id).status == FollowUpTaskStatus.OPEN
    assert state["skip_reason"] == "SUPERSEDED_ACTIVITY_REVISION"
    assert state["execution_results"] == []
    assert state["confirmation_cases"] == []
    assert state["confirmation_deliveries"] == []
    assert db_session.query(FollowUpTaskConfirmationCase).count() == 0
    assert db_session.query(FollowUpTaskConfirmationPromptDelivery).count() == 0
    assert any(event["event"] == "activity_revision_fenced" for event in state["events"])


@pytest.mark.asyncio
async def test_post_commit_workflow_preserves_activity_not_found_fence_reason(db_session):
    task = _create_open_task(db_session)
    projection_service = FakeProjectionService()

    class ActivityDeletingMatcher(FakeMatcher):
        async def match_activity(self, db, *, team_id, activity_id, include_cross_owner=False):
            result = await super().match_activity(
                db,
                team_id=team_id,
                activity_id=activity_id,
                include_cross_owner=include_cross_owner,
            )
            activity = db.query(CustomerActivity).filter_by(id=activity_id, team_id=team_id).one()
            db.delete(activity)
            db.commit()
            return result

    workflow = _workflow(
        projection_service=projection_service,
        matcher=ActivityDeletingMatcher(_match_result(task)),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.expire_all()
    assert db_session.get(FollowUpTask, task.id).status == FollowUpTaskStatus.OPEN
    assert state["skip_reason"] == "ACTIVITY_NOT_FOUND"
    assert state["confirmation_cases"] == []
    assert state["confirmation_deliveries"] == []
    assert any(
        event["event"] == "activity_revision_fenced" and event["reason"] == "ACTIVITY_NOT_FOUND"
        for event in state["events"]
    )


@pytest.mark.asyncio
async def test_post_commit_workflow_cancels_case_when_revision_changes_before_delivery(db_session):
    task = _create_open_task(db_session)
    projection_service = FakeProjectionService()

    class RevisionAdvancingConfirmationService:
        def __init__(self) -> None:
            self.delegate = FollowUpTaskConfirmationService()

        def create_case_from_plan_action(self, db, **kwargs):
            result = self.delegate.create_case_from_plan_action(db, **kwargs)
            activity = db.query(CustomerActivity).filter_by(id=190, team_id=1).one()
            activity.post_commit_revision = 2
            return result

    class DeliveryMustNotRun:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, request):
            self.calls += 1
            raise AssertionError("superseded confirmation must not be dispatched")

    delivery_workflow = DeliveryMustNotRun()
    workflow = CustomerActivityPostCommitWorkflow(
        projection_service=projection_service,
        matcher=FakeMatcher(_match_result(task, confidence=0.72)),
        confirmation_service=RevisionAdvancingConfirmationService(),
        delivery_workflow=delivery_workflow,
        checkpointer=None,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.expire_all()
    case = db_session.query(FollowUpTaskConfirmationCase).one()
    assert delivery_workflow.calls == 0
    assert case.status == FollowUpTaskConfirmationStatus.CANCELLED
    assert case.cancelled_reason == "SOURCE_ACTIVITY_REVISION_SUPERSEDED"
    assert state["skip_reason"] == "SUPERSEDED_ACTIVITY_REVISION"
    assert state["confirmation_cases"] == []
    assert state["confirmation_deliveries"] == [
        {
            "case_public_id": case.public_id,
            "status": "SKIPPED",
            "reason_code": "SUPERSEDED_ACTIVITY_REVISION",
        }
    ]
    assert state["post_commit"]["needs_user_confirmation"] is False
    assert state["post_commit"]["confirmation_case_public_ids"] == []


def _post_commit_ledger_actions(db_session) -> list[AgentWorkflowAction]:
    return (
        db_session.query(AgentWorkflowAction)
        .filter(AgentWorkflowAction.workflow_id.like("wf_pc_%"))
        .order_by(AgentWorkflowAction.action_type.asc())
        .all()
    )


class FailOneTransitionExecutionService:
    def __init__(self, failed_task_public_id: str) -> None:
        self.failed_task_public_id = failed_task_public_id
        self.calls: list[str] = []

    def execute_action(self, db, *, team_id, action, plan, actor_id, expected_owner_id, commit):
        task_public_id = str(action.task_public_id)
        self.calls.append(task_public_id)
        if task_public_id == self.failed_task_public_id:
            raise RuntimeError("simulated transition failure")
        return FollowUpTaskTransitionExecutionResult(
            status="EXECUTED",
            action=action.action,
            task_public_id=task_public_id,
            previous_status="OPEN",
            new_status="COMPLETED",
        )


class FailOneConfirmationService:
    def __init__(self, failed_task_public_id: str) -> None:
        self.failed_task_public_id = failed_task_public_id
        self.calls: list[str] = []

    def create_case_from_plan_action(self, db, *, task, **kwargs):
        self.calls.append(str(task.public_id))
        if task.public_id == self.failed_task_public_id:
            raise RuntimeError("simulated confirmation failure")
        return follow_up_task_confirmation_service.create_case_from_plan_action(
            db,
            task=task,
            **kwargs,
        )


@pytest.mark.asyncio
async def test_post_commit_workflow_isolates_one_transition_failure_and_continues_other_tasks(db_session):
    failed_task = _create_open_task(
        db_session,
        title="提供私有环境安装包",
        task_hash="transition-failure-task",
    )
    successful_task = _create_open_task(
        db_session,
        title="提供试用方案",
        task_hash="transition-success-task",
    )
    matcher = FakeMatcher(
        _batch_match_result(
            failed_task,
            successful_task,
            decisions=(
                FollowUpTaskReconciliationTaskDecision(
                    decision="COMPLETE",
                    task_public_id=failed_task.public_id,
                    confidence=0.96,
                ),
                FollowUpTaskReconciliationTaskDecision(
                    decision="COMPLETE",
                    task_public_id=successful_task.public_id,
                    confidence=0.95,
                ),
            ),
        )
    )
    execution_service = FailOneTransitionExecutionService(failed_task.public_id)
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=matcher,
        execution_service=execution_service,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    results = {item["task_public_id"]: item for item in state["execution_results"]}
    assert execution_service.calls == [failed_task.public_id, successful_task.public_id]
    assert results[failed_task.public_id]["status"] == "FAILED"
    assert results[successful_task.public_id]["status"] == "EXECUTED"
    assert state["post_commit"]["automatic_task_transitions"] == [
        {
            "task_public_id": successful_task.public_id,
            "title": successful_task.title,
            "action": "COMPLETE",
            "previous_status": "OPEN",
            "new_status": "COMPLETED",
        }
    ]
    assert state["post_commit"]["needs_user_confirmation"] is True


@pytest.mark.asyncio
async def test_post_commit_workflow_isolates_one_confirmation_failure_and_projects_remaining_cards(db_session):
    failed_task = _create_open_task(
        db_session,
        title="确认安装包是否可用",
        task_hash="confirmation-failure-task",
    )
    successful_task = _create_open_task(
        db_session,
        title="确认 POC 环境部署情况",
        task_hash="confirmation-success-task",
    )
    decisions = tuple(
        FollowUpTaskReconciliationTaskDecision(
            decision="ASK_CONFIRMATION",
            task_public_id=task.public_id,
            confidence=0.68,
            needs_confirmation=True,
            forbid_auto_reasons=("LOW_CONFIDENCE",),
        )
        for task in (failed_task, successful_task)
    )
    confirmation_service = FailOneConfirmationService(failed_task.public_id)
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(_batch_match_result(failed_task, successful_task, decisions=decisions)),
        confirmation_service=confirmation_service,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    assert confirmation_service.calls == [failed_task.public_id, successful_task.public_id]
    cases = {item["task_public_id"]: item for item in state["confirmation_cases"]}
    assert cases[failed_task.public_id]["status"] == "FAILED"
    assert cases[successful_task.public_id]["case_public_id"].startswith("fuc_")
    assert state["post_commit"]["confirmation_case_public_ids"] == [cases[successful_task.public_id]["case_public_id"]]


@pytest.mark.asyncio
async def test_post_commit_workflow_keeps_existing_pending_case_when_rebuild_fails(db_session):
    task = _create_open_task(
        db_session,
        title="确认 POC 环境部署情况",
        task_hash="retain-existing-case-on-rebuild-failure",
    )
    decision = FollowUpTaskReconciliationTaskDecision(
        decision="ASK_CONFIRMATION",
        task_public_id=task.public_id,
        confidence=0.68,
        needs_confirmation=True,
        forbid_auto_reasons=("LOW_CONFIDENCE",),
    )
    first_workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(_batch_match_result(task, decisions=(decision,))),
    )
    first_state = await first_workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )
    existing_case_public_id = first_state["confirmation_cases"][0]["case_public_id"]

    failing_workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=FakeMatcher(_batch_match_result(task, decisions=(decision,))),
        confirmation_service=FailOneConfirmationService(task.public_id),
    )
    second_state = await failing_workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    pending_cases, total = follow_up_task_confirmation_case_crud.list_pending_by_source_activity(
        db_session,
        team_id=1,
        source_activity_id=190,
    )
    assert second_state["confirmation_cases"][0]["status"] == "FAILED"
    assert total == 1
    assert [case.public_id for case in pending_cases] == [existing_case_public_id]


class CandidateCapturingMatcher:
    def __init__(self) -> None:
        self.candidate_public_ids: list[str] = []
        self.current_source_open_task_public_ids: list[str] = []

    async def match_activity(self, db, *, team_id, activity_id, include_cross_owner=False):
        self.current_source_open_task_public_ids = [
            task.public_id
            for task in (
                db.query(FollowUpTask)
                .filter(
                    FollowUpTask.team_id == team_id,
                    FollowUpTask.source_activity_id == activity_id,
                    FollowUpTask.status == FollowUpTaskStatus.OPEN,
                )
                .order_by(FollowUpTask.id.asc())
                .all()
            )
        ]
        candidate_set = task_reconciliation_service.list_candidates_for_activity(
            db,
            team_id=team_id,
            activity_id=activity_id,
            include_cross_owner=include_cross_owner,
            anchor_at=datetime(2026, 8, 25, 10, 0, 0),
        )
        self.candidate_public_ids = [candidate.public_id for candidate in candidate_set.items]
        decision = FollowUpTaskReconciliationDecision(
            candidate_public_ids=tuple(self.candidate_public_ids),
            task_decisions=tuple(
                FollowUpTaskReconciliationTaskDecision(
                    decision="COMPLETE",
                    task_public_id=candidate.public_id,
                    confidence=0.96,
                    evidence_terms=("已微信联系", "继续跟进立项流程"),
                )
                for candidate in candidate_set.items
            ),
        )
        return TaskReconciliationSemanticMatchResult(
            decision=decision,
            candidate_set=candidate_set,
            source="workflow_projection_boundary_test",
        )


class UnavailableMatcher:
    async def match_activity(self, db, *, team_id, activity_id, include_cross_owner=False):
        raise TaskReconciliationUnavailableError("AI_CONFIG_MISSING")


@pytest.mark.asyncio
async def test_post_commit_workflow_projects_new_task_before_reconciling_only_historical_tasks(db_session):
    activity = db_session.query(CustomerActivity).filter_by(id=190, team_id=1).one()
    activity.source_content = "今天已微信联系客户，客户反馈项目正在走立项流程。"
    activity.summary = "已联系客户并取得立项流程进展。"
    activity.next_action = "下周三继续跟进立项流程"
    activity.next_follow_time = datetime(2026, 9, 2, 9, 0, 0)
    activity.occurred_at = datetime(2026, 8, 25, 10, 0, 0)
    historical_task = _create_open_task(
        db_session,
        title="继续跟进立项流程",
        task_hash="historical-project-approval-task",
    )
    db_session.commit()
    matcher = CandidateCapturingMatcher()
    workflow = _workflow(
        projection_service=follow_up_task_projection_service,
        matcher=matcher,
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    db_session.expire_all()
    projected_tasks = (
        db_session.query(FollowUpTask)
        .filter(
            FollowUpTask.team_id == 1,
            FollowUpTask.source_activity_id == 190,
        )
        .order_by(FollowUpTask.id.asc())
        .all()
    )
    assert len(projected_tasks) == 1
    projected_task = projected_tasks[0]
    assert matcher.current_source_open_task_public_ids == [projected_task.public_id]
    assert matcher.candidate_public_ids == [historical_task.public_id]
    assert db_session.get(FollowUpTask, historical_task.id).status == FollowUpTaskStatus.COMPLETED
    assert projected_task.status == FollowUpTaskStatus.OPEN
    assert projected_task.title == "下周三继续跟进立项流程"
    assert state["post_commit"]["automatic_task_transitions"][0]["task_public_id"] == historical_task.public_id


@pytest.mark.asyncio
async def test_post_commit_workflow_treats_matcher_unavailable_as_technical_skip_not_user_confirmation(db_session):
    workflow = _workflow(
        projection_service=FakeProjectionService(),
        matcher=UnavailableMatcher(),
    )

    state = await workflow.run(
        activity_id=190,
        team_id=1,
        expected_activity_revision=1,
        trigger_type="ACTIVITY_CREATED_DETERMINISTIC",
        actor_id="2",
    )

    assert state["projection_result"] is not None
    assert state["match_result"] is None
    assert state["transition_plan"] is None
    assert state["execution_results"] == []
    assert state["confirmation_cases"] == []
    assert state["post_commit"]["needs_user_confirmation"] is False
    assert state["skip_reason"] == "RECONCILIATION_UNAVAILABLE"
    assert any(
        event["event"] == "historical_reconciliation_skipped"
        and event["reason"] == "AI_CONFIG_MISSING"
        for event in state["events"]
    )
