"""Behavioral checks for the offline, content-free legacy profile inventory."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.models.team import Team
from app.models.user import User
from scripts.audit_legacy_profile_versions import audit_versions


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


def _version(customer_id: int, team_id: int, text: str, refs: list[dict]) -> CustomerProfileProjectionVersion:
    return CustomerProfileProjectionVersion(
        team_id=team_id, customer_id=customer_id, public_id=f"cpv_{team_id}_{customer_id}",
        schema_version="v2", profile_version=1, publication_status="PUBLISHED",
        current_situation_json={"summary": text}, current_journeys_json=[],
        important_changes_json=[], long_term_context_json={}, follow_up_process_json=[],
        recorded_follow_ups_json=[], evidence_refs_json=refs,
        quality_report_json={}, source_watermark_json={}, source_watermark_hash="a" * 64,
        graph_version="v2", content_hash="b" * 64,
        generated_at=datetime(2026, 9, 1), published_at=datetime(2026, 9, 1),
        created_time=datetime(2026, 9, 1),
    )


def test_inventory_flags_copied_private_text_and_unavailable_citation_without_leaking_content(capsys):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        User.__table__, Team.__table__, Customer.__table__, CustomerActivity.__table__,
        CustomerActivityDeletionTombstone.__table__,
        CustomerProfileProjectionVersion.__table__, CustomerProfileCurrent.__table__,
    ])
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=9, name="owner", email="audit-owner@example.test"))
        db.add(Team(id=1, owner_id=9, name="private team", code="audit-team"))
        db.add(Customer(
            id=1, public_id="cus_1", team_id=1, account_name="private customer", city="Shanghai", creator_id="9",
        ))
        db.add_all([
            CustomerActivity(id=10, team_id=1, customer_id=1, activity_kind="meeting",
                             submission_source="ASSISTANT_2", submission_id="turn-audit-1",
                             submission_fingerprint="a" * 64,
                             source_content="private opportunity phrase 123456789", creator_id="9", owner_id="9"),
            CustomerActivity(id=11, team_id=1, customer_id=1, activity_kind="meeting",
                             submission_source="FORM", source_content="eligible source phrase 123456789",
                             creator_id="9", owner_id="9"),
        ])
        db.add(_version(1, 1, "Copied private opportunity phrase 123456789 into a historical body", [
            {"evidence_key": "activity:10", "source_type": "customer_activity", "source_id": 10},
            {"evidence_key": "activity:11", "source_type": "customer_activity", "source_id": 11},
        ]))
        db.commit()
        writes: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def watch_sql(conn, cursor, statement, parameters, context, executemany):
            if not statement.lstrip().upper().startswith("SELECT"):
                writes.append(statement)

        report = audit_versions(db)
        assert report["versions"] == 1
        assert report["uncertified_versions"] == 1
        assert report["body_matches_assistant2_source"] == 1
        assert report["body_unproven_versions"] == 1
        assert report["available_citations"] == 1
        assert report["unavailable_citations"] == 1
        assert report["blocking_versions"] == 1
        assert not writes
        assert capsys.readouterr().out == ""
        assert "private opportunity" not in str(report) and "private customer" not in str(report)
    engine.dispose()


def test_inventory_rejects_cross_team_version_and_current_pointer_without_reading_their_refs():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        User.__table__, Team.__table__, Customer.__table__, CustomerActivity.__table__,
        CustomerActivityDeletionTombstone.__table__,
        CustomerProfileProjectionVersion.__table__, CustomerProfileCurrent.__table__,
    ])
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=9, name="owner", email="audit-owner@example.test"))
        db.add_all([Team(id=1, owner_id=9, name="team one", code="audit-team-1"),
                    Team(id=2, owner_id=9, name="team two", code="audit-team-2")])
        db.add_all([Customer(id=1, public_id="cus_1", team_id=1, account_name="one", city="Shanghai", creator_id="9"),
                    Customer(id=2, public_id="cus_2", team_id=2, account_name="two", city="Shanghai", creator_id="9")])
        db.flush()
        version = _version(2, 1, "untrusted body", [{"source_type": "customer_activity", "source_id": 10}])
        db.add(version)
        db.flush()
        db.add(CustomerProfileCurrent(team_id=1, customer_id=1, current_profile_version_id=version.id,
                                      profile_status="READY", latest_source_watermark_json={}))
        db.commit()
        report = audit_versions(db)
        assert report["versions"] == 1
        assert report["unowned_versions"] == 1
        assert report["invalid_current_pointers"] == 1
        assert report["available_citations"] == report["unavailable_citations"] == 0
        assert report["blocking_versions"] == 1
    engine.dispose()
