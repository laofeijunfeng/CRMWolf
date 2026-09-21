"""Add independent DataTable export permissions.

Merges the two 136 heads and seeds nine export permissions granted to
TEAM_ADMIN only.

Revision ID: 137_datatable_export_permissions
Revises: ("136_business_journey_saved_views", "136_customer_initial_enrichment")
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "137_datatable_export_permissions"
down_revision: str | Sequence[str] | None = (
    "136_business_journey_saved_views",
    "136_customer_initial_enrichment",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, code, resource, action, scope)
EXPORT_PERMISSIONS = [
    ("导出客户", "customer:export", "customer", "export", None),
    ("导出客户追踪", "follow_up_task:export", "follow_up_task", "export", None),
    ("导出线索", "lead:export", "lead", "export", None),
    ("导出商机", "opportunity:export", "opportunity", "export", None),
    ("导出合同", "contract:export", "contract", "export", None),
    ("导出回款计划", "payment:plan:export", "payment_plan", "export", None),
    ("导出回款记录", "payment:record:export", "payment_record", "export", None),
    ("导出发票", "invoice:export", "invoice", "export", None),
    ("导出审批", "approval:export", "approval", "export", None),
]

ROLE_PERMISSION_CODES = {
    "TEAM_ADMIN": [item[1] for item in EXPORT_PERMISSIONS],
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


def _permissions_has_is_active() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("permissions"):
        return False
    return any(column["name"] == "is_active" for column in inspector.get_columns("permissions"))


def upgrade() -> None:
    if not (
        _table_exists("permissions")
        and _table_exists("roles")
        and _table_exists("role_permissions")
    ):
        return

    conn = op.get_bind()
    has_is_active = _permissions_has_is_active()
    permission_columns = "name, code, resource, action, scope"
    permission_values = ":name, :code, :resource, :action, :scope"
    if has_is_active:
        permission_columns += ", is_active"
        permission_values += ", 1"

    for name, code, resource, action, scope in EXPORT_PERMISSIONS:
        conn.execute(
            sa.text(f"""
                INSERT INTO permissions ({permission_columns})
                SELECT {permission_values}
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
            """),
            {"name": name, "code": code, "resource": resource, "action": action, "scope": scope},
        )

    for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
        conn.execute(
            sa.text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r
                JOIN permissions p ON p.code IN :permission_codes
                WHERE r.code = :role_code
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permissions rp
                      WHERE rp.role_id = r.id AND rp.permission_id = p.id
                  )
            """).bindparams(sa.bindparam("permission_codes", expanding=True)),
            {"role_code": role_code, "permission_codes": permission_codes},
        )


def downgrade() -> None:
    if not (_table_exists("permissions") and _table_exists("role_permissions")):
        return

    conn = op.get_bind()
    permission_codes = [item[1] for item in EXPORT_PERMISSIONS]
    conn.execute(
        sa.text("""
            DELETE FROM role_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions WHERE code IN :permission_codes
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
