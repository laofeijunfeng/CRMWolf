"""Add team-scoped product and module catalog."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "132_product_module_catalog"
down_revision: str | None = "131_crm_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_TABLE = "crm_products"
MODULE_TABLE = "crm_product_modules"
PRODUCT_PERMISSION_CODES = (
    "product:view",
    "product:create",
    "product:edit",
    "product:delete",
)
_SQLITE_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _seed_permissions() -> None:
    if not (_table_exists("permissions") and _table_exists("roles") and _table_exists("role_permissions")):
        return
    conn = op.get_bind()
    permissions = (
        ("查看产品", "product:view", "view"),
        ("创建产品", "product:create", "create"),
        ("编辑产品", "product:edit", "edit"),
        ("删除产品", "product:delete", "delete"),
    )
    for name, code, action in permissions:
        conn.execute(
            sa.text(
                """
                INSERT INTO permissions (name, code, resource, action, scope)
                SELECT :name, :code, 'product', :action, NULL
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
                """
            ),
            {"name": name, "code": code, "action": action},
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            JOIN permissions p ON p.code = 'product:view'
            WHERE r.code IN ('SALES_MEMBER', 'SALES_DIRECTOR')
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        PRODUCT_TABLE,
        sa.Column("id", _SQLITE_BIGINT, autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(64), nullable=False, comment="产品对外ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("code", sa.String(50), nullable=False, comment="团队内产品编码"),
        sa.Column("name", sa.String(100), nullable=False, comment="产品名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="产品描述"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否启用"),
        sa.Column("created_by", sa.String(100), nullable=False, comment="创建人"),
        sa.Column("updated_by", sa.String(100), nullable=True, comment="最后更新人"),
        sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_crm_products_public_id"),
        sa.UniqueConstraint("team_id", "code", name="uq_crm_products_team_code"),
        comment="团队级产品目录",
    )
    op.create_index("idx_crm_products_team_active", PRODUCT_TABLE, ["team_id", "is_active"])
    op.create_index("idx_crm_products_team_id", PRODUCT_TABLE, ["team_id"])
    op.create_index("idx_crm_products_code", PRODUCT_TABLE, ["code"])

    op.create_table(
        MODULE_TABLE,
        sa.Column("id", _SQLITE_BIGINT, autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(64), nullable=False, comment="模块对外ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("product_id", sa.BigInteger(), nullable=False, comment="所属产品ID"),
        sa.Column("code", sa.String(50), nullable=False, comment="产品内模块编码"),
        sa.Column("name", sa.String(100), nullable=False, comment="模块名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="模块描述"),
        sa.Column("module_role", sa.String(20), nullable=False, server_default="ADD_ON", comment="模块角色"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否启用"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="展示顺序"),
        sa.Column("created_by", sa.String(100), nullable=False, comment="创建人"),
        sa.Column("updated_by", sa.String(100), nullable=True, comment="最后更新人"),
        sa.Column("created_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.ForeignKeyConstraint(["product_id"], [f"{PRODUCT_TABLE}.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_crm_product_modules_public_id"),
        sa.UniqueConstraint("product_id", "code", name="uq_crm_product_modules_product_code"),
        sa.CheckConstraint("module_role IN ('BASE', 'ADD_ON')", name="ck_crm_product_modules_role"),
        comment="产品模块目录",
    )
    op.create_index("idx_crm_product_modules_team_product", MODULE_TABLE, ["team_id", "product_id"])
    op.create_index("idx_crm_product_modules_team_active", MODULE_TABLE, ["team_id", "is_active"])
    op.create_index("idx_crm_product_modules_product_role", MODULE_TABLE, ["product_id", "module_role"])
    _seed_permissions()


def downgrade() -> None:
    if _table_exists("role_permissions") and _table_exists("permissions"):
        conn = op.get_bind()
        conn.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE permission_id IN (
                    SELECT id FROM permissions WHERE code IN (:view, :create, :edit, :delete)
                )
                """
            ),
            {"view": "product:view", "create": "product:create", "edit": "product:edit", "delete": "product:delete"},
        )
        conn.execute(
            sa.text(
                "DELETE FROM permissions WHERE code IN (:view, :create, :edit, :delete)"
            ),
            {"view": "product:view", "create": "product:create", "edit": "product:edit", "delete": "product:delete"},
        )
    if _table_exists(MODULE_TABLE):
        op.drop_index("idx_crm_product_modules_product_role", table_name=MODULE_TABLE)
        op.drop_index("idx_crm_product_modules_team_active", table_name=MODULE_TABLE)
        op.drop_index("idx_crm_product_modules_team_product", table_name=MODULE_TABLE)
        op.drop_table(MODULE_TABLE)
    if _table_exists(PRODUCT_TABLE):
        op.drop_index("idx_crm_products_code", table_name=PRODUCT_TABLE)
        op.drop_index("idx_crm_products_team_id", table_name=PRODUCT_TABLE)
        op.drop_index("idx_crm_products_team_active", table_name=PRODUCT_TABLE)
        op.drop_table(PRODUCT_TABLE)
