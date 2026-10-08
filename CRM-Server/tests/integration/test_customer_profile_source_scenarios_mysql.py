"""Committed MySQL source scenarios for the legacy customer-profile publication boundary."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.core.database import SessionLocal, engine
from app.api import customer_profiles
from app.crud.customer_activity import customer_activity_crud
from app.crud.opportunity import opportunity_crud
from app.crud.sales_commitment import follow_up_task_crud
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_fact import CustomerFact, CustomerFactSource
from app.models.customer_intelligence_run import CustomerIntelligenceRun, CustomerIntelligenceRunStatus
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.opportunity import Opportunity
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.models.team import Team
from app.schemas.customer_activity import CustomerActivityCreate
from app.services.customer_fact_service import CustomerFactInput, CustomerFactService, CustomerFactSourceInput
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.customer_intelligence_reconciliation_service import CustomerIntelligenceReconciliationService
from app.services.deal_journey_service import deal_journey_service
from app.services.customer_profile_evidence_resolver import CustomerProfileEvidenceResolver
from app.services.customer_profile_projection_service import CustomerProfileProjectionError, CustomerProfileProjectionService
from app.services.customer_profile_version_certification import is_certified_profile_version
from app.services.legacy_profile_source import activity_origin, advance_eligible_progress, follow_up_origin, source_origin

pytestmark = pytest.mark.integration
ACTOR = "990126011"
T1 = datetime(2026, 9, 1, 10)
T2 = datetime(2026, 9, 2, 10)


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
def source_case():
    if not _isolated_mysql():
        pytest.skip("requires the exact isolated acceptance MySQL DSN")
    suffix = uuid4().hex
    with SessionLocal() as db:
        team = Team(name=f"SOURCE_{suffix[:12]}", code=suffix[:12], owner_id=int(ACTOR))
        db.add(team)
        db.flush()
        customer = Customer(team_id=team.id, account_name=f"Source {suffix}", city="广州", creator_id=ACTOR)
        db.add(customer)
        db.flush()
        team_id, customer_id, customer_public_id = int(team.id), int(customer.id), str(customer.public_id)
        db.commit()
    try:
        yield team_id, customer_id, customer_public_id
    finally:
        # Only this fixture's generated team is disposable. Remove non-FK source
        # artifacts explicitly, then children before parents for restrictive FKs.
        with SessionLocal() as db:
            params = {"team": team_id}
            for table in (
                "crm_customer_profile_current",
                "crm_customer_profile_projection_versions",
                "crm_customer_intelligence_runs",
                "crm_follow_up_task_events",
                "crm_follow_up_tasks",
                "crm_sales_commitments",
                "crm_customer_fact_sources",
                "crm_customer_fact_revisions",
                "crm_customer_facts",
                "crm_customer_vector_documents",
                "crm_customer_deal_journey_events",
                "crm_customer_legacy_source_progress",
                "crm_customer_activity_deletion_tombstones",
                "crm_opportunities",
                "crm_customer_activities",
                "crm_customer_deal_journeys",
                "crm_operation_logs",
            ):
                if table in {"crm_customer_fact_sources", "crm_customer_fact_revisions"}:
                    db.execute(text(f"DELETE FROM {table} WHERE fact_id IN (SELECT id FROM crm_customer_facts WHERE team_id=:team)"), params)
                else:
                    db.execute(text(f"DELETE FROM {table} WHERE team_id=:team"), params)
            db.execute(text("DELETE FROM crm_customers WHERE team_id=:team"), params)
            db.execute(text("DELETE FROM teams WHERE id=:team"), params)
            db.commit()


def _journey(db, team_id: int, customer_id: int, name: str = "既有旅程") -> CustomerDealJourney:
    row = CustomerDealJourney(team_id=team_id, customer_id=customer_id, name=name)
    db.add(row)
    db.flush()
    return row


def _activity(db, team_id: int, customer_id: int, content: str, *, source: str = "FORM", when: datetime = T1) -> CustomerActivity:
    suffix = uuid4().hex
    return customer_activity_crud.create(
        db,
        obj_in=CustomerActivityCreate(
            activity_kind="PHONE_FOLLOW_UP", source_content=content, summary=content,
            occurred_at=when,
        ),
        customer_id=customer_id,
        creator_id=ACTOR,
        team_id=team_id,
        submission_source=source,
        submission_id=f"source-{suffix}" if source == "ASSISTANT_2" else None,
        submission_fingerprint="a" * 64 if source == "ASSISTANT_2" else None,
        commit=False,
    )


def _task(db, team_id: int, customer_id: int, activity_id: int, title: str) -> FollowUpTask:
    return follow_up_task_crud.create(
        db,
        {
            "team_id": team_id, "customer_id": customer_id, "owner_id": ACTOR, "creator_id": ACTOR,
            "title": title, "due_at": T2, "source_type": "customer_activity",
            "source_key": f"activity:{activity_id}", "source_activity_id": activity_id,
            "task_hash": uuid4().hex,
        },
        commit=False,
    )


def _context(db, team_id: int, customer_id: int):
    return CustomerIntelligenceContextService().build_context(
        db, team_id=team_id, customer_id=customer_id, query_text="", evidence_limit=0,
    )


def _draft(db, team_id: int, customer_id: int, *, target_sections=None):
    return CustomerProfileProjectionService().draft_from_context(
        context=_context(db, team_id, customer_id).to_dict(), source_event_key=None,
        target_sections=target_sections,
    )


def _publish(db, team_id: int, customer_id: int, *, target_sections=None):
    service = CustomerProfileProjectionService()
    published = service.publish(
        db, team_id=team_id, customer_id=customer_id,
        draft=_draft(db, team_id, customer_id, target_sections=target_sections),
    )
    db.commit()
    return published


def _body(version: CustomerProfileProjectionVersion) -> str:
    return json.dumps(
        {
            "current": version.current_situation_json, "journeys": version.current_journeys_json,
            "changes": version.important_changes_json, "long_term": version.long_term_context_json,
            "process": version.follow_up_process_json, "follow_ups": version.recorded_follow_ups_json,
            "evidence": version.evidence_refs_json,
        },
        ensure_ascii=False,
    )


def _version_count(db, team_id: int, customer_id: int) -> int:
    return db.query(CustomerProfileProjectionVersion).filter_by(team_id=team_id, customer_id=customer_id).count()


def test_s01_assistant_activity_real_writer_commits_event_without_legacy_publication_change(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        journey = _journey(db, team_id, customer_id)
        legacy = _activity(db, team_id, customer_id, "旧版试用准备", when=T1)
        assert legacy.deal_journey_id == journey.id
        db.commit()
        journey_id = int(journey.id)
    with SessionLocal() as db:
        before = _context(db, team_id, customer_id)
        assert before.source_watermark["source_provenance_status"] == "UNVERIFIED"
        first = _publish(db, team_id, customer_id)
        first_id = int(first.version.id)
        progress_before = db.query(CustomerLegacySourceProgress).filter_by(team_id=team_id, customer_id=customer_id).one().eligible_revision
    with SessionLocal() as db:
        private = _activity(db, team_id, customer_id, "只属于 2.0 的最新跟进", source="ASSISTANT_2", when=T2)
        private_id = int(private.id)
        assert private.deal_journey_id == journey_id
        db.commit()
    with SessionLocal() as db:
        assert db.query(CustomerActivity).filter_by(team_id=team_id, customer_id=customer_id, id=private_id).one().submission_source == "ASSISTANT_2"
        event = db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, customer_id=customer_id, source_type="customer_activity", source_id=private_id).one()
        assert event.event_type == "activity_added"
        assert db.query(CustomerDealJourney).filter_by(id=journey_id, team_id=team_id).one().last_event_at == T2
        assert db.query(CustomerLegacySourceProgress).filter_by(team_id=team_id, customer_id=customer_id).one().eligible_revision == progress_before
        after = _context(db, team_id, customer_id)
        assert {k: v for k, v in after.strong_context.to_dict().items() if k != "source_watermarks"} == {
            k: v for k, v in before.strong_context.to_dict().items() if k != "source_watermarks"
        }
        assert after.source_watermark["source_provenance_status"] == "VERIFIED"
        assert {k: v for k, v in after.source_watermark.items() if k != "source_provenance_status"} == {
            k: v for k, v in before.source_watermark.items() if k != "source_provenance_status"
        }
        replay = _publish(db, team_id, customer_id)
        assert replay.deduplicated and replay.version.id == first_id
        assert _version_count(db, team_id, customer_id) == 1
        assert "只属于 2.0 的最新跟进" not in _body(replay.version)


def test_s02_mixed_journey_uses_only_eligible_event_time_and_order(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        journey = _journey(db, team_id, customer_id, "混合旅程")
        old = _activity(db, team_id, customer_id, "旧版第一次拜访", when=T1)
        old_id = int(old.id)
        assert old.deal_journey_id == journey.id
        db.commit()
        journey_id = int(journey.id)
    with SessionLocal() as db:
        private = _activity(db, team_id, customer_id, "2.0 次日拜访", source="ASSISTANT_2", when=T2)
        db.commit()
        private_id = int(private.id)
    with SessionLocal() as db:
        events = db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, deal_journey_id=journey_id).all()
        assert len(events) == 2 and {event.source_id for event in events} == {old_id, private_id}
        assert db.query(CustomerDealJourney).filter_by(team_id=team_id, id=journey_id).one().last_event_at == T2
        strong = _context(db, team_id, customer_id).strong_context
        assert [event["source_id"] for event in strong.deal_journey_events] == [old_id]
        assert len(strong.deal_journeys) == 1
        assert strong.deal_journeys[0]["last_event_at"] == T1.isoformat()
        assert strong.deal_journeys[0]["started_at"] == T1.isoformat()
        published = _publish(db, team_id, customer_id).version
        assert any(row.get("id") == journey_id for row in published.current_journeys_json)
        assert "2.0 次日拜访" not in _body(published)


def test_s03_deleted_origins_keep_legacy_task_and_exclude_assistant_task_after_set_null(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        old = _activity(db, team_id, customer_id, "旧版活动可核历史")
        private = _activity(db, team_id, customer_id, "2.0 活动不可继承", source="ASSISTANT_2")
        old_id, private_id = int(old.id), int(private.id)
        independent_origin = _activity(db, team_id, customer_id, "独立任务仍在的旧来源")
        independent_origin_id = int(independent_origin.id)
        old_task = _task(db, team_id, customer_id, old_id, "旧任务保留")
        private_task = _task(db, team_id, customer_id, private_id, "私有任务排除")
        old_commitment = SalesCommitment(
            team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
            title="旧承诺保留", content="旧承诺保留", source_type="customer_activity",
            source_key=f"activity:{old_id}", source_activity_id=old_id, commitment_hash=uuid4().hex,
        )
        private_commitment = SalesCommitment(
            team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
            title="私有承诺排除", content="私有承诺排除", source_type="customer_activity",
            source_key=f"activity:{private_id}", source_activity_id=private_id, commitment_hash=uuid4().hex,
        )
        independent_commitment = SalesCommitment(
            team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
            title="独立来源承诺", content="独立来源承诺", source_type="customer_activity",
            source_key=f"activity:{independent_origin_id}", source_activity_id=independent_origin_id,
            commitment_hash=uuid4().hex,
        )
        db.add_all([old_commitment, private_commitment, independent_commitment])
        db.flush()
        independent_task = follow_up_task_crud.create(
            db,
            {
                "team_id": team_id, "customer_id": customer_id, "owner_id": ACTOR, "creator_id": ACTOR,
                "title": "独立来源 NULL-FK 任务保留", "due_at": T2,
                "source_type": "sales_commitment", "source_key": f"commitment:{independent_commitment.id}",
                "commitment_id": int(independent_commitment.id), "task_hash": uuid4().hex,
            },
            commit=False,
        )
        assert independent_task.source_activity_id is None
        independent_task_id, independent_commitment_id = int(independent_task.id), int(independent_commitment.id)
        db.flush()
        old_commitment_id, private_commitment_id = int(old_commitment.id), int(private_commitment.id)
        old_fact = CustomerFactService().upsert_fact(db, CustomerFactInput(
            tenant_id=team_id, team_id=team_id, customer_id=customer_id,
            fact_type="risk", subject="old-deletion", content="旧事实保留", confidence=0.95,
            source=CustomerFactSourceInput(source_type="customer_activity", source_object_id=str(old_id)),
        ))
        private_fact = CustomerFactService().upsert_fact(db, CustomerFactInput(
            tenant_id=team_id, team_id=team_id, customer_id=customer_id,
            fact_type="risk", subject="private-deletion", content="私有事实排除", confidence=0.95,
            source=CustomerFactSourceInput(source_type="customer_activity", source_object_id=str(private_id)),
        ))
        old_fact_id, private_fact_id = int(old_fact.id), int(private_fact.id)
        old_task_id, private_task_id = int(old_task.id), int(private_task.id)
        db.commit()
    with SessionLocal() as db:
        before = _context(db, team_id, customer_id).source_watermark
        customer_activity_crud.delete(db, db.query(CustomerActivity).filter_by(team_id=team_id, id=old_id).one(), commit=False)
        customer_activity_crud.delete(db, db.query(CustomerActivity).filter_by(team_id=team_id, id=private_id).one(), commit=False)
        db.commit()
    with SessionLocal() as db:
        assert db.query(CustomerActivity).filter(CustomerActivity.id.in_([old_id, private_id]), CustomerActivity.team_id == team_id).count() == 0
        tombstones = db.query(CustomerActivityDeletionTombstone).filter_by(team_id=team_id, customer_id=customer_id).all()
        assert {(item.activity_id, item.submission_source) for item in tombstones} == {(old_id, "FORM"), (private_id, "ASSISTANT_2")}
        old_task = db.query(FollowUpTask).filter_by(team_id=team_id, id=old_task_id).one()
        private_task = db.query(FollowUpTask).filter_by(team_id=team_id, id=private_task_id).one()
        independent_task = db.query(FollowUpTask).filter_by(team_id=team_id, id=independent_task_id).one()
        independent_commitment = db.query(SalesCommitment).filter_by(team_id=team_id, id=independent_commitment_id).one()
        assert db.query(CustomerActivity).filter_by(team_id=team_id, id=independent_origin_id).one()
        assert independent_task.source_activity_id is None
        assert independent_task.commitment_id == independent_commitment.id
        assert independent_task.source_key == f"commitment:{independent_commitment.id}"
        assert old_task.source_activity_id is None and private_task.source_activity_id is None
        assert activity_origin(db, team_id, customer_id, old_id)
        assert not activity_origin(db, team_id, customer_id, private_id)
        assert follow_up_origin(db, old_task, team_id, customer_id)
        assert not follow_up_origin(db, private_task, team_id, customer_id)
        assert follow_up_origin(db, independent_commitment, team_id, customer_id)
        assert follow_up_origin(db, independent_task, team_id, customer_id)
        commitments = db.query(SalesCommitment).filter(SalesCommitment.id.in_([old_commitment_id, private_commitment_id])).all()
        assert all(row.source_activity_id is None for row in commitments)
        assert {row.id for row in commitments if follow_up_origin(db, row, team_id, customer_id)} == {old_commitment_id}
        assert independent_commitment.source_activity_id == independent_origin_id
        assert db.query(CustomerFact).filter_by(id=private_fact_id, team_id=team_id).one().content == "私有事实排除"
        assert not source_origin(db, team_id, customer_id, "customer_activity", private_id)
        assert source_origin(db, team_id, customer_id, "customer_activity", old_id)
        after = _context(db, team_id, customer_id)
        assert after.source_watermark["deletion_revision"] > before["deletion_revision"]
        assert {item["id"] for item in after.strong_context.recorded_follow_ups if item["kind"] == "task"} == {old_task_id, independent_task_id}
        assert {item["id"] for item in after.strong_context.sales_commitments} == {old_commitment_id, independent_commitment_id}
        assert {item["id"] for item in after.strong_context.customer_facts} == {old_fact_id}
        published = _publish(db, team_id, customer_id).version
        assert "旧任务保留" in _body(published)
        assert "独立来源承诺" in _body(published)
        assert "独立来源 NULL-FK 任务保留" in _body(published)
        assert "私有任务排除" not in _body(published)
        assert "私有承诺排除" not in _body(published)
        assert "私有事实排除" not in _body(published)


def test_s04_indirect_private_fact_is_stored_but_citation_resolves_unavailable(source_case):
    team_id, customer_id, customer_public_id = source_case
    with SessionLocal() as db:
        journey = _journey(db, team_id, customer_id)
        private = _activity(db, team_id, customer_id, "2.0 私有活动可按业务权限访问", source="ASSISTANT_2")
        event = db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, customer_id=customer_id, source_id=private.id).one()
        fact = CustomerFactService().upsert_fact(db, CustomerFactInput(
            tenant_id=team_id, team_id=team_id, customer_id=customer_id,
            fact_type="risk", content="不应展示的间接风险", confidence=0.95,
            source=CustomerFactSourceInput(source_type="business_flow", source_object_id=str(event.id)),
        ))
        fact_id, event_id, private_id = int(fact.id), int(event.id), int(private.id)
        db.commit()
    with SessionLocal() as db:
        assert db.query(CustomerFact).filter_by(team_id=team_id, customer_id=customer_id, id=fact_id).one().content == "不应展示的间接风险"
        assert db.query(CustomerFactSource).filter_by(fact_id=fact_id, source_object_id=str(event_id)).one().source_type == "business_flow"
        assert db.query(CustomerActivity).filter_by(team_id=team_id, id=private_id).one().source_content.startswith("2.0 私有")
        assert _context(db, team_id, customer_id).strong_context.customer_facts == []
        version = _publish(db, team_id, customer_id).version
        assert "不应展示的间接风险" not in _body(version)
        citation = CustomerProfileEvidenceResolver().resolve_one(
            db, team_id=team_id, customer_id=customer_id, customer_public_id=customer_public_id,
            reference={"evidence_key": f"fact:{fact_id}", "source_type": "customer_fact", "source_id": fact_id},
        )
        assert citation.visibility == "UNAVAILABLE" and citation.availability == "UNAVAILABLE"
        assert citation.snippet is None and citation.link is None


def test_s04_certified_historical_fact_citation_becomes_unavailable_over_profile_api(source_case, monkeypatch):
    team_id, customer_id, customer_public_id = source_case
    with SessionLocal() as db:
        _journey(db, team_id, customer_id)
        old = _activity(db, team_id, customer_id, "历史可引用旧活动")
        fact = CustomerFactService().upsert_fact(db, CustomerFactInput(
            tenant_id=team_id, team_id=team_id, customer_id=customer_id,
            fact_type="risk", content="历史风险引用内容", confidence=0.95,
            source=CustomerFactSourceInput(source_type="customer_activity", source_object_id=str(old.id)),
        ))
        fact_id = int(fact.id)
        db.commit()
    with SessionLocal() as db:
        published = _publish(db, team_id, customer_id)
        version_id = int(published.version.id)
        assert is_certified_profile_version(published.version)
        assert any(ref["evidence_key"] == f"fact:{fact_id}" for ref in published.version.evidence_refs_json)
    with SessionLocal() as db:
        private = _activity(db, team_id, customer_id, "禁止继承的 2.0 事实来源", source="ASSISTANT_2")
        event = db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, source_id=private.id).one()
        binding = db.query(CustomerFactSource).filter_by(fact_id=fact_id).one()
        binding.source_type = "business_flow"
        binding.source_object_id = str(event.id)
        db.commit()
    with SessionLocal() as db:
        partial = _draft(db, team_id, customer_id, target_sections=("follow_up_process",))
        with pytest.raises(CustomerProfileProjectionError) as exc:
            CustomerProfileProjectionService().publish(db, team_id=team_id, customer_id=customer_id, draft=partial)
        assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
        db.rollback()

    def _db():
        with SessionLocal() as db:
            yield db

    granted_codes = {"customer_profile:view"}
    monkeypatch.setattr(customer_profiles.permission_crud, "get_user_permissions", lambda *args: [
        type("Permission", (), {"code": code})() for code in granted_codes
    ])
    app = FastAPI()
    app.include_router(customer_profiles.router)
    app.dependency_overrides[customer_profiles.get_db] = _db
    app.dependency_overrides[customer_profiles.get_current_user_team] = lambda: team_id
    app.dependency_overrides[customer_profiles.get_current_active_user] = lambda: type("User", (), {"id": 990126011})()
    with TestClient(app) as client:
        denied = client.get(
            f"/v1/customers/{customer_public_id}/profile/evidence",
            params={"evidence_ref": f"fact:{fact_id}"},
        )
        assert denied.status_code == 403
        assert "历史风险引用内容" not in denied.text
        granted_codes.add("customer:view:all")
        response = client.get(
            f"/v1/customers/{customer_public_id}/profile/evidence",
            params={"evidence_ref": f"fact:{fact_id}"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["current_profile_version"] == published.version.public_id
    assert len(payload["items"]) == 1
    citation = payload["items"][0]
    assert citation["visibility"] == citation["availability"] == "UNAVAILABLE"
    assert citation["snippet"] is None and citation["link"] is None
    assert "历史风险引用内容" not in response.text
    with SessionLocal() as db:
        assert db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one().current_profile_version_id == version_id
        assert is_certified_profile_version(db.query(CustomerProfileProjectionVersion).filter_by(id=version_id).one())
        assert _context(db, team_id, customer_id).strong_context.customer_facts == []


def test_s05_display_window_does_not_hide_highest_eligible_id_outside_it(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        for index in range(51):
            _activity(db, team_id, customer_id, f"较新活动 {index}", when=T2 + timedelta(minutes=index))
        newest_id = int(_activity(db, team_id, customer_id, "最高 ID 但发生在窗口外", when=T1).id)
        db.commit()
    with SessionLocal() as db:
        before = _context(db, team_id, customer_id)
        assert len(before.strong_context.recent_activities) == 50
        assert newest_id not in {row.id for row in before.strong_context.recent_activities}
        assert db.query(CustomerActivity.id).filter_by(team_id=team_id, customer_id=customer_id).order_by(CustomerActivity.id.desc()).first()[0] == newest_id
        assert before.source_watermark["activity_id"] == newest_id
        before_hash = before.source_watermark["source_snapshot_hash"]
    with SessionLocal() as db:
        from app.services.legacy_profile_source import advance_eligible_progress
        advance_eligible_progress(db, team_id=team_id, customer_id=customer_id)
        row = db.query(CustomerActivity).filter_by(team_id=team_id, customer_id=customer_id, id=newest_id).one()
        row.summary = "窗口外已更新"
        row.source_content = "窗口外已更新"
        row.activity_revision += 1
        db.commit()
    with SessionLocal() as db:
        after = _context(db, team_id, customer_id)

        assert len(after.strong_context.recent_activities) == 50
        assert newest_id not in {row.id for row in after.strong_context.recent_activities}
        assert after.source_watermark["eligible_revision"] > before.source_watermark["eligible_revision"]
        assert after.source_watermark["source_snapshot_hash"] != before_hash

def test_s05_all_display_windows_preserve_complete_eligible_source_watermark(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        # Many rows bind to one original activity, but each is an independent eligible source row.
        origin = _activity(db, team_id, customer_id, "完整窗口来源")
        origin_id = int(origin.id)
        for index in range(51):
            journey = _journey(db, team_id, customer_id, f"可显示旅程 {index}")
            if index == 0:
                frequent_journey_id = int(journey.id)
            event = CustomerDealJourneyEvent(
                team_id=team_id, customer_id=customer_id, deal_journey_id=journey.id,
                event_type="activity_added", event_time=T2 + timedelta(minutes=index),
                source_type="customer_activity", source_id=origin_id,
            )
            db.add(event)
            subject = uuid4().hex
            fact = CustomerFact(
                fact_key=uuid4().hex, tenant_id=team_id, team_id=team_id,
                customer_id=customer_id, fact_type="risk", subject=subject,
                content=f"窗口事实 {index}", confidence=0.9, occurred_at=T2,
            )
            db.add(fact)
            db.flush()
            db.add(CustomerFactSource(fact_id=fact.id, source_type="customer_activity", source_object_id=str(origin_id)))
        hidden_fact = CustomerFact(
            fact_key=uuid4().hex, tenant_id=team_id, team_id=team_id,
            customer_id=customer_id, fact_type="risk", subject=uuid4().hex,
            content="最高 ID 窗口外事实", confidence=0.1, occurred_at=T1,
        )
        db.add(hidden_fact)
        db.flush()
        hidden_fact_id = int(hidden_fact.id)
        db.add(CustomerFactSource(fact_id=hidden_fact_id, source_type="customer_activity", source_object_id=str(origin_id)))
        oldest_journey = _journey(db, team_id, customer_id, "窗口外旅程")
        hidden_journey_id = int(oldest_journey.id)
        db.add(CustomerDealJourneyEvent(
            team_id=team_id, customer_id=customer_id, deal_journey_id=oldest_journey.id,
            event_type="activity_added", event_time=T1, source_type="customer_activity", source_id=origin_id,
        ))
        for index in range(150):
            db.add(CustomerDealJourneyEvent(
                team_id=team_id, customer_id=customer_id, deal_journey_id=frequent_journey_id,
                event_type="activity_added", event_time=T2 + timedelta(minutes=index),
                source_type="customer_activity", source_id=origin_id,
            ))
        last_event = CustomerDealJourneyEvent(
            team_id=team_id, customer_id=customer_id, deal_journey_id=frequent_journey_id,
            event_type="activity_added", event_time=T1, source_type="customer_activity", source_id=origin_id,
        )
        db.add(last_event)
        db.flush()
        hidden_event_id = int(last_event.id)
        for index in range(101):
            source_key = f"activity:{origin_id}"
            db.add(FollowUpTask(
                team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
                title=f"窗口任务 {index}", due_at=T2, source_type="customer_activity",
                source_key=source_key, source_activity_id=origin_id, task_hash=uuid4().hex,
                updated_time=T2 + timedelta(minutes=index),
            ))
            db.add(SalesCommitment(
                team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
                title=f"窗口承诺 {index}", content=f"窗口承诺 {index}",
                source_type="customer_activity", source_key=source_key,
                source_activity_id=origin_id, commitment_hash=uuid4().hex,
                updated_time=T2 + timedelta(minutes=index),
            ))
        hidden_task = FollowUpTask(
            team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
            title="最高 ID 窗口外任务", due_at=T2, source_type="customer_activity",
            source_key=f"activity:{origin_id}", source_activity_id=origin_id,
            task_hash=uuid4().hex, updated_time=T1,
        )
        hidden_commitment = SalesCommitment(
            team_id=team_id, customer_id=customer_id, owner_id=ACTOR, creator_id=ACTOR,
            title="最高 ID 窗口外承诺", content="最高 ID 窗口外承诺",
            source_type="customer_activity", source_key=f"activity:{origin_id}",
            source_activity_id=origin_id, commitment_hash=uuid4().hex, updated_time=T1,
        )
        db.add_all([hidden_task, hidden_commitment])
        db.flush()
        hidden_task_id, hidden_commitment_id = int(hidden_task.id), int(hidden_commitment.id)
        db.commit()
    with SessionLocal() as db:
        before = _context(db, team_id, customer_id)
        strong = before.strong_context
        assert len(strong.customer_facts) == len(strong.deal_journeys) == 50
        assert len(strong.deal_journey_events) == 200
        assert len(strong.recorded_follow_ups) == 200
        assert hidden_event_id not in {row["id"] for row in strong.deal_journey_events}
        assert hidden_fact_id not in {row["id"] for row in strong.customer_facts}
        assert hidden_journey_id not in {row["id"] for row in strong.deal_journeys}
        assert hidden_task_id not in {row["id"] for row in strong.recorded_follow_ups if row["kind"] == "task"}
        assert hidden_commitment_id not in {row["id"] for row in strong.sales_commitments}
        assert strong.source_watermarks["journey_event_id"] == hidden_event_id
        assert strong.source_watermarks["task_id"] == hidden_task_id
        assert strong.source_watermarks["commitment_id"] == hidden_commitment_id
        assert strong.source_watermarks["fact_id"] == hidden_fact_id
        assert strong.source_watermarks["journey_id"] == hidden_journey_id
        before_hash = before.source_watermark["source_snapshot_hash"]
    with SessionLocal() as db:
        event = db.query(CustomerDealJourneyEvent).filter_by(id=hidden_event_id, team_id=team_id).one()
        event.summary = "窗口外事件更新"
        db.commit()
    with SessionLocal() as db:
        after = _context(db, team_id, customer_id)
        assert after.source_watermark["source_snapshot_hash"] != before_hash


def test_s05_reconciliation_paginates_more_than_two_hundred_team_customers(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        for index in range(205):
            db.add(Customer(team_id=team_id, account_name=f"Page {uuid4().hex} {index}", city="广州", creator_id=ACTOR))
        db.commit()
    with SessionLocal() as db:
        expected_ids = {row[0] for row in db.query(Customer.id).filter_by(team_id=team_id).all()}
        service = CustomerIntelligenceReconciliationService()
        visited: list[int] = []
        cursor = None
        while True:
            result = service.reconcile_once(db, team_id=team_id, limit=200, after_customer_id=cursor, dry_run=True)
            assert result.success and result.errors == 0
            visited.extend(result.customer_ids)
            if result.next_customer_id is None:
                break
            assert result.next_customer_id != cursor
            cursor = result.next_customer_id
        assert len(visited) == 206 and set(visited) == expected_ids
        assert visited == sorted(visited)
        db.rollback()


def test_s06_deleting_highest_eligible_activity_advances_deletion_and_deduplicates_replay(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        survivor = _activity(db, team_id, customer_id, "保留旧记录", when=T1)
        highest = _activity(db, team_id, customer_id, "删除最高活动", when=T2)
        survivor_id, highest_id = int(survivor.id), int(highest.id)
        db.commit()
    with SessionLocal() as db:
        first = _publish(db, team_id, customer_id)
        assert "删除最高活动" in _body(first.version)
        first_id, watermark = int(first.version.id), first.version.source_watermark_json
    with SessionLocal() as db:
        customer_activity_crud.delete(db, db.query(CustomerActivity).filter_by(team_id=team_id, id=highest_id).one(), commit=False)
        db.commit()
    with SessionLocal() as db:
        assert db.query(CustomerActivity.id).filter_by(team_id=team_id, customer_id=customer_id).order_by(CustomerActivity.id.desc()).first()[0] == survivor_id
        assert db.query(CustomerActivityDeletionTombstone).filter_by(team_id=team_id, customer_id=customer_id, activity_id=highest_id, submission_source="FORM").one()
        after = _context(db, team_id, customer_id)
        assert after.source_watermark["deletion_revision"] > watermark["deletion_revision"]
        second = _publish(db, team_id, customer_id)
        assert second.version.id != first_id
        assert "删除最高活动" not in _body(second.version)
        replay = _publish(db, team_id, customer_id)
        assert replay.deduplicated and replay.version.id == second.version.id
        assert _version_count(db, team_id, customer_id) == 2


@pytest.mark.parametrize("delete", [False, True], ids=["write", "delete"])
def test_s07_rr_stale_publication_rejected_then_fresh_publication_succeeds(source_case, delete):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        original = _activity(db, team_id, customer_id, "保留已认证记录", when=T1)
        original_id = int(original.id)
        db.commit()
    with SessionLocal() as db:
        first_id = int(_publish(db, team_id, customer_id).version.id)
    with SessionLocal() as stale, SessionLocal() as writer:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        stale_draft = _draft(stale, team_id, customer_id)
        if delete:
            customer_activity_crud.delete(writer, writer.query(CustomerActivity).filter_by(team_id=team_id, id=original_id).one(), commit=False)
        else:
            _activity(writer, team_id, customer_id, "竞争提交的合法活动", when=T2)
        writer.commit()
        with pytest.raises(CustomerProfileProjectionError) as exc:
            CustomerProfileProjectionService().publish(stale, team_id=team_id, customer_id=customer_id, draft=stale_draft)
        assert exc.value.code == "PROFILE_PUBLISH_REJECTED_STALE"
        stale.rollback()
    with SessionLocal() as db:
        current = db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        assert current.current_profile_version_id == first_id
        assert is_certified_profile_version(db.query(CustomerProfileProjectionVersion).filter_by(team_id=team_id, id=first_id).one())
        assert _version_count(db, team_id, customer_id) == 1
        second = _publish(db, team_id, customer_id)
        assert second.version.id != first_id and current.current_profile_version_id == second.version.id
        if delete:
            assert "保留已认证记录" not in _body(second.version)
        else:
            assert "竞争提交的合法活动" in _body(second.version)


@pytest.mark.parametrize("delete", [False, True], ids=["write", "delete"])
def test_s07_full_reconciliation_competes_with_stale_publication(source_case, delete):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        original_id = int(_activity(db, team_id, customer_id, "对账前已认证来源").id)
        db.commit()
    with SessionLocal() as db:
        certified_id = int(_publish(db, team_id, customer_id).version.id)

    with SessionLocal() as stale, SessionLocal() as writer:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        old_draft = _draft(stale, team_id, customer_id)
        if delete:
            customer_activity_crud.delete(
                writer, writer.query(CustomerActivity).filter_by(team_id=team_id, id=original_id).one(),
                commit=False,
            )
        else:
            _activity(writer, team_id, customer_id, "对账竞争写入的合法来源", when=T2)
        writer.commit()

        reconciliation = CustomerIntelligenceReconciliationService().reconcile_once(
            writer, team_id=team_id, limit=10,
        )
        assert (reconciliation.scanned, reconciliation.stale, reconciliation.scheduled, reconciliation.errors) == (1, 1, 1, 0)
        writer.commit()
        with SessionLocal() as committed:
            current = committed.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
            assert current.profile_status == "STALE"
            assert current.current_profile_version_id == certified_id
            runs = committed.query(CustomerIntelligenceRun).filter_by(team_id=team_id, customer_id=customer_id).all()
            assert len(runs) == 1
            assert runs[0].scope == "full" and runs[0].status == CustomerIntelligenceRunStatus.PENDING

        with pytest.raises(CustomerProfileProjectionError) as exc:
            CustomerProfileProjectionService().publish(stale, team_id=team_id, customer_id=customer_id, draft=old_draft)
        assert exc.value.code == "PROFILE_PUBLISH_REJECTED_STALE"
        stale.rollback()

    with SessionLocal() as db:
        current = db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        assert current.profile_status == "STALE" and current.current_profile_version_id == certified_id
        assert _version_count(db, team_id, customer_id) == 1
        assert is_certified_profile_version(db.query(CustomerProfileProjectionVersion).filter_by(id=certified_id).one())
        fresh = _publish(db, team_id, customer_id)
        assert fresh.version.id != certified_id
        assert current.current_profile_version_id == fresh.version.id and current.profile_status == "READY"
        assert is_certified_profile_version(fresh.version)
        if delete:
            assert "对账前已认证来源" not in _body(fresh.version)
        else:
            assert "对账竞争写入的合法来源" in _body(fresh.version)


def test_s08_rr_private_writer_does_not_poison_stale_eligible_draft(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        journey = _journey(db, team_id, customer_id)
        _activity(db, team_id, customer_id, "旧版活动", when=T1)
        db.commit()
        journey_id = int(journey.id)
    with SessionLocal() as stale, SessionLocal() as writer:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        old = _draft(stale, team_id, customer_id)
        private = _activity(writer, team_id, customer_id, "隔离的 2.0 写入", source="ASSISTANT_2", when=T2)
        private_id = int(private.id)
        writer.commit()
        published = CustomerProfileProjectionService().publish(stale, team_id=team_id, customer_id=customer_id, draft=old)
        published_watermark = dict(published.version.source_watermark_json)
        published_body = _body(published.version)
        stale.commit()
    with SessionLocal() as db:
        assert db.query(CustomerActivity).filter_by(team_id=team_id, id=private_id).one()
        assert db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, source_id=private_id, event_type="activity_added").one()
        assert db.query(CustomerDealJourney).filter_by(team_id=team_id, id=journey_id).one().last_event_at == T2
        current_watermark = _draft(db, team_id, customer_id).source_watermark
        assert published_watermark == current_watermark
        assert current_watermark["source_provenance_status"] == "VERIFIED"
        assert {k: v for k, v in current_watermark.items() if k != "source_provenance_status"} == {
            k: v for k, v in old.source_watermark.items() if k != "source_provenance_status"
        }
        assert "隔离的 2.0 写入" not in published_body


def test_s09_full_partial_and_duplicate_publishing_recheck_provenance_and_pointer(source_case):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        old = _activity(db, team_id, customer_id, "真实旧引用")
        old_id = int(old.id)
        db.commit()
    with SessionLocal() as db:
        first = _publish(db, team_id, customer_id)
        first_id = int(first.version.id)
        assert not first.deduplicated
        assert is_certified_profile_version(first.version)
        replay = _publish(db, team_id, customer_id)
        assert replay.deduplicated and replay.version.id == first_id
        assert _version_count(db, team_id, customer_id) == 1
    with SessionLocal() as db:
        customer_activity_crud.delete(db, db.query(CustomerActivity).filter_by(team_id=team_id, id=old_id).one(), commit=False)
        db.commit()
    with SessionLocal() as db:
        partial = _draft(db, team_id, customer_id, target_sections=("follow_up_process",))
        with pytest.raises(CustomerProfileProjectionError) as exc:
            CustomerProfileProjectionService().publish(db, team_id=team_id, customer_id=customer_id, draft=partial)
        assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
        db.rollback()
        current = db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        assert current.current_profile_version_id == first_id
        fresh = _publish(db, team_id, customer_id)
        assert fresh.version.id != first_id and "真实旧引用" not in _body(fresh.version)
        assert is_certified_profile_version(fresh.version)


@pytest.mark.parametrize("branch", ("full", "partial", "duplicate"))
def test_s09_unknown_source_blocks_every_publication_branch_without_moving_pointer(source_case, branch):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        journey = _journey(db, team_id, customer_id)
        _activity(db, team_id, customer_id, "已经认证的旧活动")
        db.commit()
        journey_id = int(journey.id)
    with SessionLocal() as db:
        first = _publish(db, team_id, customer_id)
        first_id = int(first.version.id)
        first_watermark = dict(first.version.source_watermark_json)
    with SessionLocal() as db:
        db.add(CustomerDealJourneyEvent(
            team_id=team_id, customer_id=customer_id, deal_journey_id=journey_id,
            event_type="activity_added", event_time=T2, source_type="customer_activity",
            source_id=987654321012345, summary="来源无法核证的注入事件",
        ))
        db.commit()
    with SessionLocal() as db:
        target_sections = ("follow_up_process",) if branch == "partial" else None
        draft = _draft(db, team_id, customer_id, target_sections=target_sections)
        if branch == "duplicate":
            assert draft.source_watermark["source_snapshot_hash"] == first_watermark["source_snapshot_hash"]
        with pytest.raises(CustomerProfileProjectionError) as exc:
            CustomerProfileProjectionService().publish(db, team_id=team_id, customer_id=customer_id, draft=draft)
        assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
        db.rollback()
    with SessionLocal() as db:
        current = db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        assert current.current_profile_version_id == first_id
        assert _version_count(db, team_id, customer_id) == 1
        assert is_certified_profile_version(db.query(CustomerProfileProjectionVersion).filter_by(id=first_id).one())
        assert "来源无法核证的注入事件" not in _body(db.query(CustomerProfileProjectionVersion).filter_by(id=first_id).one())


@pytest.mark.parametrize("branch", ("full", "partial", "duplicate"))
def test_s09_committed_opportunity_deletion_revokes_draft_provenance_for_every_branch(source_case, branch):
    team_id, customer_id, _ = source_case
    with SessionLocal() as db:
        journey = _journey(db, team_id, customer_id, "有商机来源的历史旅程")
        opportunity = Opportunity(
            team_id=team_id, customer_id=customer_id, deal_journey_id=journey.id,
            opportunity_number=f"SRC-{uuid4().hex[:20]}", opportunity_name="已认证的业务来源",
            total_amount=10000, user_count=2, unit_price=5000, license_type="PERPETUAL",
            purchase_type="NEW", expected_closing_date=date(2027, 12, 1),
            owner_id=ACTOR, creator_id=ACTOR,
        )
        db.add(opportunity)
        db.flush()
        opportunity_id = int(opportunity.id)
        assert source_origin(db, team_id, customer_id, "opportunity", opportunity_id)
        event = deal_journey_service.record_event(
            db, deal_journey_id=int(journey.id), team_id=team_id, customer_id=customer_id,
            event_type="opportunity_created", source_type="opportunity", source_id=opportunity_id,
            event_time=T1, actor_id=ACTOR, summary="已认证的商机创建事件",
            enqueue_customer_intelligence=False,
        )
        assert event is not None
        event_id = int(event.id)
        db.commit()
    with SessionLocal() as db:
        first = _publish(db, team_id, customer_id)
        certified_id = int(first.version.id)
        assert is_certified_profile_version(first.version)
        certified_hash = str(first.version.source_watermark_json["source_snapshot_hash"])
        assert db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one().profile_status == "READY"
        assert any(row["id"] == event_id for row in _context(db, team_id, customer_id).strong_context.deal_journey_events)

    with SessionLocal() as stale, SessionLocal() as writer:
        assert stale.execute(text("SELECT @@transaction_isolation")).scalar_one() == "REPEATABLE-READ"
        target_sections = ("follow_up_process",) if branch == "partial" else None
        old_draft = _draft(stale, team_id, customer_id, target_sections=target_sections)
        if branch == "duplicate":
            assert old_draft.source_watermark["source_snapshot_hash"] == certified_hash
        assert writer.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, id=event_id, source_id=opportunity_id).one()
        assert opportunity_crud.delete(writer, opportunity_id)
        assert writer.query(Opportunity).filter_by(team_id=team_id, id=opportunity_id).one_or_none() is None
        assert writer.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, id=event_id).one()
        assert not source_origin(writer, team_id, customer_id, "opportunity", opportunity_id)

        with pytest.raises(CustomerProfileProjectionError) as exc:
            CustomerProfileProjectionService().publish(stale, team_id=team_id, customer_id=customer_id, draft=old_draft)
        assert exc.value.code == "PROFILE_SOURCE_FENCE_UNVERIFIED"
        stale.rollback()

    with SessionLocal() as db:
        current = db.query(CustomerProfileCurrent).filter_by(team_id=team_id, customer_id=customer_id).one()
        assert current.current_profile_version_id == certified_id
        assert current.profile_status == "READY"
        assert current.last_successful_version == 1
        assert _version_count(db, team_id, customer_id) == 1
        certified = db.query(CustomerProfileProjectionVersion).filter_by(team_id=team_id, id=certified_id).one()
        assert is_certified_profile_version(certified)
        assert "已认证的商机创建事件" in _body(certified)
        assert db.query(Opportunity).filter_by(team_id=team_id, id=opportunity_id).one_or_none() is None
        assert db.query(CustomerDealJourneyEvent).filter_by(team_id=team_id, id=event_id, source_id=opportunity_id).one()


def test_eligible_progress_first_insert_does_not_deadlock_other_customer(source_case):
    team_id, first_customer_id, _ = source_case
    with SessionLocal() as db:
        second = Customer(team_id=team_id, account_name=f"Independent {uuid4().hex}", city="广州", creator_id=ACTOR)
        db.add(second)
        db.commit()
        second_customer_id = int(second.id)

    inserts = Barrier(2, timeout=10)

    def before_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO CRM_CUSTOMER_LEGACY_SOURCE_PROGRESS"):
            inserts.wait()

    def writer(customer_id):
        with SessionLocal() as db:
            advance_eligible_progress(db, team_id=team_id, customer_id=customer_id)
            db.commit()

    event.listen(engine, "before_cursor_execute", before_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(writer, first_customer_id)
            second = pool.submit(writer, second_customer_id)
            first.result(timeout=20)
            second.result(timeout=20)
    finally:
        event.remove(engine, "before_cursor_execute", before_insert)

    with SessionLocal() as db:
        rows = db.query(CustomerLegacySourceProgress).filter(
            CustomerLegacySourceProgress.team_id == team_id,
            CustomerLegacySourceProgress.customer_id.in_([first_customer_id, second_customer_id]),
        ).all()
        assert len(rows) == 2
        assert all(row.eligible_revision == 1 for row in rows)

def test_distinct_customer_events_do_not_deadlock_on_absent_event_lookup(source_case):
    team_id, first_customer_id, _ = source_case
    with SessionLocal() as db:
        second = Customer(team_id=team_id, account_name=f"Other {uuid4().hex}", city="广州", creator_id=ACTOR)
        db.add(second)
        db.flush()
        second_customer_id = int(second.id)
        inputs = []
        for customer_id in (first_customer_id, second_customer_id):
            journey = _journey(db, team_id, customer_id)
            activity = CustomerActivity(
                team_id=team_id, customer_id=customer_id, deal_journey_id=journey.id,
                activity_kind="PHONE_FOLLOW_UP", source_content="并行独立客户活动",
                submission_source="ASSISTANT_2", submission_id=f"parallel-{uuid4().hex}",
                submission_fingerprint="a" * 64, creator_id=ACTOR, owner_id=ACTOR,
            )
            db.add(activity)
            db.flush()
            inputs.append((customer_id, int(journey.id), int(activity.id)))
        db.commit()

    both_absent_reads = Barrier(2, timeout=10)
    synchronized = local()

    def after_event_lookup(conn, cursor, statement, parameters, context, executemany):
        query = statement.upper()
        if "FROM CRM_CUSTOMER_DEAL_JOURNEY_EVENTS" in query and "SOURCE_ID" in query and not getattr(synchronized, "seen", False):
            synchronized.seen = True
            both_absent_reads.wait()

    def writer(customer_id, journey_id, activity_id):
        with SessionLocal() as db:
            row = deal_journey_service.record_event(
                db, deal_journey_id=journey_id, team_id=team_id, customer_id=customer_id,
                event_type="activity_added", source_type="customer_activity", source_id=activity_id,
                event_time=T2, enqueue_customer_intelligence=False,
            )
            db.commit()
            return int(row.id)

    event.listen(engine, "after_cursor_execute", after_event_lookup)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(writer, *item) for item in inputs]
            event_ids = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(engine, "after_cursor_execute", after_event_lookup)

    with SessionLocal() as db:
        events = db.query(CustomerDealJourneyEvent).filter(CustomerDealJourneyEvent.id.in_(event_ids)).all()
        assert len(events) == 2
        assert {row.customer_id for row in events} == {first_customer_id, second_customer_id}
