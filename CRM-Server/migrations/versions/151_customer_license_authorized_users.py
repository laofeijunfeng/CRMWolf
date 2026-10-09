"""Backfill customer License authorization snapshots from issued applications."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "151_customer_license_authorized_users"
down_revision: str | None = "150_profile_version_attestation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_customers",
        sa.Column(
            "license_authorized_users",
            sa.Integer(),
            nullable=True,
            comment="客户 License 授权人数（自动更新）",
        ),
    )

    bind = op.get_bind()
    customers = sa.table(
        "crm_customers",
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("license_type", sa.String(length=20)),
        sa.column("license_expiry_date", sa.Date()),
        sa.column("license_authorized_users", sa.Integer()),
    )
    applications = sa.table(
        "crm_license_applications",
        sa.column("id", sa.BigInteger()),
        sa.column("team_id", sa.BigInteger()),
        sa.column("customer_id", sa.BigInteger()),
        sa.column("expiry_date", sa.Date()),
        sa.column("license_type", sa.String(length=20)),
        sa.column("authorized_users", sa.Integer()),
        sa.column("status", sa.String(length=20)),
        sa.column("last_modified_time", sa.DateTime()),
    )

    customer_rows = bind.execute(
        sa.select(customers.c.id, customers.c.team_id)
    ).mappings()
    for customer in customer_rows:
        winner = bind.execute(
            sa.select(
                applications.c.license_type,
                applications.c.authorized_users,
                applications.c.expiry_date,
            )
            .where(
                applications.c.customer_id == customer["id"],
                applications.c.team_id == customer["team_id"],
                applications.c.status == "ISSUED",
            )
            .order_by(
                applications.c.expiry_date.desc(),
                applications.c.last_modified_time.desc(),
                applications.c.id.desc(),
            )
            .limit(1)
        ).mappings().first()

        values = {
            "license_type": winner["license_type"] if winner is not None else None,
            "license_authorized_users": winner["authorized_users"] if winner is not None else None,
            "license_expiry_date": winner["expiry_date"] if winner is not None else None,
        }
        bind.execute(
            customers.update()
            .where(customers.c.id == customer["id"])
            .values(**values)
        )


def downgrade() -> None:
    op.drop_column("crm_customers", "license_authorized_users")
