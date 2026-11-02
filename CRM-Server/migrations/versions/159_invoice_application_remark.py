"""Add an optional remark to invoice applications.

Revision ID: 159_invoice_application_remark
Revises: 158_assistant_model_failure_feedback
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "159_invoice_application_remark"
down_revision: str | None = "158_assistant_model_failure_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "crm_invoice_applications"
_COLUMN = "remark"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _table_exists(_TABLE) or _column_exists(_TABLE, _COLUMN):
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(length=500), nullable=True, comment="申请备注"),
    )


def downgrade() -> None:
    if _table_exists(_TABLE) and _column_exists(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
