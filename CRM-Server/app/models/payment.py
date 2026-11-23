from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.approval_phase import ApprovalPhase
from app.core.database import Base
from app.models.invoice import InvoiceApplicationStatus
from app.utils.time import business_now

if TYPE_CHECKING:
    from app.models.approval import Approval
    from app.models.contract import Contract
    from app.models.invoice import InvoiceApplication


class PaymentPlanStatus:
    PENDING = "PENDING"
    OVERDUE = "OVERDUE"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"


class PaymentConfirmationStatus:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"


class PaymentPlan(Base):
    __tablename__ = "crm_contract_payment_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    contract_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_contracts.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的合同ID",
    )
    deal_journey_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_customer_deal_journeys.id", ondelete="SET NULL"),
        nullable=True,
        comment="成交旅程ID\uff08系统自动关联\uff09",
    )

    # 新增:计划编号
    plan_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="回款计划编号\uff08系统自动生成\uff09"
    )

    stage_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="回款阶段名\uff0c如\uff1a首付款、中期款、尾款"
    )
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="计划回款金额")
    due_date: Mapped[date] = mapped_column(Date, nullable=False, comment="计划回款日期")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentPlanStatus.PENDING,
        comment="回款状态\uff1aPENDING, OVERDUE, PARTIAL, COMPLETED",
    )
    notes: Mapped[str | None] = mapped_column(Text, comment="备注")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="payment_plans")
    payment_records: Mapped[list["PaymentRecord"]] = relationship(
        "PaymentRecord", back_populates="payment_plan", cascade="all, delete-orphan"
    )
    invoice_applications: Mapped[list["InvoiceApplication"]] = relationship(
        "InvoiceApplication", back_populates="payment_plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_payment_plan_team_id", "team_id"),
        Index("idx_payment_plan_number", "plan_number"),
        Index("idx_payment_plan_deal_journey_id", "deal_journey_id"),
    )

    @property
    def paid_amount(self) -> Decimal | Literal[0]:
        """累计已回款金额 = 审批通过的回款记录金额合计"""
        try:
            if not self.payment_records:
                return Decimal("0.00")
            return sum(
                Decimal(str(r.actual_amount))
                for r in self.payment_records
                if getattr(r.approval_phase, "value", r.approval_phase) == ApprovalPhase.APPROVED.value
            )
        except Exception:
            # Handle detached instance or other errors
            return Decimal("0.00")

    @property
    def remaining_amount(self) -> Decimal:
        """待回款金额 = 计划金额 - 累计已回款"""
        return self.planned_amount - self.paid_amount

    @property
    def invoiced_amount(self) -> Decimal | Literal[0]:
        """已开票金额 = 关联发票申请的总金额\uff08仅已开票状态 ISSUED\uff09"""
        try:
            if not self.invoice_applications:
                return Decimal("0.00")
            return sum(
                Decimal(str(inv.invoice_amount))
                for inv in self.invoice_applications
                if inv.status == InvoiceApplicationStatus.ISSUED
            )
        except Exception:
            # Handle detached instance or other errors
            return Decimal("0.00")

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

    def __repr__(self) -> str:
        # 完全不访问属性,避免 DetachedInstanceError
        return "<PaymentPlan>"


class PaymentRecord(Base):
    __tablename__ = "crm_payment_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")

    # 新增:记录编号
    record_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="回款记录编号\uff08系统自动生成\uff09"
    )
    # 客户端重试标识:仅用于回款登记写入幂等,普通用户不可见。
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="回款登记幂等键")
    idempotency_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="回款登记请求指纹")

    payment_plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_contract_payment_plans.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的回款计划ID",
    )
    deal_journey_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_customer_deal_journeys.id", ondelete="SET NULL"),
        nullable=True,
        comment="成交旅程ID\uff08系统自动关联\uff09",
    )
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="实际回款金额")
    actual_payer_name: Mapped[str | None] = mapped_column(String(200), comment="实际付款方名称")
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, comment="实际回款日期")
    proof_attachment: Mapped[str | None] = mapped_column(String(500), comment="回款凭证附件URL")
    notes: Mapped[str | None] = mapped_column(Text, comment="备注")
    renewal_headcount: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="续购人数")
    renewal_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="续购金额")
    expansion_headcount: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="增购人数")
    expansion_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="增购金额")

    commission_member_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="提成协作成员系统用户ID"
    )
    commission_member_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="提成协作成员姓名")
    creator_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="创建人\uff08登记人\uff09系统用户ID")
    creator_name: Mapped[str | None] = mapped_column(String(100), comment="创建人姓名")
    confirmation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentConfirmationStatus.PENDING,
        comment="确认状态\uff1aPENDING(待确认), CONFIRMED(已确认), DISPUTED(有争议)",
    )
    approval_phase: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT.value,
        comment="审批流程状态\uff1adraft/pending_review/approved/rejected",
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(100), comment="确认人\uff08财务人员\uff09系统用户ID")
    confirmed_by_name: Mapped[str | None] = mapped_column(String(100), comment="确认人姓名")
    confirmed_time: Mapped[datetime | None] = mapped_column(DateTime, comment="确认入账时间")
    confirmation_notes: Mapped[str | None] = mapped_column(Text, comment="确认备注")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=business_now,
        onupdate=business_now,
        comment="最后更新时间",
    )

    # 审批关联
    approval_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_contract_approvals.id", ondelete="SET NULL"),
        nullable=True,
        comment="审批实例ID",
    )

    payment_plan: Mapped["PaymentPlan"] = relationship("PaymentPlan", back_populates="payment_records")
    invoice_applications: Mapped[list["InvoiceApplication"]] = relationship(
        "InvoiceApplication", back_populates="payment_record", cascade="all, delete-orphan"
    )
    approval: Mapped["Approval | None"] = relationship("Approval", foreign_keys=[approval_id])

    __table_args__ = (
        Index("idx_payment_record_team_id", "team_id"),
        Index("idx_payment_record_number", "record_number"),
        Index("uq_payment_record_idempotency", "team_id", "idempotency_key", unique=True),
        Index("idx_payment_record_deal_journey_id", "deal_journey_id"),
        CheckConstraint(
            "("
            "renewal_headcount IS NULL AND renewal_amount IS NULL "
            "AND expansion_headcount IS NULL AND expansion_amount IS NULL"
            ") OR ("
            "renewal_headcount IS NOT NULL AND renewal_amount IS NOT NULL "
            "AND expansion_headcount IS NOT NULL AND expansion_amount IS NOT NULL"
            ")",
            name="ck_payment_record_composition_complete",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PaymentRecord(id={self.id}, payment_plan_id={self.payment_plan_id}, "
            f"actual_amount={self.actual_amount}, payment_date={self.payment_date})>"
        )

    def get_current_approver_name(self) -> str | None:
        """
        获取当前审批节点名称\uff08审批中状态时\uff09

        Returns:
            当前审批节点名称\uff0c如无审批或非待审批状态则返回 None

        Note:
            审批人姓名应从 ApprovalParticipant 的冻结 user_id 查询。
        """
        if not self.approval:
            return None

        # 检查审批状态是否为 PENDING
        if self.approval.status != "PENDING":
            return None

        # 快照实例的节点名称来自提交时冻结的节点快照;旧实例回退读取历史节点关系。
        if self.approval.nodes_snapshot is not None:
            from app.services.approval_routing import snapshot_entry_for_node

            entry = snapshot_entry_for_node(self.approval, self.approval.current_node_id)
            return entry.get("node_name") if entry else None
        if not self.approval.current_node:
            return None
        return self.approval.current_node.node_name
