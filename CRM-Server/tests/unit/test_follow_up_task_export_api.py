"""Follow-up task export API tests (Task 10)."""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import follow_up_tasks
from app.core import deps
from app.core.database import Base
from app.crud.sales_commitment import follow_up_task_crud, sales_commitment_crud
from app.models.agent_persistence import AgentUIAction
from app.models.command_execution import CommandExecution
from app.models.customer import Customer, CustomerMember
from app.models.customer_activity import CustomerActivity
from app.models.customer_intelligence_run import CustomerIntelligenceRun
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTask,
    FollowUpTaskConfirmationCase,
    FollowUpTaskConfirmationPromptDelivery,
    FollowUpTaskEvent,
    FollowUpTaskLLMMatcherRun,
    FollowUpTaskProjectionRun,
    FollowUpTaskReconciliationEvaluationRun,
    FollowUpTaskReconciliationRun,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    FollowUpTaskTransitionPolicyDecisionLog,
    SalesCommitment,
)
from app.models.user import User
from app.schemas.sales_commitment import FollowUpTaskInternalCreate, SalesCommitmentInternalCreate
from app.services import follow_up_task_query_service


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db_session():
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
            User.__table__,
            CommandExecution.__table__,
            AgentUIAction.__table__,
            CustomerIntelligenceRun.__table__,
            Customer.__table__,
            CustomerMember.__table__,
            CustomerActivity.__table__,
            CustomerVectorDocument.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
            FollowUpTaskEvent.__table__,
            FollowUpTaskProjectionRun.__table__,
            FollowUpTaskConfirmationCase.__table__,
            FollowUpTaskConfirmationPromptDelivery.__table__,
            FollowUpTaskTransitionPolicyDecisionLog.__table__,
            FollowUpTaskReconciliationRun.__table__,
            FollowUpTaskLLMMatcherRun.__table__,
            FollowUpTaskReconciliationEvaluationRun.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    _seed_customer_and_activity(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    test_session_factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(follow_up_tasks, "SessionLocal", test_session_factory, raising=False)

    app = FastAPI()
    app.include_router(follow_up_tasks.router)
    app.dependency_overrides[follow_up_tasks.get_db] = lambda: db_session
    app.dependency_overrides[follow_up_tasks.get_current_user_team] = lambda: 1
    app.dependency_overrides[follow_up_tasks.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="售前",
        status="active",
    )
    app.dependency_overrides[deps.get_db] = lambda: db_session
    app.dependency_overrides[deps.get_current_user_team] = lambda: 1
    app.dependency_overrides[deps.get_current_active_user] = lambda: SimpleNamespace(
        id=2,
        name="售前",
        status="active",
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _grant(monkeypatch, *codes: str) -> None:
    from app.crud.permission import permission_crud

    monkeypatch.setattr(
        permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code=code) for code in codes],
    )
    monkeypatch.setattr(
        follow_up_tasks.permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code=code) for code in codes],
    )
    monkeypatch.setattr(
        follow_up_task_query_service.permission_crud,
        "get_user_permissions",
        lambda *args, **kwargs: [SimpleNamespace(code=code) for code in codes],
    )


def _workbook_rows(response) -> list[tuple]:
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    return list(workbook.active.values)


def _seed_customer_and_activity(db):
    db.add_all(
        [
            User(id=2, email="owner@example.com", name="售前"),
            User(id=9, email="customer-owner@example.com", name="销售负责人"),
        ]
    )
    db.add_all(
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
            Customer(
                id=2,
                public_id="cus_22222222222222222222222222222222",
                team_id=1,
                account_name="另一客户",
                city="北京",
                owner_id="9",
                creator_id="9",
            ),
        ]
    )
    db.add_all(
        [
            CustomerMember(
                id=11,
                team_id=1,
                customer_id=1,
                user_id="2",
                member_role="PRESALES",
                access_level="FOLLOW_UP",
                created_by="9",
                is_active=True,
            ),
            CustomerMember(
                id=12,
                team_id=1,
                customer_id=2,
                user_id="2",
                member_role="PRESALES",
                access_level="FOLLOW_UP",
                created_by="9",
                is_active=True,
            ),
        ]
    )
    db.add_all(
        [
            CustomerActivity(
                id=101,
                team_id=1,
                customer_id=1,
                activity_kind="PHONE_FOLLOW_UP",
                title="电话确认预算",
                source_content="客户说下周三看预算。",
                summary="客户还在确认预算。",
                next_action="下周三回访预算进展",
                next_follow_time=datetime(2026, 8, 12, 10, 0, 0),
                occurred_at=datetime(2026, 8, 6, 9, 0, 0),
                owner_id="2",
                creator_id="2",
            ),
            CustomerActivity(
                id=102,
                team_id=1,
                customer_id=2,
                activity_kind="PHONE_FOLLOW_UP",
                title="另一客户跟进",
                source_content="另一客户仍需回访。",
                summary="另一客户待继续跟进。",
                next_action="下周四继续回访",
                next_follow_time=datetime(2026, 8, 13, 10, 0, 0),
                occurred_at=datetime(2026, 8, 7, 9, 0, 0),
                owner_id="2",
                creator_id="2",
            ),
        ]
    )


def _create_commitment(
    db,
    *,
    task_id: int = 201,
    customer_id: int = 1,
    source_activity_id: int = 101,
):
    return sales_commitment_crud.create(
        db,
        SalesCommitmentInternalCreate(
            team_id=1,
            customer_id=customer_id,
            owner_id="2",
            creator_id="2",
            title="跟进预算",
            content="下周三回访预算进展",
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=source_activity_id,
            due_at=datetime(2026, 8, 12, 10, 0, 0),
            due_at_text="下周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            evidence_json={"activity_id": source_activity_id},
            commitment_hash=f"commitment-hash-{task_id}",
        ),
    )


def _create_task(
    db,
    *,
    task_id: int = 201,
    owner_id: str = "2",
    status: str = FollowUpTaskStatus.OPEN,
    customer_id: int = 1,
    source_activity_id: int = 101,
    title: str = "下周三回访预算进展",
    due_at: datetime | None = None,
):
    commitment = _create_commitment(
        db,
        task_id=task_id,
        customer_id=customer_id,
        source_activity_id=source_activity_id,
    )
    return follow_up_task_crud.create(
        db,
        FollowUpTaskInternalCreate(
            team_id=1,
            customer_id=customer_id,
            commitment_id=commitment.id,
            owner_id=owner_id,
            creator_id=owner_id,
            title=title,
            description="客户还在确认预算。",
            status=status,
            due_at=due_at or datetime(2026, 8, 12, 10, 0, 0),
            due_at_text="下周三",
            due_at_granularity=DueAtGranularity.DATETIME,
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_activity_id=source_activity_id,
            confidence=0.92,
            evidence_json={"activity_id": source_activity_id, "quote": "客户说下周三看预算"},
            task_hash=f"task-hash-{task_id}",
        ),
    )


def _create_confirmation_case(
    db,
    *,
    task: FollowUpTask,
    case_id: int = 301,
    public_id: str = "fuc_11111111111111111111111111111111",
):
    case = FollowUpTaskConfirmationCase(
        id=case_id,
        public_id=public_id,
        team_id=task.team_id,
        task_id=task.id,
        customer_id=task.customer_id,
        owner_id=task.owner_id,
        creator_id="2",
        status="PENDING",
        suggested_action="COMPLETE",
        confirmation_hash=f"confirmation-hash-{case_id}",
        question_text=f"上次安排的「{task.title}」这次是否已经完成?",
        source_activity_id=task.source_activity_id,
        source_public_id=task.source_public_id,
        source_plan_json={"plan_source": "unit_test"},
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _export_body(**overrides) -> dict:
    body = {
        "fields": ["public_id", "customer_name", "tracking_content", "status_label", "tracking_time"],
        "tab": "open",
        "filters": [],
        "sorts": [],
    }
    body.update(overrides)
    return body


def test_follow_up_export_requires_permission(client, db_session, monkeypatch):
    _grant(monkeypatch, "customer:view:own")
    _create_task(db_session)
    db_session.commit()

    denied = client.post("/v1/follow-up-tasks/export", json=_export_body())
    assert denied.status_code == 403

    _grant(monkeypatch, "follow_up_task:export", "customer:view:own")
    allowed = client.post("/v1/follow-up-tasks/export", json=_export_body(fields=["public_id"]))
    assert allowed.status_code == 200
    rows = _workbook_rows(allowed)
    assert rows[0] == ("业务 ID",)
    assert len(rows) == 2


def test_follow_up_export_is_always_scoped_to_current_owner(client, db_session, monkeypatch):
    _grant(monkeypatch, "follow_up_task:export", "customer:view:own")
    mine = _create_task(db_session, task_id=201, owner_id="2")
    _create_task(db_session, task_id=202, owner_id="9")
    db_session.commit()

    response = client.post("/v1/follow-up-tasks/export", json=_export_body(fields=["public_id"]))
    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert [row[0] for row in rows[1:]] == [mine.public_id]


def test_follow_up_export_maps_all_status_tabs_and_search_filters(client, db_session, monkeypatch):
    _grant(monkeypatch, "follow_up_task:export", "customer:view:own")
    open_task = _create_task(
        db_session,
        task_id=201,
        title="回访 Alpha 预算",
        due_at=datetime(2026, 8, 21, 10, 0, 0),
    )
    completed = _create_task(
        db_session,
        task_id=202,
        customer_id=2,
        source_activity_id=102,
        status=FollowUpTaskStatus.COMPLETED,
        title="回访 Beta 合同",
        due_at=datetime(2026, 8, 22, 10, 0, 0),
    )
    cancelled = _create_task(
        db_session,
        task_id=203,
        status=FollowUpTaskStatus.CANCELLED,
        title="关闭的追踪",
        due_at=datetime(2026, 8, 23, 10, 0, 0),
    )
    pending = _create_task(
        db_session,
        task_id=204,
        customer_id=2,
        source_activity_id=102,
        title="需确认的回访",
        due_at=datetime(2026, 8, 24, 10, 0, 0),
    )
    _create_confirmation_case(db_session, task=pending, case_id=401, public_id="fuc_pending_confirm_case_01")
    db_session.commit()

    completed_response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(fields=["public_id", "status_label"], tab="completed"),
    )
    cancelled_response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(fields=["public_id", "status_label"], tab="cancelled"),
    )
    all_response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(fields=["public_id", "status_label", "tracking_content"], tab="all"),
    )
    search_response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(
            fields=["public_id", "tracking_content"],
            tab="all",
            search="Beta",
        ),
    )
    filter_response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(
            fields=["public_id", "tracking_content", "status_label"],
            tab="all",
            filters=[{"field": "tracking_content", "op": "contains", "value": "回访"}],
            sorts=[{"field": "tracking_time", "direction": "desc"}],
        ),
    )
    open_response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(fields=["public_id", "status_label"], tab="open"),
    )

    assert completed_response.status_code == 200
    assert cancelled_response.status_code == 200
    assert all_response.status_code == 200
    assert search_response.status_code == 200
    assert filter_response.status_code == 200
    assert open_response.status_code == 200

    assert [row[0] for row in _workbook_rows(completed_response)[1:]] == [completed.public_id]
    assert _workbook_rows(completed_response)[1][1] == "已完成"
    assert [row[0] for row in _workbook_rows(cancelled_response)[1:]] == [cancelled.public_id]
    assert _workbook_rows(cancelled_response)[1][1] == "已关闭"

    all_rows = _workbook_rows(all_response)
    assert {row[0] for row in all_rows[1:]} == {
        open_task.public_id,
        completed.public_id,
        cancelled.public_id,
        pending.public_id,
    }
    labels_by_id = {row[0]: row[1] for row in all_rows[1:]}
    assert labels_by_id[pending.public_id] == "需确认"
    assert labels_by_id[open_task.public_id] == "待处理"

    search_rows = _workbook_rows(search_response)
    assert [row[0] for row in search_rows[1:]] == [completed.public_id]

    filter_rows = _workbook_rows(filter_response)
    assert [row[0] for row in filter_rows[1:]] == [
        pending.public_id,
        completed.public_id,
        open_task.public_id,
    ]

    open_ids = [row[0] for row in _workbook_rows(open_response)[1:]]
    assert set(open_ids) == {open_task.public_id, pending.public_id}
    assert cancelled.public_id not in open_ids
    assert completed.public_id not in open_ids


def test_follow_up_export_writes_all_76_rows_with_business_id(client, db_session, monkeypatch):
    _grant(monkeypatch, "follow_up_task:export", "customer:view:own")
    created = []
    for index in range(76):
        created.append(
            _create_task(
                db_session,
                task_id=900 + index,
                title=f"追踪{index:02d}",
                due_at=datetime(2026, 8, 1, 9, 0, 0) + timedelta(minutes=index),
            )
        )
    db_session.commit()

    response = client.post(
        "/v1/follow-up-tasks/export",
        json=_export_body(
            fields=["public_id", "tracking_content", "tracking_time"],
            tab="open",
            sorts=[{"field": "tracking_time", "direction": "asc"}],
        ),
    )
    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert len(rows) == 77
    assert rows[0] == ("业务 ID", "追踪内容", "跟进时效")
    assert rows[1][0] == created[0].public_id
    assert rows[76][0] == created[75].public_id
    assert rows[1][1] == "追踪00"
    assert rows[1][2] == datetime(2026, 8, 1, 9, 0, 0)


def test_follow_up_export_batch_loads_customers_users_and_confirmations(client, db_session, monkeypatch):
    _grant(monkeypatch, "follow_up_task:export", "customer:view:own")
    task = _create_task(db_session, task_id=501, title="批量投影追踪")
    _create_confirmation_case(db_session, task=task, case_id=601, public_id="fuc_batch_confirm_case_01")
    db_session.commit()

    original_customers = follow_up_task_query_service.FollowUpTaskQueryService._customers_by_id
    original_users = follow_up_task_query_service.FollowUpTaskQueryService._users_by_id
    original_confirmations = follow_up_task_query_service.FollowUpTaskQueryService._pending_confirmations_by_task_id
    customer_calls: list[list[int]] = []
    user_calls: list[list[str | None]] = []
    confirmation_calls: list[list[int]] = []

    def _customers(self, db, *, team_id, customer_ids):
        customer_calls.append(list(customer_ids))
        return original_customers(self, db, team_id=team_id, customer_ids=customer_ids)

    def _users(db, *, user_ids):
        user_calls.append(list(user_ids))
        return original_users(db, user_ids=user_ids)

    def _confirmations(self, db, *, team_id, user_id, tasks):
        confirmation_calls.append([task.id for task in tasks])
        return original_confirmations(self, db, team_id=team_id, user_id=user_id, tasks=tasks)

    with (
        patch.object(
            follow_up_task_query_service.FollowUpTaskQueryService,
            "_customers_by_id",
            _customers,
        ),
        patch.object(
            follow_up_task_query_service.FollowUpTaskQueryService,
            "_users_by_id",
            staticmethod(_users),
        ),
        patch.object(
            follow_up_task_query_service.FollowUpTaskQueryService,
            "_pending_confirmations_by_task_id",
            _confirmations,
        ),
        patch.object(
            follow_up_task_query_service.follow_up_task_query_service.semantic_evidence_service,
            "recall",
        ) as recall,
    ):
        response = client.post(
            "/v1/follow-up-tasks/export",
            json=_export_body(fields=["public_id", "customer_name", "status_label"]),
        )

    assert response.status_code == 200
    rows = _workbook_rows(response)
    assert rows[1][1] == "测试客户"
    assert rows[1][2] == "需确认"
    assert customer_calls == [[task.customer_id]]
    assert confirmation_calls == [[task.id]]
    assert user_calls and task.owner_id in user_calls[0]
    recall.assert_not_called()


def test_follow_up_export_unknown_filter_returns_400(client, monkeypatch):
    _grant(monkeypatch, "follow_up_task:export", "customer:view:own")

    response = client.post("/v1/follow-up-tasks/export", json=_export_body(
        fields=["public_id"],
        filters=[{"field": "missing", "op": "eq", "value": "x"}],
    ))

    assert response.status_code == 400, response.text
    assert "未知筛选字段" in response.text
