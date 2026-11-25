"""Duplicate blocking for customer contacts, invoice titles and deployments (CRM-164)."""

import asyncio
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine, event, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.core.database import Base
from app.core.exceptions import DuplicateRecordError, app_exception_handler
from app.crud.crud_deployment import deployment_info_crud
from app.crud.customer import contact_crud
from app.crud.invoice import invoice_title_crud
from app.models.contract import Contract
from app.models.customer import Contact, Customer
from app.models.deployment import DeploymentInfo
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.license_application import LicenseApplication
from app.schemas.customer import ContactCreate, ContactUpdate
from app.schemas.deployment import DeploymentInfoInternalCreate, DeploymentInfoUpdate
from app.schemas.invoice import InvoiceTitleCreate, InvoiceTitleUpdate
from app.utils.dedupe_normalizer import normalize_mobile, normalize_taxpayer_id, server_address_dedupe_key

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dedupe_customer_children.py"
_spec = importlib.util.spec_from_file_location("dedupe_customer_children", _SCRIPT)
assert _spec is not None and _spec.loader is not None
dedupe_script = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dedupe_script
_spec.loader.exec_module(dedupe_script)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kwargs):
    return "INTEGER"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_plain_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        # Plain index names collide across tables in SQLite; the unique dedupe indexes are kept.
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(engine, tables=[
        Customer.__table__, Contact.__table__, InvoiceTitle.__table__, DeploymentInfo.__table__,
        Contract.__table__, InvoiceApplication.__table__, LicenseApplication.__table__,
    ])
    session = sessionmaker(bind=engine)()
    session.add_all([
        Customer(id=1, team_id=1, account_name="Customer A", city="Beijing", creator_id="1"),
        Customer(id=2, team_id=1, account_name="Customer B", city="Beijing", creator_id="1"),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _contact(name: str, mobile: str) -> ContactCreate:
    return ContactCreate(name=name, gender="1", position="CTO", mobile=mobile)


def _title(taxpayer_id: str, title: str = "Title") -> InvoiceTitleCreate:
    return InvoiceTitleCreate(title_type="COMPANY", title=title, taxpayer_id=taxpayer_id)


def _deployment(server_address: str, customer_id: int = 1) -> DeploymentInfoInternalCreate:
    return DeploymentInfoInternalCreate(customer_id=customer_id, deployment_name="Prod", server_address=server_address)


@pytest.mark.parametrize(("raw", "expected"), [
    ("138 0000 5678", "13800005678"),
    ("138-0000-5678", "13800005678"),
    ("+86 13800005678", "13800005678"),
    ("8613800005678", "13800005678"),
    ("861380000567", "861380000567"),
])
def test_normalize_mobile(raw, expected):
    assert normalize_mobile(raw) == expected


def test_normalize_taxpayer_id_ignores_case_and_spacing():
    assert normalize_taxpayer_id(" 91310115ma1k 4abc12 ") == "91310115MA1K4ABC12"


def test_server_address_key_ignores_host_case_and_trailing_slash_but_not_port_or_scheme():
    key = server_address_dedupe_key("https://crm.example.com:8891")
    assert server_address_dedupe_key("https://CRM.example.com:8891/") == key
    assert server_address_dedupe_key("https://crm.example.com:8892") != key
    assert server_address_dedupe_key("http://crm.example.com:8891") != key
    assert server_address_dedupe_key("https://crm.example.com:8891/Path") != server_address_dedupe_key(
        "https://crm.example.com:8891/path"
    )


@pytest.mark.parametrize("mobile", ["138 0000 5678", "138-0000-5678", "+86 13800005678"])
def test_contact_create_blocks_same_mobile_in_customer(db, mobile):
    existing = contact_crud.create(db, _contact("Zhang San", "13800005678"), customer_id=1, team_id=1)

    with pytest.raises(DuplicateRecordError) as caught:
        contact_crud.create(db, _contact("Li Si", mobile), customer_id=1, team_id=1)

    assert caught.value.status_code == 409
    assert caught.value.payload() == {"entity": "contact", "existing_id": existing.id, "existing_name": "Zhang San"}
    assert db.query(Contact).count() == 1


def test_contact_same_mobile_allowed_for_other_customer_and_stored_normalized(db):
    contact_crud.create(db, _contact("Zhang San", "13800005678"), customer_id=1, team_id=1)
    other = contact_crud.create(db, _contact("Li Si", "+86 138-0000-5678"), customer_id=2, team_id=1)

    assert other.mobile == "13800005678"


def test_contact_update_excludes_self_and_blocks_other_contacts_mobile(db):
    first = contact_crud.create(db, _contact("Zhang San", "13800005678"), customer_id=1, team_id=1)
    second = contact_crud.create(db, _contact("Li Si", "13900001111"), customer_id=1, team_id=1)

    reformatted = contact_crud.update(db, first, ContactUpdate(mobile="138 0000 5678", name="Zhang"))
    assert (reformatted.mobile, reformatted.name) == ("13800005678", "Zhang")

    with pytest.raises(DuplicateRecordError):
        contact_crud.update(db, second, ContactUpdate(mobile="+86 13800005678"))
    db.expire_all()
    assert db.get(Contact, second.id).mobile == "13900001111"


def test_internal_contacts_with_empty_mobile_never_collide(db):
    for name in ("Lead A", "Lead B"):
        contact_crud.add(
            db, values={"name": name, "mobile": ""}, customer_id=1, team_id=1, is_primary=False, commit=True
        )

    assert [c.mobile_dedupe_key for c in db.query(Contact).all()] == [None, None]


def test_contact_race_maps_unique_violation_to_duplicate(db, monkeypatch):
    existing = contact_crud.create(db, _contact("Zhang San", "13800005678"), customer_id=1, team_id=1)
    real_find = type(contact_crud).find_duplicate
    calls = []

    def find_after_race(*args, **kwargs):
        calls.append(1)
        return None if len(calls) == 1 else real_find(*args, **kwargs)

    monkeypatch.setattr(contact_crud, "find_duplicate", find_after_race)

    with pytest.raises(DuplicateRecordError) as caught:
        contact_crud.create(db, _contact("Li Si", "138-0000-5678"), customer_id=1, team_id=1)

    assert caught.value.existing_id == existing.id
    assert db.query(Contact).count() == 1


def test_invoice_title_blocks_taxpayer_id_regardless_of_case_and_spacing(db):
    existing = invoice_title_crud.create(db, 1, _title("91310115MA1K4ABC12", "Apifox"), team_id=1)

    with pytest.raises(DuplicateRecordError) as caught:
        invoice_title_crud.create(db, 1, _title("91310115ma1k4abc12 "), team_id=1)

    assert caught.value.payload() == {"entity": "invoice_title", "existing_id": existing.id, "existing_name": "Apifox"}
    assert caught.value.detail == "该客户下已有这个税号的开票抬头：Apifox"  # noqa: RUF001
    assert invoice_title_crud.create(db, 2, _title("91310115ma1k4abc12"), team_id=1).taxpayer_id == (
        "91310115MA1K4ABC12"
    )


def test_invoice_title_update_excludes_self_and_blocks_other_title(db):
    first = invoice_title_crud.create(db, 1, _title("TAX-A"), team_id=1)
    second = invoice_title_crud.create(db, 1, _title("TAX-B"), team_id=1)

    assert invoice_title_crud.update(db, first, InvoiceTitleUpdate(taxpayer_id="tax-a")).taxpayer_id == "TAX-A"
    with pytest.raises(DuplicateRecordError):
        invoice_title_crud.update(db, second, InvoiceTitleUpdate(taxpayer_id="tax-a"))


def test_deployment_blocks_same_address_but_allows_other_port_or_scheme(db):
    existing = deployment_info_crud.create(db, 1, _deployment("https://crm.example.com:8891"))

    with pytest.raises(DuplicateRecordError) as caught:
        deployment_info_crud.create(db, 1, _deployment("https://CRM.example.com:8891/"))
    assert caught.value.payload()["existing_id"] == existing.id

    deployment_info_crud.create(db, 1, _deployment("https://crm.example.com:8892"))
    deployment_info_crud.create(db, 1, _deployment("http://crm.example.com:8891"))
    stored = deployment_info_crud.create(db, 1, _deployment("https://CRM.example.com:8891/", customer_id=2))
    assert stored.server_address == "https://CRM.example.com:8891/"


def test_deployment_update_excludes_self_and_blocks_other_deployment(db):
    first = deployment_info_crud.create(db, 1, _deployment("https://a.example.com"))
    second = deployment_info_crud.create(db, 1, _deployment("https://b.example.com"))

    deployment_info_crud.update(db, 1, first.id, DeploymentInfoUpdate(server_address="https://A.example.com/"))
    with pytest.raises(DuplicateRecordError):
        deployment_info_crud.update(db, 1, second.id, DeploymentInfoUpdate(server_address="https://a.example.com"))


def test_duplicate_error_response_carries_existing_record():
    request = Request({
        "type": "http", "method": "POST", "path": "/api/v1/customers/1/contacts", "headers": [],
        "query_string": b"", "server": ("testserver", 80), "scheme": "http",
    })
    error = DuplicateRecordError(entity="contact", existing_id=7, existing_name="Zhang San", detail="dup")

    response = asyncio.run(app_exception_handler(request, error))

    assert response.status_code == 409
    body = json.loads(response.body)
    assert body["error_code"] == "DUPLICATE_RECORD"
    assert body["duplicate"] == {"entity": "contact", "existing_id": 7, "existing_name": "Zhang San"}


def _raw_contact(db, contact_id: int, mobile: str, *, created: datetime, is_primary: int = 0, reports_to=None):
    """Insert pre-171 duplicate data that the ORM hook would otherwise reject."""
    db.execute(
        Contact.__table__.insert().values(
            id=contact_id, team_id=1, customer_id=1, name=f"C{contact_id}", mobile=mobile,
            mobile_dedupe_key=normalize_mobile(mobile) or None, is_primary=is_primary, is_decision_maker=0,
            post_commit_revision=1, reports_to=reports_to, created_time=created, updated_time=created,
        )
    )


def _drop_contact_unique_index(db) -> None:
    db.execute(text("DROP INDEX uq_contact_customer_mobile_key"))


def test_merge_script_keeps_referenced_record_and_moves_references_and_primary_flag(db):
    _drop_contact_unique_index(db)
    _raw_contact(db, 1, "13800005678", created=datetime(2024, 1, 1), is_primary=1)
    _raw_contact(db, 2, "138 0000 5678", created=datetime(2025, 1, 1))
    _raw_contact(db, 3, "13900001111", created=datetime(2025, 1, 1), reports_to=2)
    _raw_contact(db, 4, "13700002222", created=datetime(2025, 1, 1), reports_to=1)
    db.commit()
    conn = db.connection()

    plan = dedupe_script.export_plan(conn)
    # Both are referenced, so the earlier one wins.
    assert {row.record_id: (row.action, row.ref_count) for row in plan} == {1: ("keep", 1), 2: ("delete", 1)}

    report = dedupe_script.apply_plan(conn, plan)

    assert (report.groups, report.deleted) == (1, 1)
    remaining = {c.id: c for c in db.query(Contact).all()}
    assert set(remaining) == {1, 3, 4}
    assert remaining[1].is_primary == 1
    assert (remaining[3].reports_to, remaining[4].reports_to) == (1, 1)


def test_merge_script_prefers_referenced_record_over_earlier_one(db):
    _drop_contact_unique_index(db)
    _raw_contact(db, 1, "13800005678", created=datetime(2024, 1, 1), is_primary=1)
    _raw_contact(db, 2, "13800005678", created=datetime(2025, 1, 1))
    _raw_contact(db, 3, "13900001111", created=datetime(2025, 1, 1), reports_to=2)
    db.commit()
    conn = db.connection()

    dedupe_script.apply_plan(conn, dedupe_script.export_plan(conn))

    remaining = {c.id: c for c in db.query(Contact).all()}
    assert set(remaining) == {2, 3}
    assert remaining[2].is_primary == 1
    assert remaining[3].reports_to == 2


def test_merge_script_refuses_drifted_plan(db):
    _drop_contact_unique_index(db)
    _raw_contact(db, 1, "13800005678", created=datetime(2024, 1, 1))
    _raw_contact(db, 2, "13800005678", created=datetime(2025, 1, 1))
    db.commit()
    conn = db.connection()
    plan = dedupe_script.export_plan(conn)
    _raw_contact(db, 3, "138 0000 5678", created=datetime(2025, 6, 1))

    with pytest.raises(dedupe_script.PlanError, match="drifted"):
        dedupe_script.apply_plan(conn, plan)
