"""Read-side regression for polluted historical profile projections."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import customer_profiles
from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_deletion import CustomerActivityDeletionTombstone
from app.models.customer_legacy_source_progress import CustomerLegacySourceProgress
from app.models.customer_profile_projection import CustomerProfileCurrent, CustomerProfileProjectionVersion
from app.models.contract import Contract
from app.models.customer import Contact, CustomerProduct
from app.models.customer_fact import CustomerFact, CustomerFactRevision, CustomerFactSource
from app.models.deal_journey import CustomerDealJourney, CustomerDealJourneyEvent
from app.models.industry import Industry
from app.models.opportunity import Opportunity
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.product import Product, ProductModule
from app.models.sales_commitment import FollowUpTask, FollowUpTaskEvent, SalesCommitment
from app.models.team import Team
from app.models.user import User
from app.services.customer_intelligence_context_service import CustomerIntelligenceContextService
from app.services.customer_profile_projection_service import PROFILE_WORKFLOW_OWNER, customer_profile_projection_service
from tests.unit.test_customer_intelligence_context_service import _seed_customer_context
from app.crud.customer import customer_crud
from app.schemas.customer import CustomerUpdate


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def profile_read_api(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        Customer.__table__, CustomerLegacySourceProgress.__table__, CustomerProfileProjectionVersion.__table__,
        CustomerProfileCurrent.__table__, CustomerActivity.__table__, CustomerActivityDeletionTombstone.__table__,
    ])
    db = sessionmaker(bind=engine)()
    customers = [Customer(id=customer_id, public_id=f"cus_{customer_id}", team_id=team_id,
                          account_name=f"客户{customer_id}", city="上海", creator_id="1")
                 for customer_id, team_id in ((1, 1), (2, 2))]
    db.add_all(customers)
    db.flush()
    team = {"id": 1}
    def _permitted_customer(public_id, team_id, user, session):
        customer = session.query(Customer).filter_by(public_id=public_id, team_id=team_id).one_or_none()
        if customer is None:
            raise HTTPException(status_code=404, detail="客户不存在")
        return customer

    monkeypatch.setattr(customer_profiles, "check_customer_view_permission", _permitted_customer)
    monkeypatch.setattr(customer_profiles.permission_crud, "get_user_permissions",
                        lambda session, user_id, team_id: [type("Permission", (), {"code": code})()
                                                          for code in ("customer_profile:view", "customer_profile:history")])
    app = FastAPI()
    app.include_router(customer_profiles.router)
    app.dependency_overrides[customer_profiles.get_db] = lambda: db
    app.dependency_overrides[customer_profiles.get_current_user_team] = lambda: team["id"]
    app.dependency_overrides[customer_profiles.get_current_active_user] = lambda: type("User", (), {"id": 1})()
    with TestClient(app) as client:
        yield db, client, team
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()


@pytest.fixture
def published_profile_read_api(profile_read_api):
    db, client, team = profile_read_api

    @event.listens_for(db.bind, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(db.bind, tables=[
        User.__table__, Team.__table__, Contact.__table__, CustomerProduct.__table__,
        Opportunity.__table__, Contract.__table__, PaymentPlan.__table__, PaymentRecord.__table__,
        CustomerDealJourney.__table__, CustomerDealJourneyEvent.__table__, SalesCommitment.__table__,
        FollowUpTask.__table__, FollowUpTaskEvent.__table__, CustomerFact.__table__,
        CustomerFactSource.__table__, CustomerFactRevision.__table__, Industry.__table__,
        Product.__table__, ProductModule.__table__,
    ])
    db.add(User(id=9, email="profile-owner@example.test", name="Profile Owner"))
    db.add(Team(id=2, name="Profile Team", code="PROFILE_TEAM", owner_id=9))
    db.commit()
    customer = _seed_customer_context(db)
    team["id"] = 2

    def publish():
        context = CustomerIntelligenceContextService().build_context(
            db, team_id=2, customer_id=101, query_text="", evidence_limit=0,
        )
        draft = customer_profile_projection_service.draft_from_context(
            context=context.to_dict(), source_event_key=None,
        )
        publication = customer_profile_projection_service.publish(
            db, team_id=2, customer_id=101, draft=draft, publication_owner=PROFILE_WORKFLOW_OWNER,
        )
        db.commit()
        return publication.version

    return db, client, customer, publish


def _version(db, *, customer_id, number, provenance=None, text="poison", evidence=None, team_id=None):
    version = CustomerProfileProjectionVersion(
        id=customer_id * 100 + number, public_id=f"cpv_{customer_id}_{number}", team_id=team_id or customer_id,
        customer_id=customer_id, schema_version="v2", profile_version=number,
        publication_status="PUBLISHED", current_situation_json={"summary": text},
        current_journeys_json=[{"summary": text}], important_changes_json=[{"summary": text}],
        long_term_context_json={"summary": text}, follow_up_process_json=[{"summary": text}],
        recorded_follow_ups_json=[{"summary": text}], evidence_refs_json=evidence or [],
        quality_report_json={}, source_watermark_json=provenance or {}, source_watermark_hash="a" * 64,
        graph_version="v2", content_hash=f"{customer_id * 100 + number:064x}",
        generated_at=datetime(2026, 9, 1), published_at=datetime(2026, 9, 1), created_time=datetime(2026, 9, 1),
    )
    db.add(version)
    db.flush()
    return version


def _point_to(db, version):
    db.add(CustomerProfileCurrent(team_id=version.team_id, customer_id=version.customer_id,
                                  current_profile_version_id=version.id, profile_status="READY",
                                  last_successful_version=version.profile_version,
                                  latest_source_watermark_json=version.source_watermark_json))
    db.commit()


def _verified(revision=4):
    return {"source_policy_version": "LEGACY_PROFILE_ELIGIBLE_V1", "source_provenance_status": "VERIFIED",
            "source_snapshot_hash": "f" * 64, "eligible_revision": revision, "deletion_revision": 0}


@pytest.mark.parametrize("path", ["", "/journeys", "/follow-ups", "/changes", "/evidence"])
def test_unknown_version_never_serves_polluted_body(profile_read_api, path):
    db, client, _ = profile_read_api
    _point_to(db, _version(db, customer_id=1, number=1, evidence=[
        {"evidence_key": "activity:10", "source_type": "customer_activity", "source_id": 10,
         "snippet": "poison", "title": "poison"}]))
    response = client.get(f"/v1/customers/cus_1/profile{path}")
    assert response.status_code == 200, response.text
    assert "poison" not in response.text
    data = response.json()["data"]
    assert data["current_profile_version"] is None
    if path:
        assert data["items"] == []
    else:
        assert data["sections"]["current_situation"] == {}
        assert data["evidence_refs"] == []
    versions = client.get("/v1/customers/cus_1/profile/versions")
    assert versions.status_code == 200
    assert "poison" not in versions.text
    assert versions.json()["data"]["items"] == []

    if path == "/evidence":
        unavailable = client.get("/v1/customers/cus_1/profile/evidence", params={"evidence_ref": "activity:10"})
        assert unavailable.status_code == 200
        item = unavailable.json()["data"]["items"][0]
        assert item["availability"] == "UNAVAILABLE"
        assert item["snippet"] is None and item["link"] is None


@pytest.mark.parametrize("path", ("", "/journeys", "/follow-ups", "/changes", "/evidence", "/versions"))
def test_matching_progress_and_snapshot_metadata_cannot_certify_historical_body(profile_read_api, path):
    db, client, _ = profile_read_api
    db.add(CustomerLegacySourceProgress(
        team_id=1, customer_id=1, provenance_status="VERIFIED", eligible_revision=4, deletion_revision=0,
    ))
    db.add(CustomerActivity(
        id=10, team_id=1, customer_id=1, activity_kind="meeting", submission_source="FORM",
        source_content="safe original", creator_id="1", owner_id="1",
    ))
    _version(db, customer_id=1, number=1, provenance=_verified(), text="older polluted body")
    _point_to(db, _version(
        db, customer_id=1, number=2, provenance=_verified(), text="2.0-derived polluted body",
        evidence=[{"evidence_key": "activity:10", "source_type": "customer_activity", "source_id": 10,
                   "snippet": "cached polluted evidence"}],
    ))
    response = client.get(f"/v1/customers/cus_1/profile{path}")
    assert response.status_code == 200, response.text
    assert all(secret not in response.text for secret in (
        "older polluted body", "2.0-derived polluted body", "cached polluted evidence", "safe original",
    ))
    data = response.json()["data"]
    if path == "/versions":
        assert data["items"] == []
    else:
        assert data["current_profile_version"] is None
        if path:
            assert data["items"] == []
        else:
            assert data["sections"]["current_situation"] == {}
            assert data["evidence_refs"] == []
    if path == "/evidence":
        direct = client.get("/v1/customers/cus_1/profile/evidence", params={"evidence_ref": "activity:10"})
        assert direct.status_code == 200
        assert direct.json()["data"]["items"][0]["availability"] == "UNAVAILABLE"
        assert "safe original" not in direct.text and "cached polluted evidence" not in direct.text


def test_unqualified_current_does_not_expose_cached_source_freshness(profile_read_api):
    db, client, _ = profile_read_api
    db.add(CustomerLegacySourceProgress(
        team_id=1, customer_id=1, provenance_status="VERIFIED", eligible_revision=4, deletion_revision=0,
    ))
    version = _version(db, customer_id=1, number=1, provenance=_verified(), text="contaminated")
    _point_to(db, version)
    current = db.query(CustomerProfileCurrent).filter_by(team_id=1, customer_id=1).one()
    current.latest_source_watermark_json = {**_verified(), "occurred_at": "2026-09-22T13:14:15"}
    db.commit()
    response = client.get("/v1/customers/cus_1/profile")
    assert response.status_code == 200
    assert response.json()["data"]["freshness"]["latest_business_event_at"] is None
    assert "2026-09-22T13:14:15" not in response.text

def test_older_verified_metadata_cannot_revive_unsafe_current(profile_read_api):
    db, client, _ = profile_read_api
    db.add(CustomerLegacySourceProgress(team_id=1, customer_id=1, provenance_status="VERIFIED",
                                        eligible_revision=4, deletion_revision=0))
    _version(db, customer_id=1, number=1, provenance=_verified(), text="historical text")
    _point_to(db, _version(db, customer_id=1, number=2, text="polluted text"))
    for path in ("", "/changes", "/versions", "/evidence"):
        response = client.get(f"/v1/customers/cus_1/profile{path}")
        assert response.status_code == 200, response.text
        assert "historical text" not in response.text and "polluted text" not in response.text
        if path == "/versions":
            assert response.json()["data"]["items"] == []
        else:
            assert response.json()["data"]["current_profile_version"] is None


def test_progress_revocation_and_revision_changes_never_certify_old_body(profile_read_api):
    db, client, _ = profile_read_api
    progress = CustomerLegacySourceProgress(team_id=1, customer_id=1, provenance_status="VERIFIED",
                                             eligible_revision=4, deletion_revision=0)
    db.add(progress)
    _point_to(db, _version(db, customer_id=1, number=1, provenance=_verified(), text="uncertified text"))
    for provenance_status, revision in (("VERIFIED", 4), ("UNVERIFIED", 4), ("VERIFIED", 5)):
        progress.provenance_status = provenance_status
        progress.eligible_revision = revision
        db.commit()
        for path in ("", "/journeys", "/changes", "/versions"):
            response = client.get(f"/v1/customers/cus_1/profile{path}")
            assert response.status_code == 200 and "uncertified text" not in response.text
            if path != "/versions":
                assert response.json()["data"]["current_profile_version"] is None



def test_uncertified_profile_evidence_cannot_resolve_even_eligible_sources(profile_read_api):
    db, client, team = profile_read_api
    for customer_id in (1, 2):
        db.add(CustomerLegacySourceProgress(team_id=customer_id, customer_id=customer_id,
                                            provenance_status="VERIFIED", eligible_revision=4, deletion_revision=0))
    for activity_id, customer_id, origin in ((10, 1, "FORM"), (11, 1, "ASSISTANT_2"), (12, 2, "FORM")):
        db.add(CustomerActivity(id=activity_id, team_id=customer_id, customer_id=customer_id,
                                activity_kind="meeting", source_content=f"secret {activity_id}",
                                submission_source=origin,
                                submission_id=f"turn-{activity_id}" if origin == "ASSISTANT_2" else None,
                                submission_fingerprint="a" * 64 if origin == "ASSISTANT_2" else None,
                                creator_id="1", owner_id="1"))
    version = _version(db, customer_id=1, number=1, provenance=_verified(), text="uncertified",
                       evidence=[{"evidence_key": f"activity:{source_id}", "source_type": "customer_activity",
                                  "source_id": source_id, "snippet": "cached poison"} for source_id in (10, 11, 12)])
    _point_to(db, version)
    response = client.get("/v1/customers/cus_1/profile/evidence")
    assert response.status_code == 200 and response.json()["data"]["items"] == []
    assert "secret" not in response.text and "cached poison" not in response.text
    for source_id in (10, 11, 12):
        direct = client.get("/v1/customers/cus_1/profile/evidence", params={"evidence_ref": f"activity:{source_id}"})
        assert direct.json()["data"]["items"][0]["availability"] == "UNAVAILABLE"
        assert "secret" not in direct.text
    team["id"] = 2
    response = client.get("/v1/customers/cus_1/profile")
    assert response.status_code in (403, 404)
    assert "uncertified" not in response.text


def test_uncertified_history_cursor_skips_poisoned_rows_without_exposing_metadata(profile_read_api):
    db, client, _ = profile_read_api
    for number in range(1, 105):
        _version(db, customer_id=1, number=number, provenance=_verified(), text=f"secret-{number}")
    db.commit()
    for params in ({"limit": 1}, {"limit": 2, "before_version": 51}, {"limit": 1, "cursor": customer_profiles._encode_version_cursor(103, customer_public_id="cus_1")}):
        response = client.get("/v1/customers/cus_1/profile/versions", params=params)
        assert response.status_code == 200
        assert response.json()["data"] == {"items": [], "next_cursor": None, "has_more": False}
        assert "secret-" not in response.text and "cpv_" not in response.text


def test_uncertified_change_never_diffs_an_old_neighbor(profile_read_api, monkeypatch):
    db, client, _ = profile_read_api
    _version(db, customer_id=1, number=1, text="unsafe before")
    _point_to(db, _version(db, customer_id=1, number=2, text="unsafe after"))
    def forbid_diff(*args, **kwargs):
        raise AssertionError("uncertified row must never be diffed")
    monkeypatch.setattr(customer_profiles.customer_profile_projection_service, "list_changes", forbid_diff)
    response = client.get("/v1/customers/cus_1/profile/changes")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert "unsafe before" not in response.text and "unsafe after" not in response.text


def test_history_requires_distinct_permission(profile_read_api, monkeypatch):
    db, client, _ = profile_read_api
    monkeypatch.setattr(customer_profiles.permission_crud, "get_user_permissions",
                        lambda session, user_id, team_id: [type("Permission", (), {"code": "customer_profile:view"})()])
    response = client.get("/v1/customers/cus_1/profile/versions")
    assert response.status_code == 403


def test_publisher_certified_profile_exposes_current_body_and_evidence(published_profile_read_api):
    db, client, customer, publish = published_profile_read_api
    version = publish()
    response = client.get(f"/v1/customers/{customer.public_id}/profile")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["current_profile_version"] == version.public_id
    assert data["sections"]["current_situation"] == version.current_situation_json
    assert data["freshness"]["profile_as_of"] is not None
    evidence = client.get(f"/v1/customers/{customer.public_id}/profile/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["data"]["current_profile_version"] == version.public_id
    journeys = client.get(f"/v1/customers/{customer.public_id}/profile/journeys")
    assert journeys.status_code == 200
    assert journeys.json()["data"]["items"] == version.current_journeys_json


def test_certified_history_paginates_around_uncertified_rows_and_diffs_safe_neighbors(published_profile_read_api):
    db, client, customer, publish = published_profile_read_api
    _version(db, customer_id=101, team_id=2, number=0, text="historical poison")
    first = publish()
    customer_crud.update(db, customer, CustomerUpdate(city="深圳"))
    second = publish()
    for number in range(3, 106):
        _version(db, customer_id=101, team_id=2, number=number, text=f"hidden poison {number}")
    db.commit()
    path = f"/v1/customers/{customer.public_id}/profile"

    first_page = client.get(f"{path}/versions", params={"limit": 1})
    assert first_page.status_code == 200, first_page.text
    assert [item["public_id"] for item in first_page.json()["data"]["items"]] == [second.public_id]
    assert first_page.json()["data"]["has_more"] is True
    second_page = client.get(f"{path}/versions", params={"limit": 1, "cursor": first_page.json()["data"]["next_cursor"]})
    assert [item["public_id"] for item in second_page.json()["data"]["items"]] == [first.public_id]
    assert second_page.json()["data"]["has_more"] is False
    assert "historical poison" not in first_page.text + second_page.text
    assert "hidden poison" not in first_page.text + second_page.text
    assert client.get(f"{path}/versions", params={"before_version": 2}).json()["data"]["items"][0]["public_id"] == first.public_id

    changes = client.get(f"{path}/changes", params={"limit": 1})
    assert changes.status_code == 200, changes.text
    assert len(changes.json()["data"]["items"]) == 1
    item = changes.json()["data"]["items"][0]
    assert (item["from_profile_version"], item["to_profile_version"]) == (1, 2)
    assert "深圳" in changes.text and "historical poison" not in changes.text
    assert "hidden poison" not in changes.text
    assert changes.json()["data"]["has_more"] is False
    assert client.get(f"{path}/changes", params={"cursor": customer_profiles._encode_cursor(
        resource="changes", customer_public_id=str(customer.public_id), sort_key="2",
    )}).json()["data"]["items"] == []


def test_current_certificate_cannot_qualify_uncertified_adjacent_before(published_profile_read_api):
    db, client, customer, publish = published_profile_read_api
    _version(db, customer_id=101, team_id=2, number=0, text="unsafe adjacent before")
    first = publish()
    path = f"/v1/customers/{customer.public_id}/profile"
    assert client.get(path).json()["data"]["current_profile_version"] == first.public_id
    changes = client.get(f"{path}/changes")
    assert changes.status_code == 200
    assert changes.json()["data"]["items"] == []
    assert "unsafe adjacent before" not in changes.text


def test_tampered_publisher_version_is_hidden_from_every_read_path(published_profile_read_api):
    db, client, customer, publish = published_profile_read_api
    version = publish()
    version.current_situation_json = {"summary": "postpublication poison"}
    db.commit()
    for suffix in ("", "/changes", "/evidence", "/journeys", "/follow-ups", "/versions"):
        response = client.get(f"/v1/customers/{customer.public_id}/profile{suffix}")
        assert response.status_code == 200 and "postpublication poison" not in response.text
        if suffix == "/versions":
            assert response.json()["data"]["items"] == []
        else:
            assert response.json()["data"]["current_profile_version"] is None


def test_certified_before_is_never_diffed_with_tampered_after(published_profile_read_api):
    db, client, customer, publish = published_profile_read_api
    first = publish()
    customer_crud.update(db, customer, CustomerUpdate(city="深圳"))
    second = publish()
    second.current_situation_json = {"summary": "poisoned after"}
    db.commit()
    response = client.get(f"/v1/customers/{customer.public_id}/profile/changes")
    assert response.status_code == 200
    assert all(item["to_profile_version"] != second.profile_version for item in response.json()["data"]["items"])
    assert "poisoned after" not in response.text
    history = client.get(f"/v1/customers/{customer.public_id}/profile/versions")
    assert [item["public_id"] for item in history.json()["data"]["items"]] == [first.public_id]
