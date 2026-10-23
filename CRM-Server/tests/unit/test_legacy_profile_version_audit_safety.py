"""Read-only inventory regressions; no historical certificate is re-created."""

import pytest
from sqlalchemy import create_engine, event
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
from tests.unit.test_legacy_profile_version_audit import _version


@pytest.fixture
def audit_db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        User.__table__, Team.__table__, Customer.__table__, CustomerActivity.__table__,
        CustomerActivityDeletionTombstone.__table__,
        CustomerProfileProjectionVersion.__table__, CustomerProfileCurrent.__table__,
    ])
    with sessionmaker(bind=engine)() as db:
        db.add(User(id=9, name="owner", email="safety@example.test"))
        db.add_all([Team(id=1, owner_id=9, name="one", code="one"),
                    Team(id=2, owner_id=9, name="two", code="two")])
        db.add_all([
            Customer(id=i, public_id=f"cus_{i}", team_id=2 if i == 2 else 1,
                     account_name=f"private customer {i}", city="Shanghai", creator_id="9")
            for i in (1, 2, 3)
        ])
        db.flush()
        try:
            yield db, engine
        finally:
            db.rollback()
    engine.dispose()


def test_inventory_ignores_cached_availability_and_attestation_and_requires_live_scoped_sources(audit_db, capsys):
    db, engine = audit_db
    for identifier, team_id, customer_id, source in (
        (10, 1, 1, "ASSISTANT_2"), (11, 1, 1, "FORM"), (21, 2, 2, "FORM"), (31, 1, 3, "FORM"),
    ):
        db.add(CustomerActivity(
            id=identifier, team_id=team_id, customer_id=customer_id, activity_kind="MEETING",
            submission_source=source, source_content="private source text", creator_id="9", owner_id="9",
            submission_id=f"turn-{identifier}" if source == "ASSISTANT_2" else None,
            submission_fingerprint="a" * 64 if source == "ASSISTANT_2" else None,
        ))
    db.add(CustomerActivityDeletionTombstone(
        activity_id=12, team_id=1, customer_id=1, submission_source="FORM", activity_revision=1,
    ))
    refs = [
        {"evidence_key": f"activity:{identifier}", "source_type": "customer_activity", "source_id": identifier,
         "availability": "AVAILABLE", "snippet": "cached private snippet"}
        for identifier in (10, 11, 12, 21, 31, "011")
    ]
    refs.extend([
        {"evidence_key": "forged", "source_type": "unknown", "source_id": 11, "availability": "AVAILABLE"},
        {"source_type": "customer_activity", "source_id": 11, "availability": "AVAILABLE"},
        "cached private snippet",
    ])
    version = _version(1, 1, "unproven historical body", refs)
    version.source_attestation_json = {"certified": True, "signature": "cached-certificate"}
    db.add(version)
    db.commit()
    statements = []
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, sql, params, ctx, many: statements.append(sql))
    counts = audit_versions(db)
    assert counts["available_citations"] == 1
    assert counts["unavailable_citations"] == 8
    assert counts["uncertified_versions"] == counts["blocking_versions"] == 1
    assert counts["body_unproven_versions"] == 1
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    assert capsys.readouterr().out == ""
    assert "private" not in str(counts)
    assert "cached-certificate" not in str(counts)


@pytest.mark.parametrize("refs", [None, {"availability": "AVAILABLE"}, "private cached references"])
def test_inventory_malformed_reference_registry_fails_closed(audit_db, refs):
    db, _ = audit_db
    version = _version(1, 1, "", [])
    version.evidence_refs_json = refs
    db.add(version)
    db.commit()
    counts = audit_versions(db)
    assert counts["unavailable_citations"] == 1
    assert counts["available_citations"] == 0
    assert counts["uncertified_versions"] == counts["blocking_versions"] == 1
