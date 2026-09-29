from app.services.customer_evidence_retriever import CustomerEvidenceRetriever
from app.services.customer_qdrant_index_service import CustomerEvidenceSearchResult


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


def _follow_up_task_hit(score: float = 0.9, source_object_id: str = "fut_2_0") -> CustomerEvidenceSearchResult:
    return CustomerEvidenceSearchResult(
        id="task-hit", score=score, tenant_id=2, team_id=2, customer_id=101,
        source_type="follow_up_task", source_object_id=source_object_id,
        business_object_type="follow_up_task", business_object_id=source_object_id,
        title="跟进任务: 发送验收报告", text="王总明确说POC通过，周五发验收报告",
    )

def test_assistant2_backed_follow_up_task_evidence_is_excluded() -> None:
    from types import SimpleNamespace

    hit = _follow_up_task_hit()
    qdrant = FakeTaskEvidenceQdrant([hit])
    retriever = CustomerEvidenceRetriever(
        embedding_service=FakeEmbeddingService(), qdrant_index_service=qdrant, min_score=0.45,
    )
    task_row = SimpleNamespace(public_id="fut_2_0", source_activity_id=55)

    class FakeTaskDb:
        def scalar(self, statement):
            return False  # underlying activity source ineligible (ASSISTANT_2)

        def query(self, model):
            class _Query:
                def filter(self, *criteria):
                    return self

                def first(self):
                    return task_row

            return _Query()

    result = retriever.retrieve_customer_evidence(
        FakeTaskDb(), team_id=2, customer_id=101,
        query_text="POC 验收", evidence_limit=1, exclude_assistant2=True,
    )
    assert result.hits == []
    assert result.state.returned_count == 0

def test_legacy_follow_up_task_evidence_without_activity_source_still_passes() -> None:
    from types import SimpleNamespace

    hit = _follow_up_task_hit(0.7, source_object_id="fut_legacy")
    qdrant = FakeTaskEvidenceQdrant([hit])
    retriever = CustomerEvidenceRetriever(
        embedding_service=FakeEmbeddingService(), qdrant_index_service=qdrant, min_score=0.45,
    )
    task_row = SimpleNamespace(public_id="fut_legacy", source_activity_id=None)

    class FakeTaskDb:
        def scalar(self, statement):
            return True

        def query(self, model):
            class _Query:
                def filter(self, *criteria):
                    return self

                def first(self):
                    return task_row

            return _Query()

    result = retriever.retrieve_customer_evidence(
        FakeTaskDb(), team_id=2, customer_id=101,
        query_text="POC 验收", evidence_limit=1, exclude_assistant2=True,
    )
    assert [item.evidence_id for item in result.hits] == ["task-hit"]

def test_assistant2_flood_does_not_starve_legacy_evidence(monkeypatch) -> None:
    """Overfetch window full of 2.0 hits must not hide older legacy evidence."""

    legacy_hit = CustomerEvidenceSearchResult(
        id="legacy-hit", score=0.50, tenant_id=2, team_id=2, customer_id=101,
        source_type="follow_up", source_object_id="7",
        business_object_type="customer_activity", business_object_id="7",
        title="电话跟进", text="早期POC背景",
    )
    flood = [
        CustomerEvidenceSearchResult(
            id=f"assistant2-{index}", score=0.95, tenant_id=2, team_id=2, customer_id=101,
            source_type="follow_up", source_object_id=str(900 + index),
            business_object_type="customer_activity", business_object_id=str(900 + index),
            title="助手活动", text="2.0 洪泛",
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
        embedding_service=FakeEmbeddingService(), qdrant_index_service=qdrant, min_score=0.45,
    )

    result = retriever.retrieve_customer_evidence(
        object(), team_id=2, customer_id=101,
        query_text="POC", evidence_limit=1, exclude_assistant2=True,
    )
    assert [hit.evidence_id for hit in result.hits] == ["legacy-hit"]
    # The retriever must have widened the search window beyond the initial 3N.
    assert max(qdrant.limits) > 3
