"""Current provenance and source-context isolation contracts."""

from datetime import datetime

import pytest

from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_fact import CustomerFact, CustomerFactSource
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.sales_commitment import FollowUpTask, SalesCommitment
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.legacy_profile_source import fact_origin, follow_up_origin, source_origin, source_status
from tests.unit.test_customer_intelligence_context_service import _seed_customer_context, _session


def test_mixed_journey_uses_only_eligible_event_time_and_watermark():
    engine, db = _session()
    try:
        _seed_customer_context(db)
        journey = CustomerDealJourney(id=994, team_id=2, customer_id=101, name="旧旅程", status="ACTIVE")
        db.add(journey)
        db.add(
            CustomerDealJourneyEvent(
                id=995,
                team_id=2,
                customer_id=101,
                deal_journey_id=994,
                event_type="activity_added",
                event_time=datetime(2026, 9, 1, 9),
                source_type="customer_activity",
                source_id=701,
                summary="旧事件",
            )
        )
        db.flush()
        service = CustomerIntelligenceContextService()
        before = service.build_context(db, team_id=2, customer_id=101)
        db.add(
            CustomerActivity(
                id=996,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="2.0 秘密",
                occurred_at=datetime(2026, 9, 2, 9),
                creator_id="9",
                owner_id="9",
                submission_source="ASSISTANT_2",
                submission_id="turn-996",
                submission_fingerprint="a" * 64,
            )
        )
        db.add(
            CustomerDealJourneyEvent(
                id=997,
                team_id=2,
                customer_id=101,
                deal_journey_id=994,
                event_type="activity_added",
                event_time=datetime(2026, 9, 2, 9),
                source_type="customer_activity",
                source_id=996,
                summary="2.0 秘密",
            )
        )
        journey.last_event_at = datetime(2026, 9, 2, 9)
        journey.name = "2.0 注入名称"
        journey.status = "WON"
        journey.started_at = datetime(2026, 9, 2, 8)
        journey.closed_at = datetime(2026, 9, 2, 9)
        db.flush()
        after = service.build_context(db, team_id=2, customer_id=101)
        assert after.strong_context.deal_journeys == before.strong_context.deal_journeys
        assert after.source_watermark == before.source_watermark
        assert [event["summary"] for event in after.strong_context.deal_journey_events] == ["旧事件"]
        assert "2.0 注入名称" not in str(after.strong_context.deal_journeys)
    finally:
        db.close()
        engine.dispose()


def test_task_event_without_source_activity_id_cannot_enter_legacy_context():
    from app.models.sales_commitment import FollowUpTaskEvent

    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(
            FollowUpTask(
                id=930,
                team_id=2,
                customer_id=101,
                creator_id="9",
                owner_id="9",
                title="旧任务",
                due_at=datetime(2026, 9, 3),
                source_type="customer_activity",
                source_key="activity:701",
                task_hash="task-930",
            )
        )
        db.flush()
        db.add(
            FollowUpTaskEvent(
                id=931,
                team_id=2,
                task_id=930,
                event_type="UPDATED",
                source_type="customer_activity",
                source_activity_id=None,
                payload_json={"content": "来源不明的秘密"},
            )
        )
        db.flush()
        context = CustomerIntelligenceContextService().build_context(db, team_id=2, customer_id=101)
        assert context.strong_context.follow_up_task_events == []
        assert context.source_watermark.get("task_event_id") != 931
    finally:
        db.close()
        engine.dispose()


def test_task_event_with_malformed_deleted_activity_key_is_unverified_not_an_error():
    from app.models.sales_commitment import FollowUpTaskEvent
    from app.services.legacy_profile_source import task_event_source_status

    engine, db = _session()
    try:
        _seed_customer_context(db)
        task = FollowUpTask(
            id=932,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="无法归因的任务",
            due_at=datetime(2026, 10, 1),
            source_type="customer_activity",
            source_key="activity:bad-id",
            task_hash="bad-key-932",
        )
        db.add(task)
        db.flush()
        event = FollowUpTaskEvent(
            id=933,
            team_id=2,
            task_id=932,
            event_type="UPDATED",
            source_type="customer_activity",
            source_activity_id=None,
        )
        db.add(event)
        db.flush()

        assert task_event_source_status(db, event, task, 2, 101) == "UNKNOWN"
    finally:
        db.close()
        engine.dispose()


def test_conflicting_business_reference_does_not_authorize_old_activity():
    from app.services.legacy_profile_source import source_origin

    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(
            CustomerActivity(
                id=990,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="2.0",
                creator_id="9",
                owner_id="9",
                submission_source="ASSISTANT_2",
                submission_id="turn-990",
                submission_fingerprint="f" * 64,
            )
        )
        db.flush()
        assert not source_origin(db, 2, 101, "customer_activity", "701", "customer_activity", "990")
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize(
    "model,kind,alias",
    [
        (FollowUpTask, "follow_up_task", "task"),
        (SalesCommitment, "sales_commitment", "commitment"),
    ],
)
def test_public_follow_up_sources_preserve_aliases_decimal_ids_and_exact_hints(model, kind, alias):
    engine, db = _session()
    try:
        _seed_customer_context(db)
        rows = []
        for identifier in (940, 941):
            fields = (
                {"task_hash": f"task-{identifier}"}
                if model is FollowUpTask
                else {
                    "commitment_hash": f"commitment-{identifier}",
                    "content": "发送验收报告",
                }
            )
            row = model(
                id=identifier,
                team_id=2,
                customer_id=101,
                creator_id="9",
                owner_id="9",
                title="旧活动跟进",
                due_at=datetime(2026, 10, 1),
                source_type="CUSTOMER_ACTIVITY",
                source_key="activity:701",
                source_activity_id=701,
                **fields,
            )
            db.add(row)
            rows.append(row)
        db.flush()
        row, other = rows
        for source_id in (row.public_id, str(row.id), row.id):
            assert source_status(db, 2, 101, kind, source_id) == "VERIFIED"
            assert source_origin(db, 2, 101, alias, source_id, kind, source_id)
            assert source_origin(db, 2, 101, kind, source_id, alias, source_id)
        assert source_status(db, 2, 101, kind, row.public_id, kind, other.public_id) == "UNKNOWN"
        assert source_status(db, 2, 101, kind, row.public_id, kind, str(row.id)) == "UNKNOWN"
        assert source_status(db, 2, 101, kind, row.public_id, "customer_activity", "701") == "UNKNOWN"
        assert source_status(db, 2, 101, kind, row.public_id, kind, None) == "UNKNOWN"
        assert source_status(db, 2, 101, kind, row.public_id, None, row.public_id) == "UNKNOWN"
        assert source_status(db, 3, 101, kind, row.public_id, kind, row.public_id) == "UNKNOWN"
        assert source_status(db, 2, 102, kind, row.public_id, kind, row.public_id) == "UNKNOWN"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize(
    "model,kind,prefix",
    [
        (FollowUpTask, "follow_up_task", "fut"),
        (SalesCommitment, "sales_commitment", "scm"),
    ],
)
def test_public_follow_up_sources_require_canonical_ids_and_verified_provenance(model, kind, prefix):
    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(
            CustomerActivity(
                id=902,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="2.0",
                creator_id="9",
                owner_id="9",
                submission_source="ASSISTANT_2",
                submission_id="turn-902",
                submission_fingerprint="a" * 64,
            )
        )
        cases = [
            ({"source_key": "activity:902", "source_activity_id": 902}, "EXCLUDED"),
            ({"source_key": "activity:999", "source_activity_id": None}, "UNKNOWN"),
            ({"source_key": "public:unverified", "source_activity_id": None}, "UNKNOWN"),
            ({"source_key": "activity:902"}, "UNKNOWN"),
            ({"source_public_id": "act_unverified"}, "UNKNOWN"),
            ({"public_id": f"{prefix}_legacy"}, "UNKNOWN"),
        ]
        for identifier, (overrides, expected) in enumerate(cases, start=940):
            fields = (
                {"task_hash": f"task-{identifier}"}
                if model is FollowUpTask
                else {
                    "commitment_hash": f"commitment-{identifier}",
                    "content": "发送验收报告",
                }
            )
            fields.update(
                id=identifier,
                team_id=2,
                customer_id=101,
                creator_id="9",
                owner_id="9",
                title="来源校验",
                due_at=datetime(2026, 10, 1),
                source_type="CUSTOMER_ACTIVITY",
                source_key="activity:701",
                source_activity_id=701,
            )
            fields.update(overrides)
            row = model(**fields)
            db.add(row)
            db.flush()
            assert source_status(db, 2, 101, kind, row.public_id, kind, row.public_id) == expected
            assert not source_origin(db, 2, 101, kind, row.public_id, kind, row.public_id)
        for source_id in (
            None,
            "",
            f"{prefix}_" + "f" * 32,
            f"{prefix}_" + "A" * 32,
            "scm_" + "e" * 32 if prefix == "fut" else "fut_" + "e" * 32,
        ):
            assert source_status(db, 2, 101, kind, source_id, kind, source_id) == "UNKNOWN"
    finally:
        db.close()
        engine.dispose()


def test_deleted_legacy_activity_keeps_null_fk_task_and_commitment_origin():
    from app.models.sales_commitment import SalesCommitment

    engine, db = _session()
    try:
        _seed_customer_context(db)
        commitment = SalesCommitment(
            id=940,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="旧承诺",
            content="回访",
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:701",
            source_activity_id=701,
            commitment_hash="commitment-940",
        )
        task = FollowUpTask(
            id=941,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="独立旧任务",
            due_at=datetime(2026, 10, 1),
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:701",
            source_activity_id=701,
            task_hash="task-941",
        )
        db.add_all([commitment, task])
        db.flush()
        activity = db.query(CustomerActivity).filter_by(id=701).one()
        db.add(
            CustomerActivityDeletionTombstone(
                team_id=2,
                customer_id=101,
                activity_id=701,
                submission_source="FORM",
            )
        )
        commitment.source_activity_id = None
        task.source_activity_id = None
        db.delete(activity)
        db.flush()
        assert follow_up_origin(db, commitment, 2, 101)
        assert follow_up_origin(db, task, 2, 101)
    finally:
        db.close()
        engine.dispose()


def test_null_fk_standalone_origin_excludes_deleted_assistant_and_unverified_source():
    from app.models.sales_commitment import SalesCommitment

    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(
            CustomerActivityDeletionTombstone(
                team_id=2,
                customer_id=101,
                activity_id=902,
                submission_source="ASSISTANT_2",
            )
        )
        db.add(
            CustomerActivityDeletionTombstone(
                team_id=3,
                customer_id=101,
                activity_id=903,
                submission_source="FORM",
            )
        )
        db.flush()
        for source_type, key in (
            ("CUSTOMER_ACTIVITY", "activity:902"),
            ("CUSTOMER_ACTIVITY", "activity:903"),
            ("CUSTOMER_ACTIVITY", "activity:999"),
            ("CUSTOMER_ACTIVITY", "public:unverified"),
            ("HISTORICAL_BACKFILL", "activity:701"),
            ("UNKNOWN", "activity:701"),
        ):
            task = FollowUpTask(
                team_id=2,
                customer_id=101,
                creator_id="9",
                owner_id="9",
                title="不可验证任务",
                due_at=datetime(2026, 10, 1),
                source_type=source_type,
                source_key=key,
                task_hash="unverified",
            )
            commitment = SalesCommitment(
                team_id=2,
                customer_id=101,
                creator_id="9",
                owner_id="9",
                title="不可验证承诺",
                content="回访",
                source_type=source_type,
                source_key=key,
                commitment_hash="unverified",
            )
            assert not follow_up_origin(db, task, 2, 101)
            assert not follow_up_origin(db, commitment, 2, 101)
    finally:
        db.close()
        engine.dispose()


def test_follow_up_origin_rejects_conflicting_activity_public_id_and_commitment_hints():
    from app.models.sales_commitment import SalesCommitment

    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(
            CustomerActivity(
                id=703,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="另一个旧活动",
                creator_id="9",
                owner_id="9",
                submission_source="FORM",
            )
        )
        db.add(
            CustomerActivity(
                id=902,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="2.0",
                creator_id="9",
                owner_id="9",
                submission_source="ASSISTANT_2",
                submission_id="turn-902",
                submission_fingerprint="a" * 64,
            )
        )
        commitment = SalesCommitment(
            id=940,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="2.0 承诺",
            content="秘密",
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:902",
            source_activity_id=902,
            commitment_hash="commitment-940",
        )
        db.add(commitment)
        db.flush()
        task = FollowUpTask(
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="旧任务",
            due_at=datetime(2026, 10, 1),
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:701",
            source_activity_id=701,
            task_hash="conflict",
        )
        assert follow_up_origin(db, task, 2, 101)
        task.source_key = "activity:902"
        assert not follow_up_origin(db, task, 2, 101)
        task.source_key = "activity:703"
        assert not follow_up_origin(db, task, 2, 101)
        task.source_key = "activity:701"
        task.source_public_id = "act_unverified"
        assert not follow_up_origin(db, task, 2, 101)
        task.source_public_id = None
        task.commitment_id = commitment.id
        assert not follow_up_origin(db, task, 2, 101)
        task.commitment_id = None
        commitment.source_activity_id = 701
        assert not follow_up_origin(db, commitment, 2, 101)
    finally:
        db.close()
        engine.dispose()


def test_commitment_source_requires_same_customer_and_no_conflicting_task_hints():
    from app.models.sales_commitment import SalesCommitment

    engine, db = _session()
    try:
        _seed_customer_context(db)
        good = SalesCommitment(
            id=940,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="旧承诺",
            content="回访",
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:701",
            commitment_hash="commitment-940",
        )
        other_customer = SalesCommitment(
            id=941,
            team_id=2,
            customer_id=102,
            creator_id="9",
            owner_id="9",
            title="其他客户承诺",
            content="回访",
            source_type="CUSTOMER_ACTIVITY",
            source_key="activity:701",
            commitment_hash="commitment-941",
        )
        db.add_all([good, other_customer])
        db.flush()
        task = FollowUpTask(
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="关联承诺任务",
            due_at=datetime(2026, 10, 1),
            source_type="sales_commitment",
            source_key="commitment:940",
            task_hash="task-940",
        )
        assert follow_up_origin(db, task, 2, 101)
        task.commitment_id = 941
        assert not follow_up_origin(db, task, 2, 101)
        task.commitment_id = 940
        task.source_key = "commitment:941"
        assert not follow_up_origin(db, task, 2, 101)
        task.source_key = "commitment:940"
        task.source_activity_id = 701
        assert not follow_up_origin(db, task, 2, 101)
        task.source_activity_id = None
        task.source_key = "commitment:940:extra"
        assert not follow_up_origin(db, task, 2, 101)
    finally:
        db.close()
        engine.dispose()


def test_source_watermark_includes_eligible_rows_outside_display_windows():
    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(
            CustomerActivity(
                id=990,
                team_id=2,
                customer_id=101,
                activity_kind="PHONE_FOLLOW_UP",
                source_content="旧记录",
                occurred_at=datetime(2020, 1, 1),
                creator_id="9",
                owner_id="9",
            )
        )
        for offset in range(50):
            db.add(
                CustomerActivity(
                    id=800 + offset,
                    team_id=2,
                    customer_id=101,
                    activity_kind="PHONE_FOLLOW_UP",
                    source_content="最近记录",
                    occurred_at=datetime(2026, 8, 3),
                    creator_id="9",
                    owner_id="9",
                )
            )
        db.flush()
        context = CustomerIntelligenceContextService().build_context(db, team_id=2, customer_id=101)
        assert len(context.strong_context.recent_activities) == 50
        assert all(item.id != 990 for item in context.strong_context.recent_activities)
        assert context.source_watermark["activity_id"] == 990
    finally:
        db.close()
        engine.dispose()


def test_contact_mobile_change_updates_source_snapshot():
    from app.crud.customer import contact_crud
    from app.models.customer import Contact
    from app.schemas.customer import ContactUpdate

    engine, db = _session()
    try:
        _seed_customer_context(db)
        context_service = CustomerIntelligenceContextService()
        before = context_service.build_context(db, team_id=2, customer_id=101).source_watermark
        contact = db.query(Contact).filter_by(team_id=2, customer_id=101).one()

        contact_crud.update(db, contact, ContactUpdate(mobile="13900000000"))

        after = context_service.build_context(db, team_id=2, customer_id=101).source_watermark
        assert contact.mobile == "13900000000"
        assert after["source_snapshot_hash"] != before["source_snapshot_hash"]
    finally:
        db.close()
        engine.dispose()


def test_indirect_fact_and_deleted_task_do_not_reenter_legacy_profile():
    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(CustomerDealJourney(id=994, team_id=2, customer_id=101, name="隔离旅程"))
        db.add(
            CustomerActivityDeletionTombstone(
                team_id=2, customer_id=101, activity_id=902, submission_source="ASSISTANT_2"
            )
        )
        db.add(
            CustomerDealJourneyEvent(
                id=903,
                team_id=2,
                customer_id=101,
                deal_journey_id=994,
                event_type="activity_added",
                event_time=datetime(2026, 9, 2, 9),
                source_type="customer_activity",
                source_id=902,
                summary="保密摘要",
            )
        )
        fact = db.query(CustomerFactSource).filter_by(source_object_id="701").one().fact_id
        db.query(CustomerFactSource).filter_by(fact_id=fact).update(
            {
                "source_type": "business_flow",
                "source_object_id": "903",
                "business_object_type": "deal_journey_event",
                "business_object_id": "903",
            }
        )
        task = FollowUpTask(
            id=905,
            team_id=2,
            customer_id=101,
            creator_id="9",
            owner_id="9",
            title="隔离任务",
            due_at=datetime(2026, 9, 3),
            source_type="customer_activity",
            source_key="activity:902",
            task_hash="isolation-task-905",
        )
        db.add(task)
        db.flush()
        context = CustomerIntelligenceContextService().build_context(db, team_id=2, customer_id=101)
        assert not fact_origin(db, db.query(CustomerFact).filter_by(id=fact).one(), 2, 101)
        assert not follow_up_origin(db, task, 2, 101)
        assert context.strong_context.customer_facts == []
        assert all(item["id"] != 905 for item in context.strong_context.recorded_follow_ups)
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize("source_id", ["0701", "000", "-1", "701.0", " 701", True])
def test_activity_source_rejects_noncanonical_ids_even_for_excluded_origins(source_id):
    engine, db = _session()
    try:
        _seed_customer_context(db)
        activity = db.query(CustomerActivity).filter_by(id=701, team_id=2, customer_id=101).one()
        activity.submission_source = "ASSISTANT_2"
        activity.submission_id = "assistant-canonical-id"
        activity.submission_fingerprint = "a" * 64
        db.flush()
        assert source_status(db, 2, 101, "customer_activity", 701) == "EXCLUDED"
        assert source_status(db, 2, 101, "customer_activity", source_id) == "UNKNOWN"
    finally:
        db.close()
        engine.dispose()


def test_journey_and_task_event_business_hints_cannot_borrow_another_origin():
    from app.models.sales_commitment import FollowUpTaskEvent

    engine, db = _session()
    try:
        _seed_customer_context(db)
        db.add(CustomerDealJourney(id=990, team_id=2, customer_id=101, name="旧旅程", status="ACTIVE"))
        db.add(CustomerDealJourneyEvent(
            id=991, team_id=2, customer_id=101, deal_journey_id=990, event_type="activity_added",
            source_type="customer_activity", source_id="701", summary="旧来源", event_time=datetime(2026, 9, 1),
        ))
        db.add(FollowUpTask(
            id=930, team_id=2, customer_id=101, creator_id="9", owner_id="9", title="旧任务",
            source_type="customer_activity", source_key="activity:701", source_activity_id=701,
            due_at=datetime(2026, 9, 3), task_hash="task-930",
        ))
        db.flush()
        db.add(FollowUpTaskEvent(
            id=931, team_id=2, task_id=930, event_type="UPDATED", source_type="customer_activity",
            source_activity_id=701, payload_json={},
        ))
        db.flush()
        for kind, source_id, business_kind, business_id in (
            ("deal_journey_event", 991, "customer_activity", "701"),
            ("follow_up_task_event", 931, "task", "930"),
        ):
            assert source_status(db, 2, 101, kind, source_id, business_kind, business_id) == "VERIFIED"
            assert source_status(db, 2, 101, kind, source_id, business_kind, "999") == "UNKNOWN"
            assert source_status(db, 2, 101, kind, source_id, business_kind, None) == "UNKNOWN"
            assert source_status(db, 3, 101, kind, source_id, business_kind, business_id) == "UNKNOWN"
            assert source_status(db, 2, 102, kind, source_id, business_kind, business_id) == "UNKNOWN"
    finally:
        db.close()
        engine.dispose()
