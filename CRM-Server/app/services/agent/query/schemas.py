"""Stable contracts for model-planned, deterministically executed CRM queries."""

from __future__ import annotations

from typing import Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

JsonDict: TypeAlias = dict[str, JsonValue]
CRMResource: TypeAlias = Literal[
    "customer",
    "contact",
    "customer_activity",
    "follow_up_task",
    "completed_work",
    "opportunity",
    "contract",
    "payment_plan",
    "payment",
    "invoice",
    "license",
]
CRMFilterOperator: TypeAlias = Literal[
    "eq",
    "neq",
    "in",
    "not_in",
    "contains",
    "gte",
    "lte",
    "between",
    "is_null",
]
CRMMetricOperator: TypeAlias = Literal["count", "sum", "avg", "min", "max"]
QueryWarningCode: TypeAlias = Literal[
    "RESULT_TRUNCATED",
    "PARTIAL_RESULT",
    "STALE_DATA",
    "CUSTOMER_INTELLIGENCE_DEGRADED",
]
QueryErrorCode: TypeAlias = Literal[
    "QUERY_INVALID",
    "QUERY_UNSUPPORTED",
    "QUERY_EMPTY",
    "PERMISSION_DENIED",
    "QUERY_LIMIT_EXCEEDED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "MODEL_OUTPUT_INVALID",
    "INTERNAL_ERROR",
]


class QueryContractModel(BaseModel):
    """Closed-world base for contracts shared across planner and executor."""

    model_config = ConfigDict(extra="forbid", strict=True)


class EntityRef(QueryContractModel):
    """Server-issued reference to a CRM entity visible in a result set."""

    ref_id: str = Field(min_length=1, max_length=128)
    resource: CRMResource
    public_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    result_set_id: str | None = Field(default=None, min_length=1, max_length=128)


class CRMFilter(QueryContractModel):
    """One catalog-validated predicate; never an HTTP, SQL, or ORM fragment."""

    field: str = Field(min_length=1, max_length=128)
    operator: CRMFilterOperator
    value: JsonValue


class CRMSort(QueryContractModel):
    """One catalog-validated deterministic sort."""

    field: str = Field(min_length=1, max_length=128)
    direction: Literal["asc", "desc"]


class CRMMetric(QueryContractModel):
    """One catalog-validated aggregate requested by the planner."""

    key: str = Field(min_length=1, max_length=128)
    operator: CRMMetricOperator
    field: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_field_for_value_aggregates(self) -> Self:
        if self.operator != "count" and self.field is None:
            raise ValueError(f"{self.operator} metric requires field")
        return self


class CRMQuerySpec(QueryContractModel):
    """The only contract accepted by the deterministic CRM query executor."""

    resource: CRMResource
    projection: list[str] = Field(min_length=1, max_length=50)
    filters: list[CRMFilter] = Field(default_factory=list, max_length=50)
    sorts: list[CRMSort] = Field(default_factory=list, max_length=10)
    metrics: list[CRMMetric] = Field(default_factory=list, max_length=20)
    group_by: list[str] = Field(default_factory=list, max_length=10)
    scope: Literal["accessible", "mine", "team"] = "accessible"
    page_size: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)


class GroundedFact(QueryContractModel):
    """A user-visible fact tied to a deterministic or cited source."""

    fact_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    value: JsonValue
    source: Literal["CRM_API", "CUSTOMER_INTELLIGENCE", "DERIVED"]
    source_ref: str | None = Field(default=None, min_length=1, max_length=512)
    entity_ref: EntityRef | None = None


class QueryWarning(QueryContractModel):
    """Non-fatal degradation attached to an otherwise usable query result."""

    code: QueryWarningCode
    message: str = Field(min_length=1, max_length=1000)
    resource: CRMResource | None = None


class QueryError(QueryContractModel):
    """Stable query failure payload, distinct from empty and partial results."""

    code: QueryErrorCode
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool
    field: str | None = Field(default=None, min_length=1, max_length=128)
    operator: CRMFilterOperator | None = None


class CRMQueryResult(QueryContractModel):
    """Normalized deterministic output consumed by answer and UI composition."""

    query_id: str = Field(min_length=1, max_length=128)
    result_set_id: str | None = Field(default=None, min_length=1, max_length=128)
    resource: CRMResource
    status: Literal["SUCCESS", "EMPTY", "PARTIAL"]
    executed_query: CRMQuerySpec | None = None
    rows: list[JsonDict] = Field(default_factory=list, max_length=100)
    entity_refs: list[EntityRef] = Field(default_factory=list, max_length=100)
    total: int | None = Field(default=None, ge=0)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    applied_filters: list[CRMFilter] = Field(default_factory=list, max_length=50)
    applied_sorts: list[CRMSort] = Field(default_factory=list, max_length=10)
    facts: list[GroundedFact] = Field(default_factory=list, max_length=200)
    warnings: list[QueryWarning] = Field(default_factory=list, max_length=20)
