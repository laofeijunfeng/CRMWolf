# CRM-Server/migrations/versions/012_approval_generic_business.py
"""Add business_type/business_id to crm_contract_approvals and business_type to crm_approval_flows
for generic approval engine (CONTRACT/PAYMENT/INVOICE).

Revision ID: 012_approval_generic_business
Revises: 011_add_account_name_norm
Create Date: 2026-07-02

"""
import logging
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = '012_approval_generic_business'
down_revision: Union[str, None] = '011_add_account_name_norm'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.migration.012")

def upgrade() -> None:
    # 1. crm_contract_approvals 加 business_type / business_id
    op.add_column('crm_contract_approvals',
        sa.Column('business_type', sa.String(length=20), nullable=False, server_default='CONTRACT',
                  comment='业务单据类型：CONTRACT/PAYMENT/INVOICE/ORPHAN'))
    op.add_column('crm_contract_approvals',
        sa.Column('business_id', sa.BigInteger(), nullable=True, comment='业务单据ID'))

    # 2. 回填：有合同关联的旧记录 business_id = contract_id（带 orphan 守卫）
    op.execute(
        "UPDATE crm_contract_approvals SET business_id = contract_id, business_type='CONTRACT' "
        "WHERE business_id IS NULL AND contract_id IS NOT NULL"
    )
    # 2b. 孤儿行（合同已软删导致 contract_id IS NULL）标为 ORPHAN，避免 CONTRACT+NULL business_id 矛盾
    op.execute(
        "UPDATE crm_contract_approvals SET business_type='ORPHAN' "
        "WHERE business_id IS NULL AND contract_id IS NULL"
    )
    op.create_index('idx_approval_business', 'crm_contract_approvals', ['business_type', 'business_id'])

    # 3. crm_approval_flows 加 business_type（现有 flow 默认归类合同流，无需回填）
    op.add_column('crm_approval_flows',
        sa.Column('business_type', sa.String(length=20), nullable=False, server_default='CONTRACT',
                  comment='流程适用单据类型：CONTRACT/PAYMENT/INVOICE'))
    op.create_index('idx_flow_business_type', 'crm_approval_flows', ['business_type'])

    # 4. 非阻断校验：打印孤儿审批数（风格对齐 scripts/check_migrations.py，不阻断）
    bind = op.get_bind()
    orphan_count = bind.execute(
        text("SELECT COUNT(*) FROM crm_contract_approvals WHERE business_type='ORPHAN'")
    ).scalar() or 0
    logger.warning("[012] 孤儿审批记录（合同已删除）数量: %s", orphan_count)

def downgrade() -> None:
    op.drop_index('idx_flow_business_type', table_name='crm_approval_flows')
    op.drop_column('crm_approval_flows', 'business_type')
    op.drop_index('idx_approval_business', table_name='crm_contract_approvals')
    # 回滚前把 ORPHAN 还原为 CONTRACT（保持原 business_type 默认语义）
    op.execute("UPDATE crm_contract_approvals SET business_type='CONTRACT' WHERE business_type='ORPHAN'")
    op.drop_column('crm_contract_approvals', 'business_id')
    op.drop_column('crm_contract_approvals', 'business_type')