from datetime import date, datetime, timezone

from app.crud import customer_activity as customer_activity_module
from app.crud.customer_activity import customer_activity_crud
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.customer_activity_kinds import CustomerActivityKind
from app.utils.time import (
    BUSINESS_TIMEZONE,
    DUE_AT_GRANULARITY_DATE,
    DUE_AT_GRANULARITY_DATETIME,
    DUE_AT_GRANULARITY_MONTH,
    DUE_AT_GRANULARITY_WEEK,
    FOLLOW_UP_TASK_DUE_WINDOW_NEXT_WEEK,
    FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE,
    FOLLOW_UP_TASK_DUE_WINDOW_THIS_WEEK,
    FOLLOW_UP_TASK_DUE_WINDOW_TODAY,
    business_now,
    calculate_follow_up_task_due_window,
    normalize_due_at,
    to_business_naive,
)


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
    assert activity.owner_id == "1"


def test_due_at_normalization_preserves_granularity_and_business_timezone():
    date_due = normalize_due_at(date(2026, 8, 6))
    datetime_due = normalize_due_at(datetime(2026, 8, 6, 15, 30, tzinfo=timezone.utc))
    week_due = normalize_due_at(date(2026, 8, 6), granularity=DUE_AT_GRANULARITY_WEEK)
    month_due = normalize_due_at(date(2026, 8, 6), granularity=DUE_AT_GRANULARITY_MONTH)

    assert date_due.due_at == datetime(2026, 8, 6, 0, 0, 0)
    assert date_due.due_at_granularity == DUE_AT_GRANULARITY_DATE
    assert date_due.due_at_timezone == BUSINESS_TIMEZONE
    assert datetime_due.due_at == datetime(2026, 8, 6, 23, 30, 0)
    assert datetime_due.due_at_granularity == DUE_AT_GRANULARITY_DATETIME
    assert week_due.due_at == datetime(2026, 8, 3, 0, 0, 0)
    assert month_due.due_at == datetime(2026, 8, 1, 0, 0, 0)


def test_follow_up_task_due_windows_use_business_week_boundaries():
    anchor = datetime(2026, 8, 6, 15, 30, 0)

    today = calculate_follow_up_task_due_window(FOLLOW_UP_TASK_DUE_WINDOW_TODAY, now=anchor)
    this_week = calculate_follow_up_task_due_window(FOLLOW_UP_TASK_DUE_WINDOW_THIS_WEEK, now=anchor)
    next_week = calculate_follow_up_task_due_window(FOLLOW_UP_TASK_DUE_WINDOW_NEXT_WEEK, now=anchor)
    overdue = calculate_follow_up_task_due_window(FOLLOW_UP_TASK_DUE_WINDOW_OVERDUE, now=anchor)

    assert today.starts_at == datetime(2026, 8, 6, 0, 0, 0)
    assert today.ends_at == datetime(2026, 8, 7, 0, 0, 0)
    assert this_week.starts_at == datetime(2026, 8, 3, 0, 0, 0)
    assert this_week.ends_at == datetime(2026, 8, 10, 0, 0, 0)
    assert next_week.starts_at == datetime(2026, 8, 10, 0, 0, 0)
    assert next_week.ends_at == datetime(2026, 8, 17, 0, 0, 0)
    assert overdue.starts_at is None
    assert overdue.ends_at == datetime(2026, 8, 6, 0, 0, 0)
    assert overdue.anchor_now == anchor


def test_to_business_naive_converts_aware_datetime_to_business_timezone():
    assert to_business_naive(datetime(2026, 8, 6, 1, 0, 0, tzinfo=timezone.utc)) == datetime(
        2026,
        8,
        6,
        9,
        0,
        0,
    )
