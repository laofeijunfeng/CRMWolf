"""MySQL-backed LangGraph Store for customer intelligence memory."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TypeAlias, cast

from langgraph.store.base import BaseStore, GetOp, Item, ListNamespacesOp, Op, PutOp, Result, SearchItem, SearchOp
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.agent import AgentMemoryEntry
from app.services.agent.types import coerce_json_dict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
CustomerMemorySection: TypeAlias = str

CUSTOMER_MEMORY_FACTS: CustomerMemorySection = "facts"
CUSTOMER_MEMORY_SUMMARIES: CustomerMemorySection = "summaries"
CUSTOMER_MEMORY_PREFERENCES: CustomerMemorySection = "preferences"
CUSTOMER_MEMORY_RETRIEVAL: CustomerMemorySection = "retrieval"

NAMESPACE_SEPARATOR = "/"


def customer_memory_namespace(*, tenant_id: int, customer_id: int, section: CustomerMemorySection) -> tuple[str, ...]:
    return (str(tenant_id), "customer", str(customer_id), section)


def namespace_to_path(namespace: tuple[str, ...]) -> str:
    _validate_namespace(namespace)
    return NAMESPACE_SEPARATOR.join(namespace)


def namespace_from_path(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.split(NAMESPACE_SEPARATOR) if part)


class MySQLAgentMemoryStore(BaseStore):
    """LangGraph Store contract backed by the current SQLAlchemy session."""

    supports_ttl = True

    def __init__(self, db: Session) -> None:
        self.db = db

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        results: list[Result] = []
        for op in ops:
            if isinstance(op, GetOp):
                results.append(self._get(op))
                continue
            if isinstance(op, PutOp):
                results.append(self._put(op))
                continue
            if isinstance(op, SearchOp):
                results.append(self._search(op))
                continue
            if isinstance(op, ListNamespacesOp):
                results.append(self._list_namespaces(op))
                continue
            raise NotImplementedError(f"Unsupported LangGraph Store op: {type(op).__name__}")
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return self.batch(ops)

    def _get(self, op: GetOp) -> Item | None:
        namespace = namespace_to_path(op.namespace)
        entry = (
            self.db.query(AgentMemoryEntry)
            .filter(
                AgentMemoryEntry.namespace == namespace,
                AgentMemoryEntry.key == op.key,
                _not_expired_filter(),
            )
            .one_or_none()
        )
        if entry is None:
            return None
        return _item_from_entry(entry)

    def _put(self, op: PutOp) -> None:
        namespace_path = namespace_to_path(op.namespace)
        if op.value is None:
            (
                self.db.query(AgentMemoryEntry)
                .filter(AgentMemoryEntry.namespace == namespace_path, AgentMemoryEntry.key == op.key)
                .delete(synchronize_session=False)
            )
            self.db.flush()
            return None

        value = _coerce_store_value(op.value)
        now = datetime.utcnow()
        entry = (
            self.db.query(AgentMemoryEntry)
            .filter(AgentMemoryEntry.namespace == namespace_path, AgentMemoryEntry.key == op.key)
            .one_or_none()
        )
        if entry is None:
            entry = AgentMemoryEntry(
                tenant_id=_tenant_id_from_namespace(op.namespace),
                namespace=namespace_path,
                key=op.key,
                value_json=value,
                version=1,
                expires_at=_expires_at(now, op.ttl),
            )
            self.db.add(entry)
        else:
            entry.value_json = value
            entry.version = int(entry.version or 0) + 1
            entry.expires_at = _expires_at(now, op.ttl)
        self.db.flush()
        return None

    def _search(self, op: SearchOp) -> list[SearchItem]:
        prefix = namespace_to_path(op.namespace_prefix)
        query = self.db.query(AgentMemoryEntry).filter(
            _namespace_prefix_filter(prefix),
            _not_expired_filter(),
        )
        if op.filter:
            query = query.filter(*_value_filters(cast(dict[str, object], op.filter)))
        entries = (
            query.order_by(AgentMemoryEntry.updated_time.desc(), AgentMemoryEntry.id.desc())
            .offset(max(op.offset, 0))
            .limit(max(op.limit, 0))
            .all()
        )
        if op.query:
            normalized_query = op.query.strip().lower()
            entries = [
                entry
                for entry in entries
                if normalized_query in _json_for_match(coerce_json_dict(entry.value_json)).lower()
            ]
        return [_search_item_from_entry(entry) for entry in entries]

    def _list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        query = self.db.query(AgentMemoryEntry.namespace).filter(_not_expired_filter()).distinct()
        namespaces = [namespace_from_path(row[0]) for row in query.order_by(AgentMemoryEntry.namespace.asc()).all()]
        if op.match_conditions:
            namespaces = [
                namespace
                for namespace in namespaces
                if all(_matches_namespace_condition(namespace, condition.match_type, tuple(condition.path)) for condition in op.match_conditions)
            ]
        filtered = [_apply_max_depth(namespace, op.max_depth) for namespace in namespaces]
        filtered = _dedupe_namespaces(filtered)
        return filtered[max(op.offset, 0): max(op.offset, 0) + max(op.limit, 0)]


class CustomerMemoryStoreService:
    """Customer-specific helpers over the LangGraph Store contract."""

    def store(self, db: Session) -> MySQLAgentMemoryStore:
        return MySQLAgentMemoryStore(db)

    def upsert_summary(
        self,
        db: Session,
        *,
        tenant_id: int,
        customer_id: int,
        key: str,
        value: JsonObject,
    ) -> None:
        self.store(db).put(
            customer_memory_namespace(tenant_id=tenant_id, customer_id=customer_id, section=CUSTOMER_MEMORY_SUMMARIES),
            key,
            value,
            index=False,
        )

    def upsert_preference(
        self,
        db: Session,
        *,
        tenant_id: int,
        customer_id: int,
        key: str,
        value: JsonObject,
    ) -> None:
        self.store(db).put(
            customer_memory_namespace(tenant_id=tenant_id, customer_id=customer_id, section=CUSTOMER_MEMORY_PREFERENCES),
            key,
            value,
            index=False,
        )

    def upsert_fact_index(
        self,
        db: Session,
        *,
        tenant_id: int,
        customer_id: int,
        key: str,
        value: JsonObject,
    ) -> None:
        self.store(db).put(
            customer_memory_namespace(tenant_id=tenant_id, customer_id=customer_id, section=CUSTOMER_MEMORY_FACTS),
            key,
            value,
            index=False,
        )

    def upsert_retrieval_index(
        self,
        db: Session,
        *,
        tenant_id: int,
        customer_id: int,
        key: str,
        value: JsonObject,
    ) -> None:
        self.store(db).put(
            customer_memory_namespace(tenant_id=tenant_id, customer_id=customer_id, section=CUSTOMER_MEMORY_RETRIEVAL),
            key,
            value,
            index=False,
        )

    def list_customer_memory(
        self,
        db: Session,
        *,
        tenant_id: int,
        customer_id: int,
        section: CustomerMemorySection | None = None,
        limit: int = 20,
    ) -> list[SearchItem]:
        namespace = (
            customer_memory_namespace(tenant_id=tenant_id, customer_id=customer_id, section=section)
            if section
            else (str(tenant_id), "customer", str(customer_id))
        )
        return self.store(db).search(namespace, limit=limit)

    def build_context_payload(self, db: Session, *, tenant_id: int, customer_id: int, limit: int = 20) -> JsonObject:
        items = self.list_customer_memory(db, tenant_id=tenant_id, customer_id=customer_id, limit=limit)
        grouped: dict[str, list[JsonObject]] = {
            CUSTOMER_MEMORY_FACTS: [],
            CUSTOMER_MEMORY_SUMMARIES: [],
            CUSTOMER_MEMORY_PREFERENCES: [],
            CUSTOMER_MEMORY_RETRIEVAL: [],
        }
        for item in items:
            section = item.namespace[-1] if item.namespace else ""
            if section in grouped:
                grouped[section].append({
                    "key": item.key,
                    "value": _json_value(item.value),
                    "updated_at": item.updated_at.isoformat(),
                })
        return {
            "namespace_prefix": list((str(tenant_id), "customer", str(customer_id))),
            "facts": grouped[CUSTOMER_MEMORY_FACTS],
            "summaries": grouped[CUSTOMER_MEMORY_SUMMARIES],
            "preferences": grouped[CUSTOMER_MEMORY_PREFERENCES],
            "retrieval": grouped[CUSTOMER_MEMORY_RETRIEVAL],
        }


def _validate_namespace(namespace: tuple[str, ...]) -> None:
    if not namespace or any(not part or NAMESPACE_SEPARATOR in part for part in namespace):
        raise ValueError("Invalid LangGraph Store namespace")


def _tenant_id_from_namespace(namespace: tuple[str, ...]) -> int:
    first = namespace[0] if namespace else "0"
    return int(first) if first.isdigit() else 0


def _coerce_store_value(value: object) -> JsonObject:
    return _json_object(coerce_json_dict(value))


def _json_object(value: dict[str, object]) -> JsonObject:
    result: JsonObject = {}
    for key, item in value.items():
        coerced = _json_value(item)
        if coerced is not None or item is None:
            result[str(key)] = coerced
    return result


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return _json_object(cast(dict[str, object], value))
    return str(value)


def _expires_at(now: datetime, ttl_minutes: float | None) -> datetime | None:
    if ttl_minutes is None:
        return None
    return now + timedelta(minutes=ttl_minutes)


def _not_expired_filter():
    return or_(AgentMemoryEntry.expires_at.is_(None), AgentMemoryEntry.expires_at > datetime.utcnow())


def _namespace_prefix_filter(prefix: str):
    return or_(AgentMemoryEntry.namespace == prefix, AgentMemoryEntry.namespace.like(f"{prefix}{NAMESPACE_SEPARATOR}%"))


def _value_filters(filters: dict[str, object]) -> list[object]:
    clauses: list[object] = []
    for key, value in filters.items():
        clauses.append(AgentMemoryEntry.value_json[key].as_string() == str(value))
    return clauses


def _item_from_entry(entry: AgentMemoryEntry) -> Item:
    return Item(
        namespace=namespace_from_path(str(entry.namespace)),
        key=str(entry.key),
        value=_json_object(coerce_json_dict(entry.value_json)),
        created_at=entry.created_time,
        updated_at=entry.updated_time,
    )


def _search_item_from_entry(entry: AgentMemoryEntry) -> SearchItem:
    return SearchItem(
        namespace=namespace_from_path(str(entry.namespace)),
        key=str(entry.key),
        value=_json_object(coerce_json_dict(entry.value_json)),
        created_at=entry.created_time,
        updated_at=entry.updated_time,
        score=None,
    )


def _json_for_match(value: JsonObject) -> str:
    return " ".join(str(item) for item in value.values())


def _apply_max_depth(namespace: tuple[str, ...], max_depth: int | None) -> tuple[str, ...]:
    if max_depth is None or max_depth <= 0:
        return namespace
    return namespace[:max_depth]


def _dedupe_namespaces(namespaces: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    result: list[tuple[str, ...]] = []
    for namespace in namespaces:
        if namespace not in seen:
            seen.add(namespace)
            result.append(namespace)
    return result


def _matches_namespace_condition(namespace: tuple[str, ...], match_type: str, path: tuple[str, ...]) -> bool:
    if match_type == "prefix":
        return _matches_path(namespace[:len(path)], path)
    if match_type == "suffix":
        return _matches_path(namespace[-len(path):], path) if path else True
    return True


def _matches_path(candidate: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    if len(candidate) != len(pattern):
        return False
    return all(pattern_part == "*" or candidate_part == pattern_part for candidate_part, pattern_part in zip(candidate, pattern, strict=True))


customer_memory_store_service = CustomerMemoryStoreService()
