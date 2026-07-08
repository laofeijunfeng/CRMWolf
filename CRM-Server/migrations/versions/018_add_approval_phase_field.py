"""add approval_phase field to all business entity tables

Revision ID: 018_add_approval_phase_field
Revises: 017_license_approval_field
Create Date: 2026-07-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018_add_approval_phase_field'
down_revision = '017_license_approval_field'
branch_labels = None
depends_on = None


def upgrade():
    """新增 approval_phase 字段到所有业务单据表 + 数据迁移"""

    # 1. Contract 表新增 approval_phase 字段
    op.add_column(
        'crm_contracts',
        sa.Column(
            'approval_phase',
            sa.String(20),
            nullable=False,
            server_default='draft',
            comment='审批流程状态：draft/pending_review/approved/rejected'
        )
    )

    # 2. PaymentRecord 表新增 approval_phase 字段
    op.add_column(
        'crm_payment_records',
        sa.Column(
            'approval_phase',
            sa.String(20),
            nullable=False,
            server_default='draft',
            comment='审批流程状态：draft/pending_review/approved/rejected'
        )
    )

    # 3. InvoiceApplication 表新增 approval_phase 字段
    op.add_column(
        'crm_invoice_applications',
        sa.Column(
            'approval_phase',
            sa.String(20),
            nullable=False,
            server_default='draft',
            comment='审批流程状态：draft/pending_review/approved/rejected'
        )
    )

    # 4. LicenseApplication 表新增 approval_phase 字段
    op.add_column(
        'crm_license_applications',
        sa.Column(
            'approval_phase',
            sa.String(20),
            nullable=False,
            server_default='draft',
            comment='审批流程状态：draft/pending_review/approved/rejected'
        )
    )

    # 5. 数据迁移：Contract（status → approval_phase）
    op.execute("""
        UPDATE crm_contracts
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status = 'PENDING_REVIEW' THEN 'pending_review'
            WHEN status IN ('SIGNED', 'EFFECTIVE', 'EXPIRED', 'TERMINATED') THEN 'approved'
            ELSE 'draft'
        END
    """)

    # 6. 数据迁移：PaymentRecord（复杂逻辑，修复驳回状态）
    # 分步骤执行，避免复杂的单条 SQL

    # 6.1 未提交审批的 PENDING → draft
    op.execute("""
        UPDATE crm_payment_records
        SET approval_phase = 'draft'
        WHERE confirmation_status = 'PENDING' AND approval_id IS NULL
    """)

    # 6.2 审批中的 PENDING → pending_review
    op.execute("""
        UPDATE crm_payment_records pr
        SET approval_phase = 'pending_review'
        FROM crm_contract_approvals a
        WHERE pr.approval_id = a.id AND a.status = 'PENDING'
    """)

    # 6.3 审批通过的 CONFIRMED → approved
    op.execute("""
        UPDATE crm_payment_records
        SET approval_phase = 'approved'
        WHERE confirmation_status = 'CONFIRMED'
    """)

    # 6.4 审批拒绝的 PENDING → rejected（关键修复）
    op.execute("""
        UPDATE crm_payment_records pr
        SET approval_phase = 'rejected'
        FROM crm_contract_approvals a
        WHERE pr.approval_id = a.id AND a.status = 'REJECTED'
    """)

    # 6.5 有争议的 DISPUTED → rejected
    op.execute("""
        UPDATE crm_payment_records
        SET approval_phase = 'rejected'
        WHERE confirmation_status = 'DISPUTED'
    """)

    # 7. 数据迁移：InvoiceApplication
    op.execute("""
        UPDATE crm_invoice_applications
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status = 'PENDING_REVIEW' THEN 'pending_review'
            WHEN status IN ('APPROVED', 'ISSUED') THEN 'approved'
            WHEN status = 'REJECTED' THEN 'rejected'
            ELSE 'draft'
        END
    """)

    # 8. 数据迁移：LicenseApplication（修复审批拒绝但 status = PENDING）
    op.execute("""
        UPDATE crm_license_applications
        SET approval_phase = CASE
            WHEN status = 'DRAFT' THEN 'draft'
            WHEN status IN ('PENDING', 'PENDING_REVIEW') THEN 'pending_review'
            WHEN status IN ('APPROVED', 'ISSUED') THEN 'approved'
            WHEN status = 'REJECTED' THEN 'rejected'
            ELSE 'draft'
        END
    """)

    # 9. LicenseApplication.status PENDING → PENDING_REVIEW（统一命名）
    op.execute("""
        UPDATE crm_license_applications
        SET status = 'PENDING_REVIEW'
        WHERE status = 'PENDING'
    """)


def downgrade():
    """回滚 approval_phase 字段"""

    # 1. LicenseApplication.status 恢复 PENDING
    op.execute("""
        UPDATE crm_license_applications
        SET status = 'PENDING'
        WHERE status = 'PENDING_REVIEW'
    """)

    # 2. 删除所有 approval_phase 字段
    op.drop_column('crm_contracts', 'approval_phase')
    op.drop_column('crm_payment_records', 'approval_phase')
    op.drop_column('crm_invoice_applications', 'approval_phase')
    op.drop_column('crm_license_applications', 'approval_phase')