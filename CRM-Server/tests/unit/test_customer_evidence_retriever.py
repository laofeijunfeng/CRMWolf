from dataclasses import replace
from datetime import datetime

import pytest

from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.services.customer_evidence_builder import CustomerEvidenceBuilder
from app.services.customer_evidence_retriever import CustomerEvidenceRetriever
from app.services.customer_qdrant_index_service import CustomerEvidenceSearchResult
from app.services.legacy_profile_source import source_origin
from tests.unit.test_customer_intelligence_context_service import _seed_customer_context, _session


class FakeEmbeddingService:
    def embed_query(self, db, team_id, text):
        return [0.1, 0.2, 0.3]


class FakeQdrantIndexService:
    enabled = True

    def __init__(self) -> None:
        self.calls = []

    def search_customer_evidence(self, **kwargs):
        self.calls.append(kwargs)
        return [
            CustomerEvidenceSearchResult(
                id="profile",
                score=0.80,
                tenant_id=2,
                team_id=2,
                customer_id=101,
                source_type="follow_up",
                source_object_id="activity-0",
                business_object_type=None,
                business_object_id=None,
                title="电话跟进",
                text="客户正在推进 POC。",
            ),
            CustomerEvidenceSearchResult(
                id="follow-up",
                score=0.79,
                tenant_id=2,
                team_id=2,
                customer_id=101,
                source_type="follow_up",
                source_object_id="act-1",
                business_object_type="customer_activity",
                business_object_id="act-1",
                title="电话跟进",
                text="张总确认本周开始 POC。",
            ),
        ]


def test_customer_evidence_retriever_overfetches_and_ranks_by_vector_score() -> None:
    qdrant = FakeQdrantIndexService()
    retriever = CustomerEvidenceRetriever(
        embedding_service=FakeEmbeddingService(),
        qdrant_index_service=qdrant,
        min_score=0.45,
    )

    result = retriever.retrieve_customer_evidence(
        object(),
        team_id=2,
        customer_id=101,
        query_text="客户 POC 怎么样",
        evidence_limit=1,
    )

    assert qdrant.calls[0]["limit"] == 3
    assert result.state.status == "ok"
    assert result.state.strategy == "customer_semantic_qdrant"
    assert result.hits[0].evidence_id == "profile"
    assert result.hits[0].score == 0.80
    assert "adjusted_score" not in result.hits[0].to_dict()
    assert "source_weights" not in result.state.to_dict()


class FakeTaskEvidenceQdrant:
    enabled = True

    def __init__(self, hits) -> None:
        self.hits = hits

    def search_customer_evidence(self, **kwargs):
        return self.hits


def _follow_up_row(model, **overrides):
    fields = (
        {"task_hash": "task-940"}
        if model is FollowUpTask
        else {
            "commitment_hash": "commitment-940",
            "content": "周五发送验收报告",
        }
    )
    fields.update(
        id=940,
        team_id=2,
        customer_id=101,
        creator_id="9",
        owner_id="9",
        title="发送验收报告",
        due_at=datetime(2026, 10, 1),
        source_type="CUSTOMER_ACTIVITY",
        source_key="activity:701",
        source_activity_id=701,
    )
    fields.update(overrides)
    return model(**fields)


def _follow_up_hit(row):
    builder = CustomerEvidenceBuilder()
    evidence = builder.from_follow_up_task(row) if isinstance(row, FollowUpTask) else builder.from_sales_commitment(row)
    assert evidence is not None
    return CustomerEvidenceSearchResult(
        id=evidence.document_key,
        score=0.9,
        tenant_id=evidence.tenant_id,
        team_id=evidence.team_id,
        customer_id=evidence.customer_id,
        source_type=evidence.source_type,
        source_object_id=evidence.source_object_id,
        business_object_type=evidence.business_object_type,
        business_object_id=evidence.business_object_id,
        title=evidence.title,
        text=evidence.text,
    )


@pytest.mark.parametrize("model", [FollowUpTask, SalesCommitment])
@pytest.mark.parametrize("deleted_activity", [False, True], ids=["live", "deleted"])
def test_legacy_public_follow_up_evidence_survives_assistant2_filter(model, deleted_activity) -> None:
    engine, db = _session()
    try:
        _seed_customer_context(db)
        row = _follow_up_row(model)
        db.add(row)
        db.flush()
        if deleted_activity:
            db.add(
                CustomerActivityDeletionTombstone(
                    team_id=2,
                    customer_id=101,
                    activity_id=701,
                    submission_source="FORM",
                )
            )
            row.source_activity_id = None
            db.delete(db.query(CustomerActivity).filter_by(id=701).one())
            db.flush()
        hit = _follow_up_hit(row)
        retriever = CustomerEvidenceRetriever(
            embedding_service=FakeEmbeddingService(),
            qdrant_index_service=FakeTaskEvidenceQdrant([hit]),
            min_score=0.45,
        )
        result = retriever.retrieve_customer_evidence(
            db,
            team_id=2,
            customer_id=101,
            query_text="POC 验收",
            evidence_limit=1,
            exclude_assistant2=True,
        )
        assert result.state.status == "ok"
        assert [(item.evidence_id, item.source_object_id) for item in result.hits] == [(hit.id, row.public_id)]
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize("model", [FollowUpTask, SalesCommitment])
@pytest.mark.parametrize(
    "case",
    [
        "assistant2",
        "originless",
        "unknown_activity",
        "activity_conflict",
        "public_source_hint",
        "cross_team",
        "cross_customer",
        "conflicting_evidence_hint",
        "malformed_id",
        "unknown_id",
    ],
)
def test_unverified_public_follow_up_evidence_is_excluded(model, case) -> None:
    engine, db = _session()
    try:
        _seed_customer_context(db)
        row = _follow_up_row(model)
        if case in {"assistant2", "activity_conflict"}:
            db.add(
                CustomerActivity(
                    id=902,
                    team_id=2,
                    customer_id=101,
                    activity_kind="PHONE_FOLLOW_UP",
                    source_content="2.0",
                    creator_id="9",
                    owner_id="9",
                    submission_source="ASSISTANT_2",
                    submission_id="turn-902",
                    submission_fingerprint="a" * 64,
                )
            )
            row.source_key = "activity:902"
            if case == "assistant2":
                row.source_activity_id = 902
        elif case == "originless":
            row.source_activity_id = None
            row.source_key = "public:unverified"
        elif case == "public_source_hint":
            row.source_public_id = "act_unverified"
        elif case == "unknown_activity":
            row.source_activity_id = None
            row.source_key = "activity:999"
        elif case in {"cross_team", "cross_customer"}:
            row.team_id = 3 if case == "cross_team" else 2
            row.customer_id = 102
            db.add(Customer(id=102, team_id=row.team_id, account_name="其他客户", city="深圳", creator_id="9"))
            db.add(
                CustomerActivity(
                    id=903,
                    team_id=row.team_id,
                    customer_id=102,
                    activity_kind="PHONE_FOLLOW_UP",
                    source_content="其他客户的旧活动",
                    creator_id="9",
                    owner_id="9",
                    submission_source="FORM",
                )
            )
            row.source_key = "activity:903"
            row.source_activity_id = 903
        db.add(row)
        db.flush()
        hit = _follow_up_hit(row)
        if case == "conflicting_evidence_hint":
            other = _follow_up_row(
                model,
                id=941,
                **({"task_hash": "task-941"} if model is FollowUpTask else {"commitment_hash": "commitment-941"}),
            )
            db.add(other)
            db.flush()
            hit = replace(hit, business_object_id=other.public_id)
        elif case in {"malformed_id", "unknown_id"}:
            prefix = "fut" if model is FollowUpTask else "scm"
            identifier = f"{prefix}_legacy" if case == "malformed_id" else f"{prefix}_" + "f" * 32
            hit = replace(hit, source_object_id=identifier, business_object_id=identifier)
        elif case in {"cross_team", "cross_customer"}:
            assert source_origin(db, row.team_id, row.customer_id, hit.source_type, row.public_id)
            # A vector payload claiming this customer cannot borrow a real source from another scope.
            hit = replace(hit, tenant_id=2, team_id=2, customer_id=101)
        retriever = CustomerEvidenceRetriever(
            embedding_service=FakeEmbeddingService(),
            qdrant_index_service=FakeTaskEvidenceQdrant([hit]),
            min_score=0.45,
        )
        result = retriever.retrieve_customer_evidence(
            db,
            team_id=2,
            customer_id=101,
            query_text="POC 验收",
            evidence_limit=1,
            exclude_assistant2=True,
        )
        assert result.state.status == "low_confidence"
        assert result.hits == []
        assert result.state.returned_count == 0
    finally:
        db.close()
        engine.dispose()


def test_assistant2_flood_does_not_starve_legacy_evidence(monkeypatch) -> None:
    """Overfetch window full of 2.0 hits must not hide older legacy evidence."""

    legacy_hit = CustomerEvidenceSearchResult(
        id="legacy-hit",
        score=0.50,
        tenant_id=2,
        team_id=2,
        customer_id=101,
        source_type="follow_up",
        source_object_id="7",
        business_object_type="customer_activity",
        business_object_id="7",
        title="电话跟进",
        text="早期POC背景",
    )
    flood = [
        CustomerEvidenceSearchResult(
            id=f"assistant2-{index}",
            score=0.95,
            tenant_id=2,
            team_id=2,
            customer_id=101,
            source_type="follow_up",
            source_object_id=str(900 + index),
            business_object_type="customer_activity",
            business_object_id=str(900 + index),
            title="助手活动",
            text="2.0 洪泛",
        )
        for index in range(6)
    ]

    class FloodQdrant:
        enabled = True

        def __init__(self) -> None:
            self.limits = []

        def search_customer_evidence(self, **kwargs):
            self.limits.append(kwargs["limit"])
            return flood if kwargs["limit"] <= 6 else [*flood, legacy_hit]

    def eligibility_by_source(db, item, team_id, customer_id):
        # Activity ids >= 900 are ASSISTANT_2 rows; id 7 is legacy.
        return int(item.source_object_id) < 900

    monkeypatch.setattr(CustomerEvidenceRetriever, "_eligible_legacy_evidence", staticmethod(eligibility_by_source))
    qdrant = FloodQdrant()
    retriever = CustomerEvidenceRetriever(
        embedding_service=FakeEmbeddingService(),
        qdrant_index_service=qdrant,
        min_score=0.45,
    )

    result = retriever.retrieve_customer_evidence(
        object(),
        team_id=2,
        customer_id=101,
        query_text="POC",
        evidence_limit=1,
        exclude_assistant2=True,
    )
    assert [hit.evidence_id for hit in result.hits] == ["legacy-hit"]
    # The retriever must have widened the search window beyond the initial 3N.
    assert max(qdrant.limits) > 3
