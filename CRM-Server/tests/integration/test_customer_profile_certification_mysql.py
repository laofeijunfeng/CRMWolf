"""MySQL publication fences certify a version, not a matching source hash or stale session."""

from __future__ import annotations

import json
import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.api.customer_profiles import _readable_version
from app.core.database import SessionLocal, engine
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.team import Team
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.customer_profile_projection_service import (
    CustomerProfileProjectionError,
    CustomerProfileProjectionService,
)
from app.services.customer_profile_version_certification import is_certified_profile_version
from app.services.legacy_profile_source import advance_eligible_progress, lock_source_customer

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
        and not url.query
    )


@pytest.fixture
def profile_case():
    if not _isolated_mysql():
        pytest.skip("requires the exact isolated acceptance MySQL DSN")
    suffix = uuid4().hex
    with SessionLocal() as seed:
        team = Team(name=f"PROFILE_CERT_{suffix[:12]}", code=suffix[:12], owner_id=990126011)
        seed.add(team)
        seed.flush()
        customer = Customer(
            team_id=team.id,
            account_name=f"Profile certification {suffix}",
            city="广州",
            creator_id="990126011",
        )
        seed.add(customer)
        seed.flush()
        activity = CustomerActivity(
            team_id=team.id,
            customer_id=customer.id,
            activity_kind="PHONE_FOLLOW_UP",
            title="旧版电话跟进",
            source_content="客户正在筹备旧版试用",
            summary="旧版试用准备中",
            occurred_at=datetime(2026, 9, 1, 10),
            creator_id="990126011",
            owner_id="990126011",
            submission_source="FORM",
        )
        seed.add(activity)
        seed.flush()
        team_id, customer_id, activity_id = team.id, customer.id, activity.id
        seed.commit()
    try:
        yield team_id, customer_id, activity_id
    finally:
        # Only rows attached to this freshly generated team/customer are disposable.
        with SessionLocal() as cleanup:
            params = {"team": team_id, "customer": customer_id}
            cleanup.execute(
                text("DELETE FROM crm_customer_profile_current WHERE team_id=:team AND customer_id=:customer"), params
            )
            cleanup.execute(
                text(
                    "DELETE FROM crm_customer_profile_projection_versions WHERE team_id=:team AND customer_id=:customer"
                ),
                params,
            )
            cleanup.execute(
                text("DELETE FROM crm_customer_intelligence_runs WHERE team_id=:team AND customer_id=:customer"), params
            )
            cleanup.execute(
                text("DELETE FROM crm_customer_vector_documents WHERE team_id=:team AND customer_id=:customer"), params
            )
            cleanup.execute(
                text("DELETE FROM crm_customer_deal_journey_events WHERE team_id=:team AND customer_id=:customer"),
                params,
            )
            cleanup.execute(
                text("DELETE FROM crm_customer_legacy_source_progress WHERE team_id=:team AND customer_id=:customer"),
                params,
            )
            cleanup.execute(
                text("DELETE FROM crm_customer_activities WHERE team_id=:team AND customer_id=:customer"), params
            )
            cleanup.execute(
                text("DELETE FROM crm_customer_deal_journeys WHERE team_id=:team AND customer_id=:customer"), params
            )
            cleanup.execute(text("DELETE FROM crm_customers WHERE team_id=:team AND id=:customer"), params)
            cleanup.execute(text("DELETE FROM teams WHERE id=:team"), params)
            cleanup.commit()


def _context(db, team_id: int, customer_id: int):
    return CustomerIntelligenceContextService().build_context(
        db,
        team_id=team_id,
        customer_id=customer_id,
        query_text="",
        evidence_limit=0,
    )


def _draft(db, team_id: int, customer_id: int):
    return CustomerProfileProjectionService().draft_from_context(
        context=_context(db, team_id, customer_id).to_dict(),
        source_event_key=None,
    )


def _change_legacy_activity(db, *, team_id: int, customer_id: int, activity_id: int) -> None:
    lock_source_customer(db, team_id=team_id, customer_id=customer_id)
    activity = (
        db.query(CustomerActivity)
        .filter_by(
            team_id=team_id,
            customer_id=customer_id,
            id=activity_id,
        )
        .one()
    )
    activity.source_content = "客户已批准新版试用"
    activity.summary = "新版试用已获批准"
    activity.activity_revision += 1
    advance_eligible_progress(db, team_id=team_id, customer_id=customer_id)
    db.commit()


def _versions(db, team_id: int, customer_id: int):
    return (
        db.query(CustomerProfileProjectionVersion)
        .filter_by(
            team_id=team_id,
            customer_id=customer_id,
        )
        .order_by(CustomerProfileProjectionVersion.profile_version)
        .all()
    )


def test_equal_hash_legacy_version_remains_uncertified_when_new_version_is_published(profile_case) -> None:
    team_id, customer_id, _ = profile_case
    service = CustomerProfileProjectionService()
    with SessionLocal() as seed:
        # The old physical row has the exact content and source snapshot of the
        # candidate, but lacks the publisher's per-version attestation/domain.
        original = service.publish(
            seed, team_id=team_id, customer_id=customer_id, draft=_draft(seed, team_id, customer_id)
        ).version
        seed.commit()
        old_id = original.id
        original.source_attestation_json = None
        original.source_discriminator = None
        seed.commit()
    with SessionLocal() as before:
        current = before.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        old = before.query(CustomerProfileProjectionVersion).filter_by(id=old_id).one()
        assert not is_certified_profile_version(old)
        assert _readable_version(team_id=team_id, customer_id=customer_id, current=current, version=old) is None
    with SessionLocal() as publisher:
        publication = service.publish(
            publisher, team_id=team_id, customer_id=customer_id, draft=_draft(publisher, team_id, customer_id)
        )
        assert not publication.deduplicated
        publisher.commit()
        new_id = publication.version.id
    with SessionLocal() as check:
        old, new = _versions(check, team_id, customer_id)
        current = check.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        assert old.id == old_id and new.id == new_id and old.id != new.id
        assert old.content_hash == new.content_hash
        assert old.source_watermark_hash == new.source_watermark_hash
        assert old.source_watermark_json == new.source_watermark_json
        assert old.source_attestation_json is None and old.source_discriminator is None
        assert not is_certified_profile_version(old)
        assert is_certified_profile_version(new)
        assert current.current_profile_version_id == new.id
        assert _readable_version(team_id=team_id, customer_id=customer_id, current=current, version=old) is None
        assert _readable_version(team_id=team_id, customer_id=customer_id, current=current, version=new) is new


def test_source_change_between_draft_and_publish_rejects_stale_draft_under_mysql_rr(profile_case) -> None:
    team_id, customer_id, activity_id = profile_case
    service = CustomerProfileProjectionService()
    with SessionLocal() as stale, SessionLocal() as writer:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        old_activity = stale.query(CustomerActivity).filter_by(id=activity_id, team_id=team_id).one()
        old_draft = _draft(stale, team_id, customer_id)
        old_hash = old_draft.source_watermark["source_snapshot_hash"]
        _change_legacy_activity(writer, team_id=team_id, customer_id=customer_id, activity_id=activity_id)
        assert old_activity.summary == "旧版试用准备中"  # Stale identity map and RR snapshot survive the commit.
        with pytest.raises(CustomerProfileProjectionError) as exc:
            service.publish(stale, team_id=team_id, customer_id=customer_id, draft=old_draft)
        assert exc.value.code == "PROFILE_PUBLISH_REJECTED_STALE"
        stale.rollback()
    with SessionLocal() as check:
        assert _draft(check, team_id, customer_id).source_watermark["source_snapshot_hash"] != old_hash
        assert _versions(check, team_id, customer_id) == []
        assert (
            check.query(CustomerProfileCurrent)
            .filter_by(
                team_id=team_id,
                customer_id=customer_id,
            )
            .one_or_none()
            is None
        )


def test_preloaded_mysql_rr_session_publishes_fresh_draft_not_stale_identity_map(profile_case) -> None:
    team_id, customer_id, activity_id = profile_case
    service = CustomerProfileProjectionService()
    with SessionLocal() as stale, SessionLocal() as writer:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        cached_activity = stale.query(CustomerActivity).filter_by(id=activity_id, team_id=team_id).one()
        old_draft = _draft(stale, team_id, customer_id)
        _change_legacy_activity(writer, team_id=team_id, customer_id=customer_id, activity_id=activity_id)
        with SessionLocal() as fresh:
            candidate = _draft(fresh, team_id, customer_id)
        assert cached_activity.summary == "旧版试用准备中"
        assert candidate.source_watermark["source_snapshot_hash"] != old_draft.source_watermark["source_snapshot_hash"]
        publication = service.publish(stale, team_id=team_id, customer_id=customer_id, draft=candidate)
        stale.commit()
        version_id = publication.version.id
    with SessionLocal() as check:
        version = check.query(CustomerProfileProjectionVersion).filter_by(id=version_id, team_id=team_id).one()
        assert is_certified_profile_version(version)
        assert version.source_watermark_json == {
            **candidate.source_watermark, "source_provenance_status": "VERIFIED"
        }
        assert "新版试用已获批准" in json.dumps(version.follow_up_process_json, ensure_ascii=False)
        assert "旧版试用准备中" not in json.dumps(version.follow_up_process_json, ensure_ascii=False)
        assert len(_versions(check, team_id, customer_id)) == 1


def test_assistant2_shared_journey_aggregate_change_cannot_enter_legacy_certificate(profile_case) -> None:
    team_id, customer_id, activity_id = profile_case
    service = CustomerProfileProjectionService()
    with SessionLocal() as seed:
        journey = CustomerDealJourney(team_id=team_id, customer_id=customer_id, name="旧版业务旅程")
        seed.add(journey)
        seed.flush()
        seed.add(
            CustomerDealJourneyEvent(
                team_id=team_id,
                customer_id=customer_id,
                deal_journey_id=journey.id,
                event_type="activity_added",
                event_time=datetime(2026, 9, 1, 10),
                source_type="customer_activity",
                source_id=activity_id,
                summary="旧版合法跟进",
            )
        )
        seed.commit()
        journey_id = journey.id
    with SessionLocal() as initial:
        baseline = _draft(initial, team_id, customer_id)
        first = service.publish(initial, team_id=team_id, customer_id=customer_id, draft=baseline)
        initial.commit()
        version_id = first.version.id
    private_text = "Assistant 2 私有活动不得进入旧版档案"
    with SessionLocal() as assistant:
        assistant_activity = CustomerActivity(
            team_id=team_id,
            customer_id=customer_id,
            deal_journey_id=journey_id,
            activity_kind="PHONE_FOLLOW_UP",
            title=private_text,
            source_content=private_text,
            summary=private_text,
            occurred_at=datetime(2026, 9, 2, 10),
            creator_id="990126011",
            owner_id="990126011",
            submission_source="ASSISTANT_2",
            submission_id=f"profile-private-{uuid4().hex}",
            submission_fingerprint="a" * 64,
        )
        assistant.add(assistant_activity)
        assistant.flush()
        private_id = assistant_activity.id
        assistant.add(
            CustomerDealJourneyEvent(
                team_id=team_id,
                customer_id=customer_id,
                deal_journey_id=journey_id,
                event_type="activity_added",
                event_time=datetime(2026, 9, 2, 10),
                source_type="customer_activity",
                source_id=private_id,
                summary=private_text,
            )
        )
        shared_journey = assistant.query(CustomerDealJourney).filter_by(id=journey_id, team_id=team_id).one()
        shared_journey.last_event_at = datetime(2026, 9, 2, 10)
        assistant.commit()
    with SessionLocal() as after:
        journey = after.query(CustomerDealJourney).filter_by(id=journey_id, team_id=team_id).one()
        assert journey.last_event_at == datetime(2026, 9, 2, 10)  # Shared aggregate really did advance.
        assert (
            after.query(CustomerDealJourneyEvent)
            .filter_by(
                team_id=team_id,
                customer_id=customer_id,
                deal_journey_id=journey_id,
            )
            .count()
            == 2
        )
        assert (
            after.query(CustomerActivity).filter_by(id=private_id, team_id=team_id).one().submission_source
            == "ASSISTANT_2"
        )
        candidate = _draft(after, team_id, customer_id)
        assert candidate.source_watermark == {
            **baseline.source_watermark, "source_provenance_status": "VERIFIED"
        }
        assert candidate.sections.model_dump(mode="json") == baseline.sections.model_dump(mode="json")
        assert candidate.evidence_refs == baseline.evidence_refs
        replay = service.publish(after, team_id=team_id, customer_id=customer_id, draft=candidate)
        after.commit()
        assert replay.deduplicated and replay.version.id == version_id
    with SessionLocal() as check:
        version = check.query(CustomerProfileProjectionVersion).filter_by(id=version_id, team_id=team_id).one()
        assert is_certified_profile_version(version)
        assert len(_versions(check, team_id, customer_id)) == 1
        assert version.source_watermark_json == {
            **baseline.source_watermark, "source_provenance_status": "VERIFIED"
        }
        body = json.dumps(
            {
                "current": version.current_situation_json,
                "journeys": version.current_journeys_json,
                "changes": version.important_changes_json,
                "long_term": version.long_term_context_json,
                "process": version.follow_up_process_json,
                "follow_ups": version.recorded_follow_ups_json,
                "evidence": version.evidence_refs_json,
            },
            ensure_ascii=False,
        )
        assert private_text not in body
        assert f"activity:{private_id}" not in body
