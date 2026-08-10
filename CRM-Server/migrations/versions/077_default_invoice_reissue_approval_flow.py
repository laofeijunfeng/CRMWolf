"""add default invoice reissue approval flows

Revision ID: 077_default_invoice_reissue_approval_flow
Revises: 076_invoice_reissue_applications
Create Date: 2026-08-10

"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "077_default_invoice_reissue_approval_flow"
down_revision: str | None = "076_invoice_reissue_applications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    if not (
        _table_exists("teams")
        and _table_exists("crm_approval_flows")
        and _table_exists("crm_approval_nodes")
    ):
        return

    conn = op.get_bind()
    team_ids = [
        row[0]
        for row in conn.execute(sa.text("SELECT id FROM teams")).all()
    ]

    now = datetime.now()
    for team_id in team_ids:
        existing = conn.execute(
            sa.text("""
                SELECT id
                FROM crm_approval_flows
                WHERE team_id = :team_id
                  AND business_type = 'INVOICE_REISSUE'
                LIMIT 1
            """),
            {"team_id": team_id},
        ).first()
        if existing:
            continue

        flow_code = f"INVOICE_REISSUE_DEFAULT_{team_id}"
        conn.execute(
            sa.text("""
                INSERT INTO crm_approval_flows (
                    team_id,
                    flow_name,
                    flow_code,
                    description,
                    min_amount,
                    max_amount,
                    license_type,
                    business_type,
                    is_active,
                    created_time,
                    last_modified_time
                )
                VALUES (
                    :team_id,
                    '发票重开默认审批',
                    :flow_code,
                    '默认发票重开审批流程，财务审批后进入冲红并重开处理',
                    NULL,
                    NULL,
                    NULL,
                    'INVOICE_REISSUE',
                    1,
                    :now,
                    :now
                )
            """),
            {"team_id": team_id, "flow_code": flow_code, "now": now},
        )

        flow_id = conn.execute(
            sa.text("""
                SELECT id
                FROM crm_approval_flows
                WHERE team_id = :team_id
                  AND flow_code = :flow_code
                  AND business_type = 'INVOICE_REISSUE'
                LIMIT 1
            """),
            {"team_id": team_id, "flow_code": flow_code},
        ).scalar()
        if flow_id is None:
            continue

        conn.execute(
            sa.text("""
                INSERT INTO crm_approval_nodes (
                    team_id,
                    flow_id,
                    node_name,
                    node_code,
                    node_order,
                    description,
                    approve_role,
                    notify_user_ids,
                    is_required,
                    created_time
                )
                VALUES (
                    :team_id,
                    :flow_id,
                    '财务审批',
                    'FINANCE_APPROVAL',
                    1,
                    '财务确认原发票冲红和新发票重开信息',
                    'FINANCE',
                    NULL,
                    1,
                    :now
                )
            """),
            {"team_id": team_id, "flow_id": flow_id, "now": now},
        )


def downgrade() -> None:
    if not (_table_exists("crm_approval_flows") and _table_exists("crm_approval_nodes")):
        return

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM crm_approval_nodes
            WHERE flow_id IN (
                SELECT id
                FROM crm_approval_flows
                WHERE business_type = 'INVOICE_REISSUE'
                  AND flow_code LIKE 'INVOICE_REISSUE_DEFAULT_%'
            )
        """)
    )
    conn.execute(
        sa.text("""
            DELETE FROM crm_approval_flows
            WHERE business_type = 'INVOICE_REISSUE'
              AND flow_code LIKE 'INVOICE_REISSUE_DEFAULT_%'
        """)
    )
