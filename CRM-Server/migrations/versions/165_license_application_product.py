"""Add the selected product to License applications."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "165_license_application_product"
down_revision: str | None = "164_assistant_follow_up_projection_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "crm_license_applications"
_INDEX = "idx_license_product_id"
_FK = "fk_crm_license_applications_product_id"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("product_id", sa.BigInteger(), nullable=True, comment="申请产品ID"))
    op.add_column(
        _TABLE,
        sa.Column("product_name", sa.String(length=100), nullable=True, comment="申请产品名称快照（授权文件标题）"),
    )
    op.create_index(_INDEX, _TABLE, ["product_id"])
    op.create_foreign_key(_FK, _TABLE, "crm_products", ["product_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "product_name")
    op.drop_column(_TABLE, "product_id")
