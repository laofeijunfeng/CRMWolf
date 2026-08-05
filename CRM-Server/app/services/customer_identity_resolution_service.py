"""Customer identity resolution for CRM Agent customer search."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import inspect, or_
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_fact import CustomerFact, CustomerFactStatus
from app.models.customer_identity_term import (
    CustomerIdentityTerm,
    CustomerIdentityTermSource,
    CustomerIdentityTermStatus,
)
from app.services.customer_knowledge_candidate_service import CustomerVisibilityPredicate


IDENTITY_AUTO_SELECT_SCORE = 0.86
IDENTITY_AMBIGUITY_GAP = 0.08
IDENTITY_GENERATED_SCAN_LIMIT = 1000
SEMANTIC_IDENTITY_PROMOTION_SCORE = IDENTITY_AUTO_SELECT_SCORE


@dataclass(frozen=True)
class CustomerIdentityResolution:
    items: list[dict]
    related_customers: list[dict]
    metadata: dict


@dataclass(frozen=True)
class _IdentitySignal:
    customer_id: int
    customer_public_id: str
    account_name: str
    city: str | None
    score: float
    source: str
    reason: str
    matched_terms: tuple[str, ...]
    evidence: tuple[dict, ...]


class CustomerIdentityResolutionService:
    """Resolve customer identity from search, terms, facts, structure, and semantic evidence."""

    def rebuild_customer_identity_terms(self, db: Session, *, team_id: int, customer_id: int) -> int:
        if not _has_table(db, CustomerIdentityTerm.__tablename__):
            return 0
        customer = (
            db.query(Customer)
            .filter(Customer.team_id == team_id, Customer.id == customer_id)
            .first()
        )
        if customer is None:
            return 0
        return self._replace_deterministic_terms(db, customer)

    def rebuild_team_identity_terms(
        self,
        db: Session,
        *,
        team_id: int | None = None,
        customer_ids: Iterable[int] | None = None,
        limit: int = 100,
    ) -> tuple[int, ...]:
        if not _has_table(db, CustomerIdentityTerm.__tablename__):
            return ()
        query = db.query(Customer)
        if team_id is not None:
            query = query.filter(Customer.team_id == team_id)
        if customer_ids is not None:
            ids = _positive_ints(customer_ids)
            if not ids:
                return ()
            query = query.filter(Customer.id.in_(ids))
        customers = (
            query
            .order_by(Customer.last_modified_time.desc(), Customer.id.desc())
            .limit(limit)
            .all()
        )
        rebuilt: list[int] = []
        for customer in customers:
            if self._replace_deterministic_terms(db, customer) > 0:
                rebuilt.append(int(customer.id))
        return tuple(rebuilt)

    def resolve(
        self,
        db: Session,
        *,
        team_id: int,
        query_text: str,
        lexical_items: list[dict],
        semantic_items: list[dict],
        limit: int = 10,
        visibility_predicate: CustomerVisibilityPredicate | None = None,
    ) -> CustomerIdentityResolution:
        query = _clean_text(query_text)
        metadata = {
            "identity_status": "completed" if query else "skipped",
            "identity_strategy": "lexical+identity_terms+alias_facts+generated_match_terms+semantic_support",
            "identity_decision": "no_match",
            "identity_candidate_count": 0,
            "identity_related_count": 0,
        }
        if not query:
            return CustomerIdentityResolution(lexical_items[:limit], [], metadata)

        lexical_signals = self._signals_from_lexical_items(query=query, lexical_items=lexical_items)
        term_signals = self._signals_from_identity_terms(
            db,
            team_id=team_id,
            query=query,
            limit=limit * 4,
            visibility_predicate=visibility_predicate,
        )
        alias_signals = self._signals_from_alias_facts(
            db,
            team_id=team_id,
            query=query,
            limit=limit * 4,
            visibility_predicate=visibility_predicate,
        )
        generated_signals: list[_IdentitySignal] = []
        if not term_signals and not alias_signals:
            generated_signals = self._signals_from_generated_terms(
                db,
                team_id=team_id,
                query=query,
                limit=limit * 4,
                visibility_predicate=visibility_predicate,
            )
        signals: list[_IdentitySignal] = [
            *lexical_signals,
            *term_signals,
            *alias_signals,
            *generated_signals,
        ]
        source_counts: dict[str, int] = {}
        for signal in signals:
            source_counts[signal.source] = source_counts.get(signal.source, 0) + 1

        identity_items = self._merge_identity_signals(signals)
        semantic_related = self._merge_semantic_support(
            identity_items=identity_items,
            semantic_items=semantic_items,
            limit=limit,
        )
        if (
            not identity_items
            and semantic_related
            and _candidate_score(semantic_related[0]) >= SEMANTIC_IDENTITY_PROMOTION_SCORE
        ):
            promoted = dict(semantic_related.pop(0))
            match = dict(promoted.get("match") or {})
            match.setdefault("source", "customer_knowledge")
            match.setdefault("reason", "客户知识库语义匹配")
            promoted["match"] = match
            identity_items.append(promoted)
        identity_items.sort(key=lambda item: _candidate_score(item), reverse=True)
        items = identity_items[:limit]

        metadata["identity_candidate_count"] = len(items)
        metadata["identity_related_count"] = len(semantic_related)
        metadata["identity_source_counts"] = source_counts
        metadata["alias_candidate_count"] = (
            source_counts.get("customer_alias_fact", 0) + source_counts.get("generated_match_term", 0)
        )
        if len(items) == 1 and _candidate_score(items[0]) >= IDENTITY_AUTO_SELECT_SCORE:
            metadata["identity_decision"] = "auto_select"
        elif len(items) > 1:
            top_score = _candidate_score(items[0])
            second_score = _candidate_score(items[1])
            if top_score >= IDENTITY_AUTO_SELECT_SCORE and top_score - second_score >= IDENTITY_AMBIGUITY_GAP:
                metadata["identity_decision"] = "ranked_auto_selectable"
            else:
                metadata["identity_decision"] = "requires_confirmation"
                metadata["identity_conflict_count"] = len([
                    item for item in items
                    if top_score - _candidate_score(item) < IDENTITY_AMBIGUITY_GAP
                ])
        elif semantic_related:
            metadata["identity_decision"] = "semantic_related_only"
        return CustomerIdentityResolution(items, semantic_related, metadata)

    def _signals_from_lexical_items(self, *, query: str, lexical_items: list[dict]) -> list[_IdentitySignal]:
        signals: list[_IdentitySignal] = []
        for item in lexical_items:
            customer_id = item.get("id")
            account_name = str(item.get("account_name") or item.get("name") or "")
            if not isinstance(customer_id, (str, int)) or not str(customer_id) or not account_name:
                continue
            score, reason = _score_identity_text(query=query, term=account_name, term_type="full_name")
            if score <= 0:
                score = 0.74
                reason = "客户列表关键词召回"
            signals.append(_IdentitySignal(
                customer_id=_stable_customer_key(customer_id),
                customer_public_id=str(customer_id),
                account_name=account_name,
                city=str(item.get("city")) if item.get("city") else None,
                score=max(score, _candidate_score(item)),
                source="customer_search",
                reason=reason,
                matched_terms=(account_name,),
                evidence=({"title": "客户名称", "snippet": account_name, "score": score},),
            ))
        return signals

    def _replace_deterministic_terms(self, db: Session, customer: Customer) -> int:
        db.query(CustomerIdentityTerm).filter(
            CustomerIdentityTerm.team_id == customer.team_id,
            CustomerIdentityTerm.customer_id == customer.id,
            CustomerIdentityTerm.source == CustomerIdentityTermSource.DETERMINISTIC,
        ).delete(synchronize_session=False)
        created = 0
        for term, term_type in generated_identity_terms_for_customer_name(str(customer.account_name or "")):
            normalized = _normalize_text(term)
            if not normalized:
                continue
            db.add(CustomerIdentityTerm(
                tenant_id=int(customer.team_id),
                team_id=int(customer.team_id),
                customer_id=int(customer.id),
                term=term,
                normalized_term=normalized,
                term_type=term_type,
                source=CustomerIdentityTermSource.DETERMINISTIC,
                confidence=_term_confidence(term_type),
                status=CustomerIdentityTermStatus.ACTIVE,
                evidence=f"由客户名称「{customer.account_name}」生成",
            ))
            created += 1
        return created

    def _signals_from_identity_terms(
        self,
        db: Session,
        *,
        team_id: int,
        query: str,
        limit: int,
        visibility_predicate: CustomerVisibilityPredicate | None,
    ) -> list[_IdentitySignal]:
        if not _has_table(db, CustomerIdentityTerm.__tablename__):
            return []
        terms = _query_terms(query)
        if not terms:
            return []
        conditions = []
        for term in terms:
            like = f"%{term}%"
            conditions.append(CustomerIdentityTerm.normalized_term.like(like))
            conditions.append(CustomerIdentityTerm.term.like(like))
        rows = (
            db.query(CustomerIdentityTerm, Customer)
            .join(Customer, Customer.id == CustomerIdentityTerm.customer_id)
            .filter(
                CustomerIdentityTerm.team_id == team_id,
                CustomerIdentityTerm.status == CustomerIdentityTermStatus.ACTIVE,
                Customer.team_id == team_id,
                or_(*conditions),
            )
            .order_by(CustomerIdentityTerm.confidence.desc(), CustomerIdentityTerm.updated_time.desc())
            .limit(limit)
            .all()
        )
        signals: list[_IdentitySignal] = []
        for term, customer in rows:
            if visibility_predicate is not None and not visibility_predicate(customer):
                continue
            score, reason = _score_identity_text(
                query=query,
                term=str(term.term or ""),
                term_type=str(term.term_type or ""),
                confidence=float(term.confidence or 0.0),
            )
            if score <= 0:
                continue
            signals.append(_customer_signal(
                customer,
                score=score,
                source="customer_identity_term",
                reason=reason,
                terms=[term.term],
            ))
        return signals

    def _signals_from_alias_facts(
        self,
        db: Session,
        *,
        team_id: int,
        query: str,
        limit: int,
        visibility_predicate: CustomerVisibilityPredicate | None,
    ) -> list[_IdentitySignal]:
        if not _has_table(db, CustomerFact.__tablename__) or not _has_table(db, Customer.__tablename__):
            return []
        conditions = []
        for term in _query_terms(query):
            like = f"%{term}%"
            conditions.append(CustomerFact.subject.like(like))
            conditions.append(CustomerFact.content.like(like))
        if not conditions:
            return []
        rows = (
            db.query(CustomerFact, Customer)
            .join(Customer, Customer.id == CustomerFact.customer_id)
            .filter(
                CustomerFact.team_id == team_id,
                CustomerFact.fact_type == "alias",
                CustomerFact.status == CustomerFactStatus.ACTIVE,
                Customer.team_id == team_id,
                or_(*conditions),
            )
            .order_by(CustomerFact.confidence.desc(), CustomerFact.updated_time.desc())
            .limit(limit)
            .all()
        )
        signals: list[_IdentitySignal] = []
        for fact, customer in rows:
            if visibility_predicate is not None and not visibility_predicate(customer):
                continue
            terms = _dedupe_non_empty([fact.subject, fact.content])
            scores = [
                _score_identity_text(
                    query=query,
                    term=term,
                    term_type="alias",
                    confidence=float(fact.confidence or 0.0),
                )
                for term in terms
            ]
            usable = [(score, reason) for score, reason in scores if score > 0]
            if not usable:
                continue
            score, reason = max(usable, key=lambda item: item[0])
            signals.append(_customer_signal(customer, score=score, source="customer_alias_fact", reason=reason, terms=terms))
        return signals

    def _signals_from_generated_terms(
        self,
        db: Session,
        *,
        team_id: int,
        query: str,
        limit: int,
        visibility_predicate: CustomerVisibilityPredicate | None,
    ) -> list[_IdentitySignal]:
        if not _has_table(db, Customer.__tablename__):
            return []
        customers = (
            db.query(Customer)
            .filter(Customer.team_id == team_id)
            .order_by(Customer.last_modified_time.desc(), Customer.id.desc())
            .limit(IDENTITY_GENERATED_SCAN_LIMIT)
            .all()
        )
        signals: list[_IdentitySignal] = []
        for customer in customers:
            if visibility_predicate is not None and not visibility_predicate(customer):
                continue
            scored_terms = []
            for term, term_type in generated_identity_terms_for_customer_name(str(customer.account_name or "")):
                score, reason = _score_identity_text(query=query, term=term, term_type=term_type)
                if score > 0:
                    scored_terms.append((score, reason, term))
            if not scored_terms:
                continue
            score, reason, term = max(scored_terms, key=lambda item: item[0])
            signals.append(_customer_signal(
                customer,
                score=score,
                source="generated_match_term",
                reason=reason,
                terms=[term],
            ))
            if len(signals) >= limit:
                break
        return signals

    def _merge_identity_signals(self, signals: Iterable[_IdentitySignal]) -> list[dict]:
        by_customer: dict[str, dict] = {}
        for signal in signals:
            key = signal.customer_public_id or str(signal.customer_id)
            existing = by_customer.get(key)
            match = {
                "source": signal.source,
                "score": round(signal.score, 4),
                "reason": signal.reason,
                "matched_terms": list(signal.matched_terms),
                "evidence": list(signal.evidence),
            }
            item = {
                "id": key,
                "account_name": signal.account_name,
                "city": signal.city,
                "match": match,
            }
            if existing is None:
                by_customer[key] = item
                continue
            existing_match = dict(existing.get("match") or {})
            best_score = max(_candidate_score(existing), signal.score)
            sources = _dedupe_non_empty([
                existing_match.get("source"),
                signal.source,
            ])
            terms = _dedupe_non_empty([
                *(existing_match.get("matched_terms") or []),
                *signal.matched_terms,
            ])
            evidence = [
                item for item in [
                    *(existing_match.get("evidence") or []),
                    *signal.evidence,
                ]
                if isinstance(item, dict)
            ]
            existing["match"] = {
                "source": "hybrid_identity" if len(sources) > 1 else sources[0],
                "sources": sources,
                "score": round(min(1.0, best_score + 0.03 if len(sources) > 1 else best_score), 4),
                "reason": "客户身份解析多信号匹配" if len(sources) > 1 else signal.reason,
                "matched_terms": terms[:6],
                "evidence": evidence[:5],
            }
        return list(by_customer.values())

    def _merge_semantic_support(
        self,
        *,
        identity_items: list[dict],
        semantic_items: list[dict],
        limit: int,
    ) -> list[dict]:
        by_id = {str(item.get("id")): item for item in identity_items if item.get("id") is not None}
        related: list[dict] = []
        for semantic in semantic_items:
            customer_id = semantic.get("id")
            if not isinstance(customer_id, (str, int)) or not str(customer_id):
                continue
            key = str(customer_id)
            if key in by_id:
                existing = by_id[key]
                existing_match = dict(existing.get("match") or {})
                semantic_match = dict(semantic.get("match") or {})
                existing_source = existing_match.get("source")
                evidence = [
                    item for item in [
                        *(existing_match.get("evidence") or []),
                        *(semantic_match.get("evidence") or []),
                    ]
                    if isinstance(item, dict)
                ]
                existing_match["source"] = "hybrid_identity"
                existing_match["sources"] = _dedupe_non_empty([
                    *(existing_match.get("sources") or [existing_source]),
                    semantic_match.get("source") or "customer_knowledge",
                ])
                existing_match["score"] = round(max(_candidate_score(existing), _candidate_score(semantic)), 4)
                existing_match["reason"] = "客户身份解析和客户知识库均匹配"
                existing_match["evidence"] = evidence[:5]
                existing["match"] = existing_match
            else:
                related.append(semantic)
        return sorted(related, key=_candidate_score, reverse=True)[:limit]


def generated_identity_terms_for_customer_name(account_name: str) -> list[tuple[str, str]]:
    name = _clean_text(account_name)
    if not name:
        return []
    terms: list[tuple[str, str]] = [
        (name, "full_name"),
        (_normalize_text(name), "normalized_name"),
    ]
    stripped = _strip_legal_suffix(name)
    if stripped and stripped != name:
        terms.append((stripped, "normalized_name"))
    no_parenthetical = _remove_parenthetical(stripped or name)
    if no_parenthetical and no_parenthetical != stripped:
        terms.append((no_parenthetical, "generated_short_name"))
    for term in _parenthetical_short_terms(stripped or name):
        terms.append((term, "generated_short_name"))
    for term in _organization_short_terms(stripped or name):
        terms.append((term, "generated_short_name"))
    return [
        (term, term_type)
        for term, term_type in _dedupe_term_pairs(terms)
        if 2 <= len(_normalize_text(term)) <= 40
    ]


def _parenthetical_short_terms(name: str) -> list[str]:
    match = re.search(r"^(?P<prefix>[^()（）]+)[(（][^()（）]+[)）](?P<suffix>.+)$", name)
    if not match:
        return []
    prefix = _normalize_text(match.group("prefix"))
    suffix = _normalize_text(_strip_legal_suffix(match.group("suffix")))
    if len(prefix) < 2 or not suffix:
        return []
    terms = [f"{prefix}{suffix}"]
    tail = suffix[-2:] if len(suffix) >= 2 else suffix
    if tail and tail != suffix:
        terms.append(f"{prefix}{tail}")
    return terms


def _organization_short_terms(name: str) -> list[str]:
    normalized = _normalize_text(name)
    if not normalized:
        return []
    terms: list[str] = []
    prefix, body = _split_known_institution_prefix(normalized)
    if prefix:
        terms.append(prefix)
    body_short = _abbreviate_organization_body(body or normalized)
    if body_short:
        terms.append(body_short)
    if prefix and body_short:
        terms.append(f"{prefix}{body_short}")
    return terms


def _split_known_institution_prefix(normalized_name: str) -> tuple[str, str]:
    for prefix, short in _INSTITUTION_PREFIX_ABBREVIATIONS:
        if normalized_name.startswith(prefix) and len(normalized_name) > len(prefix):
            return short, normalized_name[len(prefix):]
    return "", normalized_name


def _abbreviate_organization_body(value: str) -> str:
    text, suffix_short = _strip_organization_suffix(value)
    if len(text) < 4:
        return ""
    segments = [segment for segment in re.split(r"(信息|工程|技术|网络|软件|系统|集成|研究|设计|开发|数据|智能)", text) if segment]
    if len(segments) >= 2:
        short = "".join(segment[0] for segment in segments if segment) + suffix_short
        if 2 <= len(short) <= 6:
            return short
    return ""


def _strip_organization_suffix(value: str) -> tuple[str, str]:
    compact = _clean_text(value)
    for suffix, suffix_short in _ORGANIZATION_SUFFIXES:
        if compact.endswith(suffix) and len(compact) > len(suffix) + 1:
            return compact[: -len(suffix)], suffix_short
    return compact, ""


def _score_identity_text(*, query: str, term: str, term_type: str, confidence: float = 0.86) -> tuple[float, str]:
    normalized_query = _normalize_text(query)
    normalized_term = _normalize_text(term)
    if len(normalized_query) < 2 or len(normalized_term) < 2:
        return 0.0, ""
    bounded_confidence = max(0.0, min(1.0, confidence))
    if normalized_query == normalized_term:
        base = 0.98 if term_type in {"alias", "full_name", "normalized_name"} else 0.94
        return min(1.0, max(base, bounded_confidence + 0.08)), "客户身份匹配词精确匹配"
    if len(normalized_query) == 2 and normalized_term.startswith(normalized_query):
        return max(0.9, min(0.94, bounded_confidence + 0.04)), "客户核心简称前缀匹配"
    if normalized_query in normalized_term and len(normalized_query) >= 3:
        return max(0.88, min(0.94, bounded_confidence + 0.04)), "客户名称包含匹配"
    if normalized_term in normalized_query and len(normalized_term) >= 3:
        return max(0.86, min(0.93, bounded_confidence + 0.02)), "客户输入包含已知称呼"
    subsequence_score = _ordered_overlap_score(normalized_query, normalized_term)
    if subsequence_score >= 0.96 and _has_specific_overlap(normalized_query, normalized_term):
        return 0.89, "客户名称结构匹配"
    if subsequence_score >= 0.84 and len(normalized_query) >= 4 and _has_specific_overlap(normalized_query, normalized_term):
        return 0.82, "客户名称结构弱匹配"
    return 0.0, ""


def _ordered_overlap_score(query: str, term: str) -> float:
    if not query or not term:
        return 0.0
    cursor = 0
    matched = 0
    for char in query:
        found = term.find(char, cursor)
        if found < 0:
            continue
        matched += 1
        cursor = found + 1
    coverage = matched / len(query)
    density = matched / max(len(term), len(query))
    return coverage * 0.8 + density * 0.2


def _has_specific_overlap(query: str, term: str) -> bool:
    if len(set(query) & set(term)) < 2:
        return False
    if query[:2] in term:
        return True
    return any(query[index:index + 2] in term for index in range(max(0, len(query) - 2)))


def _customer_signal(
    customer: Customer,
    *,
    score: float,
    source: str,
    reason: str,
    terms: Iterable[object],
) -> _IdentitySignal:
    matched_terms = tuple(_dedupe_non_empty(terms)[:6])
    evidence = tuple(
        {"title": "身份匹配词", "snippet": term, "score": round(score, 4)}
        for term in matched_terms[:3]
    )
    return _IdentitySignal(
        customer_id=int(customer.id),
        customer_public_id=str(customer.public_id),
        account_name=str(customer.account_name),
        city=str(customer.city) if customer.city else None,
        score=score,
        source=source,
        reason=reason,
        matched_terms=matched_terms,
        evidence=evidence,
    )


def _query_terms(value: str) -> list[str]:
    normalized = _normalize_text(value)
    return _dedupe_non_empty([value, normalized, *re.split(r"[\s,，、/／()（）]+", value.strip())])


def _strip_legal_suffix(value: str) -> str:
    compact = _clean_text(value)
    changed = True
    while changed:
        changed = False
        for suffix in _LEGAL_SUFFIXES:
            if compact.endswith(suffix) and len(compact) > len(suffix) + 1:
                compact = compact[: -len(suffix)]
                changed = True
                break
    return compact


def _remove_parenthetical(value: str) -> str:
    return re.sub(r"[(（][^()（）]+[)）]", "", value)


def _candidate_score(item: dict) -> float:
    match = item.get("match")
    if isinstance(match, dict) and isinstance(match.get("score"), (int, float)):
        return max(0.0, min(1.0, float(match["score"])))
    return 0.0


def _term_confidence(term_type: str) -> float:
    if term_type == "full_name":
        return 0.99
    if term_type == "normalized_name":
        return 0.94
    if term_type == "generated_short_name":
        return 0.88
    return 0.82


def _stable_customer_key(value: object) -> int:
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    return abs(hash(text)) % 10_000_000_000


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


def _dedupe_term_pairs(values: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term, term_type in values:
        key = _normalize_text(term)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append((_clean_text(term), term_type))
    return result


def _positive_ints(values: Iterable[object]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


def _has_table(db: Session, table_name: str) -> bool:
    bind = db.get_bind()
    return bool(bind is not None and inspect(bind).has_table(table_name))


_LEGAL_SUFFIXES: tuple[str, ...] = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "有限公司",
    "股份公司",
    "集团",
    "公司",
)

_ORGANIZATION_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("研究所", "所"),
    ("研究院", "院"),
    ("科学院", "院"),
    ("工程院", "院"),
    ("实验室", "室"),
    ("中心", "中心"),
    ("大学", "大学"),
    ("学院", "学院"),
)

_INSTITUTION_PREFIX_ABBREVIATIONS: tuple[tuple[str, str], ...] = (
    ("中国科学院大学", "国科大"),
    ("中国科学院", "中科院"),
    ("中国工程院", "工程院"),
    ("中国医学科学院", "医科院"),
    ("中国社会科学院", "社科院"),
    ("中国农业科学院", "农科院"),
)


customer_identity_resolution_service = CustomerIdentityResolutionService()
