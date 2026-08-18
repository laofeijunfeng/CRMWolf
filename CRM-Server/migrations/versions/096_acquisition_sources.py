"""Add configurable acquisition sources and backfill lead/customer source_id.

Revision ID: 096_acquisition_sources
Revises: 095_agent_async_operation_collation
Create Date: 2026-08-18
"""

import logging
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

revision: str = "096_acquisition_sources"
down_revision: str | None = "095_agent_async_operation_collation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_TABLE = "crm_acquisition_sources"
LEAD_TABLE = "crm_leads"
CUSTOMER_TABLE = "crm_customers"

logger = logging.getLogger("alembic.runtime.migration")

PERMISSIONS = [
    ("查看获客来源", "acquisition_source:view", "view"),
    ("创建获客来源", "acquisition_source:create", "create"),
    ("更新获客来源", "acquisition_source:update", "update"),
]


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _table_exists(table_name: str) -> bool:
    connection = op.get_bind()
    if _is_sqlite():
        return bool(
            connection.execute(
                text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
                {"table_name": table_name},
            ).scalar()
        )
    return bool(
        connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalar()
    )


def _column_exists(table_name: str, column_name: str) -> bool:
    connection = op.get_bind()
    if _is_sqlite():
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return any(row[1] == column_name for row in rows)
    return bool(
        connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    connection = op.get_bind()
    if _is_sqlite():
        rows = connection.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
        return any(row[1] == index_name for row in rows)
    return bool(
        connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND index_name = :index_name
                """
            ),
            {"table_name": table_name, "index_name": index_name},
        ).scalar()
    )


def _fk_exists(table_name: str, fk_name: str) -> bool:
    connection = op.get_bind()
    if _is_sqlite():
        return False
    return bool(
        connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.table_constraints
                WHERE table_schema = DATABASE()
                  AND table_name = :table_name
                  AND constraint_name = :fk_name
                  AND constraint_type = 'FOREIGN KEY'
                """
            ),
            {"table_name": table_name, "fk_name": fk_name},
        ).scalar()
    )


def _create_source_table() -> None:
    if _table_exists(SOURCE_TABLE):
        return
    op.create_table(
        SOURCE_TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("public_id", sa.String(length=64), nullable=False, comment="对外获客来源ID"),
        sa.Column("team_id", sa.BigInteger(), nullable=False, comment="团队ID"),
        sa.Column("code", sa.String(length=50), nullable=False, comment="来源编码，系统项固定，自定义项服务端生成"),
        sa.Column("name", sa.String(length=50), nullable=False, comment="展示名称"),
        sa.Column("is_system", sa.Integer(), nullable=False, server_default="0", comment="是否系统默认项: 1是, 0否"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1", comment="是否启用: 1启用, 0停用"),
        sa.Column("sort_order", sa.Integer(), nullable=False, comment="前端排序"),
        sa.Column("created_by", sa.String(length=100), nullable=False, comment="创建人系统用户ID"),
        sa.Column("updated_by", sa.String(length=100), nullable=True, comment="最后更新人系统用户ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="最后更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_acq_source_public_id"),
        sa.UniqueConstraint("team_id", "code", name="uq_acq_source_team_code"),
        sa.UniqueConstraint("team_id", "name", name="uq_acq_source_team_name"),
        comment="获客来源配置表",
    )
    op.create_index("idx_acq_source_team_active_sort", SOURCE_TABLE, ["team_id", "is_active", "sort_order"])
    op.create_index("idx_acq_source_team_id", SOURCE_TABLE, ["team_id"])


def _add_source_id(table_name: str, index_name: str, fk_name: str) -> None:
    if not _column_exists(table_name, "source_id"):
        op.add_column(
            table_name,
            sa.Column("source_id", sa.BigInteger(), nullable=True, comment="获客来源ID"),
        )
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, ["source_id"])
    if not _is_sqlite() and not _fk_exists(table_name, fk_name):
        op.create_foreign_key(
            fk_name,
            table_name,
            SOURCE_TABLE,
            ["source_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def _insert_permissions() -> None:
    if not _table_exists("permissions"):
        return
    connection = op.get_bind()
    for name, code, action in PERMISSIONS:
        exists = connection.execute(
            text("SELECT id FROM permissions WHERE code = :code LIMIT 1"),
            {"code": code},
        ).first()
        if exists:
            continue
        connection.execute(
            text(
                """
                INSERT INTO permissions (name, code, resource, action, scope)
                VALUES (:name, :code, 'acquisition_source', :action, NULL)
                """
            ),
            {"name": name, "code": code, "action": action},
        )


def _log_backfill_report(team_id: int, entity: str, report: dict[str, object]) -> None:
    dirty = report["dirty"]
    logger.warning(
        "acquisition source backfill team_id=%s entity=%s aligned=%s empty=%s dirty_count=%s dirty=%s",
        team_id,
        entity,
        report["aligned"],
        report["empty"],
        len(dirty),
        dirty,
    )


def _seed_and_backfill() -> None:
    from app.constants.acquisition_sources import classify_legacy_source, summarize_legacy_source_backfill
    from app.models.acquisition_source import AcquisitionSource
    from app.models.customer import Customer
    from app.models.lead import Lead
    from app.models.team import Team
    from app.services.acquisition_source_service import seed_default_sources

    session = Session(bind=op.get_bind())
    try:
        teams = session.query(Team).all()
        for team in teams:
            seed_default_sources(session, team.id, str(team.owner_id))
        session.flush()

        by_team_code: dict[int, dict[str, int]] = {}
        for row in session.query(AcquisitionSource).all():
            by_team_code.setdefault(int(row.team_id), {})[row.code] = int(row.id)

        leads_by_team: dict[int, list] = defaultdict(list)
        for lead in session.query(Lead).all():
            leads_by_team[int(lead.team_id)].append(lead)
        for team_id, team_leads in leads_by_team.items():
            report = summarize_legacy_source_backfill((lead.id, lead.source) for lead in team_leads)
            _log_backfill_report(team_id, "lead", report)
            for lead in team_leads:
                classification = classify_legacy_source(lead.source)
                if classification.code is None:
                    raise RuntimeError(f"线索 {lead.id} 来源为空，无法回填 source_id")
                source_id = by_team_code.get(int(lead.team_id), {}).get(classification.code)
                if source_id is None:
                    raise RuntimeError(f"线索 {lead.id} 无法映射到来源 {classification.code}")
                lead.source_id = source_id

        customers_by_team: dict[int, list] = defaultdict(list)
        for customer in session.query(Customer).all():
            customers_by_team[int(customer.team_id)].append(customer)
        for team_id, team_customers in customers_by_team.items():
            report = summarize_legacy_source_backfill(
                (customer.id, customer.source) for customer in team_customers
            )
            _log_backfill_report(team_id, "customer", report)
            for customer in team_customers:
                classification = classify_legacy_source(customer.source)
                if classification.code is None:
                    continue
                source_id = by_team_code.get(int(customer.team_id), {}).get(classification.code)
                if source_id is None:
                    raise RuntimeError(f"客户 {customer.id} 无法映射到来源 {classification.code}")
                customer.source_id = source_id

        remaining = session.query(Lead).filter(Lead.source_id.is_(None)).count()
        if remaining:
            raise RuntimeError(f"仍有 {remaining} 条线索 source_id 为空，迁移中止")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _convert_lead_source_to_varchar() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "mysql":
        op.execute("ALTER TABLE crm_leads MODIFY COLUMN source VARCHAR(50) NOT NULL COMMENT '线索来源'")
        return
    if _is_sqlite():
        return
    op.alter_column(
        LEAD_TABLE,
        "source",
        existing_type=sa.Enum(name="leadsource"),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def _make_lead_source_id_required() -> None:
    if _is_sqlite():
        return
    op.alter_column(
        LEAD_TABLE,
        "source_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )


def upgrade() -> None:
    _create_source_table()
    _add_source_id(LEAD_TABLE, "idx_leads_source_id", "fk_leads_source_id")
    _add_source_id(CUSTOMER_TABLE, "idx_customers_source_id", "fk_customers_source_id")
    _insert_permissions()
    _seed_and_backfill()
    _convert_lead_source_to_varchar()
    _make_lead_source_id_required()


def downgrade() -> None:
    if not _is_sqlite():
        if _fk_exists(LEAD_TABLE, "fk_leads_source_id"):
            op.drop_constraint("fk_leads_source_id", LEAD_TABLE, type_="foreignkey")
        if _fk_exists(CUSTOMER_TABLE, "fk_customers_source_id"):
            op.drop_constraint("fk_customers_source_id", CUSTOMER_TABLE, type_="foreignkey")
    if _index_exists(LEAD_TABLE, "idx_leads_source_id"):
        op.drop_index("idx_leads_source_id", table_name=LEAD_TABLE)
    if _index_exists(CUSTOMER_TABLE, "idx_customers_source_id"):
        op.drop_index("idx_customers_source_id", table_name=CUSTOMER_TABLE)
    if _column_exists(LEAD_TABLE, "source_id"):
        op.drop_column(LEAD_TABLE, "source_id")
    if _column_exists(CUSTOMER_TABLE, "source_id"):
        op.drop_column(CUSTOMER_TABLE, "source_id")
    if _table_exists(SOURCE_TABLE):
        op.drop_table(SOURCE_TABLE)
