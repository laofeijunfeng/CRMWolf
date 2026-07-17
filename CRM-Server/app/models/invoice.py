from sqlalchemy import Column, BigInteger, String, Text, DateTime, Numeric, Boolean, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.constants.approval_phase import ApprovalPhase


class TitleTypeEnum:
    COMPANY = "COMPANY"
    PERSONAL = "PERSONAL"


class InvoiceApplicationStatus:
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"


class InvoiceType:
    VAT_SPECIAL = "VAT_SPECIAL"
    VAT_NORMAL = "VAT_NORMAL"


class InvoiceTitle(Base):
    __tablename__ = "crm_invoice_titles"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    title_type = Column(String(10), nullable=False, comment="抬头类型：COMPANY(单位), PERSONAL(个人)")
    title = Column(String(255), nullable=False, comment="开票抬头")
    taxpayer_id = Column(String(100), nullable=False, comment="纳税人识别号")
    bank_name = Column(String(255), comment="开户行")
    bank_account = Column(String(100), comment="开户账号")
    address = Column(String(500), comment="开票地址")
    phone = Column(String(50), comment="电话")
    is_default = Column(Boolean, nullable=False, default=False, comment="是否默认抬头：0:否, 1:是")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="invoice_titles")
    invoice_applications = relationship("InvoiceApplication", back_populates="invoice_title")

    __table_args__ = (
        Index('idx_invoice_title_team_id', 'team_id'),
    )

    def __repr__(self):
        return f"<InvoiceTitle(id={self.id}, title={self.title}, taxpayer_id={self.taxpayer_id})>"


class InvoiceApplication(Base):
    __tablename__ = "crm_invoice_applications"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    application_number = Column(String(50), nullable=False, unique=True, comment="申请单号")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='CASCADE'), nullable=False, comment="关联合同ID")
    opportunity_id = Column(BigInteger, ForeignKey('crm_opportunities.id', ondelete='CASCADE'), nullable=False, comment="关联商机ID")
    payment_plan_id = Column(BigInteger, ForeignKey('crm_contract_payment_plans.id', ondelete='CASCADE'), nullable=False, comment="关联回款计划ID")
    payment_record_id = Column(BigInteger, ForeignKey('crm_payment_records.id', ondelete='SET NULL'), comment="关联回款记录ID")
    invoice_title_id = Column(BigInteger, ForeignKey('crm_invoice_titles.id', ondelete='SET NULL'), comment="开票抬头ID（可为空，抬头删除后发票记录仍保留抬头信息）")
    invoice_amount = Column(Numeric(12, 2), nullable=False, comment="开票金额")
    invoice_type = Column(String(20), nullable=False, comment="发票类型：VAT_SPECIAL(增值税专用发票), VAT_NORMAL(普通发票)")
    status = Column(String(20), nullable=False, default=InvoiceApplicationStatus.DRAFT, comment="申请状态：DRAFT, PENDING_REVIEW, APPROVED, REJECTED, ISSUED")
    approval_phase = Column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT,
        comment="审批流程状态：draft/pending_review/approved/rejected"
    )
    applicant_id = Column(String(100), nullable=False, comment="申请人系统用户ID")
    reviewer_id = Column(String(100), comment="审批人系统用户ID")
    review_comment = Column(String(500), comment="审批意见")
    reviewed_time = Column(DateTime, comment="审批时间")
    
    invoice_title_type = Column(String(10), nullable=False, comment="抬头类型：COMPANY(单位), PERSONAL(个人)（开票时的快照）")
    invoice_title_text = Column(String(255), nullable=False, comment="开票抬头（开票时的快照）")
    invoice_taxpayer_id = Column(String(100), nullable=False, comment="纳税人识别号（开票时的快照）")
    invoice_bank_name = Column(String(255), comment="开户行（开票时的快照）")
    invoice_bank_account = Column(String(100), comment="开户账号（开票时的快照）")
    invoice_address = Column(String(500), comment="开票地址（开票时的快照）")
    invoice_phone = Column(String(50), comment="电话（开票时的快照）")

    # Task 2: 发票文件上传字段
    invoice_file_path = Column(String(500), comment="发票文件路径（相对路径）")
    invoice_number = Column(String(100), comment="发票号码（可选，便于后续查询）")
    issued_time = Column(DateTime, comment="开票时间（上传发票文件时间）")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="invoice_applications")
    contract = relationship("Contract", back_populates="invoice_applications")
    opportunity = relationship("Opportunity", back_populates="invoice_applications")
    payment_plan = relationship("PaymentPlan", back_populates="invoice_applications")
    payment_record = relationship("PaymentRecord", back_populates="invoice_applications")
    invoice_title = relationship("InvoiceTitle", back_populates="invoice_applications")

    __table_args__ = (
        Index('idx_invoice_application_team_id', 'team_id'),
    )

    def __repr__(self):
        return f"<InvoiceApplication(id={self.id}, application_number={self.application_number}, status={self.status})>"
