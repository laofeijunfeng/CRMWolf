from __future__ import annotations

import pytest

from app.services.agent.query import CRMFilter, CRMQueryAuthority, CRMQueryAuthorityError, EntityRef


def _customer_ref(public_id: str, ref_id: str | None = None) -> EntityRef:
    return EntityRef(
        ref_id=ref_id or f"eref_{public_id}",
        resource="customer",
        public_id=public_id,
        display_name=f"客户 {public_id}",
    )


def _query_payload(*filters: dict[str, object]) -> dict[str, object]:
    return {
        "resource": "customer_activity",
        "projection": ["id", "customer_id", "summary"],
        "filters": list(filters),
        "sorts": [],
        "metrics": [],
        "group_by": [],
        "scope": "accessible",
        "page_size": 20,
        "cursor": None,
    }


def test_authority_allows_one_customer_selected_from_multi_customer_scope() -> None:
    authority = CRMQueryAuthority(
        entity_refs=(_customer_ref("cus_a"), _customer_ref("cus_b")),
    )

    constrained = authority.constrain_query(
        "customer_activity",
        _query_payload({"field": "customer_id", "operator": "eq", "value": "cus_b"}),
    )

    assert constrained["filters"] == [
        {"field": "customer_id", "operator": "eq", "value": "cus_b"},
    ]


def test_authority_rejects_fabricated_customer_in_multi_customer_scope() -> None:
    authority = CRMQueryAuthority(
        entity_refs=(_customer_ref("cus_a"), _customer_ref("cus_b")),
    )

    with pytest.raises(CRMQueryAuthorityError, match="server-authoritative customer scope"):
        authority.constrain_query(
            "customer_activity",
            _query_payload({"field": "customer_id", "operator": "eq", "value": "cus_fabricated"}),
        )


def test_authority_forces_customer_lookup_to_single_canonical_customer() -> None:
    authority = CRMQueryAuthority(entity_refs=(_customer_ref("cus_a"),))

    constrained = authority.constrain_query(
        "customer",
        {
            "resource": "customer",
            "projection": ["public_id", "account_name"],
            "filters": [{"field": "public_id", "operator": "eq", "value": "cus_fabricated"}],
            "sorts": [],
            "metrics": [],
            "group_by": [],
            "scope": "accessible",
            "page_size": 20,
            "cursor": None,
        },
    )

    assert constrained["filters"] == [
        {"field": "public_id", "operator": "eq", "value": "cus_a"},
    ]


def test_authority_canonicalizes_same_customer_context_reference() -> None:
    canonical = _customer_ref("cus_a", "eref_canonical")
    authority = CRMQueryAuthority(entity_refs=(canonical,))

    constrained = authority.constrain_context(
        {
            "customer_ref": _customer_ref("cus_a", "eref_model_selected"),
            "sections": ["profile"],
            "question": "客户当前情况",
            "evidence_limit": 6,
        }
    )

    assert constrained["customer_ref"] == canonical.model_dump(mode="json")


def test_authority_replaces_conflicting_forced_filters_and_scope() -> None:
    authority = CRMQueryAuthority(
        filters=(
            CRMFilter(field="status", operator="eq", value="open"),
            CRMFilter(field="due_window", operator="eq", value="this_week"),
        ),
        scope="mine",
    )

    constrained = authority.constrain_query(
        "follow_up_task",
        _query_payload(
            {"field": "status", "operator": "eq", "value": "completed"},
            {"field": "priority", "operator": "eq", "value": "high"},
        ),
    )

    assert constrained["scope"] == "mine"
    assert constrained["filters"] == [
        {"field": "priority", "operator": "eq", "value": "high"},
        {"field": "status", "operator": "eq", "value": "open"},
        {"field": "due_window", "operator": "eq", "value": "this_week"},
    ]
