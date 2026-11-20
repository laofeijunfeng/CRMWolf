"""Support permanent OFFICIAL licenses (CRM-148).

Permanent ⇒ license_type == 'OFFICIAL' AND expiry date IS NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "166_license_permanent"
down_revision: str | None = "165_license_application_product"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "crm_license_applications",
        "expiry_date",
        existing_type=sa.Date(),
        nullable=True,
        existing_comment="到期时间",
    )
    op.add_column(
        "crm_license_applications",
        sa.Column(
            "is_permanent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否永久授权（仅正式 License，永久时到期时间为空）",
        ),
    )
    op.add_column(
        "crm_customers",
        sa.Column(
            "license_is_permanent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="客户 License 是否永久（自动更新，永久时到期时间为空）",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    permanent_applications = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM crm_license_applications "
            "WHERE is_permanent IS TRUE OR expiry_date IS NULL"
        )
    ).scalar_one()
    permanent_customers = bind.execute(
        sa.text("SELECT COUNT(*) FROM crm_customers WHERE license_is_permanent IS TRUE")
    ).scalar_one()
    if permanent_applications or permanent_customers:
        raise RuntimeError(
            "Cannot downgrade 166_license_permanent: "
            f"{permanent_applications} license application(s) and "
            f"{permanent_customers} customer(s) are permanent or have no expiry date. "
            "Resolve these rows manually before downgrading."
        )

    op.drop_column("crm_customers", "license_is_permanent")
    op.drop_column("crm_license_applications", "is_permanent")
    op.alter_column(
        "crm_license_applications",
        "expiry_date",
        existing_type=sa.Date(),
        nullable=False,
        existing_comment="到期时间",
    )
