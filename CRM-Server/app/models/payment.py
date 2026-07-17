from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, BigInteger, String, Text, DateTime, Date, Numeric, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.invoice import InvoiceApplicationStatus
from app.constants.approval_phase import ApprovalPhase


class PaymentPlanStatus:
    PENDING = "PENDING"
    OVERDUE = "OVERDUE"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"


class PaymentConfirmationStatus:
    DRAFT = "DRAFT"          # 草稿状态（新增）
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"


class PaymentPlan(Base):
    __tablename__ = "crm_contract_payment_plans"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='CASCADE'), nullable=False, comment="关联的合同ID")

    # 新增：计划编号
    plan_number = Column(String(50), unique=True, nullable=False, comment="回款计划编号（系统自动生成）")

    stage_name = Column(String(100), nullable=False, comment="回款阶段名，如：首付款、中期款、尾款")
    planned_amount = Column(Numeric(12, 2), nullable=False, comment="计划回款金额")
    due_date = Column(Date, nullable=False, comment="计划回款日期")
    status = Column(String(20), nullable=False, default=PaymentPlanStatus.PENDING, comment="回款状态：PENDING, OVERDUE, PARTIAL, COMPLETED")
    notes = Column(Text, comment="备注")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    contract = relationship("Contract", back_populates="payment_plans")
    payment_records = relationship("PaymentRecord", back_populates="payment_plan", cascade="all, delete-orphan")
    invoice_applications = relationship("InvoiceApplication", back_populates="payment_plan", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_payment_plan_team_id', 'team_id'),
        Index('idx_payment_plan_number', 'plan_number'),
    )

    @property
    def paid_amount(self) -> Decimal:
        """累计已回款金额 = sum of payment_records.actual_amount"""
        try:
            if not self.payment_records:
                return Decimal('0.00')
            return sum(Decimal(str(r.actual_amount)) for r in self.payment_records)
        except Exception:
            # Handle detached instance or other errors
            return Decimal('0.00')

    @property
    def remaining_amount(self) -> Decimal:
        """待回款金额 = 计划金额 - 累计已回款"""
        return self.planned_amount - self.paid_amount

    @property
    def invoiced_amount(self) -> Decimal:
        """已开票金额 = 关联发票申请的总金额（仅已开票状态 ISSUED）"""
        try:
            if not self.invoice_applications:
                return Decimal('0.00')
            return sum(
                Decimal(str(inv.invoice_amount)) for inv in self.invoice_applications
                if inv.status == InvoiceApplicationStatus.ISSUED
            )
        except Exception:
            # Handle detached instance or other errors
            return Decimal('0.00')

    @property
    def invoice_count(self) -> int:
        """发票申请数量"""
        try:
            if not self.invoice_applications:
                return 0
            return len(self.invoice_applications)
        except Exception:
            # Handle detached instance or other errors
            return 0

    def __repr__(self):
        # 完全不访问属性，避免 DetachedInstanceError
        return f"<PaymentPlan>"


class PaymentRecord(Base):
    __tablename__ = "crm_payment_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")

    # 新增：记录编号
    record_number = Column(String(50), unique=True, nullable=False, comment="回款记录编号（系统自动生成）")

    payment_plan_id = Column(BigInteger, ForeignKey('crm_contract_payment_plans.id', ondelete='CASCADE'), nullable=False, comment="关联的回款计划ID")
    actual_amount = Column(Numeric(12, 2), nullable=False, comment="实际回款金额")
    actual_payer_name = Column(String(200), comment="实际付款方名称")
    payment_date = Column(Date, nullable=False, comment="实际回款日期")
    proof_attachment = Column(String(500), comment="回款凭证附件URL")
    notes = Column(Text, comment="备注")
    creator_id = Column(String(100), nullable=False, comment="创建人（登记人）系统用户ID")
    creator_name = Column(String(100), comment="创建人姓名")
    confirmation_status = Column(String(20), nullable=False, default=PaymentConfirmationStatus.PENDING, comment="确认状态：PENDING(待确认), CONFIRMED(已确认), DISPUTED(有争议)")
    approval_phase = Column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT,
        comment="审批流程状态：draft/pending_review/approved/rejected"
    )
    confirmed_by = Column(String(100), comment="确认人（财务人员）系统用户ID")
    confirmed_by_name = Column(String(100), comment="确认人姓名")
    confirmed_time = Column(DateTime, comment="确认入账时间")
    confirmation_notes = Column(Text, comment="确认备注")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")

    # 审批关联
    approval_id = Column(BigInteger, ForeignKey('crm_contract_approvals.id', ondelete='SET NULL'), nullable=True, comment="审批实例ID")

    payment_plan = relationship("PaymentPlan", back_populates="payment_records")
    invoice_applications = relationship("InvoiceApplication", back_populates="payment_record", cascade="all, delete-orphan")
    approval = relationship("Approval", foreign_keys=[approval_id])

    __table_args__ = (
        Index('idx_payment_record_team_id', 'team_id'),
        Index('idx_payment_record_number', 'record_number'),
    )

    def __repr__(self):
        return f"<PaymentRecord(id={self.id}, payment_plan_id={self.payment_plan_id}, actual_amount={self.actual_amount}, payment_date={self.payment_date})>"

    def get_current_approver_name(self) -> Optional[str]:
        """
        获取当前审批节点名称（审批中状态时）

        Returns:
            当前审批节点名称，如无审批或非待审批状态则返回 None

        Note:
            此方法返回的是审批节点名称（node_name），不是审批人姓名。
            审批人姓名应该从 approve_role 查询角色成员得到。
            此方法已废弃，建议使用 API 层的 _get_current_approver_names 函数。
        """
        if not self.approval:
            return None

        # 检查审批状态是否为 PENDING
        if self.approval.status != 'PENDING':
            return None

        # 获取当前审批节点
        if not self.approval.current_node:
            return None

        # 注意：此方法返回节点名称，不是审批人姓名
        # 审批人姓名应该从 approve_role 查询
        return self.approval.current_node.node_name
