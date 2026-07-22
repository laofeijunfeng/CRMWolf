"""recalculate payment status by approved records

Revision ID: 031_recalculate_payment_status_by_approved_records
Revises: 030_approval_node_notify_user_ids
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op


revision: str = "031_recalculate_payment_status_by_approved_records"
down_revision: Union[str, None] = "030_approval_node_notify_user_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE crm_contract_payment_plans
        SET status = CASE
            WHEN COALESCE((
                SELECT SUM(r.actual_amount)
                FROM crm_payment_records r
                WHERE r.payment_plan_id = crm_contract_payment_plans.id
                  AND r.approval_phase = 'approved'
            ), 0) >= planned_amount THEN 'COMPLETED'
            WHEN COALESCE((
                SELECT SUM(r.actual_amount)
                FROM crm_payment_records r
                WHERE r.payment_plan_id = crm_contract_payment_plans.id
                  AND r.approval_phase = 'approved'
            ), 0) > 0 THEN 'PARTIAL'
            WHEN due_date < CURRENT_DATE THEN 'OVERDUE'
            ELSE 'PENDING'
        END
        """
    )

    op.execute(
        """
        UPDATE crm_contracts
        SET total_paid_amount = COALESCE((
            SELECT SUM(r.actual_amount)
            FROM crm_contract_payment_plans p
            JOIN crm_payment_records r ON r.payment_plan_id = p.id
            WHERE p.contract_id = crm_contracts.id
              AND r.approval_phase = 'approved'
        ), 0)
        """
    )

    op.execute(
        """
        UPDATE crm_contracts
        SET payment_status = CASE
            WHEN NOT EXISTS (
                SELECT 1
                FROM crm_contract_payment_plans p
                WHERE p.contract_id = crm_contracts.id
            ) THEN 'UNPAID'
            WHEN EXISTS (
                SELECT 1
                FROM crm_contract_payment_plans p
                WHERE p.contract_id = crm_contracts.id
                  AND p.status = 'OVERDUE'
            ) THEN 'OVERDUE'
            WHEN total_paid_amount >= COALESCE((
                SELECT SUM(p.planned_amount)
                FROM crm_contract_payment_plans p
                WHERE p.contract_id = crm_contracts.id
            ), 0) THEN 'COMPLETED'
            WHEN total_paid_amount > 0 THEN 'PARTIAL'
            ELSE 'UNPAID'
        END
        """
    )


def downgrade() -> None:
    pass
