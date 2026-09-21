from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import or_

from app.crud.industry import industry_crud
from app.models.customer import Customer

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.orm import Session

    from app.services.customer_enrichment_contracts import CustomerEnrichmentDecision


@dataclass(frozen=True)
class CustomerEnrichmentPlan:
    version: str
    fields: tuple[str, ...]
    backfill_enabled: bool


ACTIVE_CUSTOMER_ENRICHMENT_PLAN = CustomerEnrichmentPlan(
    version="customer-initial-v1",
    fields=("industry",),
    backfill_enabled=True,
)


class CustomerEnrichmentFieldHandler(Protocol):
    field_key: str
    @property
    def customer_column(self) -> object: ...

    def is_missing(self, value: object) -> bool: ...

    @property
    def missing_condition(self) -> object: ...

    def catalog(self, db: Session) -> list[dict[str, object]]: ...

    def validate_catalog(self, catalog: Sequence[dict[str, object]]) -> None: ...

    def validate(self, value: str, catalog: Sequence[dict[str, object]]) -> None: ...


class IndustryEnrichmentField:
    field_key = "industry"
    @property
    def customer_column(self) -> object:
        return Customer.industry

    @staticmethod
    def is_missing(value: object) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @property
    def missing_condition(self) -> object:
        return or_(Customer.industry.is_(None), Customer.industry.regexp_match(r"^\s*$"))

    def catalog(self, db: Session) -> list[dict[str, object]]:
        catalog: list[dict[str, object]] = []
        for industry in industry_crud.get_all_active(db):
            if getattr(industry, "is_active", 0) != 1:
                continue
            parent = getattr(industry, "parent", None)
            catalog.append(
                {
                    "code": industry.code,
                    "name": industry.name,
                    "level": industry.level,
                    "parent_code": getattr(parent, "code", None),
                    "parent_name": getattr(parent, "name", None),
                }
            )
        return catalog

    def validate_catalog(self, catalog: Sequence[dict[str, object]]) -> None:
        other = next((entry for entry in catalog if entry.get("code") == "other"), None)
        if other is None or other.get("level") != 1:
            raise _inference_error("客户补全行业目录缺少启用的一级 other")

    def validate(self, value: str, catalog: Sequence[dict[str, object]]) -> None:
        self.validate_catalog(catalog)
        item = next((entry for entry in catalog if entry.get("code") == value), None)
        if item is None:
            raise _inference_error(f"客户补全行业代码不在启用目录中: {value}")


class CustomerEnrichmentFieldRegistry:
    def __init__(self, handlers: Iterable[CustomerEnrichmentFieldHandler] | None = None) -> None:
        values = tuple(handlers) if handlers is not None else (IndustryEnrichmentField(),)
        self._handlers = {item.field_key: item for item in values}

    def get(self, field_key: str) -> CustomerEnrichmentFieldHandler:
        try:
            return self._handlers[field_key]
        except KeyError as exc:
            raise _inference_error(f"未注册的客户补全字段: {field_key}") from exc

    def is_missing(self, field_key: str, value: object) -> bool:
        return self.get(field_key).is_missing(value)

    def missing_condition(self, field_key: str) -> object:
        return self.get(field_key).missing_condition

    def catalogs(
        self,
        db: Session,
        team_id: int,
        fields: tuple[str, ...],
    ) -> dict[str, list[dict[str, object]]]:
        del team_id
        return {field: self.get(field).catalog(db) for field in fields}

    def validate_catalogs(
        self,
        requested_fields: Sequence[str],
        catalogs: dict[str, list[dict[str, object]]],
    ) -> None:
        for field in requested_fields:
            try:
                catalog = catalogs[field]
            except KeyError as exc:
                raise _inference_error(f"客户补全字段目录缺失: {field}") from exc
            self.get(field).validate_catalog(catalog)

    def validate(
        self,
        decisions: Sequence[CustomerEnrichmentDecision],
        requested_fields: Sequence[str],
        catalogs: dict[str, list[dict[str, object]]],
    ) -> tuple[CustomerEnrichmentDecision, ...]:
        requested = tuple(requested_fields)
        decision_fields = tuple(item.field for item in decisions)
        if len(set(decision_fields)) != len(decision_fields):
            raise _inference_error("客户补全结果字段重复")
        if len(decisions) != len(requested) or set(decision_fields) != set(requested):
            raise _inference_error("客户补全结果必须逐字段完整返回")
        self.validate_catalogs(requested, catalogs)
        for decision in decisions:
            try:
                catalog = catalogs[decision.field]
            except KeyError as exc:
                raise _inference_error(f"客户补全字段目录缺失: {decision.field}") from exc
            self.get(decision.field).validate(decision.value, catalog)
        return tuple(decisions)


def _inference_error(message: str) -> Exception:
    # Delayed import keeps the registry reusable while the inference service owns
    # the public error contract.
    from app.services.customer_enrichment_inference_service import CustomerEnrichmentInferenceError

    return CustomerEnrichmentInferenceError(message)
