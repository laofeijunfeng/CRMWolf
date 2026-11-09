"""Add Unicode-normalized customer name dedupe key.

Revision ID: 162_customer_name_dedupe_key
Revises: 161_ai_assistant_model_capabilities

Existing customers keep their names. Within one team, only the lowest id of a
group of equivalent names receives the key; the rest stay NULL so legacy rows
never block the unique index, while new writes are checked against them.
"""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "162_customer_name_dedupe_key"
down_revision: str | None = "161_ai_assistant_model_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "crm_customers"
COLUMN_NAME = "account_name_dedupe_key"
UNIQUE_INDEX = "uq_customer_team_name_dedupe_key"


def _dedupe_key(name: str | None) -> str | None:
    """Frozen copy of app.utils.name_normalizer.build_customer_name_dedupe_key."""
    if not name:
        return None
    n = unicodedata.normalize("NFKC", name)
    n = "".join(ch for ch in n if unicodedata.category(ch) != "Cf")
    n = " ".join(n.split())
    return n or None


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column(COLUMN_NAME, sa.String(512), nullable=True, comment="客户名称判重键: NFKC/去格式字符/统一空白"),
    )
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, team_id, account_name FROM {TABLE_NAME} ORDER BY id")).all()
    claimed: set[tuple[int, str]] = set()
    updates = []
    for row in rows:
        key = _dedupe_key(row.account_name)
        if key is None or (row.team_id, key) in claimed:
            continue
        claimed.add((row.team_id, key))
        updates.append({"id": row.id, "key": key})
    if updates:
        bind.execute(sa.text(f"UPDATE {TABLE_NAME} SET {COLUMN_NAME} = :key WHERE id = :id"), updates)
    op.create_index(UNIQUE_INDEX, TABLE_NAME, ["team_id", COLUMN_NAME], unique=True)


def downgrade() -> None:
    op.drop_index(UNIQUE_INDEX, table_name=TABLE_NAME)
    op.drop_column(TABLE_NAME, COLUMN_NAME)
