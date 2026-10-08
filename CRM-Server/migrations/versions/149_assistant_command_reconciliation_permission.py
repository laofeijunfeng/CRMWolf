"""Seed an opt-in team role for assistant command reconciliation.

Revision ID: 149_assistant_command_operator
Revises: 148_assistant_legacy_source_guard
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "149_assistant_command_operator"
down_revision: str | None = "148_assistant_legacy_source_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_CODE = "assistant:commands:reconcile:team"
ROLE_CODE = "ASSISTANT_COMMAND_OPERATOR"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not all(inspector.has_table(table) for table in ("permissions", "roles", "role_permissions")):
        return

    permission_columns = "name, code, resource, action, scope"
    permission_values = ":name, :code, 'assistant_command', 'reconcile', 'team'"
    if "is_active" in {column["name"] for column in inspector.get_columns("permissions")}:
        permission_columns += ", is_active"
        permission_values += ", 1"
    connection.execute(
        sa.text(f"""
            INSERT INTO permissions ({permission_columns})
            SELECT {permission_values}
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
        """),
        {"name": "核对团队助手命令", "code": PERMISSION_CODE},
    )
    connection.execute(
        sa.text("""
            INSERT INTO roles (name, code, description)
            SELECT :name, :code, :description
            WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = :code)
        """),
        {"name": "助手命令核对员", "code": ROLE_CODE, "description": "仅核对本团队的助手命令执行结果"},
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
    inspector = sa.inspect(connection)
    if not all(inspector.has_table(table) for table in ("permissions", "roles", "role_permissions")):
        return

    connection.execute(
        sa.text("""
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE code = :role_code)
              AND permission_id IN (SELECT id FROM permissions WHERE code = :permission_code)
        """),
        {"role_code": ROLE_CODE, "permission_code": PERMISSION_CODE},
    )
    # A role already assigned to team members is retained; never discard user grants.
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
