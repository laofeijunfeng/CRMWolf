"""Add lead and customer product intent tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "134_lead_customer_product_intent"
down_revision: str | None = "133_opportunity_product_assignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_lead_products",
        sa.Column("lead_id", sa.BigInteger(), nullable=False, comment="线索ID"),
        sa.Column("product_id", sa.BigInteger(), nullable=False, comment="产品ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["crm_leads.id"],
            ondelete="CASCADE",
            name="fk_crm_lead_products_lead",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["crm_products.id"],
            ondelete="RESTRICT",
            name="fk_crm_lead_products_product",
        ),
        sa.PrimaryKeyConstraint("lead_id", "product_id"),
        comment="线索意向产品",
    )
    op.create_index("idx_lead_products_team", "crm_lead_products", ["team_id"])
    op.create_index("idx_lead_products_product", "crm_lead_products", ["product_id"])

    op.create_table(
        "crm_customer_products",
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户ID"),
        sa.Column("product_id", sa.BigInteger(), nullable=False, comment="产品ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["crm_customers.id"],
            ondelete="CASCADE",
            name="fk_crm_customer_products_customer",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["crm_products.id"],
            ondelete="RESTRICT",
            name="fk_crm_customer_products_product",
        ),
        sa.PrimaryKeyConstraint("customer_id", "product_id"),
        comment="客户意向产品",
    )
    op.create_index("idx_customer_products_team", "crm_customer_products", ["team_id"])
    op.create_index("idx_customer_products_product", "crm_customer_products", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_customer_products_product", table_name="crm_customer_products")
    op.drop_index("idx_customer_products_team", table_name="crm_customer_products")
    op.drop_table("crm_customer_products")
    op.drop_index("idx_lead_products_product", table_name="crm_lead_products")
    op.drop_index("idx_lead_products_team", table_name="crm_lead_products")
    op.drop_table("crm_lead_products")
