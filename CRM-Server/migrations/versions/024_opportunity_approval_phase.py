"""add approval phase to opportunities

Revision ID: 024_opportunity_approval_phase
Revises: 023_payment_record_actual_payer_name
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '024_opportunity_approval_phase'
down_revision = '023_payment_record_actual_payer_name'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    col_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_opportunities'
        AND column_name = 'approval_phase'
    """)).scalar()

    if col_exists == 0:
        op.add_column(
            'crm_opportunities',
            sa.Column(
                'approval_phase',
                sa.String(length=20),
                nullable=False,
                server_default='draft',
                comment='审批流程状态：draft/pending_review/approved/rejected'
            )
        )
        # 历史商机不应被新审批机制拦住，统一视为已审批通过。
        op.execute("UPDATE crm_opportunities SET approval_phase = 'approved'")
        op.create_index(
            'idx_opportunity_approval_phase',
            'crm_opportunities',
            ['approval_phase']
        )


def downgrade():
    conn = op.get_bind()
    index_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_opportunities'
        AND index_name = 'idx_opportunity_approval_phase'
    """)).scalar()
    if index_exists > 0:
        op.drop_index('idx_opportunity_approval_phase', table_name='crm_opportunities')

    col_exists = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'crm_opportunities'
        AND column_name = 'approval_phase'
    """)).scalar()
    if col_exists > 0:
        op.drop_column('crm_opportunities', 'approval_phase')
