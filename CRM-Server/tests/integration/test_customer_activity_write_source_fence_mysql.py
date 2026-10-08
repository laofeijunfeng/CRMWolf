"""Activity deletion routes legacy work from the current source under MySQL RR."""

from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.sales_commitment import FollowUpTaskProjectionRun
from app.models.team import Team
from app.services.customer_activity_write_service import CustomerActivityWriteService

pytestmark = pytest.mark.integration


def _isolated_mysql() -> bool:
    url = engine.url
    return (
        os.getenv("RUN_MYSQL_INTEGRATION") == "1"
        and url.drivername == "mysql+pymysql"
        and url.username == "root"
        and url.password == "assistant-test-only"
        and url.host == "127.0.0.1"
        and url.port == 3308
        and url.database == "crm_assistant_acceptance"
    )


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
@pytest.mark.parametrize("initial,current", [("FORM", "ASSISTANT_2"), ("ASSISTANT_2", "FORM")])
def test_delete_routes_projection_and_refresh_from_current_activity_source(initial: str, current: str) -> None:
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"ACTIVITY_SERVICE_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(team_id=team.id, account_name=f"Activity service {suffix}", city="深圳", creator_id="990126011")
        seed.add(customer)
        seed.flush()
        activity = CustomerActivity(
            team_id=team.id, customer_id=customer.id, activity_kind="PHONE_CALL",
            source_content="可归因的活动原文", occurred_at=datetime(2026, 9, 30, 10),
            creator_id="990126011", owner_id="990126011", submission_source=initial,
            submission_id=f"activity-{suffix}", submission_fingerprint="a" * 64,
        )
        seed.add(activity)
        seed.flush()
        seed.add(CustomerLegacySourceProgress(team_id=team.id, customer_id=customer.id))
        seed.commit()
        team_id, customer_id, activity_id = team.id, customer.id, activity.id

    try:
        with SessionLocal() as stale, SessionLocal() as editor:
            assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
            cached = stale.query(CustomerActivity).filter_by(team_id=team_id, id=activity_id).one()
            assert cached.submission_source == initial
            editor.execute(
                text("UPDATE crm_customer_activities SET submission_source=:source WHERE id=:activity AND team_id=:team"),
                {"source": current, "activity": activity_id, "team": team_id},
            )
            editor.commit()
            assert cached.submission_source == initial

            result = CustomerActivityWriteService().delete(stale, activity=cached, actor_id="990126011")
            assert (result.customer_intelligence_request is not None) == (current == "FORM")

        with SessionLocal() as check:
            assert check.query(CustomerActivity).filter_by(team_id=team_id, id=activity_id).one_or_none() is None
            tombstone = check.query(CustomerActivityDeletionTombstone).filter_by(
                team_id=team_id, activity_id=activity_id,
            ).one()
            assert tombstone.submission_source == current
            progress = check.query(CustomerLegacySourceProgress).filter_by(team_id=team_id, customer_id=customer_id).one()
            expected = int(current == "FORM")
            assert (progress.eligible_revision, progress.deletion_revision) == (expected, expected)
            assert check.query(FollowUpTaskProjectionRun).filter_by(team_id=team_id).count() == expected
    finally:
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "activity": activity_id}
            cleanup.execute(text("DELETE FROM crm_customer_intelligence_runs WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_profile_current WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_follow_up_task_projection_runs WHERE team_id=:team"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activity_deletion_tombstones WHERE team_id=:team AND activity_id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customer_vector_documents WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activities WHERE team_id=:team AND id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()
