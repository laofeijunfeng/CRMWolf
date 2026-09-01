from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_fact import CustomerFact
from app.models.deal_journey import CustomerDealJourneyEvent
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.services.customer_profile_evidence_resolver import CustomerProfileEvidenceResolver


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def evidence_db():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerDealJourneyEvent.__table__,
            CustomerFact.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            Customer(
                id=1,
                public_id="cus_profile_evidence",
                team_id=1,
                account_name="证据测试客户",
                city="上海",
                creator_id="user_1",
            ),
            Customer(
                id=2,
                public_id="cus_other_team",
                team_id=2,
                account_name="其他团队客户",
                city="广州",
                creator_id="user_2",
            ),
        ]
    )
    session.flush()
    occurred_at = datetime(2026, 8, 29, 10, 0, 0)
    session.add(
        CustomerActivity(
            id=10,
            team_id=1,
            customer_id=1,
            activity_kind="meeting",
            title="服务器需求沟通",
            source_content="客户提出线上服务器使用需求",
            summary="讨论线上服务器",
            occurred_at=occurred_at,
            creator_id="user_1",
            owner_id="user_1",
        )
    )
    session.add(
        CustomerActivity(
            id=11,
            team_id=2,
            customer_id=2,
            activity_kind="meeting",
            title="不应被读取",
            source_content="跨团队内容",
            occurred_at=occurred_at,
            creator_id="user_2",
            owner_id="user_2",
        )
    )
    session.add(
        CustomerDealJourneyEvent(
            id=20,
            team_id=1,
            customer_id=1,
            deal_journey_id=101,
            event_type="opportunity_stage_changed",
            event_time=occurred_at,
            source_type="opportunity",
            source_id=301,
            summary="商机进入方案评估",
        )
    )
    session.add(
        CustomerFact(
            id=30,
            fact_key="fact:30",
            tenant_id=1,
            team_id=1,
            customer_id=1,
            fact_type="usage_requirement",
            subject="线上服务器",
            content="客户需要线上服务器",
            confidence=0.9,
            occurred_at=occurred_at,
        )
    )
    session.add(
        SalesCommitment(
            id=40,
            public_id="scm_40",
            team_id=1,
            customer_id=1,
            owner_id="user_1",
            creator_id="user_1",
            title="补充服务器方案",
            content="整理并补充线上服务器方案",
            source_type="customer_activity",
            source_key="activity:10",
            commitment_hash="hash-40",
        )
    )
    session.add(
        FollowUpTask(
            id=50,
            public_id="fut_50",
            team_id=1,
            customer_id=1,
            owner_id="user_1",
            creator_id="user_1",
            title="发送服务器方案",
            description="发送方案给客户",
            due_at=occurred_at,
            source_type="sales_commitment",
            source_key="commitment:40",
            task_hash="hash-50",
        )
    )
    session.commit()
    yield session
    session.close()
    engine.dispose()


def test_resolves_all_supported_evidence_types_with_customer_scoped_links(evidence_db):
    resolver = CustomerProfileEvidenceResolver()
    registry = [
        {"evidence_key": "activity:10", "source_type": "customer_activity", "source_id": 10, "source_version": 7},
        {"evidence_key": "journey-event:20", "source_type": "deal_journey_event", "source_id": 20},
        {"evidence_key": "task:50", "source_type": "follow_up_task", "source_id": 50},
        {"evidence_key": "commitment:40", "source_type": "sales_commitment", "source_id": 40},
        {"evidence_key": "fact:30", "source_type": "customer_fact", "source_id": 30},
    ]

    resolved = resolver.resolve_registry(
        evidence_db,
        team_id=1,
        customer_id=1,
        customer_public_id="cus_profile_evidence",
        registry=registry,
    )

    assert [item["availability"] for item in resolved] == ["AVAILABLE"] * 5
    assert resolved[0]["snippet"] == "客户提出线上服务器使用需求"
    assert resolved[0]["source_version"] == 7
    assert resolved[1]["title"] == "opportunity_stage_changed"
    assert resolved[2]["title"] == "发送服务器方案"
    assert resolved[3]["title"] == "补充服务器方案"
    assert resolved[4]["title"] == "usage_requirement"
    assert all("cus_profile_evidence" in str(item["link"]) for item in resolved)


def test_missing_source_is_explicitly_unavailable_without_reusing_stale_text(evidence_db):
    resolver = CustomerProfileEvidenceResolver()

    resolved = resolver.resolve_one(
        evidence_db,
        team_id=1,
        customer_id=1,
        customer_public_id="cus_profile_evidence",
        reference={
            "evidence_key": "activity:999",
            "source_type": "customer_activity",
            "source_id": 999,
            "title": "旧标题",
            "snippet": "旧内容",
        },
    )

    assert resolved.availability == "UNAVAILABLE"
    assert resolved.visibility == "UNAVAILABLE"
    assert resolved.link is None
    assert resolved.reason
    assert resolved.title == "原始记录不可用"
    assert resolved.snippet is None


def test_cross_team_and_cross_customer_references_cannot_be_resolved(evidence_db):
    resolver = CustomerProfileEvidenceResolver()

    cross_team = resolver.resolve_one(
        evidence_db,
        team_id=1,
        customer_id=1,
        customer_public_id="cus_profile_evidence",
        reference={"evidence_key": "activity:11", "source_type": "customer_activity", "source_id": 11},
    )
    wrong_customer = resolver.resolve_one(
        evidence_db,
        team_id=1,
        customer_id=999,
        customer_public_id="cus_profile_evidence",
        reference={
            "evidence_key": "activity:10",
            "source_type": "customer_activity",
            "source_id": 10,
            "source_version": 7,
        },
    )

    assert cross_team.availability == "UNAVAILABLE"
    assert wrong_customer.availability == "UNAVAILABLE"


def test_unknown_or_legacy_reference_preserves_registry_metadata_as_unavailable(evidence_db):
    resolver = CustomerProfileEvidenceResolver()

    resolved = resolver.resolve_one(
        evidence_db,
        team_id=1,
        customer_id=1,
        customer_public_id="cus_profile_evidence",
        reference={
            "evidence_id": "legacy-1",
            "source_type": "legacy_note",
            "occurred_at": "2026-08-28T08:00:00",
            "title": "历史记录",
            "snippet": "历史证据",
        },
    )

    assert resolved.evidence_key == "legacy-1"
    assert resolved.source_id is None
    assert resolved.availability == "UNAVAILABLE"
    assert resolved.occurred_at == "2026-08-28T08:00:00"
