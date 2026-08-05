from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.crud.payment import payment_plan_crud
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.payment import PaymentPlan, PaymentPlanStatus
from app.models.user import User
from app.schemas.payment import PaymentPlanCreate
from app.utils.time import business_now


class _FakeQuery:
    def __init__(self, value):
        self._value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._value


class _FakeDb:
    def __init__(self, *, contract, customer, user):
        self.contract = contract
        self.customer = customer
        self.user = user
        self._next_id = 100
        self.added = []
        self.commits = 0

    def query(self, model):
        values = {
            Contract: self.contract,
            Customer: self.customer,
            User: self.user,
        }
        return _FakeQuery(values.get(model))

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
    assert log_calls
    assert log_calls[0]["event_type"] == "PAYMENT_PLAN_CREATED"
    assert log_calls[0]["team_id"] == 7
