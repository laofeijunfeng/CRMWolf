"""add invoice reissue permissions

Revision ID: 078_invoice_reissue_permissions
Revises: 077_default_invoice_reissue_approval_flow
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "078_invoice_reissue_permissions"
down_revision: str | None = "077_default_invoice_reissue_approval_flow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVOICE_REISSUE_PERMISSIONS = [
    ("查看所有发票重开申请", "invoice_reissue:view:all", "view", "all"),
    ("查看自己的发票重开申请", "invoice_reissue:view:own", "view", "own"),
    ("创建发票重开申请", "invoice_reissue:create", "create", None),
    ("提交发票重开申请", "invoice_reissue:submit", "submit", None),
    ("撤回发票重开申请", "invoice_reissue:withdraw", "withdraw", None),
    ("审批发票重开申请", "invoice_reissue:approve", "approve", None),
    ("审批自己的发票重开申请", "invoice_reissue:approve:own", "approve", "own"),
    ("审批所有发票重开申请", "invoice_reissue:approve:all", "approve", "all"),
]

ROLE_PERMISSION_CODES = {
    "TEAM_ADMIN": [item[1] for item in INVOICE_REISSUE_PERMISSIONS],
    "SALES_DIRECTOR": [
        "invoice_reissue:view:all",
        "invoice_reissue:view:own",
        "invoice_reissue:create",
        "invoice_reissue:submit",
        "invoice_reissue:withdraw",
        "invoice_reissue:approve:own",
    ],
    "SALES_MEMBER": [
        "invoice_reissue:view:own",
        "invoice_reissue:create",
        "invoice_reissue:submit",
        "invoice_reissue:withdraw",
    ],
    "FINANCE": [
        "invoice_reissue:view:all",
        "invoice_reissue:view:own",
        "invoice_reissue:create",
        "invoice_reissue:submit",
        "invoice_reissue:withdraw",
        "invoice_reissue:approve",
    ],
}


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        rows = conn.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).all()
        return bool(rows)

    return (
        conn.execute(
            sa.text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
            """),
            {"table_name": table_name},
        ).scalar()
        > 0
    )


def upgrade() -> None:
    if not (_table_exists("permissions") and _table_exists("roles") and _table_exists("role_permissions")):
        return

    conn = op.get_bind()

    for name, code, action, scope in INVOICE_REISSUE_PERMISSIONS:
        exists = conn.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code LIMIT 1"),
            {"code": code},
        ).first()
        if exists:
            continue

        conn.execute(
            sa.text("""
                INSERT INTO permissions (name, code, resource, action, scope)
                VALUES (:name, :code, 'invoice_reissue', :action, :scope)
            """),
            {"name": name, "code": code, "action": action, "scope": scope},
        )

    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        role_id = conn.execute(
            sa.text("SELECT id FROM roles WHERE code = :role_code LIMIT 1"),
            {"role_code": role_code},
        ).scalar()
        if role_id is None:
            continue

        for permission_code in permission_codes:
            permission_id = conn.execute(
                sa.text("SELECT id FROM permissions WHERE code = :code LIMIT 1"),
                {"code": permission_code},
            ).scalar()
            if permission_id is None:
                continue

            exists = conn.execute(
                sa.text("""
                    SELECT id
                    FROM role_permissions
                    WHERE role_id = :role_id
                      AND permission_id = :permission_id
                    LIMIT 1
                """),
                {"role_id": role_id, "permission_id": permission_id},
            ).first()
            if exists:
                continue

            conn.execute(
                sa.text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (:role_id, :permission_id)
                """),
                {"role_id": role_id, "permission_id": permission_id},
            )


def downgrade() -> None:
    if not (_table_exists("permissions") and _table_exists("role_permissions")):
        return

    conn = op.get_bind()
    permission_codes = [item[1] for item in INVOICE_REISSUE_PERMISSIONS]
    conn.execute(
        sa.text("""
            DELETE FROM role_permissions
            WHERE permission_id IN (
                SELECT id
                FROM permissions
                WHERE code IN :permission_codes
            )
        """).bindparams(sa.bindparam("permission_codes", expanding=True)),
        {"permission_codes": permission_codes},
    )
    conn.execute(
        sa.text("DELETE FROM permissions WHERE code IN :permission_codes").bindparams(
            sa.bindparam("permission_codes", expanding=True)
        ),
        {"permission_codes": permission_codes},
    )
