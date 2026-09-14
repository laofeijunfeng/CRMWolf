from types import SimpleNamespace

import pytest

from app.core.exceptions import ConflictException
from app.crud.customer import customer_crud
from app.models.outbound_notification_job import OutboundNotificationEventType
from app.services.customer_status_transition_service import (
    CustomerStatusTransitionError,
    customer_status_transition_service,
)


def test_plans_following_to_won_with_won_notification():
    decision = customer_status_transition_service.plan(current_status=0, target_status=1)

    assert decision.previous_status == 0
    assert decision.new_status == 1
    assert decision.notification_event == OutboundNotificationEventType.ACCOUNT_STATUS_WON


def test_plans_won_to_following_without_notification():
    decision = customer_status_transition_service.plan(current_status=1, target_status=0)

    assert decision.previous_status == 1
    assert decision.new_status == 0
    assert decision.notification_event is None


@pytest.mark.parametrize("current_status", [2, 3])
def test_rejects_non_lifecycle_current_status(current_status: int):
    with pytest.raises(CustomerStatusTransitionError):
        customer_status_transition_service.plan(current_status=current_status, target_status=0)


@pytest.mark.parametrize("target_status", [2, 3])
def test_rejects_non_lifecycle_target_status(target_status: int):
    with pytest.raises(CustomerStatusTransitionError):
        customer_status_transition_service.plan(current_status=0, target_status=target_status)


def test_rejects_noop_transition():
    with pytest.raises(CustomerStatusTransitionError):
        customer_status_transition_service.plan(current_status=0, target_status=0)


class _LockedQuery:
    def __init__(self, customer):
        self.customer = customer
        self.locked = False

    def filter(self, *conditions):
        return self

    def with_for_update(self):
        self.locked = True
        return self

    def first(self):
        return self.customer


class _FakeSession:
    def __init__(self, customer):
        self.query_result = _LockedQuery(customer)
        self.commits = 0
        self.refreshed = []

    def query(self, model):
        return self.query_result

    def commit(self):
        self.commits += 1

    def refresh(self, customer):
        self.refreshed.append(customer)


def test_locked_status_update_checks_version_before_mutation():
    customer = SimpleNamespace(id=11, team_id=7, status=0, version=3)
    db = _FakeSession(customer)

    with pytest.raises(ConflictException):
        customer_crud.update_status_with_version(
            db,
            customer,
            status=1,
            expected_version=2,
        )

    assert db.query_result.locked is True
    assert customer.status == 0
    assert customer.version == 3
    assert db.commits == 0
    assert db.refreshed == []


def test_locked_status_update_applies_target_and_increments_version():
    customer = SimpleNamespace(id=11, team_id=7, status=0, version=3)
    db = _FakeSession(customer)

    updated = customer_crud.update_status_with_version(
        db,
        customer,
        status=1,
        expected_version=3,
    )

    assert db.query_result.locked is True
    assert updated is customer
    assert customer.status == 1
    assert customer.version == 4
    assert db.commits == 1
    assert db.refreshed == [customer]
