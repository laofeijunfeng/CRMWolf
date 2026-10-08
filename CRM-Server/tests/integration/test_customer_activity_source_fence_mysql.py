"""Current activity origin, not an RR-stale ORM object, controls legacy progress."""

from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.core.database import SessionLocal, engine
from app.crud.customer_activity import customer_activity_crud
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.customer_vector_document import CustomerVectorDocument
from app.models.team import Team

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


def _finalize(db, activity: CustomerActivity) -> None:
    customer_activity_crud.apply_finalization(
        db, activity, title="已整理", content_json={"content": "已整理"}, summary="已整理",
        next_action=None, next_action_source=None, next_follow_time=None,
        next_follow_time_source=None, effectiveness_score=90, effectiveness_is_valid=True,
        effectiveness_reason="已核验", effectiveness_detail_json=None,
        increment_revision=True, commit=False,
    )


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
@pytest.mark.parametrize("action,initial,current", [
    ("finalize", "FORM", "ASSISTANT_2"),
    ("finalize", "ASSISTANT_2", "FORM"),
    ("delete", "FORM", "ASSISTANT_2"),
    ("delete", "ASSISTANT_2", "FORM"),
])
def test_activity_origin_changed_after_repeatable_read_uses_current_source(
    action: str, initial: str, current: str,
) -> None:
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"ACTIVITY_ORIGIN_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(team_id=team.id, account_name=f"Activity origin {suffix}", city="深圳", creator_id="990126011")
        seed.add(customer)
        seed.flush()
        activity = CustomerActivity(
            team_id=team.id, customer_id=customer.id, activity_kind="PHONE_CALL",
            source_content="真实原文", occurred_at=datetime(2026, 9, 30, 10),
            creator_id="990126011", owner_id="990126011", submission_source=initial,
            submission_id=f"activity-{suffix}", submission_fingerprint="a" * 64,
        )
        seed.add(activity)
        seed.flush()
        progress = CustomerLegacySourceProgress(team_id=team.id, customer_id=customer.id)
        seed.add(progress)
        seed.commit()
        team_id, customer_id, activity_id = team.id, customer.id, activity.id

    try:
        with SessionLocal() as stale, SessionLocal() as updater:
            assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
            preloaded = stale.query(CustomerActivity).filter_by(id=activity_id, team_id=team_id).one()
            assert preloaded.submission_source == initial
            updater.execute(
                text("UPDATE crm_customer_activities SET submission_source=:source WHERE id=:activity AND team_id=:team"),
                {"source": current, "activity": activity_id, "team": team_id},
            )
            updater.commit()
            assert preloaded.submission_source == initial  # The identity map remains stale.

            if action == "delete":
                customer_activity_crud.delete(stale, preloaded, commit=False, deleted_by="990126011")
            else:
                _finalize(stale, preloaded)
            stale.commit()

        with SessionLocal() as check:
            revision, deletions = check.query(
                CustomerLegacySourceProgress.eligible_revision,
                CustomerLegacySourceProgress.deletion_revision,
            ).filter_by(team_id=team_id, customer_id=customer_id).one()
            expected = int(current == "FORM")
            assert (revision, deletions) == (expected, expected if action == "delete" else 0)
            if action == "delete":
                tombstone = check.query(CustomerActivityDeletionTombstone).filter_by(
                    team_id=team_id, activity_id=activity_id,
                ).one()
                assert tombstone.customer_id == customer_id
                assert tombstone.submission_source == current
                assert check.query(CustomerActivity).filter_by(id=activity_id).one_or_none() is None
            else:
                actual = check.query(CustomerActivity).filter_by(id=activity_id).one()
                assert actual.submission_source == current
                assert actual.summary == "已整理"
    finally:
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "activity": activity_id}
            cleanup.execute(text("DELETE FROM crm_customer_activity_deletion_tombstones WHERE team_id=:team AND activity_id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customer_vector_documents WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activities WHERE team_id=:team AND id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
@pytest.mark.parametrize("action", ["finalize", "delete"])
def test_activity_moved_after_preload_rejects_stale_customer_identity(action: str) -> None:
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"ACTIVITY_MOVE_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        first = Customer(team_id=team.id, account_name=f"Activity old {suffix}", city="深圳", creator_id="990126011")
        second = Customer(team_id=team.id, account_name=f"Activity new {suffix}", city="深圳", creator_id="990126011")
        seed.add_all([first, second])
        seed.flush()
        activity = CustomerActivity(
            team_id=team.id, customer_id=first.id, activity_kind="PHONE_CALL",
            source_content="真实原文", occurred_at=datetime(2026, 9, 30, 10),
            creator_id="990126011", owner_id="990126011", submission_source="FORM",
        )
        seed.add(activity)
        seed.commit()
        team_id, first_id, second_id, activity_id = team.id, first.id, second.id, activity.id

    try:
        with SessionLocal() as stale, SessionLocal() as updater:
            preloaded = stale.query(CustomerActivity).filter_by(id=activity_id, team_id=team_id).one()
            assert preloaded.customer_id == first_id
            updater.execute(
                text("UPDATE crm_customer_activities SET customer_id=:new WHERE id=:activity AND team_id=:team"),
                {"new": second_id, "activity": activity_id, "team": team_id},
            )
            updater.commit()
            with pytest.raises(ValueError, match="客户活动.*(客户|归属).*(变化|一致)|客户活动归属已变化"):
                if action == "delete":
                    customer_activity_crud.delete(stale, preloaded, commit=False)
                else:
                    _finalize(stale, preloaded)
            stale.rollback()

        with SessionLocal() as check:
            actual = check.query(CustomerActivity).filter_by(id=activity_id).one()
            assert actual.customer_id == second_id and actual.summary is None
            assert check.query(CustomerLegacySourceProgress).filter_by(team_id=team_id).count() == 0
            assert check.query(CustomerActivityDeletionTombstone).filter_by(team_id=team_id).count() == 0
    finally:
        with SessionLocal() as cleanup:
            params = {"team": team_id, "first": first_id, "second": second_id, "activity": activity_id}
            cleanup.execute(text("DELETE FROM crm_customer_vector_documents WHERE team_id=:team AND source_object_id=:activity"),
                            {"team": team_id, "activity": str(activity_id)})
            cleanup.execute(text("DELETE FROM crm_customer_activity_deletion_tombstones WHERE team_id=:team AND activity_id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id IN (:first, :second)"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activities WHERE team_id=:team AND id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id IN (:first, :second)"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_activity_delete_with_vector_evidence_does_not_commit_progress_early() -> None:
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"ACTIVITY_DELETE_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(team_id=team.id, account_name=f"Activity delete {suffix}", city="深圳", creator_id="990126011")
        seed.add(customer)
        seed.flush()
        activity = CustomerActivity(
            team_id=team.id, customer_id=customer.id, activity_kind="PHONE_CALL",
            source_content="真实原文", occurred_at=datetime(2026, 9, 30, 10),
            creator_id="990126011", owner_id="990126011", submission_source="FORM",
        )
        seed.add(activity)
        seed.flush()
        seed.add(CustomerLegacySourceProgress(team_id=team.id, customer_id=customer.id))
        seed.add(CustomerVectorDocument(
            team_id=team.id, tenant_id=team.id, customer_id=customer.id,
            document_key=uuid4().hex, qdrant_point_id=uuid4().hex,
            source_type="follow_up", source_object_id=str(activity.id),
            title="真实活动", text="真实原文", text_hash="a" * 64,
        ))
        seed.commit()
        team_id, customer_id, activity_id = team.id, customer.id, activity.id

    try:
        with SessionLocal() as deleting:
            loaded = deleting.query(CustomerActivity).filter_by(id=activity_id).one()
            customer_activity_crud.delete(deleting, loaded, commit=False)
            deleting.rollback()
        with SessionLocal() as check:
            assert check.query(CustomerActivity).filter_by(id=activity_id).one_or_none() is not None
            assert check.query(CustomerActivityDeletionTombstone).filter_by(team_id=team_id, activity_id=activity_id).one_or_none() is None
            progress = check.query(CustomerLegacySourceProgress).filter_by(team_id=team_id, customer_id=customer_id).one()
            assert (progress.eligible_revision, progress.deletion_revision) == (0, 0)
            evidence = check.query(CustomerVectorDocument).filter_by(
                team_id=team_id, source_type="follow_up", source_object_id=str(activity_id),
            ).one()
            assert evidence.sync_status == "PENDING"
    finally:
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "activity": activity_id}
            cleanup.execute(text("DELETE FROM crm_customer_activity_deletion_tombstones WHERE team_id=:team AND activity_id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customer_vector_documents WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activities WHERE team_id=:team AND id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


@pytest.mark.skipif(not _isolated_mysql(), reason="requires isolated acceptance MySQL")
def test_vector_metadata_projection_failure_rolls_back_activity_tombstone_and_eligible_progress() -> None:
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"ACTIVITY_VECTOR_FAIL_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(team_id=team.id, account_name=f"Activity vector failure {suffix}", city="深圳", creator_id="990126011")
        seed.add(customer)
        seed.flush()
        activity = CustomerActivity(
            team_id=team.id, customer_id=customer.id, activity_kind="PHONE_CALL",
            source_content="真实原文", occurred_at=datetime(2026, 9, 30, 10),
            creator_id="990126011", owner_id="990126011", submission_source="FORM",
        )
        seed.add(activity)
        seed.flush()
        seed.add(CustomerLegacySourceProgress(team_id=team.id, customer_id=customer.id))
        seed.add(CustomerVectorDocument(
            team_id=team.id, tenant_id=team.id, customer_id=customer.id,
            document_key=uuid4().hex, qdrant_point_id=uuid4().hex,
            source_type="follow_up", source_object_id=str(activity.id),
            title="真实活动", text="真实原文", text_hash="a" * 64,
        ))
        seed.commit()
        team_id, customer_id, activity_id = team.id, customer.id, activity.id

    attempted_vector_projection = False

    def fail_vector_projection(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        nonlocal attempted_vector_projection
        if statement.lstrip().upper().startswith("SELECT ") and "FROM CRM_CUSTOMER_VECTOR_DOCUMENTS" in statement.upper():
            attempted_vector_projection = True
            raise RuntimeError("injected vector metadata projection failure")

    try:
        event.listen(engine, "before_cursor_execute", fail_vector_projection)
        try:
            failure = None
            with SessionLocal() as deleting:
                loaded = deleting.query(CustomerActivity).filter_by(id=activity_id).one()
                try:
                    customer_activity_crud.delete(deleting, loaded, commit=False)
                    # A caller committing an apparently successful delete must not
                    # persist source progress while the vector evidence stays live.
                    deleting.commit()
                except RuntimeError as exc:
                    failure = exc
                    deleting.rollback()
        finally:
            event.remove(engine, "before_cursor_execute", fail_vector_projection)

        with SessionLocal() as check:
            activity_exists = check.query(CustomerActivity).filter_by(id=activity_id).one_or_none() is not None
            tombstone_exists = check.query(CustomerActivityDeletionTombstone).filter_by(
                team_id=team_id, activity_id=activity_id,
            ).one_or_none() is not None
            progress = check.query(CustomerLegacySourceProgress).filter_by(team_id=team_id, customer_id=customer_id).one()
            evidence = check.query(CustomerVectorDocument).filter_by(
                team_id=team_id, source_type="follow_up", source_object_id=str(activity_id),
            ).one()
            assert (
                activity_exists, tombstone_exists,
                progress.eligible_revision, progress.deletion_revision, evidence.sync_status,
            ) == (True, False, 0, 0, "PENDING")
        assert attempted_vector_projection
        assert failure is not None and str(failure) == "injected vector metadata projection failure"
    finally:
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id, "activity": activity_id}
            cleanup.execute(text("DELETE FROM crm_customer_activity_deletion_tombstones WHERE team_id=:team AND activity_id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customer_vector_documents WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"), params)
            cleanup.execute(text("DELETE FROM crm_customer_activities WHERE team_id=:team AND id=:activity"), params)
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()
