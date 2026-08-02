"""Reusable customer alias recall for Agent and knowledge search."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_fact import CustomerFact, CustomerFactStatus
from app.services.customer_knowledge_candidate_service import CustomerVisibilityPredicate


@dataclass(frozen=True)
class CustomerAliasMatch:
    customer_id: int
    account_name: str
    city: str | None
    score: float
    reason: str
    matched_aliases: tuple[str, ...]


class CustomerAliasService:
    """Find customers by approved aliases and deterministic organization-name variants.

    Authoritative customer identity still comes from ``crm_customers``. Alias
    facts and generated variants are recall signals only; downstream resource
    resolution decides whether a candidate is confident enough to auto-select.
    """

    fact_type = "alias"
    generated_scan_limit = 500

    def expand_query_terms(self, query_text: str, *, limit: int = 8) -> list[str]:
        query = _clean_text(query_text)
        if not query:
            return []
        terms = [query, _normalize_text(query)]
        terms.extend(_split_terms(query))
        return _dedupe_non_empty(terms)[:limit]

    def recall(
        self,
        db: Session,
        *,
        team_id: int,
        query_text: str,
        limit: int = 8,
        visibility_predicate: CustomerVisibilityPredicate | None = None,
    ) -> list[CustomerAliasMatch]:
        query = _clean_text(query_text)
        if not query:
            return []
        by_customer: dict[int, CustomerAliasMatch] = {}
        for match in self._recall_from_alias_facts(
            db,
            team_id=team_id,
            query=query,
            limit=limit * 3,
            visibility_predicate=visibility_predicate,
        ):
            by_customer[match.customer_id] = match
        for match in self._recall_from_generated_aliases(
            db,
            team_id=team_id,
            query=query,
            limit=limit * 3,
            visibility_predicate=visibility_predicate,
        ):
            existing = by_customer.get(match.customer_id)
            if existing is None or match.score > existing.score:
                by_customer[match.customer_id] = match
        return sorted(by_customer.values(), key=lambda item: item.score, reverse=True)[:limit]

    def _recall_from_alias_facts(
        self,
        db: Session,
        *,
        team_id: int,
        query: str,
        limit: int,
        visibility_predicate: CustomerVisibilityPredicate | None,
    ) -> list[CustomerAliasMatch]:
        terms = self.expand_query_terms(query)
        if not terms:
            return []
        if not _has_table(db, CustomerFact.__tablename__) or not _has_table(db, Customer.__tablename__):
            return []
        like_conditions = []
        for term in terms:
            like = f"%{term}%"
            like_conditions.append(CustomerFact.subject.like(like))
            like_conditions.append(CustomerFact.content.like(like))
        rows = (
            db.query(CustomerFact, Customer)
            .join(Customer, Customer.id == CustomerFact.customer_id)
            .filter(
                CustomerFact.team_id == team_id,
                CustomerFact.fact_type == self.fact_type,
                CustomerFact.status == CustomerFactStatus.ACTIVE,
                Customer.team_id == team_id,
                or_(*like_conditions),
            )
            .order_by(CustomerFact.confidence.desc(), CustomerFact.updated_time.desc())
            .limit(limit)
            .all()
        )
        matches: list[CustomerAliasMatch] = []
        for fact, customer in rows:
            if visibility_predicate is not None and not visibility_predicate(customer):
                continue
            aliases = _dedupe_non_empty([fact.subject, fact.content])
            score = _alias_fact_score(query=query, aliases=aliases, confidence=float(fact.confidence or 0))
            if score <= 0:
                continue
            matches.append(CustomerAliasMatch(
                customer_id=int(customer.id),
                account_name=str(customer.account_name),
                city=str(customer.city) if customer.city else None,
                score=score,
                reason="客户智能档案中的常用称呼匹配",
                matched_aliases=tuple(aliases[:3]),
            ))
        return matches

    def _recall_from_generated_aliases(
        self,
        db: Session,
        *,
        team_id: int,
        query: str,
        limit: int,
        visibility_predicate: CustomerVisibilityPredicate | None,
    ) -> list[CustomerAliasMatch]:
        if not _has_table(db, Customer.__tablename__):
            return []
        customers = (
            db.query(Customer)
            .filter(Customer.team_id == team_id)
            .order_by(Customer.last_modified_time.desc(), Customer.id.desc())
            .limit(self.generated_scan_limit)
            .all()
        )
        matches: list[CustomerAliasMatch] = []
        normalized_query = _normalize_text(query)
        for customer in customers:
            if visibility_predicate is not None and not visibility_predicate(customer):
                continue
            aliases = generated_aliases_for_customer_name(str(customer.account_name or ""))
            matched = _matched_aliases(normalized_query, aliases)
            if not matched:
                continue
            score = 0.86 if any(_normalize_text(alias) == normalized_query for alias in matched) else 0.78
            matches.append(CustomerAliasMatch(
                customer_id=int(customer.id),
                account_name=str(customer.account_name),
                city=str(customer.city) if customer.city else None,
                score=score,
                reason="客户名称的常用简称匹配",
                matched_aliases=tuple(matched[:3]),
            ))
            if len(matches) >= limit:
                break
        return sorted(matches, key=lambda item: item.score, reverse=True)


def generated_aliases_for_customer_name(account_name: str) -> list[str]:
    name = _clean_text(account_name)
    if not name:
        return []
    normalized = _normalize_text(name)
    aliases = [name, normalized]
    stripped = _strip_organization_suffix(name)
    if stripped and stripped != name:
        aliases.append(stripped)
    aliases.extend(_institution_abbreviations(name))
    aliases.extend(_segment_abbreviations(stripped or name))
    return [alias for alias in _dedupe_non_empty(aliases) if 2 <= len(_normalize_text(alias)) <= 30]


def _institution_abbreviations(name: str) -> list[str]:
    aliases: list[str] = []
    compact = _normalize_text(name)
    for full_name, short_name in _INSTITUTION_ROOT_ALIASES:
        if full_name not in compact:
            continue
        remainder = compact.split(full_name, 1)[1]
        remainder_alias = _segment_abbreviation(remainder)
        aliases.append(f"{short_name}{remainder_alias}" if remainder_alias else short_name)
    return aliases


def _segment_abbreviations(name: str) -> list[str]:
    compact = _normalize_text(name)
    if len(compact) < 4:
        return []
    parts = _split_by_org_words(compact)
    aliases = [_segment_abbreviation(compact)]
    if len(parts) > 1:
        aliases.append("".join(_segment_abbreviation(part) for part in parts))
    return aliases


def _segment_abbreviation(value: str) -> str:
    marker = _suffix_marker(value)
    compact = _normalize_text(_strip_functional_suffix(_strip_organization_suffix(value)))
    if not compact:
        return ""
    pieces = _split_by_org_words(compact)
    if len(pieces) > 1:
        return "".join(piece[0] for piece in pieces if piece) + marker
    word_alias = _org_word_abbreviation(compact)
    if word_alias:
        return f"{word_alias}{marker}"
    if len(compact) <= 4:
        return f"{compact}{marker}"
    return "".join(compact[index] for index in range(0, len(compact), 2))[:6]


def _suffix_marker(value: str) -> str:
    compact = _normalize_text(value)
    for suffix, marker in _ORG_SUFFIX_MARKERS:
        if compact.endswith(suffix):
            return marker
    return ""


def _strip_organization_suffix(value: str) -> str:
    compact = _clean_text(value)
    changed = True
    while changed:
        changed = False
        for suffix in _ORG_SUFFIXES:
            if compact.endswith(suffix) and len(compact) > len(suffix) + 1:
                compact = compact[: -len(suffix)]
                changed = True
                break
    return compact


def _strip_functional_suffix(value: str) -> str:
    compact = _normalize_text(value)
    for suffix, _marker in _ORG_SUFFIX_MARKERS:
        if compact.endswith(suffix) and len(compact) > len(suffix) + 1:
            return compact[: -len(suffix)]
    return compact


def _org_word_abbreviation(value: str) -> str:
    compact = _normalize_text(value)
    initials: list[str] = []
    cursor = 0
    while cursor < len(compact):
        matched = ""
        for word in _ORG_WORDS:
            if compact.startswith(word, cursor):
                matched = word
                break
        if matched:
            initials.append(matched[0])
            cursor += len(matched)
        else:
            cursor += 1
    return "".join(initials)


def _split_by_org_words(value: str) -> list[str]:
    compact = _normalize_text(value)
    if not compact:
        return []
    pattern = "|".join(re.escape(word) for word in _ORG_WORDS)
    parts = [part for part in re.split(pattern, compact) if part]
    return parts or [compact]


def _split_terms(value: str) -> list[str]:
    return [part for part in re.split(r"[\s,，、/／()（）]+", value.strip()) if part]


def _matched_aliases(normalized_query: str, aliases: Iterable[str]) -> list[str]:
    matched: list[str] = []
    for alias in aliases:
        normalized_alias = _normalize_text(alias)
        if not normalized_alias:
            continue
        if normalized_query == normalized_alias or normalized_query in normalized_alias or normalized_alias in normalized_query:
            matched.append(alias)
    return _dedupe_non_empty(matched)


def _alias_fact_score(*, query: str, aliases: list[str], confidence: float) -> float:
    normalized_query = _normalize_text(query)
    matched = _matched_aliases(normalized_query, aliases)
    if not matched:
        return 0.0
    exact = any(_normalize_text(alias) == normalized_query for alias in matched)
    base = 0.98 if exact else 0.9
    return min(base, max(0.0, min(1.0, confidence)) + 0.12)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_text(value: object) -> str:
    return re.sub(r"[\s·,，、.。/／()（）【】\\-]+", "", str(value or "").strip().lower())


def _dedupe_non_empty(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        key = _normalize_text(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _has_table(db: Session, table_name: str) -> bool:
    bind = db.get_bind()
    return bool(bind is not None and inspect(bind).has_table(table_name))


_INSTITUTION_ROOT_ALIASES: tuple[tuple[str, str], ...] = (
    ("中国科学院", "中科院"),
    ("中国工程院", "工程院"),
    ("中国社会科学院", "社科院"),
)

_ORG_SUFFIX_MARKERS: tuple[tuple[str, str], ...] = (
    ("研究所", "所"),
    ("研究院", "院"),
    ("学院", "院"),
    ("大学", "大学"),
    ("医院", "医院"),
)

_ORG_SUFFIXES: tuple[str, ...] = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "有限公司",
    "股份公司",
    "集团",
    "公司",
)

_ORG_WORDS: tuple[str, ...] = (
    "信息",
    "工程",
    "技术",
    "科技",
    "软件",
    "数据",
    "网络",
    "智能",
    "安全",
    "研究",
)


customer_alias_service = CustomerAliasService()
