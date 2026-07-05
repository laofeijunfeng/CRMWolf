#!/usr/bin/env python3
"""
发票审批数据迁移脚本

为现有 PENDING_REVIEW 状态的发票创建 Approval 记录
修复历史数据：发票创建时未提交审批导致的 Approval 记录缺失

使用方法：
    cd CRM-Server
    python scripts/migrate_invoice_approval.py

前提条件：
    1. 审批流程已配置（business_type=INVOICE）
    2. 审批节点已配置（有审批人）
"""

import sys
import os
import asyncio
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus
from app.models.approval import Approval, ApprovalRecord, ApprovalStatus, ApprovalAction, ApprovalFlow, ApprovalNode
from app.constants.business_types import BusinessType
from app.crud.approval import approval_crud, approval_flow_crud
from app.crud.invoice import invoice_application_crud
from app.services.approval_adapter import get_adapter
from app.services.notification import notification_service_factory
from app.api.approvals import get_approvers_by_role
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_invoice_approvals(db: Session, team_id: int = None):
    """
    为现有 PENDING_REVIEW 发票创建 Approval 记录

    Args:
        db: 数据库会话
        team_id: 团队ID（可选，不指定则处理所有团队）
    """
    # 1. 查询所有 PENDING_REVIEW 状态的发票
    query = db.query(InvoiceApplication).filter(
        InvoiceApplication.status == InvoiceApplicationStatus.PENDING_REVIEW
    )

    if team_id:
        query = query.filter(InvoiceApplication.team_id == team_id)

    invoices = query.all()

    logger.info(f"找到 {len(invoices)} 个 PENDING_REVIEW 状态的发票")

    if not invoices:
        logger.info("没有需要迁移的发票")
        return

    # 2. 遍历发票，为每个发票创建 Approval 记录
    success_count = 0
    skip_count = 0
    error_count = 0

    for invoice in invoices:
        try:
            # 检查是否已有 Approval 记录
            existing_approval = db.query(Approval).filter(
                Approval.business_type == BusinessType.INVOICE,
                Approval.business_id == invoice.id,
                Approval.status == ApprovalStatus.PENDING  # 只处理 PENDING 状态
            ).first()

            adapter = get_adapter(BusinessType.INVOICE)

            if existing_approval:
                # 已有 Approval，检查是否需要发送通知
                if existing_approval.current_node:
                    notification_service = notification_service_factory(db, invoice.team_id)
                    approvers = get_approvers_by_role(db, existing_approval.current_node.approve_role)
                    flow = db.query(ApprovalFlow).filter(ApprovalFlow.id == existing_approval.flow_id).first()

                    for approver in approvers:
                        try:
                            asyncio.run(notification_service.notify_approval_pending(
                                entity_type=BusinessType.INVOICE,
                                entity_name=adapter.get_name(invoice) or invoice.application_number,
                                flow_name=flow.flow_name if flow else "发票审批",
                                node_name=existing_approval.current_node.node_name,
                                approver_open_id=approver.feishu_open_id or "",
                                approver_name=approver.name,
                                business_id=invoice.id,
                            ))
                            logger.info(f"发票 {invoice.id} 通知已发送给审批人 {approver.name}")
                        except Exception as notify_error:
                            logger.warning(f"发票 {invoice.id} 通知发送失败: {str(notify_error)}")

                logger.info(f"发票 {invoice.id} 已有 Approval 记录，通知已发送")
                skip_count += 1
                continue

            # 匹配审批流程
            flow, err = approval_flow_crud.match_flow_generic(
                db,
                BusinessType.INVOICE,
                invoice.team_id,
                amount=float(invoice.invoice_amount),
                license_type=None
            )

            if flow is None and err:
                logger.warning(f"发票 {invoice.id} 未匹配审批流程: {err}")
                # 未匹配流程，直接标记为 APPROVED（免审批直通）
                invoice.status = InvoiceApplicationStatus.APPROVED
                invoice.reviewed_time = datetime.now()
                db.commit()
                logger.info(f"发票 {invoice.id} 免审批直通，已标记为 APPROVED")
                success_count += 1
                continue

            if flow is None:
                logger.warning(f"发票 {invoice.id} 未配置审批流程，跳过")
                skip_count += 1
                continue

            # 创建 Approval 记录
            approval = approval_crud.create_approval_generic(
                db,
                BusinessType.INVOICE,
                invoice.id,
                invoice.team_id,
                flow,
                invoice.applicant_id,
                None  # applicant_name 为 None
            )

            # 创建审批记录（SUBMIT 动作）
            db.add(ApprovalRecord(
                approval_id=approval.id,
                node_id=approval.current_node_id,
                approver_id=invoice.applicant_id,
                approver_name=None,
                action=ApprovalAction.SUBMIT,
                comment=None,
                team_id=invoice.team_id,
                created_time=invoice.created_time  # 使用发票创建时间
            ))

            db.commit()

            # 发送飞书通知给审批人
            if approval.current_node:
                notification_service = notification_service_factory(db, invoice.team_id)
                approvers = get_approvers_by_role(db, approval.current_node.approve_role)

                for approver in approvers:
                    try:
                        # 使用 asyncio 运行异步通知方法
                        asyncio.run(notification_service.notify_approval_pending(
                            entity_type=BusinessType.INVOICE,
                            entity_name=adapter.get_name(invoice) or invoice.application_number,
                            flow_name=flow.flow_name,
                            node_name=approval.current_node.node_name,
                            approver_open_id=approver.feishu_open_id or "",
                            approver_name=approver.name,
                            business_id=invoice.id,
                        ))
                        logger.info(f"发票 {invoice.id} 通知已发送给审批人 {approver.name}")
                    except Exception as notify_error:
                        logger.warning(f"发票 {invoice.id} 通知发送失败: {str(notify_error)}")

            logger.info(f"发票 {invoice.id} Approval 记录创建成功（Approval ID: {approval.id})")
            success_count += 1

        except Exception as e:
            logger.error(f"发票 {invoice.id} 处理失败: {str(e)}")
            error_count += 1
            db.rollback()

    # 3. 输出统计结果
    logger.info("=" * 50)
    logger.info(f"迁移完成:")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  跳过: {skip_count}")
    logger.info(f"  失败: {error_count}")
    logger.info("=" * 50)


def main():
    """主函数"""
    logger.info("开始发票审批数据迁移...")

    # 创建数据库会话
    db = SessionLocal()

    try:
        # 执行迁移
        migrate_invoice_approvals(db)

        logger.info("迁移脚本执行完成")

    except Exception as e:
        logger.error(f"迁移脚本执行失败: {str(e)}")
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()