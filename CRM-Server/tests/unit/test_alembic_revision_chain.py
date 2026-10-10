"""The approved proposal-policy revision stays on the linear Alembic chain."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_revision_151_is_present_and_descends_from_150() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(config)

    revision = script.get_revision("151_assistant_proposal_policy")

    assert revision.down_revision == "151_customer_license_authorized_users"
    assert script.get_current_head() == "153_remove_customer_profile_complete"
