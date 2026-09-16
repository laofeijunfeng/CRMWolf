"""Publish-time grounding: profile prose must appear in cited evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas.customer_profile import CustomerProfileSections
from app.services.customer_profile_projection_validator import (
    CustomerProfileProjectionValidationError,
)

PROFILE_CLAIM_UNGROUNDED = "PROFILE_CLAIM_UNGROUNDED"
TEMPLATE_PLOT_TERMS = (
    "安装包",
    "试用方案",
    "轻量交互页面",
    "账号已用满",
    "向上级CTO汇报",
    "立项材料已提交",
    "人员出差",
)


def assert_claims_grounded(
    sections: CustomerProfileSections | Mapping[str, Any],
    *,
    evidence_refs: object,
    product_catalog_names: object,
) -> None:
    """Reject demand prose that invents catalog products or template plot."""

    payload = sections.model_dump(mode="python") if isinstance(sections, CustomerProfileSections) else sections
    if not isinstance(payload, Mapping):
        return
    registry = _snippet_registry(evidence_refs)
    catalog = [str(name) for name in (product_catalog_names or []) if str(name).strip()]
    current = payload.get("current_situation")
    demand_items: list[Mapping[str, Any]] = []
    demand: object = None
    if isinstance(current, Mapping):
        demand = current.get("demand_background")
        if isinstance(demand, Mapping) and isinstance(demand.get("items"), list):
            demand_items = [item for item in demand["items"] if isinstance(item, Mapping)]
        _assert_text_grounded(
            current.get("summary"),
            evidence_refs=_collect_refs(demand_items),
            product_names=_collect_names(demand_items),
            registry=registry,
            catalog=catalog,
        )
    if isinstance(demand, Mapping):
        _assert_text_grounded(
            demand.get("summary"),
            evidence_refs=_collect_refs(demand_items),
            product_names=_collect_names(demand_items),
            registry=registry,
            catalog=catalog,
        )
        for item in demand_items:
            _assert_text_grounded(
                item.get("statement"),
                evidence_refs=item.get("evidence_refs"),
                product_names=item.get("product_names"),
                registry=registry,
                catalog=catalog,
            )
    process = payload.get("follow_up_process")
    if isinstance(process, list):
        for item in process:
            if not isinstance(item, Mapping):
                continue
            _assert_text_grounded(
                item.get("business_change"),
                evidence_refs=item.get("evidence_refs"),
                product_names=item.get("product_names"),
                registry=registry,
                catalog=catalog,
            )


def _fold(value: str) -> str:
    return value.casefold()


def _snippet_registry(evidence_refs: object) -> dict[str, str]:
    registry: dict[str, str] = {}
    if not isinstance(evidence_refs, list):
        return registry
    for item in evidence_refs:
        if not isinstance(item, Mapping):
            continue
        key = item.get("evidence_key") or item.get("evidence_id") or item.get("id")
        if not isinstance(key, str) or not key.strip():
            continue
        snippet = item.get("snippet")
        registry[key.strip()] = snippet if isinstance(snippet, str) else ""
    return registry


def _collect_refs(items: Sequence[Mapping[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in items:
        value = item.get("evidence_refs")
        if not isinstance(value, list):
            continue
        for ref in value:
            if isinstance(ref, str) and ref.strip():
                refs.append(ref.strip())
    return list(dict.fromkeys(refs))


def _collect_names(items: Sequence[Mapping[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in items:
        value = item.get("product_names")
        if not isinstance(value, list):
            continue
        for name in value:
            if isinstance(name, str) and name.strip():
                names.append(name)
    return names


def _assert_text_grounded(
    statement: object,
    *,
    evidence_refs: object,
    product_names: object,
    registry: dict[str, str],
    catalog: list[str],
) -> None:
    if not isinstance(statement, str) or not statement.strip():
        return
    quotes: list[str] = []
    if isinstance(evidence_refs, list):
        for ref in evidence_refs:
            if isinstance(ref, str) and ref.strip():
                quotes.append(registry.get(ref.strip(), ""))
    folded_statement = _fold(statement)
    allowed_names = product_names if isinstance(product_names, list) else []
    for name in catalog:
        if _fold(name) not in folded_statement:
            continue
        in_quotes = any(_fold(name) in _fold(snippet or "") for snippet in quotes)
        if in_quotes or name in allowed_names:
            continue
        raise CustomerProfileProjectionValidationError("档案陈述缺少出处", code=PROFILE_CLAIM_UNGROUNDED)
    for term in TEMPLATE_PLOT_TERMS:
        if _fold(term) not in folded_statement:
            continue
        if any(_fold(term) in _fold(snippet or "") for snippet in quotes):
            continue
        raise CustomerProfileProjectionValidationError("档案陈述缺少出处", code=PROFILE_CLAIM_UNGROUNDED)
