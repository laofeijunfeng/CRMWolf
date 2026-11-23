from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.approval_phase import ApprovalPhase
from app.core.database import Base
from app.utils.time import business_now

if TYPE_CHECKING:
    from app.models.approval import Approval
    from app.models.customer import Customer
    from app.models.invoice import InvoiceApplication
    from app.models.license_application import LicenseApplication
    from app.models.opportunity import Opportunity
    from app.models.payment import PaymentPlan


class ContractStatus:
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    SIGNED = "SIGNED"
    EFFECTIVE = "EFFECTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class PaymentStatus:
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"


class Contract(Base):
    __tablename__ = "crm_contracts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")

    contract_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="合同编号\uff08系统自动生成\uff09"
    )
    contract_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="合同名称")

    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID"
    )
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey('crm_opportunities.id', ondelete='CASCADE'), nullable=False, comment="关联商机ID"
    )
    deal_journey_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey('crm_customer_deal_journeys.id', ondelete='SET NULL'),
        nullable=True,
        comment="成交旅程ID\uff08系统自动关联\uff09",
    )
    signing_contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey('crm_contacts.id', ondelete='SET NULL'), nullable=True, comment="客户签约人ID"
    )

    user_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="采购用户数")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="合同总金额")
    license_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="授权模式\uff1aSUBSCRIPTION:订阅, PERPETUAL:买断"
    )
    subscription_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="订阅年限\uff08订阅制时必填\uff09"
    )
    standard_unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="标准单价\uff08系统反算\uff09"
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ContractStatus.DRAFT, comment="合同状态")
    approval_phase: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT.value,
        comment="审批流程状态\uff1adraft/pending_review/approved/rejected",
    )
    signing_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="签署日期")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生效日期")
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="到期日期")

    total_paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, comment="累计已回款金额"
    )
    payment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentStatus.UNPAID,
        comment="合同回款状态\uff1aUNPAID, PARTIAL, COMPLETED, OVERDUE",
    )
    contract_file_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="合同附件路径\uff08相对路径\uff09"
    )
    contract_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="合同附件原始文件名")
    contract_file_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="合同附件大小\uff08字节\uff09"
    )
    contract_file_mime_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="合同附件 MIME 类型"
    )

    created_time: Mapped[datetime] = mapped_column(DateTime, default=business_now, nullable=False, comment="创建时间")
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="合同负责人系统用户ID")
    creator_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="创建人系统用户ID")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, default=business_now, onupdate=business_now, nullable=False, comment="最后修改时间"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="删除时间\uff08软删除标记\uff09"
    )

    payment_plans: Mapped[list["PaymentPlan"]] = relationship(
        "PaymentPlan", back_populates="contract", cascade="all, delete-orphan"
    )
    invoice_applications: Mapped[list["InvoiceApplication"]] = relationship(
        "InvoiceApplication", back_populates="contract", cascade="all, delete-orphan"
    )
    license_applications: Mapped[list["LicenseApplication"]] = relationship(
        "LicenseApplication", back_populates="contract"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        "Approval", back_populates="contract", foreign_keys="[Approval.contract_id]"
    )
    customer: Mapped["Customer"] = relationship("Customer", back_populates="contracts")
    opportunity: Mapped["Opportunity"] = relationship("Opportunity", back_populates="contracts")

    __table_args__ = (
        Index('idx_contract_customer', 'customer_id'),
        Index('idx_contract_opportunity', 'opportunity_id'),
        Index('idx_contract_deal_journey_id', 'deal_journey_id'),
        Index('idx_contract_status', 'status'),
        Index('idx_contract_number', 'contract_number'),
        Index('idx_contract_signing_contact', 'signing_contact_id'),
        Index('idx_contract_payment_status', 'payment_status'),
        Index('idx_team_id', 'team_id'),
        Index('idx_contract_owner_id', 'owner_id'),
    )
