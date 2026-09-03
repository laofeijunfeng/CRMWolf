"""Add server-side idempotency fields for payment registration.

Revision ID: 123_payment_record_idempotency
Revises: 122_customer_activity_cutover
Create Date: 2026-09-02

The key is optional for backward compatibility.  A composite unique index
prevents two requests in the same team from creating two payment records for
the same client operation while allowing historical rows without a key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "123_payment_record_idempotency"
down_revision: str | None = "122_customer_activity_cutover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "crm_payment_records"
INDEX = "uq_payment_record_idempotency"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("idempotency_key", sa.String(length=128), nullable=True, comment="回款登记幂等键"),
    )
    op.add_column(
        TABLE,
        sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=True, comment="回款登记请求指纹"),
    )
    op.create_index(INDEX, TABLE, ["team_id", "idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "idempotency_fingerprint")
    op.drop_column(TABLE, "idempotency_key")
