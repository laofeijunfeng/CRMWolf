"""backfill opportunity approval snapshots

Revision ID: 035_backfill_opportunity_approval_snapshots
Revises: 034_crm_agent_tables
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "035_backfill_opportunity_approval_snapshots"
down_revision: Union[str, None] = "034_crm_agent_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKFILL_COMMENT = "历史商机审批快照：迁移补齐审批流程记录"
BACKFILL_SUBMITTER_NAME = "系统迁移"


def run_opportunity_approval_snapshot_backfill(bind) -> None:
    """Backfill approved legacy opportunities into the generic approval engine.

    Migration 024 marked existing opportunities as approved so the new approval
    gate would not block legacy data, but it did not create Approval rows. The
    detail UI reads the generic approval engine, so those rows looked approved
    on the opportunity itself while the approval process showed "not submitted".
    """
    bind.execute(text(
        """
        INSERT INTO crm_contract_approvals
            (team_id, contract_id, business_type, business_id, flow_id,
             current_node_id, status, submitter_id, submitter_name,
             created_time, updated_time)
        SELECT
            o.team_id, NULL, 'OPPORTUNITY', o.id, NULL,
            NULL, 'APPROVED', o.creator_id, :submitter_name,
            o.created_time, COALESCE(o.last_modified_time, o.created_time)
        FROM crm_opportunities o
        WHERE o.approval_phase = 'approved'
              AND NOT EXISTS (
                  SELECT 1 FROM crm_contract_approvals a
                  WHERE a.team_id = o.team_id
                    AND a.business_type = 'OPPORTUNITY'
                    AND a.business_id = o.id
              )
        """
    ), {"submitter_name": BACKFILL_SUBMITTER_NAME})

    bind.execute(text(
        """
        INSERT INTO crm_contract_approval_records
            (team_id, approval_id, node_id, approver_id, approver_name,
             action, comment, created_time)
        SELECT
            a.team_id, a.id, NULL, a.submitter_id, NULL,
            'APPROVE', :comment, a.updated_time
        FROM crm_contract_approvals a
        JOIN crm_opportunities o
          ON o.team_id = a.team_id AND o.id = a.business_id
        WHERE a.business_type = 'OPPORTUNITY'
              AND a.status = 'APPROVED'
              AND a.submitter_name = :submitter_name
              AND o.approval_phase = 'approved'
              AND NOT EXISTS (
                  SELECT 1 FROM crm_contract_approval_records r
                  WHERE r.approval_id = a.id
              )
        """
    ), {"comment": BACKFILL_COMMENT, "submitter_name": BACKFILL_SUBMITTER_NAME})


def upgrade() -> None:
    run_opportunity_approval_snapshot_backfill(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(
        """
        DELETE FROM crm_contract_approval_records
        WHERE comment = :comment
        """
    ), {"comment": BACKFILL_COMMENT})
    bind.execute(text(
        """
        DELETE a FROM crm_contract_approvals a
        LEFT JOIN crm_contract_approval_records r ON r.approval_id = a.id
        JOIN crm_opportunities o ON o.team_id = a.team_id AND o.id = a.business_id
        WHERE a.business_type = 'OPPORTUNITY'
          AND a.status = 'APPROVED'
          AND a.flow_id IS NULL
          AND a.current_node_id IS NULL
          AND o.approval_phase = 'approved'
          AND r.id IS NULL
        """
    ))
