from datetime import datetime

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.contract import Contract
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.invoice import InvoiceApplication
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.procurement import OpportunityStageSnapshot
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.models.customer import Customer
from app.models.customer_fact import CustomerFact, CustomerFactRevision, CustomerFactSource
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.services.customer_fact_service import (
    CustomerFactCandidateInput,
    CustomerFactInput,
    CustomerFactSourceInput,
    customer_fact_service,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(engine, tables=[
        Customer.__table__,
        CustomerActivity.__table__,
        CustomerActivityDeletionTombstone.__table__,
        CustomerDealJourney.__table__,
        CustomerDealJourneyEvent.__table__,
        Opportunity.__table__,
        OpportunityStageSnapshot.__table__,
        Contract.__table__,
        PaymentPlan.__table__,
        PaymentRecord.__table__,
        InvoiceApplication.__table__,
        FollowUpTask.__table__,
        SalesCommitment.__table__,
        CustomerFact.__table__,
        CustomerFactSource.__table__,
        CustomerFactRevision.__table__,
        CustomerLegacySourceProgress.__table__,
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


def test_fact_progress_excludes_assistant_origin_and_advances_eligible_mutations():
    db = _session()
    _customer(db)
    legacy = CustomerFactInput(
        tenant_id=2, team_id=2, customer_id=101, fact_type="need", subject="采购",
        content="初版", confidence=0.8,
        source=CustomerFactSourceInput(source_type="customer_activity", source_object_id="701"),
    )
    assistant = CustomerFactInput(
        tenant_id=2, team_id=2, customer_id=101, fact_type="risk", subject="风险",
        content="仅 2.0", confidence=0.8,
        source=CustomerFactSourceInput(source_type="customer_activity", source_object_id="902"),
    )
    db.add_all([
        CustomerActivity(id=701, team_id=2, customer_id=101, activity_kind="PHONE_FOLLOW_UP",
                         source_content="旧源", creator_id="9", owner_id="9"),
        CustomerActivity(id=902, team_id=2, customer_id=101, activity_kind="PHONE_FOLLOW_UP",
                         source_content="秘密", creator_id="9", owner_id="9", submission_source="ASSISTANT_2",
                         submission_id="turn-902", submission_fingerprint="a" * 64),
    ])
    db.flush()
    customer_fact_service.upsert_fact(db, legacy)
    progress = db.query(CustomerLegacySourceProgress).filter_by(team_id=2, customer_id=101).one()
    assert progress.eligible_revision == 1
    customer_fact_service.upsert_fact(db, assistant)
    db.refresh(progress)
    assert progress.eligible_revision == 1
    customer_fact_service.upsert_fact(db, CustomerFactInput(
        tenant_id=2, team_id=2, customer_id=101, fact_type="need", subject="采购",
        content="新版", confidence=0.8, source=legacy.source,
    ))
    db.refresh(progress)
    assert progress.eligible_revision == 2
    customer_fact_service.upsert_fact(db, CustomerFactInput(
        tenant_id=2, team_id=2, customer_id=101, fact_type="need", subject="采购",
        content="新版", confidence=0.8, source=legacy.source,
    ))
    db.refresh(progress)
    assert progress.eligible_revision == 2

def test_assistant_fact_cannot_overwrite_eligible_content():
    import pytest

    db = _session()
    _customer(db)
    db.add_all([
        CustomerActivity(id=701, team_id=2, customer_id=101, activity_kind="PHONE_FOLLOW_UP",
                         source_content="旧来源", creator_id="9", owner_id="9"),
        CustomerActivity(id=902, team_id=2, customer_id=101, activity_kind="PHONE_FOLLOW_UP",
                         source_content="2.0 来源", creator_id="9", owner_id="9", submission_source="ASSISTANT_2",
                         submission_id="turn-902", submission_fingerprint="a" * 64),
    ])
    db.flush()
    old_fact = customer_fact_service.upsert_fact(db, CustomerFactInput(
        tenant_id=2, team_id=2, customer_id=101, fact_type="need", subject="采购",
        content="已核实需求", source=CustomerFactSourceInput(source_type="customer_activity", source_object_id="701"),
    ))
    with pytest.raises(ValueError, match="未经验证"):
        customer_fact_service.upsert_fact(db, CustomerFactInput(
            tenant_id=2, team_id=2, customer_id=101, fact_type="need", subject="采购",
            content="未核实的 2.0 内容", source=CustomerFactSourceInput(
                source_type="customer_activity", source_object_id="902",
            ),
        ))
    db.refresh(old_fact)
    assert old_fact.content == "已核实需求"


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


def test_customer_fact_service_ignores_low_confidence_conflicting_candidate():
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

    assert assessment.action == "ignore"
    assert assessment.reason == "low_confidence_or_conflicting_fact_ignored"
    assert assessment.existing_fact_id == 501
    assert assessment.existing_version == 3
    assert assessment.conflict_reason == "候选事实与客户智能档案中的既有事实内容不同"


def test_customer_fact_service_ignores_high_confidence_candidate_without_evidence():
    assessment = customer_fact_service.assess_candidate_against_context(
        candidate=CustomerFactCandidateInput(
            fact_type="need",
            subject="私有化部署",
            content="客户需要私有环境安装包和试用方案。",
            confidence=0.96,
            action="upsert",
            evidence_quote=None,
        ),
        existing_facts=[],
    )

    assert assessment.action == "ignore"
    assert assessment.reason == "missing_evidence_ignored"


def test_customer_fact_service_silently_ignores_high_confidence_conflict():
    assessment = customer_fact_service.assess_candidate_against_context(
        candidate=CustomerFactCandidateInput(
            fact_type="stage",
            subject="POC",
            content="客户已经完成 POC，准备进入合同审批。",
            confidence=0.97,
            action="upsert",
            evidence_quote="客户明确表示 POC 已完成",
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

    assert assessment.action == "ignore"
    assert assessment.reason == "conflicting_fact_ignored"
    assert assessment.existing_fact_id == 501
    assert assessment.existing_version == 3
    assert assessment.conflict_reason == "候选事实与客户智能档案中的既有事实内容不同"
