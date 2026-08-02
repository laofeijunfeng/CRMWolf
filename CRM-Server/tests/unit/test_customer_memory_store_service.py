from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.agent import AgentMemoryEntry
from app.services.customer_memory_store_service import (
    CUSTOMER_MEMORY_RETRIEVAL,
    CUSTOMER_MEMORY_SUMMARIES,
    customer_memory_namespace,
    customer_memory_store_service,
    namespace_from_path,
    namespace_to_path,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[AgentMemoryEntry.__table__])
    Session = sessionmaker(bind=engine)
    return Session()


def test_customer_memory_namespace_round_trips_to_store_path():
    namespace = customer_memory_namespace(tenant_id=2, customer_id=101, section=CUSTOMER_MEMORY_SUMMARIES)

    path = namespace_to_path(namespace)

    assert path == "2/customer/101/summaries"
    assert namespace_from_path(path) == namespace


def test_store_upserts_memory_idempotently_and_increments_version():
    db = _session()

    customer_memory_store_service.upsert_summary(
        db,
        tenant_id=2,
        customer_id=101,
        key="latest_customer_intelligence_event",
        value={"summary": "客户进入 POC", "source": {"source_type": "follow_up"}},
    )
    customer_memory_store_service.upsert_summary(
        db,
        tenant_id=2,
        customer_id=101,
        key="latest_customer_intelligence_event",
        value={"summary": "客户准备签合同", "source": {"source_type": "follow_up"}},
    )
    db.commit()

    entry = db.query(AgentMemoryEntry).one()
    assert entry.version == 2
    assert entry.value_json["summary"] == "客户准备签合同"
    assert entry.namespace == "2/customer/101/summaries"


def test_store_get_search_delete_and_ttl_follow_langgraph_contract():
    db = _session()
    store = customer_memory_store_service.store(db)
    namespace = customer_memory_namespace(tenant_id=2, customer_id=101, section=CUSTOMER_MEMORY_RETRIEVAL)

    store.put(namespace, "latest_evidence_refs", {"kind": "retrieval", "title": "POC 跟进"}, ttl=10)
    store.put(("2", "customer", "102", CUSTOMER_MEMORY_RETRIEVAL), "other", {"kind": "retrieval"})
    db.commit()

    item = store.get(namespace, "latest_evidence_refs")
    results = store.search(("2", "customer", "101"), query="POC", limit=5)
    namespaces = store.list_namespaces(prefix=("2", "customer"), max_depth=4)
    customer_101_namespaces = store.list_namespaces(prefix=("2", "customer", "101"), suffix=(CUSTOMER_MEMORY_RETRIEVAL,))
    store.delete(namespace, "latest_evidence_refs")
    db.commit()

    assert item is not None
    assert item.value["title"] == "POC 跟进"
    assert len(results) == 1
    assert namespaces == [namespace, ("2", "customer", "102", CUSTOMER_MEMORY_RETRIEVAL)]
    assert customer_101_namespaces == [namespace]
    assert store.get(namespace, "latest_evidence_refs") is None


def test_store_ignores_expired_entries():
    db = _session()
    expired = AgentMemoryEntry(
        tenant_id=2,
        namespace="2/customer/101/summaries",
        key="old",
        value_json={"summary": "旧摘要"},
        version=1,
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(expired)
    db.commit()

    payload = customer_memory_store_service.build_context_payload(db, tenant_id=2, customer_id=101)

    assert payload["summaries"] == []
