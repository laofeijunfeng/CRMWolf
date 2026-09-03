"""Canonicalize persisted historical follow-up confirmation questions.

The old confirmation flow asked about postponing/cancelling a task.  The
canonical flow only asks whether the task is complete.  This is a one-time
cutover of persisted snapshots; application reads must not carry a legacy
mapping forever.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence as SequenceType

revision: str = "127_canonicalize_follow_up_confirmation_questions"
down_revision: str | None = "126_expand_customer_profile_publication_status"
branch_labels: str | SequenceType[str] | None = None
depends_on: str | SequenceType[str] | None = None

_CASE_TABLE = "crm_follow_up_task_confirmation_cases"
_DELIVERY_TABLE = "crm_follow_up_task_confirmation_prompt_deliveries"
_MESSAGE_TABLE = "crm_agent_messages"
_LEGACY_SUFFIXES = (
    "需要延期吗?",
    "需要延期吗？",
    "不需要继续跟进了吗?",
    "不需要继续跟进了吗？",
)
_CANONICAL_SUFFIX = "现在完成了吗?"


def _canonicalize_question(value: str) -> str:
    text = str(value or "").strip()
    for suffix in _LEGACY_SUFFIXES:
        if text.endswith(suffix):
            return f"{text[:-len(suffix)]}{_CANONICAL_SUFFIX}"
    return text


def _rewrite_delivery_payload(value: Any) -> tuple[Any, bool]:
    if isinstance(value, Mapping):
        changed = False
        rewritten: dict[Any, Any] = {}
        for key, item in value.items():
            if key == "question_text" and isinstance(item, str):
                updated = _canonicalize_question(item)
            else:
                updated, item_changed = _rewrite_delivery_payload(item)
                changed = changed or item_changed
            changed = changed or updated != item
            rewritten[key] = updated
        return rewritten, changed
    if isinstance(value, list):
        rewritten_items = []
        changed = False
        for item in value:
            updated, item_changed = _rewrite_delivery_payload(item)
            rewritten_items.append(updated)
            changed = changed or item_changed
        return rewritten_items, changed
    return value, False


def _rewrite_message_ui(value: Any) -> tuple[Any, bool]:
    if isinstance(value, Mapping):
        changed = False
        rewritten: dict[Any, Any] = {}
        compact_completion = value.get("presentation") == "COMPACT_TASK_COMPLETION"
        for key, item in value.items():
            if compact_completion and key == "prompt" and isinstance(item, str):
                updated = _canonicalize_question(item)
            else:
                updated, item_changed = _rewrite_message_ui(item)
                changed = changed or item_changed
            changed = changed or updated != item
            rewritten[key] = updated
        return rewritten, changed
    if isinstance(value, list):
        rewritten_items = []
        changed = False
        for item in value:
            updated, item_changed = _rewrite_message_ui(item)
            rewritten_items.append(updated)
            changed = changed or item_changed
        return rewritten_items, changed
    return value, False


def _table_columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    if not sa.inspect(bind).has_table(table_name):
        return set()
    return {str(column["name"]) for column in sa.inspect(bind).get_columns(table_name)}


def _rewrite_scalar_questions(bind: sa.engine.Connection) -> int:
    columns = _table_columns(bind, _CASE_TABLE)
    if "id" not in columns or "question_text" not in columns:
        return 0
    table = sa.table(
        _CASE_TABLE,
        sa.column("id", sa.BigInteger()),
        sa.column("question_text", sa.Text()),
    )
    rows = bind.execute(sa.select(table.c.id, table.c.question_text)).mappings().all()
    changed = 0
    for row in rows:
        updated = _canonicalize_question(row["question_text"])
        if updated != row["question_text"]:
            bind.execute(
                table.update().where(table.c.id == row["id"]).values(question_text=updated)
            )
            changed += 1
    return changed


def _rewrite_json_column(
    bind: sa.engine.Connection,
    *,
    table_name: str,
    column_name: str,
    rewrite: Any,
) -> int:
    columns = _table_columns(bind, table_name)
    if "id" not in columns or column_name not in columns:
        return 0
    table = sa.table(
        table_name,
        sa.column("id", sa.BigInteger()),
        sa.column(column_name, sa.JSON()),
    )
    rows = bind.execute(
        sa.select(table.c.id, table.c[column_name]).where(table.c[column_name].is_not(None))
    ).mappings().all()
    changed = 0
    for row in rows:
        updated, row_changed = rewrite(row[column_name])
        if row_changed:
            bind.execute(
                table.update().where(table.c.id == row["id"]).values({column_name: updated})
            )
            changed += 1
    return changed


def migrate_confirmation_question_data(bind: sa.engine.Connection | None = None) -> dict[str, int]:
    """Rewrite all persisted confirmation-question snapshots exactly once."""

    connection = bind or op.get_bind()
    return {
        "cases": _rewrite_scalar_questions(connection),
        "deliveries": _rewrite_json_column(
            connection,
            table_name=_DELIVERY_TABLE,
            column_name="payload_json",
            rewrite=_rewrite_delivery_payload,
        ),
        "messages": _rewrite_json_column(
            connection,
            table_name=_MESSAGE_TABLE,
            column_name="ui_json",
            rewrite=_rewrite_message_ui,
        ),
    }


def upgrade() -> None:
    migrate_confirmation_question_data()


def downgrade() -> None:
    # The old wording is intentionally not restored.  This revision is a
    # destructive vocabulary cutover and retaining the legacy mapping would
    # recreate the compatibility debt this migration removes.
    pass
