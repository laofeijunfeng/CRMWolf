# CRM-Server/migrations/versions/013_invoice_approval_data_migration.py
"""Invoice 在途数据平迁到通用审批引擎（B2）。

把旧自管单步审批的发票数据迁到通用审批引擎表：
- APPROVED 旧发票 → 补建 Approval(INVOICE, APPROVED) + ApprovalRecord(APPROVE)，
  approver_id 取 reviewer_id，作为历史审计快照（flow_id=NULL，不再驱动状态机）。
- PENDING_REVIEW 旧记录 → 回退 DRAFT，reviewer_id / review_comment / reviewed_time 清空，
  由申请人重新经通用 `/v1/approvals/INVOICE/{id}/submit` 提交。
- ISSUED / REJECTED / DRAFT → 不动（已终态或不属于审批可平迁范围）。

平迁 SQL 体（`run_invoice_approval_data_migration(bind)`）抽到模块级函数，
migration upgrade() 委托调用，并供 tests/unit/test_invoice_data_migration.py 直接 import，
保证平迁逻辑在无 MySQL 环境下能用内存 SQLite 复验（E7 契约）。

Revision ID: 013_invoice_approval_data_migration
Revises: 012_approval_generic_business
Create Date: 2026-07-02
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = '013_invoice_approval_data_migration'
down_revision: Union[str, None] = '012_approval_generic_business'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.migration.013")


def run_invoice_approval_data_migration(bind) -> None:
    """发票在途数据平迁到通用审批引擎。

    幂等性：APPROVED 补建 INSERT 带 `WHERE NOT EXISTS` 守卫——重跑不会重复
    补建 Approval/ApprovalRecord（I-3）。PENDING_REVIEW→DRAFT 的 UPDATE 本身
    幂等（二次跑命中 status='PENDING_REVIEW' 的行数为 0）。E7 测试固化"对
    ISSUED/REJECTED/DRAFT 态零影响"。

    Args:
        bind: SQLAlchemy Engine / Connection（alembic op.get_bind() 或测试会话 bind）
    """
    # 1. APPROVED 旧发票 → 补建 Approval(INVOICE, APPROVED) 审计快照
    #    flow_id 留 NULL：历史数据无对应模板，仅作审计，不再驱动状态机。
    #    I-3：NOT EXISTS 守卫防止重跑重复补建 Approval 实例。
    bind.execute(text(
        """
        INSERT INTO crm_contract_approvals
            (team_id, business_type, business_id, flow_id, current_node_id,
             status, submitter_id, submitter_name,
             created_time, updated_time)
        SELECT
            team_id, 'INVOICE', id, NULL, NULL,
            'APPROVED', applicant_id, NULL,
            created_time,
            COALESCE(reviewed_time, last_modified_time)
        FROM crm_invoice_applications a
        WHERE a.status = 'APPROVED'
              AND NOT EXISTS (
                  SELECT 1 FROM crm_contract_approvals a2
                  WHERE a2.business_type = 'INVOICE' AND a2.business_id = a.id
              )
        """
    ))

    # 2. 对应 ApprovalRecord(APPROVE) 一条，approver_id 取 reviewer_id（非空才补）
    #    I-3：NOT EXISTS 守卫防止重跑为同一 Approval 重复补建 APPROVE 记录。
    bind.execute(text(
        """
        INSERT INTO crm_contract_approval_records
            (team_id, approval_id, node_id, approver_id, approver_name,
             action, comment, created_time)
        SELECT
            a.team_id, ap.id, NULL, a.reviewer_id, NULL,
            'APPROVE', a.review_comment, a.reviewed_time
        FROM crm_invoice_applications a
        JOIN crm_contract_approvals ap
          ON ap.business_type = 'INVOICE' AND ap.business_id = a.id
        WHERE a.status = 'APPROVED' AND a.reviewer_id IS NOT NULL
              AND a.reviewed_time IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM crm_contract_approval_records r2
                  WHERE r2.approval_id = ap.id AND r2.action = 'APPROVE'
              )
        """
    ))

    # 3. PENDING_REVIEW 旧记录回退 DRAFT，清空 reviewer 快照
    bind.execute(text(
        """
        UPDATE crm_invoice_applications
        SET status = 'DRAFT',
            reviewer_id = NULL,
            review_comment = NULL,
            reviewed_time = NULL
        WHERE status = 'PENDING_REVIEW'
        """
    ))


def upgrade() -> None:
    bind = op.get_bind()

    # 非阻断预检：统计在途数据规模，便于运维回看
    approved_cnt = bind.execute(
        text("SELECT COUNT(*) FROM crm_invoice_applications WHERE status = 'APPROVED'")
    ).scalar() or 0
    pending_cnt = bind.execute(
        text("SELECT COUNT(*) FROM crm_invoice_applications WHERE status = 'PENDING_REVIEW'")
    ).scalar() or 0
    logger.warning(
        "[013] 发票在途平迁：APPROVED=%s / PENDING_REVIEW=%s",
        approved_cnt, pending_cnt,
    )

    run_invoice_approval_data_migration(bind)

    # 非阻断校验：平迁后 Approval(INVOICE) 行数应等于原 APPROVED 行数
    approval_cnt = bind.execute(
        text(
            "SELECT COUNT(*) FROM crm_contract_approvals "
            "WHERE business_type = 'INVOICE' AND status = 'APPROVED'"
        )
    ).scalar() or 0
    logger.warning("[013] 平迁后 INVOICE 审批实例数: %s", approval_cnt)


def downgrade() -> None:
    """回滚：删除本次平迁补建的 INVOICE 审批实例与记录。

    注：PENDING_REVIEW → DRAFT 的状态回退不可逆（reviewer 快照已清空，无法恢复
    原值）。若需精细回滚请从备份恢复。本 downgrade 只清引擎表，避免破 alembic
    链路。
    """
    bind = op.get_bind()
    bind.execute(text(
        """
        DELETE FROM crm_contract_approval_records
        WHERE approval_id IN (
            SELECT id FROM crm_contract_approvals
            WHERE business_type = 'INVOICE'
        )
        """
    ))
    bind.execute(text(
        "DELETE FROM crm_contract_approvals WHERE business_type = 'INVOICE'"
    ))