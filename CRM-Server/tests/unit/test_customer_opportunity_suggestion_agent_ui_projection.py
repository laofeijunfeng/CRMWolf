from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import AgentMessage, AgentSession
from app.models.agent_async_operation import (
    AgentAsyncOperation,
    AgentAsyncOperationEvent,
    AgentAsyncOperationStatus,
)
from app.models.agent_persistence import AgentUIAction
from app.models.customer_opportunity_suggestion_job import CustomerOpportunitySuggestionJob
from app.services.agent.async_operation_service import AgentAsyncOperationService
from app.services.customer_activity_contracts import CustomerActivitySuggestionJobStatus
from app.services.customer_opportunity_suggestion_agent_ui_projection import (
    CustomerOpportunitySuggestionAgentUIProjection,
)
from app.services.customer_opportunity_suggestion_operation_projector import (
    CustomerOpportunitySuggestionOperationProjector,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AgentSession.__table__,
            AgentMessage.__table__,
            AgentUIAction.__table__,
            AgentAsyncOperation.__table__,
            AgentAsyncOperationEvent.__table__,
            CustomerOpportunitySuggestionJob.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    db.add(AgentSession(id=3, session_key="suggestion-ui-session", team_id=1, user_id=2))
    db.commit()
    return engine, db


def _job(decision: str):
    return CustomerOpportunitySuggestionJob(
        public_id="cosj_ui_001",
        team_id=1,
        activity_id=241,
        activity_revision=1,
        submission_source="AGENT",
        status=CustomerActivitySuggestionJobStatus.COMPLETED.value,
        attempt_count=1,
        run_id="run-ui-001",
        graph_thread_id="thread-ui-001",
        result_json={
            "success": True,
            "decision": decision,
            "requires_user_action": True,
            "suggestion": {"title": "企业版采购", "execution_payload": {"amount": 100}},
        },
        created_time=datetime(2026, 9, 1, 10, 0),
        updated_time=datetime(2026, 9, 1, 10, 1),
    )


def _operation(db):
    return AgentAsyncOperationService().ensure_scheduled(
        db,
        operation_key="customer-opportunity-suggestion:cosj_ui_001",
        request_id="cosj_ui_001",
        team_id=1,
        user_id=2,
        session_id=3,
        source_user_message_id=11,
        source_assistant_message_id=12,
        operation_type="customer_opportunity_suggestion",
        resource_type="customer_activity",
        resource_id=241,
        resource_public_id="cosj_ui_001",
        summary="正在分析是否需要推进商机",
    )


def _project_waiting(db, decision: str):
    db.add(_job(decision))
    db.commit()
    operation = _operation(db)
    CustomerOpportunitySuggestionOperationProjector().project_request(
        db,
        team_id=1,
        request_id="cosj_ui_001",
        operation_public_id=operation.public_id,
    )
    db.commit()
    return db.get(AgentAsyncOperation, operation.id)


def test_create_suggestion_projects_one_agent_message_and_action_idempotently():
    engine, db = _session()
    try:
        operation = _project_waiting(db, "CREATE_OPPORTUNITY")
        projector = CustomerOpportunitySuggestionAgentUIProjection()

        message_id = projector.project_operation(db, operation=operation)
        db.commit()
        assert message_id is not None
        assert db.query(AgentMessage).count() == 1
        assert db.query(AgentUIAction).count() == 1
        action = db.query(AgentUIAction).one()
        assert action.message_id == message_id
        assert action.root_context_role == "PROJECTION_ONLY"
        assert action.target_json["workflow_trigger"]["job_public_id"] == "cosj_ui_001"
        assert action.target_json["workflow_trigger"]["action"] == "CREATE_OPPORTUNITY"
        assert action.target_json["interaction_type"] == "confirmation"
        assert action.target_json["submit_on_select"] is True

        replay_id = projector.project_operation(db, operation=operation)
        db.commit()
        assert replay_id == message_id
        assert db.query(AgentMessage).count() == 1
        assert db.query(AgentUIAction).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_move_suggestion_projects_separate_agent_choice():
    engine, db = _session()
    try:
        operation = _project_waiting(db, "MOVE_OPPORTUNITY_STAGE")
        message_id = CustomerOpportunitySuggestionAgentUIProjection().project_operation(db, operation=operation)
        db.commit()
        message = db.get(AgentMessage, message_id)
        action = db.query(AgentUIAction).one()
        assert "推进机会" in message.content
        assert action.target_json["interaction_type"] == "confirmation"
        assert action.target_json["workflow_trigger"]["action"] == "MOVE_OPPORTUNITY_STAGE"
    finally:
        db.close()
        engine.dispose()


def test_non_actionable_suggestion_does_not_project_agent_ui():
    engine, db = _session()
    try:
        db.add(
            CustomerOpportunitySuggestionJob(
                public_id="cosj_ui_no_action",
                team_id=1,
                activity_id=242,
                activity_revision=1,
                submission_source="AGENT",
                status=CustomerActivitySuggestionJobStatus.COMPLETED.value,
                attempt_count=1,
                run_id="run-ui-no-action",
                graph_thread_id="thread-ui-no-action",
                result_json={"success": True, "decision": "NO_ACTION"},
            )
        )
        db.commit()
        operation = AgentAsyncOperationService().ensure_scheduled(
            db,
            operation_key="customer-opportunity-suggestion:cosj_ui_no_action",
            request_id="cosj_ui_no_action",
            team_id=1,
            user_id=2,
            session_id=3,
            source_user_message_id=11,
            source_assistant_message_id=12,
            operation_type="customer_opportunity_suggestion",
            resource_type="customer_activity",
            resource_id=242,
            resource_public_id="cosj_ui_no_action",
            summary="正在分析是否需要推进商机",
        )
        CustomerOpportunitySuggestionOperationProjector().project_request(
            db,
            team_id=1,
            request_id="cosj_ui_no_action",
            operation_public_id=operation.public_id,
        )
        db.commit()
        assert operation.status == AgentAsyncOperationStatus.SUCCEEDED
        assert CustomerOpportunitySuggestionAgentUIProjection().project_operation(db, operation=operation) is None
        assert db.query(AgentMessage).count() == 0
        assert db.query(AgentUIAction).count() == 0
    finally:
        db.close()
        engine.dispose()
