from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
import pytest

from app.core.database import Base
from app.models.agent import AgentMemoryEntry
from app.services.customer_memory_store_service import customer_memory_store_service


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[AgentMemoryEntry.__table__])
    return sessionmaker(bind=engine)()


def test_customer_memory_rejects_profile_sections() -> None:
    db = _session()
    for method in ("upsert_summary", "upsert_preference", "upsert_fact_index"):
        with pytest.raises(ValueError, match="CUSTOMER_MEMORY_SECTION_REMOVED"):
            getattr(customer_memory_store_service, method)(
                db,
                tenant_id=2,
                customer_id=101,
                key="removed",
                value={"text": "不应保留"},
            )
    assert db.query(AgentMemoryEntry).count() == 0


def test_retrieval_memory_accepts_only_evidence_reference_fields() -> None:
    db = _session()
    reference = {
        "source_type": "follow_up",
        "source_object_id": "701",
        "document_key": "evidence-701",
        "score": 0.91,
    }

    customer_memory_store_service.upsert_retrieval_index(
        db,
        tenant_id=2,
        customer_id=101,
        key="latest_evidence_refs",
        value=reference,
    )
    with pytest.raises(ValueError, match="CUSTOMER_MEMORY_REFERENCE_INVALID"):
        customer_memory_store_service.upsert_retrieval_index(
            db,
            tenant_id=2,
            customer_id=101,
            key="unsafe",
            value={**reference, "quote": "客户预算十万元"},
        )

    payload = customer_memory_store_service.build_context_payload(db, tenant_id=2, customer_id=101)
    assert set(payload) == {"retrieval"}
    assert payload["retrieval"][0]["value"] == reference
