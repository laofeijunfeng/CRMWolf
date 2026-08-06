from datetime import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.sales_commitment import DueAtGranularity, FollowUpTask, FollowUpTaskSourceType, SalesCommitment
from app.services.follow_up_task_query_service import FollowUpTaskQueryService
from app.services.follow_up_task_semantic_evidence_service import FollowUpTaskSemanticEvidenceResult
from app.services.follow_up_task_semantic_query_golden_suite import (
    DEFAULT_SEMANTIC_QUERY_GOLDEN_CASES_PATH,
    FollowUpTaskSemanticQueryGoldenCase,
    load_golden_cases,
    run_follow_up_task_semantic_query_golden_suite,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class GoldenSemanticEvidenceService:
    def __init__(self, case: FollowUpTaskSemanticQueryGoldenCase) -> None:
        self.case = case
        self.calls: list[dict[str, object]] = []

    def recall(self, db, *, team_id, query_text, limit=50):
        self.calls.append({"team_id": team_id, "query_text": query_text, "limit": limit})
        return FollowUpTaskSemanticEvidenceResult(
            evidence_by_task_public_id={
                task_public_id: [
                    {
                        "source_type": "follow_up_task",
                        "object_public_id": task_public_id,
                        "title": f"语义证据: {task_public_id}",
                        "snippet": query_text,
                        "score": round(0.99 - index * 0.01, 2),
                    }
                ]
                for index, task_public_id in enumerate(self.case.semantic_task_public_ids)
            },
            retrieval_event={
                "event": "follow_up_task_semantic_evidence",
                "status": "ok",
                "candidate_task_count": len(self.case.semantic_task_public_ids),
                "hit_count": len(self.case.semantic_task_public_ids),
            },
        )


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            SalesCommitment.__table__,
            FollowUpTask.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    return Session()


def test_follow_up_task_semantic_query_golden_cases_load_from_fixture():
    cases = load_golden_cases()
    categories = {case.category for case in cases}

    assert DEFAULT_SEMANTIC_QUERY_GOLDEN_CASES_PATH.exists()
    assert len(cases) >= 8
    assert categories >= {
        "budget",
        "trial",
        "contract",
        "procurement",
        "owner_scope",
        "stale_status",
        "ranking",
        "no_hit",
    }


def test_follow_up_task_semantic_query_golden_suite_passes_static_contracts():
    summary = run_follow_up_task_semantic_query_golden_suite()

    assert summary.ok is True
    assert summary.total >= 8
    assert summary.failed == 0


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda case: case.name)
def test_follow_up_task_semantic_query_golden_case_runs_against_query_service(case):
    db = _session()
    _seed_case(db, case)
    evidence_service = GoldenSemanticEvidenceService(case)
    query_service = FollowUpTaskQueryService(semantic_evidence_service=evidence_service)

    result = query_service.list_tasks(
        db,
        team_id=2,
        user_id=case.user_id,
        status=case.status,
        owner_scope=case.owner_scope,
        query_text=case.query_text,
        limit=20,
    )

    returned_task_ids = [item["id"] for item in result["items"]]
    assert evidence_service.calls == [{"team_id": 2, "query_text": case.query_text, "limit": 20}]
    assert returned_task_ids == list(case.expected_task_public_ids)
    assert not (set(returned_task_ids) & set(case.forbidden_task_public_ids))
    assert result["semantic_retrieval"]["status"] == "ok"
    for item in result["items"]:
        assert item["semantic_evidence"]


def _seed_case(db, case: FollowUpTaskSemanticQueryGoldenCase) -> None:
    customers_by_public_id: dict[str, Customer] = {}
    for task_case in case.tasks:
        customer = customers_by_public_id.get(task_case.customer_public_id)
        if customer is None:
            customer = Customer(
                team_id=2,
                public_id=task_case.customer_public_id,
                account_name=task_case.customer_name,
                city="上海",
                owner_id=task_case.owner_id,
                creator_id=task_case.owner_id,
            )
            db.add(customer)
            db.flush()
            customers_by_public_id[task_case.customer_public_id] = customer

        task = FollowUpTask(
            team_id=2,
            public_id=task_case.public_id,
            customer_id=customer.id,
            owner_id=task_case.owner_id,
            creator_id=task_case.owner_id,
            title=task_case.title,
            description=task_case.description,
            status=task_case.status,
            due_at=datetime.fromisoformat(task_case.due_at),
            due_at_text=task_case.due_at,
            due_at_granularity=DueAtGranularity.DATETIME,
            due_at_timezone="Asia/Shanghai",
            source_type=FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
            source_key=f"semantic-query-golden:{case.name}:{task_case.public_id}",
            confidence=0.93,
            evidence_json={"query_category": case.category},
            task_hash=f"hash-{case.name}-{task_case.public_id}",
            completed_at=datetime.fromisoformat(task_case.completed_at) if task_case.completed_at else None,
            cancelled_at=datetime.fromisoformat(task_case.cancelled_at) if task_case.cancelled_at else None,
        )
        db.add(task)
    db.commit()
