from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_context_answer_telemetry import CustomerContextAnswerTelemetry
from app.models.customer_vector_document import CustomerVectorDocument
from app.services.customer_intelligence_health_service import customer_intelligence_health_service


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


class _VectorParams:
    size = 1024


class _CollectionParams:
    vectors = _VectorParams()


class _CollectionConfig:
    params = _CollectionParams()


class _CollectionInfo:
    config = _CollectionConfig()
    points_count = 43


def _session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerVectorDocument.__table__,
            CustomerContextAnswerTelemetry.__table__,
        ],
    )
    return engine, sessionmaker(bind=engine)()


def test_customer_intelligence_health_reports_degraded_when_embedding_config_missing(monkeypatch):
    engine, db = _session()

    class Settings:
        QDRANT_ENABLED = True
        QDRANT_VECTOR_SIZE = 1024
        CUSTOMER_EVIDENCE_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"

        def get_customer_evidence_embedding_api_key(self):
            return ""

        def get_customer_evidence_embedding_base_url(self):
            return ""

        def get_customer_evidence_embedding_dimensions(self):
            return 1024

    class Client:
        def collection_exists(self, collection_name):
            return True

        def get_collection(self, collection_name):
            return _CollectionInfo()

    monkeypatch.setattr("app.services.customer_intelligence_health_service.get_settings", lambda: Settings())
    monkeypatch.setattr(
        "app.services.customer_intelligence_health_service.customer_qdrant_index_service.collection_name",
        "crm_customer_evidence",
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_health_service.customer_qdrant_index_service._client",
        Client(),
    )
    db.add(CustomerContextAnswerTelemetry(
        tenant_id=2,
        team_id=2,
        customer_id=101,
        answer_source="langchain_structured_output",
        answer_mode="grounded",
        retrieval_status="ok",
        semantic_evidence_count=2,
        citation_count=1,
    ))
    db.add(CustomerContextAnswerTelemetry(
        tenant_id=2,
        team_id=2,
        customer_id=101,
        answer_source="deterministic_context_fallback",
        answer_mode="degraded",
        retrieval_status="embedding_unavailable",
        semantic_evidence_count=0,
        citation_count=0,
    ))
    db.commit()

    try:
        result = customer_intelligence_health_service.check(db)
    finally:
        db.close()
        engine.dispose()

    assert result["status"] == "unhealthy"
    assert "embedding_api_key_missing" in result["issues"]
    assert "embedding_base_url_missing" in result["issues"]
    assert result["qdrant"]["status"] == "ok"
    assert result["answer_quality"]["total_answers"] == 2
    assert result["answer_quality"]["status"] == "degraded"
    assert result["answer_quality"]["alerts"] == ["hard_retrieval_failures_observed"]
    assert result["answer_quality"]["by_answer_mode"] == {"grounded": 1, "degraded": 1}
    assert result["answer_quality"]["by_retrieval_status"] == {"ok": 1, "embedding_unavailable": 1}
    assert result["answer_quality"]["grounded_rate"] == 0.5


def test_customer_intelligence_health_flags_unhealthy_answer_quality(monkeypatch):
    engine, db = _session()

    class Settings:
        QDRANT_ENABLED = True
        QDRANT_VECTOR_SIZE = 1024
        CUSTOMER_EVIDENCE_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"

        def get_customer_evidence_embedding_api_key(self):
            return "configured"

        def get_customer_evidence_embedding_base_url(self):
            return "https://api.siliconflow.cn/v1"

        def get_customer_evidence_embedding_dimensions(self):
            return 1024

    class Client:
        def collection_exists(self, collection_name):
            return True

        def get_collection(self, collection_name):
            return _CollectionInfo()

    monkeypatch.setattr("app.services.customer_intelligence_health_service.get_settings", lambda: Settings())
    monkeypatch.setattr(
        "app.services.customer_intelligence_health_service.customer_qdrant_index_service.collection_name",
        "crm_customer_evidence",
    )
    monkeypatch.setattr(
        "app.services.customer_intelligence_health_service.customer_qdrant_index_service._client",
        Client(),
    )
    for _ in range(2):
        db.add(CustomerContextAnswerTelemetry(
            tenant_id=2,
            team_id=2,
            customer_id=101,
            answer_source="langchain_structured_output",
            answer_mode="grounded",
            retrieval_status="ok",
            semantic_evidence_count=2,
            citation_count=1,
            top_score=0.82,
        ))
    for _ in range(8):
        db.add(CustomerContextAnswerTelemetry(
            tenant_id=2,
            team_id=2,
            customer_id=101,
            answer_source="deterministic_context_fallback",
            answer_mode="fallback",
            retrieval_status="embedding_unavailable",
            semantic_evidence_count=0,
            citation_count=0,
        ))
    db.commit()

    try:
        result = customer_intelligence_health_service.check(db)
    finally:
        db.close()
        engine.dispose()

    assert result["status"] == "unhealthy"
    assert result["issues"] == []
    assert result["answer_quality"]["status"] == "unhealthy"
    assert result["answer_quality"]["total_answers"] == 10
    assert result["answer_quality"]["grounded_rate"] == 0.2
    assert result["answer_quality"]["retrieval_ok_rate"] == 0.2
    assert result["answer_quality"]["weak_answer_rate"] == 0.8
    assert result["answer_quality"]["average_top_score"] == 0.82
    assert "grounded_rate_critically_low" in result["answer_quality"]["alerts"]
    assert "retrieval_ok_rate_critically_low" in result["answer_quality"]["alerts"]
    assert "weak_answer_rate_critically_high" in result["answer_quality"]["alerts"]
