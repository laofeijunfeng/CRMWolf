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
    assert script.get_revision("02352b41bcb6").down_revision == "153_remove_customer_profile_complete"
    assert script.get_revision("154_assistant_conversations").down_revision == "153_remove_customer_profile_complete"
    assert script.get_revision("155_assistant_message_identity").down_revision == "154_assistant_conversations"
    assert script.get_revision("156_assistant_historical_messages").down_revision == "155_assistant_message_identity"
    assert script.get_revision("157_merge_assistant_conversation_paths").down_revision == (
        "02352b41bcb6",
        "156_assistant_historical_messages",
    )
    assert script.get_revision("158_assistant_model_failure_feedback").down_revision == (
        "157_merge_assistant_conversation_paths"
    )
    assert script.get_heads() == ["158_assistant_model_failure_feedback"]
