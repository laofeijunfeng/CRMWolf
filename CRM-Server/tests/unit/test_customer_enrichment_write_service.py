from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.industry import Industry
from app.models.operation_log import OperationLog
from app.services.customer_enrichment_contracts import CustomerEnrichmentDecision
from app.services.customer_enrichment_plan import (
    CustomerEnrichmentFieldRegistry,
    IndustryEnrichmentField,
)
from app.services.customer_enrichment_write_service import (
    CustomerEnrichmentWriteError,
    CustomerEnrichmentWriteService,
)
from app.services.operation_log_service import OperationLogService


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


def _seed_customer(
    *,
    industry: str | None,
    version: int,
    address: str | None = None,
    active_saas: bool = True,
):
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[Industry.__table__, Customer.__table__, OperationLog.__table__],
    )
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    primary = Industry(level=1, code="internet", name="互联网", is_active=1, sort_order=10)
    db.add(primary)
    db.flush()
    db.add_all(
        [
            Industry(
                level=2,
                parent_id=primary.id,
                code="internet_saas",
                name="SaaS公司",
                is_active=1 if active_saas else 0,
                sort_order=20,
            ),
            Industry(level=1, code="other", name="其他", is_active=1, sort_order=999),
        ]
    )
    customer = Customer(
        public_id="cus_enrichment_write",
        team_id=2,
        account_name="星云研发科技",
        city="上海",
        industry=industry,
        address=address,
        creator_id="tester",
        status=0,
        version=version,
    )
    db.add(customer)
    db.commit()
    return db, customer


def _service(
    *,
    field_registry: CustomerEnrichmentFieldRegistry | None = None,
    log_service: OperationLogService | None = None,
) -> CustomerEnrichmentWriteService:
    return CustomerEnrichmentWriteService(
        field_registry=field_registry,
        log_service=log_service,
    )


def _industry_decision(value: str = "internet_saas") -> CustomerEnrichmentDecision:
    return CustomerEnrichmentDecision(field="industry", value=value, reason="软件研发")


class _RecordingOperationLogService(OperationLogService):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def log(self, **kwargs):
        self.calls.append(dict(kwargs))
        return super().log(**kwargs)


def test_apply_sets_null_industry_and_logs_once():
    db, customer = _seed_customer(industry=None, version=4)
    log_service = _RecordingOperationLogService()

    result = _service(log_service=log_service).apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(_industry_decision(),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )

    db.refresh(customer)
    assert result.outcome == "APPLIED"
    assert result.applied_fields == ("industry",)
    assert result.customer_version == 5
    assert customer.industry == "internet_saas"
    assert customer.version == 5
    assert len(log_service.calls) == 1
    assert log_service.calls[0]["commit"] is False
    log = db.query(OperationLog).one()
    assert log.team_id == 2
    assert log.event_type == "CUSTOMER_UPDATED"
    assert log.event_action == "UPDATE"
    assert log.primary_resource_type == "CUSTOMER"
    assert log.primary_resource_id == customer.id
    assert log.operator_id == "system"
    assert log.operator_name == "系统"
    assert log.content == {
        "changed_fields": ["industry"],
        "before": {"industry": None},
        "after": {"industry": "internet_saas"},
        "source": "CUSTOMER_INITIAL_ENRICHMENT",
        "plan_version": "customer-initial-v1",
        "job_public_id": "cej_1",
    }


def test_apply_without_commit_flushes_then_rollback_undoes_customer_and_audit():
    db, customer = _seed_customer(industry=None, version=4)

    result = _service().apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(_industry_decision(),),
        plan_version="customer-initial-v1",
        job_public_id="cej_atomic",
        commit=False,
    )

    db.refresh(customer)
    assert result.outcome == "APPLIED"
    assert customer.industry == "internet_saas"
    assert customer.version == 5
    assert db.query(OperationLog).count() == 1

    db.rollback()
    db.expire_all()
    stored = db.get(Customer, customer.id)
    assert stored is not None
    assert stored.industry is None
    assert stored.version == 4
    assert db.query(OperationLog).count() == 0

def test_apply_does_not_overwrite_existing_industry():
    db, customer = _seed_customer(industry="finance", version=4)

    result = _service().apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(_industry_decision(),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )

    db.refresh(customer)
    assert result.outcome == "SKIPPED"
    assert result.reason == "FIELD_ALREADY_FILLED"
    assert customer.industry == "finance"
    assert customer.version == 4
    assert db.query(OperationLog).count() == 0


def test_apply_retries_when_customer_version_changed_but_field_still_null():
    db, customer = _seed_customer(industry=None, version=5)

    result = _service().apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(_industry_decision(),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )

    db.refresh(customer)
    assert result.outcome == "RETRY"
    assert result.reason == "CUSTOMER_CHANGED_DURING_ENRICHMENT"
    assert customer.industry is None
    assert customer.version == 5
    assert db.query(OperationLog).count() == 0


def test_apply_is_tenant_scoped():
    db, customer = _seed_customer(industry=None, version=4)

    result = _service().apply(
        db,
        team_id=3,
        customer_id=customer.id,
        expected_version=4,
        decisions=(_industry_decision(),),
        plan_version="customer-initial-v1",
        job_public_id="cej_1",
    )

    db.refresh(customer)
    assert result.outcome == "RETRY"
    assert result.reason == "CUSTOMER_CHANGED_DURING_ENRICHMENT"
    assert customer.industry is None
    assert customer.version == 4
    assert db.query(OperationLog).count() == 0


def test_apply_revalidates_active_industry_before_write():
    db, customer = _seed_customer(industry=None, version=4, active_saas=False)

    with pytest.raises(CustomerEnrichmentWriteError):
        _service().apply(
            db,
            team_id=2,
            customer_id=customer.id,
            expected_version=4,
            decisions=(_industry_decision(),),
            plan_version="customer-initial-v1",
            job_public_id="cej_1",
        )

    db.expire_all()
    stored = db.get(Customer, customer.id)
    assert stored is not None
    assert stored.industry is None
    assert stored.version == 4
    assert db.query(OperationLog).count() == 0


def test_apply_rolls_back_when_operation_log_fails(monkeypatch):
    db, customer = _seed_customer(industry=None, version=4)
    monkeypatch.setattr(
        "app.services.customer_enrichment_write_service.operation_log_service.log",
        lambda **kwargs: None,
    )

    with pytest.raises(CustomerEnrichmentWriteError):
        _service().apply(
            db,
            team_id=2,
            customer_id=customer.id,
            expected_version=4,
            decisions=(_industry_decision(),),
            plan_version="customer-initial-v1",
            job_public_id="cej_1",
        )

    db.expire_all()
    stored = db.get(Customer, customer.id)
    assert stored is not None
    assert stored.industry is None
    assert stored.version == 4
    assert db.query(OperationLog).count() == 0


@dataclass(frozen=True)
class _AddressEnrichmentField:
    field_key: str = "address"

    @property
    def customer_column(self):
        return Customer.address

    def catalog(self, db):
        del db
        return []

    def validate(self, value, catalog):
        del catalog
        if not value.strip():
            raise ValueError("address must be nonblank")


def _registry_with_industry_and_address() -> CustomerEnrichmentFieldRegistry:
    return CustomerEnrichmentFieldRegistry(
        handlers=(IndustryEnrichmentField(), _AddressEnrichmentField())
    )


def test_future_multi_field_plan_writes_all_fields_with_one_version_increment():
    db, customer = _seed_customer(industry=None, address=None, version=4)
    service = _service(field_registry=_registry_with_industry_and_address())

    result = service.apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(
            _industry_decision(),
            CustomerEnrichmentDecision(field="address", value="上海市", reason="明确地址"),
        ),
        plan_version="test-v2",
        job_public_id="cej_2",
    )

    db.refresh(customer)
    assert result.outcome == "APPLIED"
    assert result.applied_fields == ("industry", "address")
    assert result.customer_version == 5
    assert customer.industry == "internet_saas"
    assert customer.address == "上海市"
    assert customer.version == 5
    log = db.query(OperationLog).one()
    assert log.content["changed_fields"] == ["industry", "address"]


def test_future_multi_field_plan_does_not_write_when_one_decision_is_invalid():
    db, customer = _seed_customer(industry=None, address=None, version=4)
    service = _service(field_registry=_registry_with_industry_and_address())

    with pytest.raises(CustomerEnrichmentWriteError):
        service.apply(
            db,
            team_id=2,
            customer_id=customer.id,
            expected_version=4,
            decisions=(
                _industry_decision("missing"),
                CustomerEnrichmentDecision(field="address", value="上海市", reason="明确地址"),
            ),
            plan_version="test-v2",
            job_public_id="cej_3",
        )

    db.expire_all()
    stored = db.get(Customer, customer.id)
    assert stored is not None
    assert stored.industry is None
    assert stored.address is None
    assert stored.version == 4
    assert db.query(OperationLog).count() == 0


def test_future_multi_field_plan_skips_everything_when_one_target_is_filled():
    db, customer = _seed_customer(industry=None, address="人工地址", version=4)
    service = _service(field_registry=_registry_with_industry_and_address())

    result = service.apply(
        db,
        team_id=2,
        customer_id=customer.id,
        expected_version=4,
        decisions=(
            _industry_decision(),
            CustomerEnrichmentDecision(field="address", value="上海市", reason="明确地址"),
        ),
        plan_version="test-v2",
        job_public_id="cej_4",
    )

    db.refresh(customer)
    assert result.outcome == "SKIPPED"
    assert result.reason == "FIELD_ALREADY_FILLED"
    assert customer.industry is None
    assert customer.address == "人工地址"
    assert customer.version == 4
    assert db.query(OperationLog).count() == 0
