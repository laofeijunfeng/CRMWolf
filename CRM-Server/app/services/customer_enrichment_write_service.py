from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.operation_log_events import EventActions, EventTypes, ResourceTypes
from app.models.customer import Customer
from app.services.customer_enrichment_contracts import CustomerEnrichmentDecision
from app.services.customer_enrichment_plan import CustomerEnrichmentFieldRegistry
from app.services.operation_log_service import OperationLogService, operation_log_service
from app.utils.time import business_now

APPLIED = "APPLIED"
SKIPPED = "SKIPPED"
RETRY = "RETRY"


@dataclass(frozen=True)
class CustomerEnrichmentWriteResult:
    outcome: Literal["APPLIED", "SKIPPED", "RETRY"]
    applied_fields: tuple[str, ...] = ()
    customer_version: int | None = None
    reason: str | None = None


class CustomerEnrichmentWriteError(RuntimeError):
    """Validated enrichment decisions could not be applied safely."""


class CustomerEnrichmentWriteService:
    def __init__(
        self,
        *,
        field_registry: CustomerEnrichmentFieldRegistry | None = None,
        log_service: OperationLogService | None = None,
    ) -> None:
        self._field_registry = field_registry or CustomerEnrichmentFieldRegistry()
        self._log_service = log_service or operation_log_service

    def apply(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        expected_version: int,
        decisions: tuple[CustomerEnrichmentDecision, ...],
        plan_version: str,
        job_public_id: str,
    ) -> CustomerEnrichmentWriteResult:
        try:
            applied_fields, applied_values, column_values = self._validated_values(db, decisions)
            conditions = [
                Customer.id == customer_id,
                Customer.team_id == team_id,
                Customer.version == expected_version,
                *(column.is_(None) for column in column_values),
            ]
            result = db.execute(
                update(Customer)
                .where(*conditions)
                .values(
                    {
                        **column_values,
                        Customer.version: Customer.version + 1,
                        Customer.last_modified_time: business_now(),
                    }
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 0:
                db.rollback()
                return self._conflict_result(
                    db,
                    team_id=team_id,
                    customer_id=customer_id,
                    columns=tuple(column_values),
                )

            log = self._log_service.log(
                db=db,
                event_type=EventTypes.CUSTOMER_UPDATED,
                event_action=EventActions.UPDATE,
                resource_type=ResourceTypes.CUSTOMER,
                resource_id=customer_id,
                operator_id="system",
                operator_name="系统",
                team_id=team_id,
                commit=False,
                content={
                    "changed_fields": applied_fields,
                    "before": {field: None for field in applied_fields},
                    "after": applied_values,
                    "source": "CUSTOMER_INITIAL_ENRICHMENT",
                    "plan_version": plan_version,
                    "job_public_id": job_public_id,
                },
            )
            if log is None:
                raise CustomerEnrichmentWriteError("客户补全操作日志写入失败")

            db.commit()
            return CustomerEnrichmentWriteResult(
                outcome=APPLIED,
                applied_fields=applied_fields,
                customer_version=expected_version + 1,
            )
        except CustomerEnrichmentWriteError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise CustomerEnrichmentWriteError("客户补全写入失败") from exc

    def _validated_values(
        self,
        db: Session,
        decisions: tuple[CustomerEnrichmentDecision, ...],
    ) -> tuple[tuple[str, ...], dict[str, str], dict[object, str]]:
        if not decisions:
            raise CustomerEnrichmentWriteError("客户补全决策不能为空")

        applied_fields: list[str] = []
        applied_values: dict[str, str] = {}
        column_values: dict[object, str] = {}
        for decision in decisions:
            if decision.field in applied_values:
                raise CustomerEnrichmentWriteError("客户补全决策字段重复")
            handler = self._field_registry.get(decision.field)
            catalog = handler.catalog(db)
            handler.validate(decision.value, catalog)
            applied_fields.append(decision.field)
            applied_values[decision.field] = decision.value
            column_values[handler.customer_column] = decision.value
        return tuple(applied_fields), applied_values, column_values

    @staticmethod
    def _conflict_result(
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        columns: tuple[object, ...],
    ) -> CustomerEnrichmentWriteResult:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id, Customer.team_id == team_id)
            .populate_existing()
            .first()
        )
        if customer is not None and any(getattr(customer, column.key) is not None for column in columns):
            return CustomerEnrichmentWriteResult(
                outcome=SKIPPED,
                reason="FIELD_ALREADY_FILLED",
                customer_version=customer.version,
            )
        return CustomerEnrichmentWriteResult(
            outcome=RETRY,
            reason="CUSTOMER_CHANGED_DURING_ENRICHMENT",
            customer_version=customer.version if customer is not None else None,
        )
