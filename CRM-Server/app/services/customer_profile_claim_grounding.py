"""Publish-time grounding: profile prose must appear in cited evidence."""

from __future__ import annotations

import json
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
    inherited_payload: Mapping[str, Any] | None = None,
) -> None:
    """Reject demand prose that invents catalog products or template plot."""

    payload = sections.model_dump(mode="python") if isinstance(sections, CustomerProfileSections) else sections
    if not isinstance(payload, Mapping):
        return
    registry = _snippet_registry(evidence_refs)
    catalog = [str(name) for name in (product_catalog_names or []) if str(name).strip()]
    inherited = inherited_payload if isinstance(inherited_payload, Mapping) else {}
    inherit_enabled = inherited_payload is not None
    current = payload.get("current_situation")
    demand_items: list[Mapping[str, Any]] = []
    demand: object = None
    inherited_current = inherited.get("current_situation") if inherit_enabled else None
    if isinstance(current, Mapping):
        demand = current.get("demand_background")
        if isinstance(demand, Mapping) and isinstance(demand.get("items"), list):
            demand_items = [item for item in demand["items"] if isinstance(item, Mapping)]
        summary_refs = [*_direct_refs(current.get("evidence_refs")), *_collect_refs(demand_items)]
        if not _unchanged(current, inherited_current, enabled=inherit_enabled):
            _assert_text_grounded(
                current.get("summary"),
                evidence_refs=summary_refs,
                product_names=_collect_bound_names(demand_items),
                registry=registry,
                catalog=catalog,
            )
    inherited_demand = (
        inherited_current.get("demand_background") if isinstance(inherited_current, Mapping) else None
    )
    if isinstance(demand, Mapping) and not _unchanged(demand, inherited_demand, enabled=inherit_enabled):
        _assert_text_grounded(
            demand.get("summary"),
            evidence_refs=_collect_refs(demand_items),
            product_names=_collect_bound_names(demand_items),
            registry=registry,
            catalog=catalog,
        )
        for item in demand_items:
            _assert_text_grounded(
                item.get("statement"),
                evidence_refs=item.get("evidence_refs"),
                product_names=_bound_product_names(item),
                registry=registry,
                catalog=catalog,
            )
    process = payload.get("follow_up_process")
    inherited_process = inherited.get("follow_up_process") if inherit_enabled else None
    if isinstance(process, list) and not _unchanged(process, inherited_process, enabled=inherit_enabled):
        for item in process:
            if not isinstance(item, Mapping):
                continue
            _assert_text_grounded(
                item.get("business_change"),
                evidence_refs=item.get("evidence_refs"),
                product_names=_bound_product_names(item),
                registry=registry,
                catalog=catalog,
            )


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _unchanged(value: object, inherited_value: object, *, enabled: bool) -> bool:
    return enabled and _canonical(value) == _canonical(inherited_value)


def _direct_refs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(ref.strip() for ref in value if isinstance(ref, str) and ref.strip()))


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


def _bound_product_names(item: Mapping[str, Any]) -> list[str]:
    names = item.get("product_names")
    public_ids = item.get("product_public_ids")
    if not isinstance(names, list) or not isinstance(public_ids, list):
        return []
    if len(names) != len(public_ids):
        return []
    bound: list[str] = []
    for name, public_id in zip(names, public_ids, strict=True):
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(public_id, str) or not public_id.strip():
            continue
        bound.append(name)
    return bound


def _collect_bound_names(items: Sequence[Mapping[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in items:
        names.extend(_bound_product_names(item))
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
