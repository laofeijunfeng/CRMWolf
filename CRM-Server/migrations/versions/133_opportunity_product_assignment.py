"""Add opportunity product and module assignment."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "133_opportunity_product_assignment"
down_revision: str | None = "132_product_module_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_opportunities",
        sa.Column("product_id", sa.BigInteger(), nullable=True, comment="关联产品ID"),
    )
    op.create_index("idx_opportunity_product_id", "crm_opportunities", ["product_id"])
    op.create_foreign_key(
        "fk_crm_opportunities_product_id",
        "crm_opportunities",
        "crm_products",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "crm_opportunity_product_modules",
        sa.Column("opportunity_id", sa.BigInteger(), nullable=False, comment="商机ID"),
        sa.Column("product_module_id", sa.BigInteger(), nullable=False, comment="产品模块ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm_opportunities.id"],
            ondelete="CASCADE",
            name="fk_opportunity_product_modules_opportunity",
        ),
        sa.ForeignKeyConstraint(
            ["product_module_id"],
            ["crm_product_modules.id"],
            ondelete="RESTRICT",
            name="fk_opportunity_product_modules_module",
        ),
        sa.PrimaryKeyConstraint("opportunity_id", "product_module_id"),
        sa.UniqueConstraint("opportunity_id", "product_module_id", name="uq_opportunity_product_module"),
        comment="商机所选产品模块",
    )
    op.create_index(
        "idx_opportunity_product_modules_team",
        "crm_opportunity_product_modules",
        ["team_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_opportunity_product_modules_team", table_name="crm_opportunity_product_modules")
    op.drop_table("crm_opportunity_product_modules")
    op.drop_constraint("fk_crm_opportunities_product_id", "crm_opportunities", type_="foreignkey")
    op.drop_index("idx_opportunity_product_id", table_name="crm_opportunities")
    op.drop_column("crm_opportunities", "product_id")
