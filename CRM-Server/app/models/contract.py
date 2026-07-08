from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Date, Numeric, Index, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.constants.approval_phase import ApprovalPhase


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

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")

    contract_number = Column(String(50), unique=True, nullable=False, comment="合同编号（系统自动生成）")
    contract_name = Column(String(255), nullable=False, comment="合同名称")

    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    opportunity_id = Column(BigInteger, ForeignKey('crm_opportunities.id', ondelete='CASCADE'), nullable=False, comment="关联商机ID")
    signing_contact_id = Column(BigInteger, ForeignKey('crm_contacts.id', ondelete='SET NULL'), nullable=False, comment="客户签约人ID")

    user_count = Column(Integer, nullable=False, comment="采购用户数")
    total_amount = Column(Numeric(12, 2), nullable=False, comment="合同总金额")
    license_type = Column(String(20), nullable=False, comment="授权模式：SUBSCRIPTION:订阅, PERPETUAL:买断")
    subscription_years = Column(Integer, nullable=True, comment="订阅年限（订阅制时必填）")
    standard_unit_price = Column(Numeric(10, 2), nullable=False, comment="标准单价（系统反算）")

    status = Column(String(20), nullable=False, default=ContractStatus.DRAFT, comment="合同状态")
    approval_phase = Column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT,
        comment="审批流程状态：draft/pending_review/approved/rejected"
    )
    signing_date = Column(Date, nullable=True, comment="签署日期")
    effective_date = Column(Date, nullable=True, comment="生效日期")
    expiry_date = Column(Date, nullable=True, comment="到期日期")

    total_paid_amount = Column(Numeric(12, 2), nullable=False, default=0, comment="累计已回款金额")
    payment_status = Column(String(20), nullable=False, default=PaymentStatus.UNPAID, comment="合同回款状态：UNPAID, PARTIAL, COMPLETED, OVERDUE")

    created_time = Column(DateTime, default=func.now(), nullable=False, comment="创建时间")
    creator_id = Column(String(100), nullable=False, comment="创建人飞书用户ID")
    last_modified_time = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False, comment="最后修改时间")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间（软删除标记）")

    payment_plans = relationship("PaymentPlan", back_populates="contract", cascade="all, delete-orphan")
    invoice_applications = relationship("InvoiceApplication", back_populates="contract", cascade="all, delete-orphan")
    license_applications = relationship("LicenseApplication", back_populates="contract")
    approvals = relationship("Approval", back_populates="contract", foreign_keys="[Approval.contract_id]")
    # 新增：Customer 和 Opportunity relationships
    customer = relationship("Customer", back_populates="contracts")
    opportunity = relationship("Opportunity", back_populates="contracts")

    __table_args__ = (
        Index('idx_contract_customer', 'customer_id'),
        Index('idx_contract_opportunity', 'opportunity_id'),
        Index('idx_contract_status', 'status'),
        Index('idx_contract_number', 'contract_number'),
        Index('idx_contract_signing_contact', 'signing_contact_id'),
        Index('idx_contract_payment_status', 'payment_status'),
        Index('idx_team_id', 'team_id'),
    )
