from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.crud.payment import payment_plan_crud
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.payment import PaymentPlan, PaymentPlanStatus
from app.models.user import User
from app.schemas.payment import PaymentPlanCreate, PaymentPlanUpdate
from app.utils.time import business_now


class _FakeQuery:
    def __init__(self, value, *, rows=None):
        self._value = value
        self._rows = rows if rows is not None else ([] if value is None else [value])
        self._locked = False

    def filter(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def with_for_update(self):
        self._locked = True
        return self

    def first(self):
        return self._value

    def all(self):
        return list(self._rows)


class _FakeDb:
    def __init__(self, *, contract, customer, user, existing_plans=None):
        self.contract = contract
        self.customer = customer
        self.user = user
        self.existing_plans = list(existing_plans or [])
        self._next_id = 100
        self.added = []
        self.commits = 0
        self.locked_contracts = []

    def query(self, model):
        if model is PaymentPlan:
            return _FakeQuery(self.existing_plans[0] if self.existing_plans else None, rows=self.existing_plans)
        if model is PaymentPlan.planned_amount:
            return _FakeQuery(None, rows=[(plan.planned_amount,) for plan in self.existing_plans])
        values = {
            Contract: self.contract,
            Customer: self.customer,
            User: self.user,
        }
        query = _FakeQuery(values.get(model))

        original_with_for_update = query.with_for_update

        def with_for_update():
            if model is Contract:
                self.locked_contracts.append(self.contract)
            return original_with_for_update()

        query.with_for_update = with_for_update
        return query

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, PaymentPlan):
            obj.id = self._next_id
            self._next_id += 1
            obj.planned_amount = Decimal(str(obj.planned_amount))
            obj.status = obj.status or PaymentPlanStatus.PENDING
            obj.created_time = obj.created_time or business_now()
            obj.last_modified_time = obj.last_modified_time or obj.created_time
            obj.payment_records = []
            obj.invoice_applications = []

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return None


class _FakeDealJourneyService:
    def __init__(self):
        self.events = []
        self.refreshed = []

    def record_event(self, db, **kwargs):
        self.events.append(kwargs)

    def refresh_closure_status(self, db, deal_journey_id):
        self.refreshed.append(deal_journey_id)


def test_batch_create_passes_team_id_to_operation_log(monkeypatch):
    contract = SimpleNamespace(
        id=39,
        team_id=7,
        customer_id=137,
        deal_journey_id=501,
        total_amount=Decimal("100000.00"),
        contract_number="CT202607270001",
        contract_name="Hashkey Digital Asset Group Limited-130 users-1 year",
    )
    customer = SimpleNamespace(
        id=137,
        team_id=7,
        account_name="Hashkey Digital Asset Group Limited",
    )
    user = SimpleNamespace(id=1, name="Eddie")
    db = _FakeDb(contract=contract, customer=customer, user=user)

    generated_numbers = iter(["PP202608050001"])
    monkeypatch.setattr(
        "app.crud.payment.BusinessNumberGenerator.generate",
        lambda prefix, db: next(generated_numbers),
    )

    fake_deal_journey_service = _FakeDealJourneyService()
    monkeypatch.setattr(
        "app.services.deal_journey_service.deal_journey_service",
        fake_deal_journey_service,
    )

    log_calls = []

    def fake_log(**kwargs):
        log_calls.append(kwargs)
        return SimpleNamespace(id=1)

    monkeypatch.setattr("app.services.operation_log_service.operation_log_service.log", fake_log)

    result = payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(
                stage_name="Full payment",
                planned_amount=46800,
                due_date=date(2026, 8, 31),
            )
        ],
        creator_id="1",
        team_id=7,
    )

    assert len(result) == 1
    assert isinstance(result[0], PaymentPlan)
    assert hasattr(result[0], "contract")
    assert log_calls
    assert log_calls[0]["event_type"] == "PAYMENT_PLAN_CREATED"
    assert log_calls[0]["team_id"] == 7


def _contract_40000():
    return SimpleNamespace(
        id=39,
        team_id=7,
        customer_id=137,
        deal_journey_id=501,
        total_amount=Decimal("40000.00"),
        contract_number="CT1",
        contract_name="合同",
    )


def _customer():
    return SimpleNamespace(id=137, team_id=7, account_name="客户")


def _user():
    return SimpleNamespace(id=1, name="Eddie")


def _plan(*, plan_id, amount, stage="已有"):
    return SimpleNamespace(
        id=plan_id,
        contract_id=39,
        planned_amount=Decimal(str(amount)),
        stage_name=stage,
        due_date=date(2026, 8, 31),
        notes=None,
        deal_journey_id=501,
    )


def _patch_create_deps(monkeypatch):
    generated_numbers = iter([f"PP{i}" for i in range(1, 20)])
    monkeypatch.setattr(
        "app.crud.payment.BusinessNumberGenerator.generate",
        lambda prefix, db: next(generated_numbers),
    )
    monkeypatch.setattr(
        "app.services.deal_journey_service.deal_journey_service",
        _FakeDealJourneyService(),
    )
    monkeypatch.setattr(
        "app.services.operation_log_service.operation_log_service.log",
        lambda **kwargs: SimpleNamespace(id=1),
    )
    monkeypatch.setattr(
        "app.crud.user.user_crud.get_by_id",
        lambda db, user_id: _user(),
    )
    monkeypatch.setattr(
        "app.crud.customer.customer_crud.get_by_id",
        lambda db, customer_id: _customer(),
    )


def test_batch_create_rejects_when_existing_plus_requested_exceeds_contract(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    with pytest.raises(ValueError, match=r"回款计划总额\(42000\.00\)不能超过合同总额\(40000\.00\)"):
        payment_plan_crud.batch_create(
            db,
            contract_id=39,
            plans_data=[
                PaymentPlanCreate(stage_name="二期", planned_amount=30000, due_date=date(2026, 9, 30)),
            ],
            creator_id="1",
            team_id=7,
        )

    assert db.locked_contracts
    assert db.added == []


def test_batch_create_accepts_remaining_allocatable_amount(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    result = payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(stage_name="二期", planned_amount=28000, due_date=date(2026, 9, 30)),
        ],
        creator_id="1",
        team_id=7,
    )

    assert len(result) == 1
    assert result[0].planned_amount == Decimal("28000.00")
    assert db.locked_contracts


def test_batch_create_rejects_batch_over_contract_with_no_existing(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(contract=_contract_40000(), customer=_customer(), user=_user())

    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.batch_create(
            db,
            contract_id=39,
            plans_data=[
                PaymentPlanCreate(stage_name="A", planned_amount=20000, due_date=date(2026, 9, 1)),
                PaymentPlanCreate(stage_name="B", planned_amount=20001, due_date=date(2026, 9, 2)),
            ],
            creator_id="1",
            team_id=7,
        )


def test_batch_create_accepts_batch_equal_to_contract(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(contract=_contract_40000(), customer=_customer(), user=_user())

    result = payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(stage_name="A", planned_amount=20000, due_date=date(2026, 9, 1)),
            PaymentPlanCreate(stage_name="B", planned_amount=20000, due_date=date(2026, 9, 2)),
        ],
        creator_id="1",
        team_id=7,
    )

    assert len(result) == 2


def test_create_rejects_when_existing_plus_requested_exceeds_contract(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.create(
            db,
            contract_id=39,
            obj_in=PaymentPlanCreate(stage_name="二期", planned_amount=30000, due_date=date(2026, 9, 30)),
            team_id=7,
        )


def test_update_rejects_raising_total_above_contract(monkeypatch):
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service", _FakeDealJourneyService())
    monkeypatch.setattr(
        payment_plan_crud,
        "update_status",
        lambda db, plan, commit=False: plan,
    )
    monkeypatch.setattr(
        "app.crud.payment.payment_record_crud._update_contract_payment_status",
        lambda db, contract_id, commit=False: None,
    )
    db_obj = _plan(plan_id=1, amount="12000.00", stage="一期")
    db = _FakeDb(contract=_contract_40000(), customer=_customer(), user=_user(), existing_plans=[db_obj])

    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.update(
            db,
            db_obj,
            PaymentPlanUpdate(planned_amount=41000),
        )


def test_update_allows_lowering_amount_when_already_over_cap(monkeypatch):
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service", _FakeDealJourneyService())
    monkeypatch.setattr(
        payment_plan_crud,
        "update_status",
        lambda db, plan, commit=False: plan,
    )
    monkeypatch.setattr(
        "app.crud.payment.payment_record_crud._update_contract_payment_status",
        lambda db, contract_id, commit=False: None,
    )
    first = _plan(plan_id=1, amount="12000.00")
    second = _plan(plan_id=2, amount="30000.00", stage="二期")
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[first, second],
    )

    updated = payment_plan_crud.update(db, second, PaymentPlanUpdate(planned_amount=25000))
    assert Decimal(str(updated.planned_amount)) == Decimal("25000.00")


def test_update_allows_stage_only_change_when_already_over_cap(monkeypatch):
    monkeypatch.setattr("app.services.deal_journey_service.deal_journey_service", _FakeDealJourneyService())
    monkeypatch.setattr(
        payment_plan_crud,
        "update_status",
        lambda db, plan, commit=False: plan,
    )
    monkeypatch.setattr(
        "app.crud.payment.payment_record_crud._update_contract_payment_status",
        lambda db, contract_id, commit=False: None,
    )
    first = _plan(plan_id=1, amount="12000.00")
    second = _plan(plan_id=2, amount="30000.00", stage="二期")
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[first, second],
    )

    updated = payment_plan_crud.update(db, second, PaymentPlanUpdate(stage_name="尾款"))
    assert updated.stage_name == "尾款"
    assert Decimal(str(updated.planned_amount)) == Decimal("30000.00")


def test_batch_create_uses_cent_precision(monkeypatch):
    _patch_create_deps(monkeypatch)
    db = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )

    payment_plan_crud.batch_create(
        db,
        contract_id=39,
        plans_data=[
            PaymentPlanCreate(stage_name="二期", planned_amount=28000.00, due_date=date(2026, 9, 30)),
        ],
        creator_id="1",
        team_id=7,
    )

    db_over = _FakeDb(
        contract=_contract_40000(),
        customer=_customer(),
        user=_user(),
        existing_plans=[_plan(plan_id=1, amount="12000.00")],
    )
    with pytest.raises(ValueError, match="不能超过合同总额"):
        payment_plan_crud.batch_create(
            db_over,
            contract_id=39,
            plans_data=[
                PaymentPlanCreate(stage_name="二期", planned_amount=28000.01, due_date=date(2026, 9, 30)),
            ],
            creator_id="1",
            team_id=7,
        )
