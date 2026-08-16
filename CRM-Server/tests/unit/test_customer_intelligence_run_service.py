from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound

from app.core.database import Base
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.services.customer_intelligence_event_service import CustomerIntelligenceEvent, CustomerIntelligenceSource
from app.services.customer_intelligence_run_service import (
    CustomerIntelligenceRunClaimStatus,
    CustomerIntelligenceRunInput,
    CustomerIntelligenceRunLeaseMutationStatus,
    customer_intelligence_run_service,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ANN001, ANN003
    return "INTEGER"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CustomerIntelligenceRun.__table__])
    Session = sessionmaker(bind=engine)
    return Session()


def _event(
    *,
    event_key: str = "event-1",
    team_id: int = 2,
    customer_id: int = 101,
    request_id: str = "request-1",
) -> CustomerIntelligenceEvent:
    return CustomerIntelligenceEvent(
        event_key=event_key,
        trigger_type="manual_refresh_requested",
        tenant_id=team_id,
        team_id=team_id,
        customer_id=customer_id,
        occurred_at=datetime(2026, 8, 2, 10, 0, 0),
        source=CustomerIntelligenceSource(source_type="manual_refresh", source_object_id=request_id),
        actor_id="9",
    )


def _input(**kwargs) -> CustomerIntelligenceRunInput:  # noqa: ANN003
    request_id = str(kwargs.pop("request_id", "request-1"))
    max_attempts = int(kwargs.pop("max_attempts", 3))
    return CustomerIntelligenceRunInput(
        request_id=request_id,
        event=_event(request_id=request_id, **kwargs),
        scope="brief",
        max_attempts=max_attempts,
    )


def test_pending_run_is_claimed_once_and_live_lease_is_busy():
    db = _session()
    run_input = _input()
    now = datetime(2026, 8, 2, 10, 0, 0)

    first = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now, lease_seconds=120)
    second = customer_intelligence_run_service.claim_for_execution(
        db,
        run_input,
        now=now + timedelta(seconds=30),
        lease_seconds=120,
    )

    assert first.status == CustomerIntelligenceRunClaimStatus.CLAIMED
    assert first.lease_token
    assert first.run.attempt_count == 1
    assert second.status == CustomerIntelligenceRunClaimStatus.BUSY
    assert second.lease_token is None
    assert second.run.attempt_count == 1


def test_expired_running_lease_is_reclaimed_with_new_token():
    db = _session()
    run_input = _input()
    now = datetime(2026, 8, 2, 10, 0, 0)
    first = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now, lease_seconds=30)

    reclaimed = customer_intelligence_run_service.claim_for_execution(
        db,
        run_input,
        now=now + timedelta(seconds=31),
        lease_seconds=30,
    )

    assert reclaimed.status == CustomerIntelligenceRunClaimStatus.CLAIMED
    assert reclaimed.lease_token != first.lease_token
    assert reclaimed.run.attempt_count == 2


def test_terminal_run_is_never_restarted_by_ensure_or_claim():
    db = _session()
    run_input = _input()
    now = datetime(2026, 8, 2, 10, 0, 0)
    claim = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now)
    completed = customer_intelligence_run_service.mark_succeeded_if_lease_owner(
        db,
        run_input,
        lease_token=str(claim.lease_token),
        result={
            "route": "refresh_brief",
            "event": {"event_key": "event-1"},
            "visible_trace": [{"title": "提炼客户事实", "content": "提炼出 6 条可沉淀事实"}],
        },
        finished_at=now + timedelta(seconds=2),
    )
    customer_intelligence_run_service.ensure_pending(db, run_input)
    terminal = customer_intelligence_run_service.claim_for_execution(
        db,
        run_input,
        now=now + timedelta(minutes=5),
    )

    assert completed.status == CustomerIntelligenceRunLeaseMutationStatus.APPLIED
    assert terminal.status == CustomerIntelligenceRunClaimStatus.TERMINAL
    assert terminal.run.status == CustomerIntelligenceRunStatus.SUCCESS
    assert terminal.run.attempt_count == 1
    assert terminal.run.visible_trace_json[0]["title"] == "提炼客户事实"


def test_stale_lease_cannot_overwrite_new_owner_success():
    db = _session()
    run_input = _input()
    now = datetime(2026, 8, 2, 10, 0, 0)
    stale = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now, lease_seconds=30)
    owner = customer_intelligence_run_service.claim_for_execution(
        db,
        run_input,
        now=now + timedelta(seconds=31),
        lease_seconds=30,
    )

    stale_result = customer_intelligence_run_service.mark_succeeded_if_lease_owner(
        db,
        run_input,
        lease_token=str(stale.lease_token),
        result={"route": "stale"},
        finished_at=now + timedelta(seconds=32),
    )
    owner_result = customer_intelligence_run_service.mark_succeeded_if_lease_owner(
        db,
        run_input,
        lease_token=str(owner.lease_token),
        result={"route": "refresh_brief"},
        finished_at=now + timedelta(seconds=33),
    )

    assert stale_result.status == CustomerIntelligenceRunLeaseMutationStatus.STALE_LEASE
    assert owner_result.status == CustomerIntelligenceRunLeaseMutationStatus.APPLIED
    assert owner_result.run.route == "refresh_brief"


def test_failure_schedules_retry_then_exhaustion_becomes_terminal():
    db = _session()
    run_input = _input(max_attempts=2)
    now = datetime(2026, 8, 2, 10, 0, 0)
    first = customer_intelligence_run_service.claim_for_execution(db, run_input, now=now)
    failed = customer_intelligence_run_service.mark_failed_if_lease_owner(
        db,
        run_input,
        lease_token=str(first.lease_token),
        error_message="graph failed",
        finished_at=now + timedelta(seconds=1),
    )
    second = customer_intelligence_run_service.claim_for_execution(
        db,
        run_input,
        now=failed.run.next_retry_at,
    )
    failed_again = customer_intelligence_run_service.mark_failed_if_lease_owner(
        db,
        run_input,
        lease_token=str(second.lease_token),
        error_message="graph failed again",
        finished_at=now + timedelta(minutes=2),
    )
    terminal = customer_intelligence_run_service.claim_for_execution(
        db,
        run_input,
        now=now + timedelta(minutes=3),
    )

    assert second.status == CustomerIntelligenceRunClaimStatus.CLAIMED
    assert failed_again.run.status == CustomerIntelligenceRunStatus.FAILED
    assert terminal.status == CustomerIntelligenceRunClaimStatus.TERMINAL


def test_list_due_excludes_live_leases_and_other_teams():
    db = _session()
    now = datetime(2026, 8, 2, 10, 0, 0)
    pending = _input(request_id="pending", event_key="pending")
    live = _input(request_id="live", event_key="live")
    expired = _input(request_id="expired", event_key="expired")
    other = _input(request_id="other", event_key="other", team_id=3, customer_id=303)
    customer_intelligence_run_service.ensure_pending(db, pending)
    customer_intelligence_run_service.claim_for_execution(db, live, now=now, lease_seconds=120)
    customer_intelligence_run_service.claim_for_execution(db, expired, now=now, lease_seconds=30)
    customer_intelligence_run_service.ensure_pending(db, other)

    due = customer_intelligence_run_service.list_due(
        db,
        now=now + timedelta(seconds=31),
        team_id=2,
    )

    assert [run.request_id for run in due] == ["pending", "expired"]


def test_request_lookup_is_tenant_scoped():
    db = _session()
    customer_intelligence_run_service.ensure_pending(db, _input(request_id="shared", team_id=2, event_key="a"))
    customer_intelligence_run_service.ensure_pending(db, _input(request_id="shared", team_id=3, event_key="b"))

    assert customer_intelligence_run_service.get_by_request_id(db, team_id=2, request_id="shared").team_id == 2
    assert customer_intelligence_run_service.get_by_request_id(db, team_id=4, request_id="shared") is None


def test_lease_mutation_cannot_lock_cross_team_row_even_with_same_run_key():
    db = _session()
    run_input = _input(team_id=2)
    run_key = customer_intelligence_run_service.run_key(run_input)
    cross_team_run = CustomerIntelligenceRun(
        run_key=run_key,
        request_id=run_input.request_id,
        event_key=run_input.event.event_key,
        event_json=run_input.event.to_dict(),
        tenant_id=3,
        team_id=3,
        customer_id=303,
        trigger_type=run_input.event.trigger_type,
        scope=run_input.scope,
        status=CustomerIntelligenceRunStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
        lease_token="cross-team-lease",
    )
    db.add(cross_team_run)
    db.commit()

    with pytest.raises(NoResultFound):
        customer_intelligence_run_service.mark_succeeded_if_lease_owner(
            db,
            run_input,
            lease_token="cross-team-lease",
            result={"route": "should-not-apply"},
        )

    db.refresh(cross_team_run)
    assert cross_team_run.team_id == 3
    assert cross_team_run.status == CustomerIntelligenceRunStatus.RUNNING
    assert cross_team_run.route is None
