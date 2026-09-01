"""Single declarative catalog for deterministic CRM query capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.services.agent.query.schemas import CRMFilterOperator, CRMResource


class CRMQueryCatalogError(LookupError):
    """Raised when a resource is not registered in the query catalog."""


@dataclass(frozen=True)
class CRMQueryResourceDefinition:
    """Closed declaration consumed by policy validation and API adapters."""

    resource: CRMResource
    adapter_key: str
    default_projection: tuple[str, ...]
    projection_fields: frozenset[str]
    filterable_fields: Mapping[str, frozenset[CRMFilterOperator]]
    sortable_fields: frozenset[str]
    relations: frozenset[str]
    default_scope: str
    allowed_scopes: frozenset[str]
    team_scope_permission: str | None = None
    required_exact_filters: frozenset[str] = frozenset()

    def filter_operators(self, field: str) -> frozenset[CRMFilterOperator]:
        return self.filterable_fields.get(field, frozenset())


_CUSTOMER_FILTERS: Mapping[str, frozenset[CRMFilterOperator]] = MappingProxyType(
    {
        "public_id": frozenset({"eq"}),
        "account_name": frozenset({"eq", "contains"}),
        "city": frozenset({"eq", "in"}),
        "industry": frozenset({"eq", "in", "not_in"}),
        "status": frozenset({"eq", "in", "not_in"}),
        "owner_id": frozenset({"eq", "in"}),
        "acquisition_source": frozenset({"eq", "in"}),
        "company_scale": frozenset({"eq", "in"}),
        "created_time": frozenset({"gte", "lte", "between"}),
        "keyword": frozenset({"contains"}),
    }
)

_CUSTOMER = CRMQueryResourceDefinition(
    resource="customer",
    adapter_key="customers_api",
    default_projection=(
        "public_id",
        "account_name",
        "city",
        "industry",
        "status",
        "owner",
    ),
    projection_fields=frozenset(
        {
            "public_id",
            "account_name",
            "city",
            "industry",
            "status",
            "owner",
            "owner_id",
            "acquisition_source",
            "company_scale",
            "created_time",
            "last_modified_time",
        }
    ),
    filterable_fields=_CUSTOMER_FILTERS,
    sortable_fields=frozenset({"created_time", "last_modified_time", "account_name", "city", "status"}),
    relations=frozenset({"contacts", "activities", "opportunities", "contracts", "payments", "invoices"}),
    default_scope="accessible",
    allowed_scopes=frozenset({"accessible", "mine", "team"}),
    team_scope_permission="customer:view:all",
)

_CONTACT = CRMQueryResourceDefinition(
    resource="contact",
    adapter_key="customer_contacts_api",
    default_projection=("id", "customer_id", "name", "position", "mobile", "is_primary"),
    projection_fields=frozenset(
        {
            "id",
            "customer_id",
            "name",
            "gender",
            "position",
            "is_decision_maker",
            "mobile",
            "email",
            "wechat_id",
            "remark",
            "reports_to",
            "is_primary",
            "created_time",
        }
    ),
    filterable_fields=MappingProxyType({"customer_id": frozenset({"eq"})}),
    sortable_fields=frozenset(),
    relations=frozenset({"customer"}),
    default_scope="accessible",
    allowed_scopes=frozenset({"accessible"}),
    required_exact_filters=frozenset({"customer_id"}),
)

_CUSTOMER_ACTIVITY = CRMQueryResourceDefinition(
    resource="customer_activity",
    adapter_key="customer_activities_api",
    default_projection=(
        "id",
        "customer_id",
        "activity_kind",
        "title",
        "summary",
        "next_action",
        "occurred_at",
        "owner",
    ),
    projection_fields=frozenset(
        {
            "id",
            "customer_id",
            "activity_kind",
            "activity_label",
            "title",
            "summary",
            "next_action",
            "next_follow_time",
            "occurred_at",
            "owner_id",
            "owner",
            "created_time",
            "updated_time",
        }
    ),
    filterable_fields=MappingProxyType({"customer_id": frozenset({"eq"})}),
    sortable_fields=frozenset(),
    relations=frozenset({"customer"}),
    default_scope="accessible",
    allowed_scopes=frozenset({"accessible"}),
    required_exact_filters=frozenset({"customer_id"}),
)

_DEPLOYMENT_INFO = CRMQueryResourceDefinition(
    resource="deployment_info",
    adapter_key="deployment_infos_api",
    default_projection=(
        "id",
        "customer_id",
        "deployment_name",
        "server_address",
        "authorized_users",
        "is_default",
        "created_time",
        "last_modified_time",
    ),
    projection_fields=frozenset(
        {
            "id",
            "customer_id",
            "deployment_name",
            "server_address",
            "authorized_users",
            "is_default",
            "created_time",
            "last_modified_time",
        }
    ),
    filterable_fields=MappingProxyType({"customer_id": frozenset({"eq"})}),
    sortable_fields=frozenset(),
    relations=frozenset({"customer"}),
    default_scope="accessible",
    allowed_scopes=frozenset({"accessible"}),
    required_exact_filters=frozenset({"customer_id"}),
)

_FOLLOW_UP_TASK = CRMQueryResourceDefinition(
    resource="follow_up_task",
    adapter_key="follow_up_tasks_api",
    default_projection=("public_id", "customer", "title", "status", "due_at", "owner"),
    projection_fields=frozenset(
        {
            "public_id",
            "customer",
            "owner_id",
            "owner",
            "creator_id",
            "title",
            "description",
            "status",
            "due_at",
            "due_at_text",
            "overdue_days",
            "completed_at",
            "cancelled_at",
            "created_time",
            "updated_time",
        }
    ),
    filterable_fields=MappingProxyType(
        {
            "status": frozenset({"eq"}),
            "due_window": frozenset({"eq"}),
            "customer_id": frozenset({"eq"}),
            "customer_name": frozenset({"eq", "contains"}),
            "tracking_content": frozenset({"eq", "contains"}),
            "status_label": frozenset({"eq", "in", "not_in"}),
            "tracking_time": frozenset({"gte", "lte", "between"}),
        }
    ),
    sortable_fields=frozenset({"customer_name", "tracking_content", "status_label", "tracking_time"}),
    relations=frozenset({"customer"}),
    default_scope="mine",
    allowed_scopes=frozenset({"mine"}),
)

_COMPLETED_WORK = CRMQueryResourceDefinition(
    resource="completed_work",
    adapter_key="completed_work_api",
    default_projection=("fact_id", "fact_type", "occurred_at", "customer", "title", "payload"),
    projection_fields=frozenset(
        {"fact_id", "fact_type", "source_group", "occurred_at", "customer", "attribution", "title", "payload"}
    ),
    filterable_fields=MappingProxyType(
        {
            "window": frozenset({"eq"}),
            "customer_id": frozenset({"eq"}),
            "occurred_at": frozenset({"between"}),
        }
    ),
    sortable_fields=frozenset(),
    relations=frozenset({"customer"}),
    default_scope="mine",
    allowed_scopes=frozenset({"mine"}),
)

_DEFAULT_DEFINITIONS: Mapping[CRMResource, CRMQueryResourceDefinition] = MappingProxyType(
    {
        "customer": _CUSTOMER,
        "contact": _CONTACT,
        "customer_activity": _CUSTOMER_ACTIVITY,
        "deployment_info": _DEPLOYMENT_INFO,
        "follow_up_task": _FOLLOW_UP_TASK,
        "completed_work": _COMPLETED_WORK,
    }
)


class CRMQueryCatalog:
    """Resolve resource capabilities without exposing transport implementation."""

    def __init__(
        self,
        definitions: Mapping[CRMResource, CRMQueryResourceDefinition] | None = None,
    ) -> None:
        self._definitions = MappingProxyType(dict(definitions or _DEFAULT_DEFINITIONS))

    def resolve(self, resource: CRMResource) -> CRMQueryResourceDefinition:
        try:
            return self._definitions[resource]
        except KeyError as exc:
            raise CRMQueryCatalogError(f"unsupported CRM query resource: {resource}") from exc
