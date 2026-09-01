"""Server-owned constraints for one CRM Query Agent turn.

The model may choose a projection and explain returned facts, but it never owns
entity scope.  This module is the seam where Root's resolved identity and
policy constraints are applied to every read-tool invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.agent.query.schemas import CRMFilter, CRMResource, EntityRef


class CRMQueryAuthorityError(ValueError):
    """A model-produced read request conflicts with Root-owned authority."""


_CUSTOMER_ID_RESOURCES = frozenset({
    "contact",
    "customer_activity",
    "deployment_info",
    "follow_up_task",
    "completed_work",
})


@dataclass(frozen=True)
class CRMQueryAuthority:
    """Apply immutable Root-owned entity, filter, and scope constraints."""

    entity_refs: tuple[EntityRef, ...] = ()
    filters: tuple[CRMFilter, ...] = ()
    scope: Literal["accessible", "mine", "team"] | None = None

    @property
    def customer_refs(self) -> tuple[EntityRef, ...]:
        return tuple(ref for ref in self.entity_refs if ref.resource == "customer")

    def constrain_query(self, resource: CRMResource, payload: dict[str, object]) -> dict[str, object]:
        """Return a tool payload that cannot widen Root's authority."""

        constrained = dict(payload)
        if resource == "customer":
            self._constrain_customer_lookup(constrained)
        elif resource in _CUSTOMER_ID_RESOURCES:
            self._constrain_customer_id(resource, constrained)
        self._apply_filters(constrained)
        if self.scope is not None:
            constrained["scope"] = self.scope
        return constrained

    def constrain_context(self, payload: dict[str, object]) -> dict[str, object]:
        """Canonicalize and validate a get_customer_context request."""

        refs = self.customer_refs
        if not refs:
            raise CRMQueryAuthorityError(
                "get_customer_context requires a server-authoritative customer reference"
            )

        raw_ref = payload.get("customer_ref")
        if isinstance(raw_ref, EntityRef):
            public_id = raw_ref.public_id
        elif isinstance(raw_ref, dict):
            public_id = raw_ref.get("public_id")
        else:
            raise CRMQueryAuthorityError("customer_ref must be selected by the server")
        if not isinstance(public_id, str) or not public_id.strip():
            raise CRMQueryAuthorityError("customer_ref must contain a server-issued public_id")
        matching = next((ref for ref in refs if ref.public_id == public_id), None)
        if matching is None:
            raise CRMQueryAuthorityError("customer_ref is outside the server-authoritative customer scope")

        return {**payload, "customer_ref": matching.model_dump(mode="json")}

    def _constrain_customer_lookup(self, payload: dict[str, object]) -> None:
        refs = self.customer_refs
        if len(refs) == 1:
            self._replace_filter(
                payload,
                field="public_id",
                filter_value=CRMFilter(field="public_id", operator="eq", value=refs[0].public_id),
            )
        elif len(refs) > 1 and _filter_value(payload, "public_id") is None:
            raise CRMQueryAuthorityError(
                "multiple authoritative customers require one customer to be selected before lookup"
            )
        elif len(refs) > 1:
            value = _filter_value(payload, "public_id")
            if value not in {ref.public_id for ref in refs}:
                raise CRMQueryAuthorityError("public_id is outside the server-authoritative customer scope")

    def _constrain_customer_id(self, resource: CRMResource, payload: dict[str, object]) -> None:
        refs = self.customer_refs
        if not refs:
            return
        allowed_ids = {ref.public_id for ref in refs}
        requested = _filter_value(payload, "customer_id")
        if len(refs) == 1:
            self._replace_filter(
                payload,
                field="customer_id",
                filter_value=CRMFilter(field="customer_id", operator="eq", value=refs[0].public_id),
            )
            return
        if requested not in allowed_ids:
            raise CRMQueryAuthorityError(
                f"{resource} requires one customer_id from the server-authoritative customer scope"
            )

    def _apply_filters(self, payload: dict[str, object]) -> None:
        if not self.filters:
            return
        raw_filters = payload.get("filters")
        model_filters = raw_filters if isinstance(raw_filters, list) else []
        forced_fields = {condition.field for condition in self.filters}
        retained = [
            _filter_payload(item)
            for item in model_filters
            if _filter_field(item) not in forced_fields
        ]
        payload["filters"] = [
            *retained,
            *(condition.model_dump(mode="json") for condition in self.filters),
        ]

    @staticmethod
    def _replace_filter(payload: dict[str, object], *, field: str, filter_value: CRMFilter) -> None:
        raw_filters = payload.get("filters")
        model_filters = raw_filters if isinstance(raw_filters, list) else []
        retained = [
            _filter_payload(item)
            for item in model_filters
            if _filter_field(item) != field
        ]
        payload["filters"] = [*retained, filter_value.model_dump(mode="json")]


def _filter_field(item: object) -> str | None:
    if isinstance(item, CRMFilter):
        return item.field
    if isinstance(item, dict):
        field = item.get("field")
        return field if isinstance(field, str) else None
    return None


def _filter_payload(item: object) -> dict[str, object]:
    if isinstance(item, CRMFilter):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return dict(item)
    return {}


def _filter_value(payload: dict[str, object], field: str) -> object | None:
    raw_filters = payload.get("filters")
    if not isinstance(raw_filters, list):
        return None
    for item in raw_filters:
        if _filter_field(item) != field:
            continue
        if isinstance(item, CRMFilter):
            if item.operator == "eq":
                return item.value
        elif isinstance(item, dict) and item.get("operator") == "eq":
            return item.get("value")
    return None
