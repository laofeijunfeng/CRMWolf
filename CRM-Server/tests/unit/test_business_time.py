from datetime import datetime

from app.crud import customer_activity as customer_activity_module
from app.crud.customer_activity import customer_activity_crud
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.customer_activity_kinds import CustomerActivityKind
from app.utils.time import business_now


class FakeDB:
    def __init__(self):
        self.added = None
        self.commits = 0

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        obj.id = getattr(obj, "id", None) or 1


class FakeDealJourneyService:
    def infer_for_customer(self, db, customer_id, team_id):
        return None

    def record_event(self, *args, **kwargs):
        return None


class FakeOperationLogService:
    def log_customer_activity(self, *args, **kwargs):
        return None


def test_business_now_returns_naive_business_local_time():
    now = business_now()

    assert now.tzinfo is None
    assert 7 * 3600 < (now - datetime.utcnow()).total_seconds() < 9 * 3600


def test_customer_activity_default_occurred_at_uses_business_now(monkeypatch):
    fixed_now = datetime(2026, 8, 4, 16, 30, 0)

    monkeypatch.setattr(customer_activity_module, "business_now", lambda: fixed_now)
    monkeypatch.setattr(customer_activity_module, "_upsert_customer_activity_evidence", lambda *args, **kwargs: None)

    import app.services.deal_journey_service as deal_journey_module
    import app.services.operation_log_service as operation_log_module

    monkeypatch.setattr(deal_journey_module, "deal_journey_service", FakeDealJourneyService())
    monkeypatch.setattr(operation_log_module, "operation_log_service", FakeOperationLogService())

    db = FakeDB()
    activity = customer_activity_crud.create(
        db,
        CustomerActivityCreate(
            activity_kind=CustomerActivityKind.OTHER_FOLLOW_UP,
            source_content="客户同意下周继续沟通",
        ),
        customer_id=1,
        creator_id="1",
        team_id=1,
    )

    assert activity is db.added
    assert activity.occurred_at == fixed_now
