"""Deterministic adapters from catalog-backed QuerySpec to authoritative CRM APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Protocol

from pydantic import TypeAdapter, ValidationError

from app.schemas.common import PaginatedResponse
from app.schemas.customer import ContactResponse, CustomerDetailResponse, CustomerListResponse
from app.schemas.customer_activity import CustomerActivityResponse
from app.schemas.deployment import DeploymentInfoResponse
from app.schemas.sales_commitment import FollowUpTaskListResponse
from app.services.agent.query.completed_work_contracts import CompletedWorkQueryResponse
from app.services.agent.query.cursor import decode_offset_cursor, encode_offset_cursor
from app.services.agent.query.schemas import (
    CRMFilter,
    CRMQuerySpec,
    CRMResource,
    EntityRef,
    GroundedFact,
    JsonDict,
    QueryWarning,
)

if TYPE_CHECKING:
    from app.services.agent.tools.api_client import InternalCRMAPIClient
    from app.services.agent.tools.base import AgentToolContext


class CRMQueryAdapterResponseError(ValueError):
    """The authoritative endpoint returned a payload outside its published schema."""


@dataclass(frozen=True)
class CRMQueryAdapterPage:
    rows: list[JsonDict]
    entity_refs: list[EntityRef]
    total: int | None
    next_cursor: str | None
    warnings: list[QueryWarning]
    facts: list[GroundedFact] = dataclass_field(default_factory=list)


class CRMQueryAdapter(Protocol):
    async def execute(
        self,
        spec: CRMQuerySpec,
        context: AgentToolContext,
    ) -> CRMQueryAdapterPage: ...


_CUSTOMER_PAGE_ADAPTER = TypeAdapter(PaginatedResponse[CustomerListResponse])
_CUSTOMER_DETAIL_ADAPTER = TypeAdapter(CustomerDetailResponse)
_CONTACT_LIST_ADAPTER = TypeAdapter(list[ContactResponse])
_ACTIVITY_LIST_ADAPTER = TypeAdapter(list[CustomerActivityResponse])
_DEPLOYMENT_INFO_LIST_ADAPTER = TypeAdapter(list[DeploymentInfoResponse])
_CUSTOMER_FILTER_FIELD_MAP = {"acquisition_source": "source"}
_CUSTOMER_PROJECTION_FIELD_MAP = {
    "owner": "owner_info",
    "acquisition_source": "source_info",
}
_ACTIVITY_PROJECTION_FIELD_MAP = {"owner": "owner_info"}
_FOLLOW_UP_PROJECTION_FIELD_MAP = {"owner": "owner_info"}


def _project(item: JsonDict, projection: list[str], field_map: dict[str, str] | None = None) -> JsonDict:
    aliases = field_map or {}
    return {field: item.get(aliases.get(field, field)) for field in projection}


def _exact_string_filter(spec: CRMQuerySpec, field: str) -> str | None:
    matches = [item for item in spec.filters if item.field == field and item.operator == "eq"]
    if not matches:
        return None
    value = matches[0].value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"exact filter requires a non-empty string: {field}")
    return value.strip()


def _truncation_warning(resource: CRMResource, returned: int, total: int | None) -> QueryWarning:
    suffix = f", 共 {total} 条" if total is not None else ""
    return QueryWarning(
        code="RESULT_TRUNCATED",
        message=f"当前返回 {returned} 条{suffix}。",
        resource=resource,
    )


class CustomersAPIAdapter:
    """Map customer QuerySpec values to ``GET /v1/customers/``."""

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def execute(
        self,
        spec: CRMQuerySpec,
        context: AgentToolContext,
    ) -> CRMQueryAdapterPage:
        public_id = _exact_string_filter(spec, "public_id")
        if public_id is not None:
            return await self._execute_exact_public_id(spec, context, public_id)

        offset = decode_offset_cursor(spec.cursor)
        params: dict[str, object] = {"skip": offset, "limit": spec.page_size}
        if spec.scope == "accessible":
            params["scope"] = "accessible"
        elif spec.scope == "mine":
            params["owner_id"] = "me"

        keyword = next(
            (
                condition.value
                for condition in spec.filters
                if condition.field == "keyword" and condition.operator == "contains"
            ),
            None,
        )
        if keyword is not None:
            params["keyword"] = keyword
        filters = self._transport_filters(spec)
        if filters:
            params["filters"] = json.dumps(filters, ensure_ascii=False, separators=(",", ":"))
        if spec.sorts:
            params["sorts"] = json.dumps(
                [sort.model_dump(mode="json") for sort in spec.sorts],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        payload = await self._api_client.request("GET", "/v1/customers/", context.authorization, params=params)
        try:
            page = _CUSTOMER_PAGE_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("customers API returned an invalid response") from exc

        raw_items = [item.model_dump(mode="json") for item in page.items]
        rows = [_project(item, spec.projection, _CUSTOMER_PROJECTION_FIELD_MAP) for item in raw_items]
        entity_refs = [
            EntityRef(
                ref_id=f"eref_customer_{item['public_id']}",
                resource="customer",
                public_id=str(item["public_id"]),
                display_name=str(item["account_name"]),
            )
            for item in raw_items
        ]
        next_offset = offset + len(rows)
        next_cursor = encode_offset_cursor(next_offset) if next_offset < page.total else None
        warnings = [_truncation_warning("customer", len(rows), page.total)] if next_cursor else []
        return CRMQueryAdapterPage(rows, entity_refs, page.total, next_cursor, warnings)

    async def _execute_exact_public_id(
        self,
        spec: CRMQuerySpec,
        context: AgentToolContext,
        public_id: str,
    ) -> CRMQueryAdapterPage:
        if spec.cursor is not None:
            raise ValueError("exact customer lookup does not accept a cursor")
        if len(spec.filters) != 1:
            raise ValueError("public_id exact lookup cannot be combined with other filters")
        payload = await self._api_client.request(
            "GET",
            f"/v1/customers/{public_id}",
            context.authorization,
        )
        try:
            item = _CUSTOMER_DETAIL_ADAPTER.validate_python(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("customer detail API returned an invalid response") from exc
        row = _project(item, spec.projection, _CUSTOMER_PROJECTION_FIELD_MAP)
        ref = EntityRef(
            ref_id=f"eref_customer_{item['public_id']}",
            resource="customer",
            public_id=str(item["public_id"]),
            display_name=str(item["account_name"]),
        )
        return CRMQueryAdapterPage([row], [ref], 1, None, [])

    @staticmethod
    def _transport_filters(spec: CRMQuerySpec) -> list[dict[str, object]]:
        filters: list[dict[str, object]] = []
        for condition in spec.filters:
            if condition.field == "keyword":
                continue
            field = _CUSTOMER_FILTER_FIELD_MAP.get(condition.field, condition.field)
            if condition.operator == "between":
                value = condition.value
                if not isinstance(value, list) or len(value) != 2:
                    raise ValueError(f"between filter requires two values: {condition.field}")
                filters.extend(
                    [
                        {"field": field, "op": "after", "value": value[0]},
                        {"field": field, "op": "before", "value": value[1]},
                    ]
                )
                continue
            operator = {"gte": "after", "lte": "before"}.get(condition.operator, condition.operator)
            filters.append({"field": field, "op": operator, "value": condition.value})
        return filters


class CustomerContactsAPIAdapter:
    """Read one customer's contacts and apply deterministic local pagination."""

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryAdapterPage:
        customer_id = _exact_string_filter(spec, "customer_id")
        if customer_id is None:
            raise ValueError("customer_id is required")
        offset = decode_offset_cursor(spec.cursor)
        payload = await self._api_client.request("GET", f"/v1/customers/{customer_id}/contacts", context.authorization)
        try:
            contacts = _CONTACT_LIST_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("customer contacts API returned an invalid response") from exc
        total = len(contacts)
        selected = contacts[offset : offset + spec.page_size]
        rows = [_project(item.model_dump(mode="json"), spec.projection) for item in selected]
        next_offset = offset + len(selected)
        next_cursor = encode_offset_cursor(next_offset) if next_offset < total else None
        warnings = [_truncation_warning("contact", len(rows), total)] if next_cursor else []
        return CRMQueryAdapterPage(rows, [], total, next_cursor, warnings)


class CustomerActivitiesAPIAdapter:
    """Map one customer's activity query to its paged authoritative endpoint."""

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryAdapterPage:
        customer_id = _exact_string_filter(spec, "customer_id")
        if customer_id is None:
            raise ValueError("customer_id is required")
        offset = decode_offset_cursor(spec.cursor)
        payload = await self._api_client.request(
            "GET",
            f"/v1/customer-activities/{customer_id}",
            context.authorization,
            params={"skip": offset, "limit": spec.page_size},
        )
        try:
            activities = _ACTIVITY_LIST_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("customer activities API returned an invalid response") from exc
        raw_items = [item.model_dump(mode="json") for item in activities]
        rows = [_project(item, spec.projection, _ACTIVITY_PROJECTION_FIELD_MAP) for item in raw_items]
        next_cursor = encode_offset_cursor(offset + len(rows)) if len(rows) == spec.page_size else None
        warnings = [_truncation_warning("customer_activity", len(rows), None)] if next_cursor else []
        return CRMQueryAdapterPage(rows, [], None, next_cursor, warnings)


class DeploymentInfosAPIAdapter:
    """Map a customer-scoped deployment read to the deployment API."""

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryAdapterPage:
        customer_id = _exact_string_filter(spec, "customer_id")
        if customer_id is None:
            raise ValueError("customer_id is required")
        payload = await self._api_client.request(
            "GET",
            "/v1/deployment-infos/",
            context.authorization,
            params={"customer_id": customer_id},
        )
        try:
            deployments = _DEPLOYMENT_INFO_LIST_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("deployment infos API returned an invalid response") from exc
        raw_items = [item.model_dump(mode="json") for item in deployments]
        rows = [_project(item, spec.projection) for item in raw_items]
        entity_refs = [
            EntityRef(
                ref_id=f"eref_deployment_info_{item['id']}",
                resource="deployment_info",
                public_id=str(item["id"]),
                display_name=str(item["deployment_name"]),
            )
            for item in raw_items
        ]
        return CRMQueryAdapterPage(rows, entity_refs, len(rows), None, [])


class FollowUpTasksAPIAdapter:
    """Map follow-up task QuerySpec values to the existing list endpoint."""

    _DEDICATED_FIELDS = frozenset({"status", "due_window", "customer_id", "tracking_content"})

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryAdapterPage:
        offset = decode_offset_cursor(spec.cursor)
        params: dict[str, object] = {
            "skip": offset,
            "limit": spec.page_size,
            "owner_scope": "mine",
        }
        for field in ("status", "due_window"):
            value = _exact_string_filter(spec, field)
            if value is not None:
                params[field] = value
        customer_id = _exact_string_filter(spec, "customer_id")
        if customer_id is not None:
            params["customer_id"] = customer_id
            params["owner_scope"] = "customer"

        semantic_task_text = None
        if context.query_retrieval_mode == "semantic_filter":
            semantic_task_text = next(
                (
                    condition.value
                    for condition in spec.filters
                    if condition.field == "tracking_content"
                    and condition.operator in {"eq", "contains"}
                ),
                None,
            )
        if semantic_task_text is not None:
            if not isinstance(semantic_task_text, str) or not semantic_task_text.strip():
                raise ValueError("tracking_content semantic filter requires non-empty text")
            params["query_text"] = semantic_task_text.strip()
            params["retrieval_mode"] = "semantic_filter"

        dedicated_fields = self._DEDICATED_FIELDS
        if semantic_task_text is None:
            # Preserve the legacy structured-filter transport unless the
            # server explicitly enabled semantic retrieval for this turn.
            dedicated_fields = dedicated_fields - {"tracking_content"}
        filters = [
            transported
            for item in spec.filters
            if item.field not in dedicated_fields
            for transported in self._list_filters(item)
        ]
        if filters:
            params["filters"] = json.dumps(filters, ensure_ascii=False, separators=(",", ":"))
        if spec.sorts:
            params["sorts"] = json.dumps(
                [sort.model_dump(mode="json") for sort in spec.sorts],
                ensure_ascii=False,
                separators=(",", ":"),
            )

        payload = await self._api_client.request("GET", "/v1/follow-up-tasks", context.authorization, params=params)
        try:
            page = FollowUpTaskListResponse.model_validate(payload)
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("follow-up tasks API returned an invalid response") from exc
        raw_items = [item.model_dump(mode="json") for item in page.items]
        rows = [_project(item, spec.projection, _FOLLOW_UP_PROJECTION_FIELD_MAP) for item in raw_items]
        entity_refs = [
            EntityRef(
                ref_id=f"eref_follow_up_task_{item['public_id']}",
                resource="follow_up_task",
                public_id=str(item["public_id"]),
                display_name=str(item["title"]),
            )
            for item in raw_items
        ]
        next_offset = offset + len(rows)
        next_cursor = encode_offset_cursor(next_offset) if next_offset < page.total else None
        warnings = [_truncation_warning("follow_up_task", len(rows), page.total)] if next_cursor else []
        return CRMQueryAdapterPage(rows, entity_refs, page.total, next_cursor, warnings)

    @staticmethod
    def _list_filters(condition: CRMFilter) -> list[dict[str, object]]:
        if condition.operator == "between":
            value = condition.value
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError(f"between filter requires two values: {condition.field}")
            return [
                {"field": condition.field, "op": "after", "value": value[0]},
                {"field": condition.field, "op": "before", "value": value[1]},
            ]
        operator = {"gte": "after", "lte": "before"}.get(condition.operator, condition.operator)
        return [{"field": condition.field, "op": operator, "value": condition.value}]


class CompletedWorkAPIAdapter:
    """Map completed-work QuerySpec values to the dedicated read-only endpoint."""

    def __init__(self, api_client: InternalCRMAPIClient) -> None:
        self._api_client = api_client

    async def execute(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQueryAdapterPage:
        params: dict[str, object] = {"window": "this_week", "limit": spec.page_size}
        window = _exact_string_filter(spec, "window")
        if window is not None:
            params["window"] = window
        customer_id = _exact_string_filter(spec, "customer_id")
        if customer_id is not None:
            params["customer_id"] = customer_id
        occurred_range = next(
            (
                condition.value
                for condition in spec.filters
                if condition.field == "occurred_at" and condition.operator == "between"
            ),
            None,
        )
        if occurred_range is not None:
            if not isinstance(occurred_range, list) or len(occurred_range) != 2:
                raise ValueError("occurred_at between requires exactly two values")
            params.update({"window": "custom", "start_at": occurred_range[0], "end_at": occurred_range[1]})
        if spec.cursor is not None:
            params["cursor"] = spec.cursor

        payload = await self._api_client.request(
            "GET", "/v1/agent-query/completed-work", context.authorization, params=params
        )
        try:
            page = CompletedWorkQueryResponse.model_validate(payload)
        except ValidationError as exc:
            raise CRMQueryAdapterResponseError("completed-work API returned an invalid response") from exc
        raw_items = [item.model_dump(mode="json") for item in page.items]
        rows = [_project(item, spec.projection) for item in raw_items]
        try:
            facts = [
                GroundedFact(
                    fact_id=item.fact_id,
                    label=item.title,
                    value=raw_item,
                    source="CRM_API",
                    source_ref=item.source_public_id,
                )
                for item, raw_item in zip(page.items, raw_items, strict=True)
            ]
        except ValidationError as exc:
            # This is a response-contract failure, not a malformed query. Do
            # not let the Query Agent spend a correction turn changing a
            # perfectly valid QuerySpec because CRM returned unusable data.
            raise CRMQueryAdapterResponseError("completed-work API returned an invalid response") from exc
        warnings = [_truncation_warning("completed_work", len(rows), page.available_total)] if page.truncated else []
        return CRMQueryAdapterPage(
            rows,
            [],
            page.available_total,
            page.next_cursor,
            warnings,
            facts,
        )
