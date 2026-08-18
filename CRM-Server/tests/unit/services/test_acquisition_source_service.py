"""Acquisition source service seams from TRD 9.1 UT-01 to UT-04."""

from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, create_engine, text as sql_text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"

from app.core.database import Base
from app.models.acquisition_source import AcquisitionSource
from app.constants.acquisition_sources import (
    SYSTEM_DEFAULT_SOURCES,
    summarize_legacy_source_backfill,
)
from app.services.acquisition_source_service import (
    AcquisitionSourceError,
    default_source_name,
    format_active_source_names,
    map_legacy_source,
    resolve_for_write,
    resolve_source_for_ai,
    resolve_write_fields_for_ai,
    seed_default_sources,
    update_source,
)

EXPECTED_SYSTEM_CODES = (
    "ONLINE_REGISTER",
    "MARKETING_ACTIVITY",
    "REFERRAL",
    "COLD_CALL",
    "WEBSITE_INQUIRY",
    "EXHIBITION",
    "OTHER",
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AcquisitionSource.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_seed_default_sources_is_idempotent(db_session):
    first = seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()
    second = seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()

    rows = (
        db_session.query(AcquisitionSource)
        .filter(AcquisitionSource.team_id == 1)
        .order_by(AcquisitionSource.sort_order)
        .all()
    )

    assert len(first) == 7
    assert len(second) == 7
    assert [row.code for row in rows] == list(EXPECTED_SYSTEM_CODES)
    assert {row.public_id for row in rows} == {row.public_id for row in first}
    assert all(row.public_id.startswith("acq_") and len(row.public_id) == 36 for row in rows)
    assert all(row.is_system == 1 and row.is_active == 1 for row in rows)


def test_seed_reuses_existing_same_name_as_system_item(db_session):
    existing = AcquisitionSource(
        public_id="acq_existingexhibition000000000000",
        team_id=1,
        code="CUSTOM_deadbeef",
        name="展会",
        is_system=0,
        is_active=1,
        sort_order=99,
        created_by="1",
    )
    db_session.add(existing)
    db_session.commit()

    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()

    rows = (
        db_session.query(AcquisitionSource)
        .filter(AcquisitionSource.team_id == 1)
        .all()
    )
    exhibition = next(row for row in rows if row.name == "展会")

    assert len(rows) == 7
    assert exhibition.id == existing.id
    assert exhibition.code == "EXHIBITION"
    assert exhibition.is_system == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("线上注册", "ONLINE_REGISTER"),
        ("ONLINE_REGISTER", "ONLINE_REGISTER"),
        ("online_register", "ONLINE_REGISTER"),
        ("客户推荐", "REFERRAL"),
        ("REFERRAL", "REFERRAL"),
        ("线索转化", "OTHER"),
        ("LEAD_CONVERSION", "OTHER"),
        ("地推", "OTHER"),
        ("", None),
        (None, None),
    ],
)
def test_map_legacy_source(raw, expected):
    assert map_legacy_source(raw) == expected


def test_resolve_for_write_hides_other_team_public_id(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    seed_default_sources(db_session, team_id=2, created_by="2")
    db_session.commit()

    other_team_row = (
        db_session.query(AcquisitionSource)
        .filter(
            AcquisitionSource.team_id == 2,
            AcquisitionSource.code == "EXHIBITION",
        )
        .one()
    )

    with pytest.raises(AcquisitionSourceError) as exc_info:
        resolve_for_write(db_session, team_id=1, public_id=other_team_row.public_id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "获客来源不存在"


def _source_by_code(db_session, team_id: int, code: str):
    return (
        db_session.query(AcquisitionSource)
        .filter(AcquisitionSource.team_id == team_id, AcquisitionSource.code == code)
        .one()
    )


def test_resolve_source_for_ai_maps_referral_alias_to_current_name(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()
    referral = _source_by_code(db_session, 1, "REFERRAL")
    update_source(
        db_session,
        team_id=1,
        public_id=referral.public_id,
        updater_id="1",
        name="朋友介绍",
    )

    resolved = resolve_source_for_ai(db_session, 1, "朋友介绍的")

    assert resolved.code == "REFERRAL"
    assert resolved.name == "朋友介绍"
    assert resolved.public_id == referral.public_id


def test_resolve_source_for_ai_uses_renamed_other_when_source_missing(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()
    other = _source_by_code(db_session, 1, "OTHER")
    update_source(
        db_session,
        team_id=1,
        public_id=other.public_id,
        updater_id="1",
        name="未分类",
    )

    resolved = resolve_source_for_ai(db_session, 1, None)

    assert resolved.code == "OTHER"
    assert resolved.name == "未分类"
    assert resolved.name != "其他"


def test_resolve_source_for_ai_falls_back_to_other_for_unknown_custom_name(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()

    resolved = resolve_source_for_ai(db_session, 1, "地推")

    assert resolved.code == "OTHER"
    assert resolved.name == "其他"
    assert (
        db_session.query(AcquisitionSource)
        .filter(AcquisitionSource.team_id == 1, AcquisitionSource.name == "地推")
        .first()
        is None
    )


def test_resolve_source_for_ai_never_writes_lead_conversion(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()

    resolved = resolve_source_for_ai(db_session, 1, "线索转化")

    assert resolved.code == "OTHER"
    assert resolved.name != "线索转化"


def test_default_source_helpers_fallback_when_session_is_not_queryable():
    fake_db = object()

    assert default_source_name(fake_db, 1) == "其他"
    assert format_active_source_names(fake_db, 1) == [
        str(item["name"]) for item in SYSTEM_DEFAULT_SOURCES
    ]


def test_default_source_helpers_fallback_when_source_table_missing_without_poisoning_transaction():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.execute(sql_text("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)"))
        db.execute(sql_text("INSERT INTO notes (body) VALUES ('keep-me')"))

        assert default_source_name(db, 1) == "其他"
        assert format_active_source_names(db, 1) == [
            str(item["name"]) for item in SYSTEM_DEFAULT_SOURCES
        ]

        db.commit()
        assert db.execute(sql_text("SELECT body FROM notes")).scalar() == "keep-me"
    finally:
        db.close()
        engine.dispose()


def test_default_source_name_follows_renamed_other(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()
    other = _source_by_code(db_session, 1, "OTHER")
    update_source(
        db_session,
        team_id=1,
        public_id=other.public_id,
        updater_id="1",
        name="未分类",
    )

    assert default_source_name(db_session, 1) == "未分类"
    assert "未分类" in format_active_source_names(db_session, 1)
    assert "其他" not in format_active_source_names(db_session, 1)


def test_resolve_write_fields_for_ai_uses_renamed_other_public_id(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()
    other = _source_by_code(db_session, 1, "OTHER")
    update_source(
        db_session,
        team_id=1,
        public_id=other.public_id,
        updater_id="1",
        name="未分类",
    )

    resolved = resolve_write_fields_for_ai(
        {"lead_name": "越秀金融", "city": "广州"},
        db_session,
        1,
    )

    assert resolved["source_public_id"] == other.public_id
    assert "source" not in resolved
    assert "其他" not in resolved.values()


def test_resolve_write_fields_for_ai_maps_spoken_other_to_public_id(db_session):
    seed_default_sources(db_session, team_id=1, created_by="1")
    db_session.commit()
    other = _source_by_code(db_session, 1, "OTHER")
    update_source(
        db_session,
        team_id=1,
        public_id=other.public_id,
        updater_id="1",
        name="未分类",
    )

    resolved = resolve_write_fields_for_ai({"source": "其他"}, db_session, 1)

    assert resolved["source_public_id"] == other.public_id
    assert "source" not in resolved


def test_resolve_write_fields_for_ai_omits_chinese_source_without_db():
    resolved = resolve_write_fields_for_ai({"source": "其他", "city": "广州"})

    assert resolved == {"city": "广州"}


def test_resolve_write_fields_for_ai_omits_chinese_source_when_table_missing_without_poisoning_transaction():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.execute(sql_text("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)"))
        db.execute(sql_text("INSERT INTO notes (body) VALUES ('keep-me')"))

        resolved = resolve_write_fields_for_ai({"source": "其他", "city": "广州"}, db, 1)

        assert resolved == {"city": "广州"}
        db.commit()
        assert db.execute(sql_text("SELECT body FROM notes")).scalar() == "keep-me"
    finally:
        db.close()
        engine.dispose()


def test_summarize_legacy_source_backfill_reports_empty_aligned_and_dirty():
    report = summarize_legacy_source_backfill([
        (1, None),
        (2, ""),
        (3, "线上注册"),
        (4, "other"),
        (5, "地推渠道"),
        (6, "自定义脏值"),
    ])

    assert report == {
        "aligned": 2,
        "empty": 2,
        "dirty": [
            {"id": 5, "original": "地推渠道"},
            {"id": 6, "original": "自定义脏值"},
        ],
    }
