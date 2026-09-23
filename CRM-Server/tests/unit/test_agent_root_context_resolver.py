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
from app.models.customer import Customer
from app.models.sales_commitment import FollowUpTask, FollowUpTaskConfirmationCase
from app.schemas.agent_persistence import (
    AgentQueryResultSetCreate,
    AgentResultPage,
    AgentUIActionRegistration,
)
from app.services.agent.orchestrator import (
    RootContextUnavailableError,
    RootConversationMemory,
    RootRuntimeContext,
    RootTurnInput,
    TextTurnInput,
    WorkflowContinuation,
    WorkflowRef,
)
from app.services.agent.orchestrator.context import DatabaseRootContextResolver
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
            Customer.__table__,
            FollowUpTask.__table__,
            FollowUpTaskConfirmationCase.__table__,
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
            root_thread_id="crm_agent_turn:test",
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
                root_context_role="RESUMABLE_WORKFLOW",
                target={
                    "workflow_continuation": continuation.model_dump(mode="json"),
                    "interaction_type": "confirmation",
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
        assert snapshot.resumable_workflow_continuations[0].waiting_interaction_type == "confirmation"
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


async def test_pending_case_action_is_not_implicit_root_workflow_context() -> None:
    engine, db = _db_session()
    try:
        session = AgentSession(session_key="root-context-pending-case", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        message = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="有一个待确认待办",
        )
        db.add(message)
        db.flush()
        continuation = WorkflowContinuation(
            root_thread_id="crm_agent_turn:test",
            workflow_ref=WorkflowRef(
                workflow_id="wf_pending_case_must_not_resume",
                interrupt_id="int_pending_case",
            ),
            parent_checkpoint_id="cp_pending_case",
            subgraph_checkpoint_ns="workflow_subgraph:pending-case",
            subgraph_checkpoint_id="cp_pending_case_subgraph",
        )
        AgentUIActionRepository().register(
            db,
            AgentUIActionRegistration(
                public_id="act_pending_case_context",
                team_id=1,
                user_id=2,
                session_id=session.id,
                message_id=message.id,
                action_type="submit_interaction",
                root_context_role="PENDING_CASE",
                target={
                    "workflow_continuation": continuation.model_dump(mode="json"),
                    "follow_up_confirmation_case_public_id": "fuc_11111111111111111111111111111111",
                },
                consumption_mode="ONE_SHOT",
            ),
            now=datetime(2026, 8, 23, 10, 0, 0),
        )
        db.commit()

        snapshot = await DatabaseRootContextResolver().resolve(
            turn=_turn(session_id=session.id),
            runtime=RootRuntimeContext(
                db=db,
                metadata={"now": datetime(2026, 8, 23, 10, 30, 0)},
            ),
        )

        assert snapshot.active_workflow is None
        assert snapshot.resumable_workflows == []
    finally:
        db.close()
        engine.dispose()


async def test_database_context_resolver_loads_owned_memory_and_recent_messages_without_current_turn() -> None:
    engine, db = _db_session()
    try:
        session = AgentSession(
            session_key="root-memory",
            team_id=1,
            user_id=2,
            context_json={
                "client_context": {"view": "customers"},
                "_root_conversation_memory": {
                    "schema_version": "crm.agent.root-memory.v1",
                    "resolved_customer": {
                        "customer_id": "cus_00000000000000000000000000000001",
                        "customer_name": "河南双汇实业有限公司",
                        "lookup_name": "河南双汇",
                    },
                    "current_task": "customer_activity",
                    "known_activity_content": "刚刚和客户沟通了 POC 部署",
                    "known_next_action": "下周五再联系",
                },
            },
        )
        db.add(session)
        db.flush()
        db.add_all(
            [
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    content="刚刚和河南双汇沟通了 POC 部署",
                    client_request_id="old-request",
                ),
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.ASSISTANT,
                    content="已识别客户河南双汇实业有限公司",
                ),
                AgentMessage(
                    team_id=1,
                    user_id=2,
                    session_id=session.id,
                    role=AgentMessageRole.USER,
                    content="下周五再联系",
                    client_request_id="current-request",
                ),
            ]
        )
        db.flush()

        context = await DatabaseRootContextResolver().resolve(
            turn=RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=session.id,
                client_request_id="current-request",
                input=TextTurnInput(type="text", text="下周五再联系"),
            ),
            runtime=RootRuntimeContext(db=db),
        )

        assert context.conversation_memory.resolved_customer is not None
        assert context.conversation_memory.resolved_customer.customer_name == "河南双汇实业有限公司"
        assert [message.content for message in context.recent_messages] == [
            "刚刚和河南双汇沟通了 POC 部署",
            "已识别客户河南双汇实业有限公司",
        ]
    finally:
        db.close()
        engine.dispose()


async def test_database_context_resolver_persists_root_memory_without_overwriting_other_context() -> None:
    engine, db = _db_session()
    try:
        session = AgentSession(
            session_key="root-memory-write",
            team_id=1,
            user_id=2,
            context_json={"client_context": {"view": "customers"}},
        )
        db.add(session)
        db.flush()
        turn = _turn(session_id=session.id)
        memory = RootConversationMemory(
            resolved_customer={
                "customer_id": "cus_00000000000000000000000000000001",
                "customer_name": "河南双汇实业有限公司",
            },
            current_task="customer_activity",
        )

        DatabaseRootContextResolver().persist_conversation_memory(db, turn=turn, memory=memory)
        db.refresh(session)

        assert session.context_json["client_context"] == {"view": "customers"}
        assert session.context_json["_root_conversation_memory"]["current_task"] == "customer_activity"
    finally:
        db.close()
        engine.dispose()


async def test_cancelled_follow_up_cutoff_wins_over_stale_root_memory_writer(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'root-cancel-race.db'}")
    Base.metadata.create_all(engine, tables=[AgentSession.__table__, AgentMessage.__table__])
    sessions = sessionmaker(bind=engine)
    setup = sessions()
    stale = sessions()
    cancelling = sessions()
    check = sessions()
    try:
        session = AgentSession(
            session_key="root-cancel-race",
            team_id=1,
            user_id=2,
            context_json={
                "client_context": {"view": "customers"},
                "_root_conversation_memory": RootConversationMemory(
                    current_task="customer_activity",
                    known_activity_content="旧客户跟进",
                ).model_dump(mode="json", exclude_none=True),
            },
        )
        setup.add(session)
        setup.flush()
        setup.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.USER,
                content="旧客户跟进",
                client_request_id="old-request",
            )
        )
        setup.commit()
        session_id = session.id

        # The old turn has already loaded its Root snapshot before cancellation.
        assert stale.get(AgentSession, session_id).context_json["_root_conversation_memory"][
            "known_activity_content"
        ] == "旧客户跟进"
        cancelled_result = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session_id,
            role=AgentMessageRole.ASSISTANT,
            content="已取消当前工作流。",
        )
        cancelling.add(cancelled_result)
        cancelling.flush()
        cancelling.get(AgentSession, session_id).context_json = {
            "client_context": {"view": "customers"},
            "_root_conversation_memory": RootConversationMemory().model_dump(mode="json", exclude_none=True),
            "recent_messages_after_id": cancelled_result.id,
        }
        cancelling.commit()

        DatabaseRootContextResolver().persist_conversation_memory(
            stale,
            turn=RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=session_id,
                client_request_id="old-request",
                input=TextTurnInput(type="text", text="旧客户跟进"),
            ),
            memory=RootConversationMemory(current_task="customer_activity", known_activity_content="旧客户跟进"),
        )
        stale.commit()
        saved = check.get(AgentSession, session_id).context_json
        assert saved["recent_messages_after_id"] == cancelled_result.id
        assert RootConversationMemory.model_validate(saved["_root_conversation_memory"]).current_task is None
        assert saved["client_context"] == {"view": "customers"}
    finally:
        check.close()
        cancelling.close()
        stale.close()
        setup.close()
        engine.dispose()


async def test_cancelled_follow_up_cutoff_excludes_old_messages_but_keeps_new_request_context() -> None:
    engine, db = _db_session()
    try:
        session = AgentSession(session_key="root-cancel-cutoff", team_id=1, user_id=2)
        db.add(session)
        db.flush()
        old_user = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            content="河南双汇旧任务跟进",
            client_request_id="old-task",
        )
        db.add(old_user)
        db.flush()
        cancelled_result = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content="已取消当前工作流。",
        )
        db.add(cancelled_result)
        db.flush()
        session.context_json = {"recent_messages_after_id": cancelled_result.id}
        new_user = AgentMessage(
            team_id=1,
            user_id=2,
            session_id=session.id,
            role=AgentMessageRole.USER,
            content="为新客户创建完整跟进",
            client_request_id="new-task",
        )
        db.add(new_user)
        db.flush()
        first = await DatabaseRootContextResolver().resolve(
            turn=RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=session.id,
                client_request_id="new-task",
                input=TextTurnInput(type="text", text="为新客户创建完整跟进"),
            ),
            runtime=RootRuntimeContext(db=db),
        )
        assert first.recent_messages == []
        db.add(
            AgentMessage(
                team_id=1,
                user_id=2,
                session_id=session.id,
                role=AgentMessageRole.ASSISTANT,
                content="新任务需澄清客户",
            )
        )
        db.flush()
        second = await DatabaseRootContextResolver().resolve(
            turn=RootTurnInput(
                team_id=1,
                user_id=2,
                session_id=session.id,
                client_request_id="another-task",
                input=TextTurnInput(type="text", text="继续新任务"),
            ),
            runtime=RootRuntimeContext(db=db),
        )
        assert [message.content for message in second.recent_messages] == [
            "为新客户创建完整跟进",
            "新任务需澄清客户",
        ]
    finally:
        db.close()
        engine.dispose()
