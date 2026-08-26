"""Persistence-backed context resolution for the Root Orchestrator seam."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

from app.core.database import Base
from app.models.agent import AgentMessage, AgentMessageRole, AgentSession
from app.models.agent_persistence import AgentQueryResultSet, AgentUIAction
from app.schemas.agent_persistence import (
    AgentQueryResultSetCreate,
    AgentResultPage,
    AgentUIActionRegistration,
)
from app.services.agent.orchestrator.context import DatabaseRootContextResolver
from app.services.agent.orchestrator import (
    RootContextUnavailableError,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowContinuation,
    WorkflowRef,
)
from app.services.agent.query.result_sets import AgentQueryResultSetRepository
from app.services.agent.query.schemas import CRMFilter, CRMQuerySpec, EntityRef
from app.services.agent.ui.actions import AgentUIActionRepository


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _db_session():
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
            AgentQueryResultSet.__table__,
            AgentUIAction.__table__,
        ],
    )
    return engine, sessionmaker(bind=engine)()


def _turn(*, session_id: int) -> RootTurnInput:
    return RootTurnInput(
        team_id=1,
        user_id=2,
        session_id=session_id,
        client_request_id="req_context_resolver",
        input=TextTurnInput(type="text", text="重点客户呢"),
    )


async def test_database_context_resolver_loads_latest_owned_query_and_workflow() -> None:
    engine, db = _db_session()
    try:
        session = AgentSession(session_key="root-context", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="上海客户列表",
        )
        db.add(message)
        db.flush()
        query = CRMQuerySpec(
            resource="customer",
            projection=["public_id", "account_name", "city"],
            filters=[CRMFilter(field="city", operator="eq", value="上海")],
        )
        ref = EntityRef(
            ref_id="eref_customer_1",
            resource="customer",
            public_id="cus_11111111111111111111111111111111",
            display_name="上海星云科技",
        )
        AgentQueryResultSetRepository().create(
            db,
            AgentQueryResultSetCreate(
                public_id="rs_context_latest",
                team_id=1,
                user_id=2,
                session_id=session.id,
                source_message_id=message.id,
                resource="customer",
                query=query,
                ordered_entity_refs=[ref],
                page=AgentResultPage(
                    page_size=20,
                    range_start=1,
                    range_end=1,
                    total=1,
                ),
            ),
            now=datetime(2026, 8, 23, 10, 0, 0),
        )
        continuation = WorkflowContinuation(
            workflow_ref=WorkflowRef(
                workflow_id="wf_context_follow_up",
                interrupt_id="int_context_confirm",
            ),
            parent_checkpoint_id="cp_root_context",
            subgraph_checkpoint_ns="workflow_subgraph:context",
            subgraph_checkpoint_id="cp_workflow_context",
        )
        AgentUIActionRepository().register(
            db,
            AgentUIActionRegistration(
                public_id="act_context_confirm",
                team_id=1,
                user_id=2,
                session_id=session.id,
                message_id=message.id,
                action_type="submit_interaction",
                target={
                    "workflow_continuation": continuation.model_dump(mode="json"),
                    "type": "confirmation",
                },
                consumption_mode="ONE_SHOT",
            ),
            now=datetime(2026, 8, 23, 10, 0, 0),
        )
        db.commit()
        resolver = DatabaseRootContextResolver()
        turn = _turn(session_id=session.id)

        snapshot = await resolver.resolve(
            turn=turn,
            runtime=RootRuntimeContext(
                db=db,
                metadata={"now": datetime(2026, 8, 23, 10, 30, 0)},
            ),
        )

        assert snapshot.previous_query == query
        assert snapshot.result_set is not None
        assert snapshot.result_set.result_set_id == "rs_context_latest"
        assert snapshot.result_set.ordered_entity_refs[0].result_set_id == "rs_context_latest"
        assert snapshot.active_workflow == continuation.workflow_ref
        assert snapshot.resumable_workflows == [continuation.workflow_ref]
    finally:
        db.close()
        engine.dispose()


async def test_database_context_resolver_ignores_expired_query_context() -> None:
    engine, db = _db_session()
    try:
        session = AgentSession(session_key="root-context-expired", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="过期客户列表",
        )
        db.add(message)
        db.flush()
        AgentQueryResultSetRepository().create(
            db,
            AgentQueryResultSetCreate(
                public_id="rs_context_expired",
                team_id=1,
                user_id=2,
                session_id=session.id,
                source_message_id=message.id,
                resource="customer",
                query=CRMQuerySpec(resource="customer", projection=["public_id"]),
                ordered_entity_refs=[],
                page=AgentResultPage(page_size=20, range_start=0, range_end=0, total=0),
                expires_at=datetime(2026, 8, 23, 10, 0, 0) - timedelta(seconds=1),
            ),
            now=datetime(2026, 8, 23, 9, 0, 0),
        )
        db.commit()
        resolver = DatabaseRootContextResolver()

        snapshot = await resolver.resolve(
            turn=_turn(session_id=session.id),
            runtime=RootRuntimeContext(
                db=db,
                metadata={"now": datetime(2026, 8, 23, 10, 0, 0)},
            ),
        )

        assert snapshot.previous_query is None
        assert snapshot.result_set is None
    finally:
        db.close()
        engine.dispose()


async def test_database_context_resolver_requires_database_runtime() -> None:
    resolver = DatabaseRootContextResolver()

    with pytest.raises(RootContextUnavailableError):
        await resolver.resolve(turn=_turn(session_id=1), runtime=RootRuntimeContext())
