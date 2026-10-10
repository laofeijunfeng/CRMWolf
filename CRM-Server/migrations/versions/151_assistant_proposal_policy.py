"""Add the per-team assistant proposal gate and explicit operator grant.

Revision ID: 151_assistant_proposal_policy
Revises: 151_customer_license_authorized_users
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "151_assistant_proposal_policy"
down_revision: str | None = "151_customer_license_authorized_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_CODE = "assistant:proposals:manage:team"
ROLE_CODE = "ASSISTANT_PROPOSAL_OPERATOR"


def upgrade() -> None:
    op.create_table(
        "crm_assistant_proposal_policies",
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("generation", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_time", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "crm_assistant_proposal_policy_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_assistant_proposal_policy_audit_team",
        "crm_assistant_proposal_policy_audit",
        ["team_id", "id"],
    )

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not all(inspector.has_table(table) for table in ("permissions", "roles", "role_permissions")):
        return
    permission_columns = "name, code, resource, action, scope"
    permission_values = ":name, :code, 'assistant_proposal', 'manage', 'team'"
    if "is_active" in {column["name"] for column in inspector.get_columns("permissions")}:
        permission_columns += ", is_active"
        permission_values += ", 1"
    connection.execute(
        sa.text(f"""
            INSERT INTO permissions ({permission_columns})
            SELECT {permission_values}
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
        """),
        {"name": "管理团队助手提案", "code": PERMISSION_CODE},
    )
    connection.execute(
        sa.text("""
            INSERT INTO roles (name, code, description)
            SELECT :name, :code, :description
            WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = :code)
        """),
        {"name": "助手提案操作员", "code": ROLE_CODE, "description": "仅管理本团队的助手提案启停"},
    )
    connection.execute(
        sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
            WHERE r.code = :role_code AND p.code = :permission_code
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """),
        {"role_code": ROLE_CODE, "permission_code": PERMISSION_CODE},
    )


def downgrade() -> None:
    connection = op.get_bind()
    # A downgrade must not silently erase an enabled gate or its actor audit trail.
    for table in ("crm_assistant_proposal_policies", "crm_assistant_proposal_policy_audit"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None:
            raise RuntimeError(f"Archive and remove {table} rows before downgrading proposal policy")

    inspector = sa.inspect(connection)
    if all(inspector.has_table(table) for table in ("permissions", "roles", "role_permissions")):
        connection.execute(
            sa.text("""
                DELETE FROM role_permissions
                WHERE role_id IN (SELECT id FROM roles WHERE code = :role_code)
                  AND permission_id IN (SELECT id FROM permissions WHERE code = :permission_code)
            """),
            {"role_code": ROLE_CODE, "permission_code": PERMISSION_CODE},
        )
        if inspector.has_table("user_roles"):
            connection.execute(
                sa.text("""
                    DELETE FROM roles WHERE code = :code
                      AND NOT EXISTS (SELECT 1 FROM user_roles ur WHERE ur.role_id = roles.id)
                      AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = roles.id)
                """),
                {"code": ROLE_CODE},
            )
        connection.execute(
            sa.text("""
                DELETE FROM permissions WHERE code = :code
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = permissions.id)
            """),
            {"code": PERMISSION_CODE},
        )
    op.drop_index("idx_assistant_proposal_policy_audit_team", table_name="crm_assistant_proposal_policy_audit")
    op.drop_table("crm_assistant_proposal_policy_audit")
    op.drop_table("crm_assistant_proposal_policies")
