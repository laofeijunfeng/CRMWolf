"""Deterministic policy validation for model-produced CRM query specifications."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Never
from zoneinfo import ZoneInfo

from app.services.agent.query.catalog import CRMQueryCatalog, CRMQueryCatalogError
from app.services.agent.query.schemas import CRMQuerySpec, QueryError

if TYPE_CHECKING:
    from app.services.agent.query.schemas import CRMFilterOperator, QueryErrorCode
    from app.services.agent.tools.base import AgentToolContext


class QueryPolicyError(ValueError):
    """A typed policy rejection safe to map to the public query error contract."""

    def __init__(self, error: QueryError) -> None:
        super().__init__(error.message)
        self.error = error


MAX_QUERY_PAGE_SIZE = 50
MAX_TEMPORAL_SPAN_DAYS = 366
_TEMPORAL_FIELDS = frozenset({"created_time", "tracking_time", "occurred_at"})
_COLLECTION_OPERATORS = frozenset({"in", "not_in"})


class QueryPolicyValidator:
    """Validate query shape and requested scope before any CRM API call."""

    def __init__(self, catalog: CRMQueryCatalog | None = None) -> None:
        self._catalog = catalog or CRMQueryCatalog()

    def validate(self, spec: CRMQuerySpec, context: AgentToolContext) -> CRMQuerySpec:
        self._require_server_context(context)
        try:
            definition = self._catalog.resolve(spec.resource)
        except CRMQueryCatalogError as exc:
            self._reject("QUERY_UNSUPPORTED", str(exc))

        self._reject_relation_traversal(spec)
        if spec.metrics or spec.group_by:
            self._reject("QUERY_UNSUPPORTED", "aggregate queries are not supported for this resource")
        if spec.page_size > MAX_QUERY_PAGE_SIZE:
            self._reject(
                "QUERY_LIMIT_EXCEEDED",
                f"page_size exceeds the P0 single-tool limit: {MAX_QUERY_PAGE_SIZE}",
            )

        for field in spec.projection:
            if field not in definition.projection_fields:
                self._reject("QUERY_INVALID", f"projection field is not allowed: {field}", field=field)

        for condition in spec.filters:
            operators = definition.filter_operators(condition.field)
            if not operators:
                self._reject(
                    "QUERY_INVALID",
                    f"filter field is not allowed: {condition.field}",
                    field=condition.field,
                )
            if condition.operator not in operators:
                self._reject(
                    "QUERY_INVALID",
                    f"filter operator is not allowed for {condition.field}: {condition.operator}",
                    field=condition.field,
                    operator=condition.operator,
                )
            self._validate_filter_value(condition.field, condition.operator, condition.value)

        for sort in spec.sorts:
            if sort.field not in definition.sortable_fields:
                self._reject("QUERY_INVALID", f"sort field is not allowed: {sort.field}", field=sort.field)

        for required_field in definition.required_exact_filters:
            matching = [
                condition
                for condition in spec.filters
                if condition.field == required_field and condition.operator == "eq"
            ]
            if len(matching) != 1 or not isinstance(matching[0].value, str) or not matching[0].value.strip():
                self._reject(
                    "QUERY_INVALID",
                    f"exact filter is required: {required_field}",
                    field=required_field,
                )

        if spec.scope not in definition.allowed_scopes:
            self._reject("QUERY_INVALID", f"scope is not allowed for {spec.resource}: {spec.scope}")

        if (
            spec.scope == "team"
            and definition.team_scope_permission
            and definition.team_scope_permission not in context.permission_codes
        ):
            self._reject(
                "PERMISSION_DENIED",
                f"team scope requires {definition.team_scope_permission}",
            )

        return spec

    @staticmethod
    def _reject_relation_traversal(spec: CRMQuerySpec) -> None:
        fields = [
            *spec.projection,
            *(condition.field for condition in spec.filters),
            *(sort.field for sort in spec.sorts),
            *spec.group_by,
            *(metric.field for metric in spec.metrics if metric.field is not None),
        ]
        dotted = next((field for field in fields if "." in field), None)
        if dotted is not None:
            QueryPolicyValidator._reject(
                "QUERY_UNSUPPORTED",
                f"relation traversal is not supported in QuerySpec fields: {dotted}",
                field=dotted,
            )

    @staticmethod
    def _validate_filter_value(field: str, operator: CRMFilterOperator, value: object) -> None:
        if operator in _COLLECTION_OPERATORS and (
            not isinstance(value, list)
            or not value
            or any(isinstance(item, (list, dict)) or item is None for item in value)
        ):
            QueryPolicyValidator._reject(
                "QUERY_INVALID",
                f"{operator} filter requires a non-empty array of scalar values: {field}",
                field=field,
                operator=operator,
            )
        if operator == "between" and (not isinstance(value, list) or len(value) != 2):
            QueryPolicyValidator._reject(
                "QUERY_INVALID",
                f"between filter requires exactly two values: {field}",
                field=field,
                operator=operator,
            )
        if field in _TEMPORAL_FIELDS:
            values = value if isinstance(value, list) else [value]
            parsed = [QueryPolicyValidator._parse_temporal(field, item, operator) for item in values]
            if operator == "between":
                starts_at, ends_at = parsed
                if starts_at > ends_at:
                    QueryPolicyValidator._reject(
                        "QUERY_INVALID",
                        f"temporal range start must not be after end: {field}",
                        field=field,
                        operator=operator,
                    )
                if (ends_at - starts_at).days > MAX_TEMPORAL_SPAN_DAYS:
                    QueryPolicyValidator._reject(
                        "QUERY_LIMIT_EXCEEDED",
                        f"temporal range exceeds {MAX_TEMPORAL_SPAN_DAYS} days: {field}",
                        field=field,
                        operator=operator,
                    )

    @staticmethod
    def _parse_temporal(field: str, value: object, operator: CRMFilterOperator) -> datetime:
        if not isinstance(value, str) or not value.strip():
            QueryPolicyValidator._reject(
                "QUERY_INVALID",
                f"temporal filter requires an ISO date or datetime string: {field}",
                field=field,
                operator=operator,
            )
        normalized = value.strip().replace("Z", "+00:00")
        try:
            if "T" in normalized or " " in normalized:
                parsed = datetime.fromisoformat(normalized)
                if parsed.utcoffset() is not None:
                    return parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
                return parsed
            return datetime.combine(date.fromisoformat(normalized), datetime.min.time())
        except ValueError:
            QueryPolicyValidator._reject(
                "QUERY_INVALID",
                f"invalid ISO temporal value: {field}",
                field=field,
                operator=operator,
            )

    @staticmethod
    def _require_server_context(context: AgentToolContext) -> None:
        if context.team_id <= 0 or context.user_id <= 0 or context.session_id <= 0:
            QueryPolicyValidator._reject("QUERY_INVALID", "invalid server query context")
        if not context.authorization.strip():
            QueryPolicyValidator._reject("PERMISSION_DENIED", "missing server authorization")

    @staticmethod
    def _reject(
        code: QueryErrorCode,
        message: str,
        *,
        field: str | None = None,
        operator: CRMFilterOperator | None = None,
    ) -> Never:
        raise QueryPolicyError(
            QueryError(
                code=code,
                message=message,
                retryable=False,
                field=field,
                operator=operator,
            )
        )
