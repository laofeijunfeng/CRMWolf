import importlib.util
from pathlib import Path
from types import ModuleType

from app.utils.public_id import generate_public_id, is_deal_journey_public_id


def test_generate_deal_journey_public_id_matches_pattern() -> None:
    value = generate_public_id("djy")
    assert is_deal_journey_public_id(value)


def test_is_deal_journey_public_id_rejects_internal_id_and_opportunity_id() -> None:
    assert is_deal_journey_public_id("12") is False
    assert is_deal_journey_public_id(12) is False
    assert is_deal_journey_public_id("opp_" + "a" * 32) is False
    assert is_deal_journey_public_id("") is False


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "135_deal_journey_public_ids.py"
    )
    spec = importlib.util.spec_from_file_location("deal_journey_public_ids_135", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain() -> None:
    migration = _load_migration()
    assert migration.revision == "135_deal_journey_public_ids"
    assert migration.down_revision == "134_lead_customer_product_intent"
