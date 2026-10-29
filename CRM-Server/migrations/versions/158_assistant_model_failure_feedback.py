"""Add Root model failure diagnostics to assistant conversation entries.

Revision ID: 158_assistant_model_failure_feedback
Revises: 157_merge_assistant_conversation_paths
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "158_assistant_model_failure_feedback"
down_revision: str | None = "157_merge_assistant_conversation_paths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTRY_TABLE = "crm_assistant_conversation_entries"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _table_exists(_ENTRY_TABLE):
        return
    if not _column_exists(_ENTRY_TABLE, "error_code"):
        op.add_column(_ENTRY_TABLE, sa.Column("error_code", sa.String(length=64), nullable=True))
    if not _column_exists(_ENTRY_TABLE, "error_retryable"):
        op.add_column(_ENTRY_TABLE, sa.Column("error_retryable", sa.Boolean(), nullable=True))


def downgrade() -> None:
    if not _table_exists(_ENTRY_TABLE):
        return
    if _column_exists(_ENTRY_TABLE, "error_retryable"):
        op.drop_column(_ENTRY_TABLE, "error_retryable")
    if _column_exists(_ENTRY_TABLE, "error_code"):
        op.drop_column(_ENTRY_TABLE, "error_code")
