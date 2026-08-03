from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.business_number_generator import BusinessNumberGenerator


def _session():
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    for table_name, number_column in (
        ("crm_invoice_applications", "application_number"),
        ("crm_license_applications", "application_number"),
        ("crm_opportunities", "opportunity_number"),
    ):
        session.execute(text(f"""
            CREATE TABLE {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {number_column} VARCHAR(50)
            )
        """))
    session.commit()
    return session, engine


def test_generate_unified_invoice_license_and_opportunity_numbers():
    db, engine = _session()
    today = datetime.now().strftime("%Y%m%d")

    try:
        assert BusinessNumberGenerator.generate("INV", db) == f"INV{today}0001"
        db.execute(
            text("INSERT INTO crm_invoice_applications (application_number) VALUES (:number)"),
            {"number": f"INV{today}0001"},
        )
        db.commit()

        assert BusinessNumberGenerator.generate("INV", db) == f"INV{today}0002"
        assert BusinessNumberGenerator.generate("LIC", db) == f"LIC{today}0001"
        assert BusinessNumberGenerator.generate("OPP", db) == f"OPP{today}0001"
    finally:
        db.close()
        engine.dispose()
