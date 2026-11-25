"""Add dedupe keys to customer contacts, invoice titles and deployments (CRM-164).

- crm_contacts.mobile_dedupe_key / crm_invoice_titles.taxpayer_dedupe_key /
  crm_deployment_infos.server_address_dedupe_key, each with a plain
  (customer_id, key) index.
- Rewrites existing mobile and taxpayer_id to their normalized form (every change is
  logged with before/after values) and backfills all keys. Deletes nothing.
- 172_customer_child_unique_keys makes the indexes unique once duplicates are merged
  with scripts/dedupe_customer_children.py.

Revision ID: 171_customer_child_dedupe_keys
Revises: 170_owner_transfer_notifications
"""

import logging
from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from app.utils.dedupe_normalizer import (
    mobile_dedupe_key,
    normalize_mobile,
    normalize_taxpayer_id,
    server_address_dedupe_key,
    taxpayer_dedupe_key,
)

revision: str = "171_customer_child_dedupe_keys"
down_revision: str | None = "170_owner_transfer_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

_Normalizer = Callable[[str | None], str]
_KeyBuilder = Callable[[str | None], str | None]

# (table, value column, key column, key length, plain index, value normalizer or None, key builder)
_TARGETS: tuple[tuple[str, str, str, int, str, _Normalizer | None, _KeyBuilder], ...] = (
    (
        "crm_contacts", "mobile", "mobile_dedupe_key", 20,
        "idx_contact_customer_mobile_key", normalize_mobile, mobile_dedupe_key,
    ),
    (
        "crm_invoice_titles", "taxpayer_id", "taxpayer_dedupe_key", 100,
        "idx_invoice_title_customer_taxpayer_key", normalize_taxpayer_id, taxpayer_dedupe_key,
    ),
    (
        "crm_deployment_infos", "server_address", "server_address_dedupe_key", 500,
        "idx_deployment_customer_address_key", None, server_address_dedupe_key,
    ),
)


def _backfill(
    table: str,
    value_column: str,
    key_column: str,
    normalize: Callable[[str | None], str] | None,
    build_key: Callable[[str | None], str | None],
) -> None:
    bind = op.get_bind()
    rows = bind.execute(text(f"SELECT id, {value_column} FROM {table}")).all()
    params: list[dict[str, object]] = []
    rewritten = 0
    for row_id, raw in rows:
        value = normalize(raw) if normalize is not None else raw
        if normalize is not None and value != raw:
            rewritten += 1
            logger.info("CRM-164 %s.%s id=%s: %r -> %r", table, value_column, row_id, raw, value)
        params.append({"id": row_id, "value": value, "key": build_key(value)})
    if params:
        bind.execute(
            text(f"UPDATE {table} SET {value_column} = :value, {key_column} = :key WHERE id = :id"),
            params,
        )
    logger.info("CRM-164 %s: %d rows keyed, %d %s values normalized", table, len(params), rewritten, value_column)


def upgrade() -> None:
    for table, value_column, key_column, length, index_name, normalize, build_key in _TARGETS:
        op.add_column(table, sa.Column(key_column, sa.String(length), nullable=True))
        _backfill(table, value_column, key_column, normalize, build_key)
        op.create_index(index_name, table, ["customer_id", key_column])


def downgrade() -> None:
    # Normalized mobile / taxpayer_id values are kept: the originals are only in the upgrade log.
    for table, _value_column, key_column, _length, index_name, _normalize, _build_key in reversed(_TARGETS):
        op.drop_index(index_name, table_name=table)
        op.drop_column(table, key_column)
