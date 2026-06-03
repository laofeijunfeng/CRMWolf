from sqlalchemy import Column, BigInteger, String, Text, DateTime, Date, Numeric, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


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

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='CASCADE'), nullable=False, comment="关联的合同ID")
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
    )

    def __repr__(self):
        return f"<PaymentPlan(id={self.id}, contract_id={self.contract_id}, stage_name={self.stage_name}, planned_amount={self.planned_amount})>"


class PaymentRecord(Base):
    __tablename__ = "crm_payment_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    payment_plan_id = Column(BigInteger, ForeignKey('crm_contract_payment_plans.id', ondelete='CASCADE'), nullable=False, comment="关联的回款计划ID")
    actual_amount = Column(Numeric(12, 2), nullable=False, comment="实际回款金额")
    payment_date = Column(Date, nullable=False, comment="实际回款日期")
    proof_attachment = Column(String(500), comment="回款凭证附件URL")
    notes = Column(Text, comment="备注")
    creator_id = Column(String(100), nullable=False, comment="创建人（登记人）飞书用户ID")
    creator_name = Column(String(100), comment="创建人姓名")
    confirmation_status = Column(String(20), nullable=False, default=PaymentConfirmationStatus.PENDING, comment="确认状态：PENDING(待确认), CONFIRMED(已确认), DISPUTED(有争议)")
    confirmed_by = Column(String(100), comment="确认人（财务人员）飞书用户ID")
    confirmed_by_name = Column(String(100), comment="确认人姓名")
    confirmed_time = Column(DateTime, comment="确认入账时间")
    confirmation_notes = Column(Text, comment="确认备注")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")

    payment_plan = relationship("PaymentPlan", back_populates="payment_records")
    invoice_applications = relationship("InvoiceApplication", back_populates="payment_record", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_payment_record_team_id', 'team_id'),
    )

    def __repr__(self):
        return f"<PaymentRecord(id={self.id}, payment_plan_id={self.payment_plan_id}, actual_amount={self.actual_amount}, payment_date={self.payment_date})>"
