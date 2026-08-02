from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_fact import CustomerFact, CustomerFactReviewAudit, CustomerFactRevision, CustomerFactSource
from app.services.customer_fact_service import (
    CustomerFactCandidateInput,
    CustomerFactInput,
    CustomerFactReviewAuditInput,
    CustomerFactSourceInput,
    customer_fact_service,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        Customer.__table__,
        CustomerFact.__table__,
        CustomerFactSource.__table__,
        CustomerFactRevision.__table__,
        CustomerFactReviewAudit.__table__,
    ])
    Session = sessionmaker(bind=engine)
    return Session()


def _customer(db):
    customer = Customer(id=101, team_id=2, account_name="越秀金融", city="广州", creator_id="9")
    db.add(customer)
    db.commit()
    return customer


def test_customer_fact_service_upserts_fact_and_source_idempotently():
    db = _session()
    _customer(db)

    first = customer_fact_service.upsert_fact(
        db,
        CustomerFactInput(
            tenant_id=2,
            team_id=2,
            customer_id=101,
            fact_type="need",
            subject="采购流程",
            content="客户希望规范合同和采购流程。",
            confidence=0.82,
            occurred_at=datetime(2026, 8, 2, 10, 0, 0),
            source=CustomerFactSourceInput(
                source_type="customer_activity",
                source_object_id="701",
                business_object_type="customer_activity",
                business_object_id="701",
                evidence_id="ev-701",
                quote="希望规范合同和采购流程",
            ),
        ),
    )
    second = customer_fact_service.upsert_fact(
        db,
        CustomerFactInput(
            tenant_id=2,
            team_id=2,
            customer_id=101,
            fact_type="need",
            subject="采购流程",
            content="客户希望先规范采购流程，再推进合同审批。",
            confidence=1.2,
            source=CustomerFactSourceInput(
                source_type="customer_activity",
                source_object_id="701",
                business_object_type="customer_activity",
                business_object_id="701",
                evidence_id="ev-701",
                quote="先规范采购流程",
            ),
        ),
    )
    db.commit()

    assert first.id == second.id
    assert db.query(CustomerFact).count() == 1
    assert db.query(CustomerFactSource).count() == 1
    assert db.query(CustomerFactRevision).count() == 2
    assert second.content == "客户希望先规范采购流程，再推进合同审批。"
    assert second.confidence == 1.0
    assert second.version == 2
    revisions = db.query(CustomerFactRevision).order_by(CustomerFactRevision.version.asc()).all()
    assert revisions[0].change_type == "CREATED"
    assert revisions[0].previous_content is None
    assert revisions[0].new_content == "客户希望规范合同和采购流程。"
    assert revisions[1].change_type == "UPDATED"
    assert revisions[1].previous_content == "客户希望规范合同和采购流程。"
    assert revisions[1].new_content == "客户希望先规范采购流程，再推进合同审批。"


def test_customer_fact_service_does_not_create_revision_for_duplicate_fact_payload():
    db = _session()
    _customer(db)
    fact_input = CustomerFactInput(
        tenant_id=2,
        team_id=2,
        customer_id=101,
        fact_type="need",
        subject="采购流程",
        content="客户希望规范合同和采购流程。",
        confidence=0.82,
        occurred_at=datetime(2026, 8, 2, 10, 0, 0),
        source=CustomerFactSourceInput(
            source_type="customer_activity",
            source_object_id="701",
        ),
    )

    first = customer_fact_service.upsert_fact(db, fact_input)
    second = customer_fact_service.upsert_fact(db, fact_input)
    db.commit()

    assert first.id == second.id
    assert second.version == 1
    assert db.query(CustomerFactRevision).count() == 1


def test_customer_fact_service_projects_context_payload_with_sources():
    db = _session()
    _customer(db)
    customer_fact_service.upsert_fact(
        db,
        CustomerFactInput(
            tenant_id=2,
            team_id=2,
            customer_id=101,
            fact_type="risk",
            subject="审批",
            content="客户内部审批链较长。",
            confidence=0.76,
            source=CustomerFactSourceInput(
                source_type="deal_journey_event",
                source_object_id="801",
                business_object_type="opportunity",
                business_object_id="301",
            ),
        ),
    )
    db.commit()

    payload = customer_fact_service.to_context_payload(db, team_id=2, customer_id=101)

    assert payload[0]["fact_type"] == "risk"
    assert payload[0]["version"] == 1
    assert payload[0]["sources"][0]["business_object_id"] == "301"


def test_customer_fact_service_marks_conflicting_candidate_for_review():
    assessment = customer_fact_service.assess_candidate_against_context(
        candidate=CustomerFactCandidateInput(
            fact_type="stage",
            subject="POC",
            content="客户已经完成 POC，准备进入合同审批。",
            confidence=0.76,
            action="upsert",
        ),
        existing_facts=[{
            "id": 501,
            "fact_type": "stage",
            "subject": "POC",
            "content": "客户刚开始 POC。",
            "confidence": 0.9,
            "status": "ACTIVE",
            "version": 3,
        }],
    )

    assert assessment.action == "review"
    assert assessment.existing_fact_id == 501
    assert assessment.existing_version == 3
    assert assessment.conflict_reason == "候选事实与客户智能档案中的既有事实内容不同"


def test_customer_fact_service_records_review_decision_idempotently():
    db = _session()
    _customer(db)
    audit_input = CustomerFactReviewAuditInput(
        tenant_id=2,
        team_id=2,
        customer_id=101,
        event_key="event-1",
        fact_type="risk",
        subject="审批",
        content="客户内部审批链可能较长。",
        confidence=0.62,
        decision="REJECTED",
        reviewer_id=9,
        decision_source="web",
        reason="表达不够确定",
        conflict_reason="候选事实与客户智能档案中的既有事实内容不同",
        evidence_quote="需要再走内部流程",
    )

    first = customer_fact_service.record_review_decision(db, audit_input)
    second = customer_fact_service.record_review_decision(db, audit_input)
    db.commit()

    assert first.id == second.id
    assert db.query(CustomerFactReviewAudit).count() == 1
    assert second.decision == "REJECTED"
    assert second.reviewer_id == 9
