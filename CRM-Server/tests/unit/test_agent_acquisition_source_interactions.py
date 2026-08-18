"""Agent interaction options for configurable acquisition sources."""

from sqlalchemy import BigInteger, create_engine, text as sql_text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.acquisition_source import AcquisitionSource
from app.services.acquisition_source_service import seed_default_sources
from app.services.agent.interactions import _acquisition_source_options, _fields_for_missing


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


def test_acquisition_source_options_fallback_to_empty_without_team():
    options = _acquisition_source_options(None, None)

    assert options == []


def test_missing_lead_and_customer_source_fields_use_empty_options_without_db():
    lead_fields = _fields_for_missing("lead", ["source"])
    customer_fields = _fields_for_missing("customer", ["source"])

    assert lead_fields[0]["key"] == "source"
    assert lead_fields[0]["type"] == "select"
    assert lead_fields[0].get("options", []) == []
    assert customer_fields[0].get("options", []) == []


def test_acquisition_source_options_fallback_when_session_is_not_queryable():
    options = _acquisition_source_options(object(), 1)

    assert options == []


def test_acquisition_source_options_fallback_when_source_table_missing_without_poisoning_transaction():
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

        options = _acquisition_source_options(db, 1)

        assert options == []

        db.commit()
        assert db.execute(sql_text("SELECT body FROM notes")).scalar() == "keep-me"
    finally:
        db.close()
        engine.dispose()


def test_acquisition_source_options_use_public_id_when_table_exists():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[AcquisitionSource.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_default_sources(db, team_id=1, created_by="1")
        db.commit()

        options = _acquisition_source_options(db, 1)
        lead_fields = _fields_for_missing("lead", ["source"], db=db, team_id=1)

        assert options[0]["label"] == "线上注册"
        assert options[-1]["label"] == "其他"
        assert all(item["value"].startswith("acq_") for item in options)
        assert lead_fields[0]["options"] == options
    finally:
        db.close()
        engine.dispose()
