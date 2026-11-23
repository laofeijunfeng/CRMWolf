from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.approval_phase import ApprovalPhase
from app.core.database import Base
from app.utils.time import business_now

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity
    from app.models.payment import PaymentPlan, PaymentRecord
    from app.models.user import User


class TitleTypeEnum:
    COMPANY = "COMPANY"
    PERSONAL = "PERSONAL"


class InvoiceApplicationStatus:
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"


class InvoiceReissueApplicationStatus:
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class InvoiceRedOffsetSourceType:
    MANUAL = "MANUAL"
    REISSUE = "REISSUE"


class InvoiceType:
    VAT_SPECIAL = "VAT_SPECIAL"
    VAT_NORMAL = "VAT_NORMAL"


class InvoiceTitle(Base):
    __tablename__ = "crm_invoice_titles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False, comment="关联客户ID"
    )
    title_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="抬头类型\uff1aCOMPANY(单位), PERSONAL(个人)"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="开票抬头")
    taxpayer_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="纳税人识别号")
    bank_name: Mapped[str | None] = mapped_column(String(255), comment="开户行")
    bank_account: Mapped[str | None] = mapped_column(String(100), comment="开户账号")
    address: Mapped[str | None] = mapped_column(String(500), comment="开票地址")
    phone: Mapped[str | None] = mapped_column(String(50), comment="电话")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否默认抬头\uff1a0:否, 1:是"
    )
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="invoice_titles")
    invoice_applications: Mapped[list["InvoiceApplication"]] = relationship(
        "InvoiceApplication", back_populates="invoice_title"
    )

    __table_args__ = (Index("idx_invoice_title_team_id", "team_id"),)

    def __repr__(self) -> str:
        return f"<InvoiceTitle(id={self.id}, title={self.title}, taxpayer_id={self.taxpayer_id})>"


class InvoiceApplication(Base):
    __tablename__ = "crm_invoice_applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    application_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment="申请单号")
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=False, comment="关联客户ID"
    )
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_contracts.id", ondelete="CASCADE"), nullable=False, comment="关联合同ID"
    )
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_opportunities.id", ondelete="CASCADE"), nullable=False, comment="关联商机ID"
    )
    payment_plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_contract_payment_plans.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联回款计划ID",
    )
    deal_journey_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_customer_deal_journeys.id", ondelete="SET NULL"),
        nullable=True,
        comment="成交旅程ID\uff08系统自动关联\uff09",
    )
    payment_record_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("crm_payment_records.id", ondelete="SET NULL"), comment="关联回款记录ID"
    )
    invoice_title_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_invoice_titles.id", ondelete="SET NULL"),
        comment="开票抬头ID\uff08可为空\uff0c抬头删除后发票记录仍保留抬头信息\uff09",
    )
    invoice_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="开票金额")
    invoice_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="发票类型\uff1aVAT_SPECIAL(增值税专用发票), VAT_NORMAL(普通发票)"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InvoiceApplicationStatus.DRAFT,
        comment="申请状态\uff1aDRAFT, PENDING_REVIEW, APPROVED, REJECTED, ISSUED",
    )
    approval_phase: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT.value,
        comment="审批流程状态\uff1adraft/pending_review/approved/rejected",
    )
    applicant_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="申请人系统用户ID")
    reviewer_id: Mapped[str | None] = mapped_column(String(100), comment="审批人系统用户ID")
    review_comment: Mapped[str | None] = mapped_column(String(500), comment="审批意见")
    reviewed_time: Mapped[datetime | None] = mapped_column(DateTime, comment="审批时间")

    invoice_title_type: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="抬头类型\uff1aCOMPANY(单位), PERSONAL(个人)\uff08开票时的快照\uff09"
    )
    invoice_title_text: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="开票抬头\uff08开票时的快照\uff09"
    )
    invoice_taxpayer_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="纳税人识别号\uff08开票时的快照\uff09"
    )
    invoice_bank_name: Mapped[str | None] = mapped_column(String(255), comment="开户行\uff08开票时的快照\uff09")
    invoice_bank_account: Mapped[str | None] = mapped_column(String(100), comment="开户账号\uff08开票时的快照\uff09")
    invoice_address: Mapped[str | None] = mapped_column(String(500), comment="开票地址\uff08开票时的快照\uff09")
    invoice_phone: Mapped[str | None] = mapped_column(String(50), comment="电话\uff08开票时的快照\uff09")
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="申请备注")

    # Task 2: 发票文件上传字段
    invoice_file_path: Mapped[str | None] = mapped_column(String(500), comment="发票文件路径\uff08相对路径\uff09")
    invoice_number: Mapped[str | None] = mapped_column(
        String(100), comment="发票号码\uff08可选\uff0c便于后续查询\uff09"
    )
    issued_time: Mapped[datetime | None] = mapped_column(DateTime, comment="开票时间\uff08上传发票文件时间\uff09")

    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="invoice_applications")
    contract: Mapped["Contract"] = relationship("Contract", back_populates="invoice_applications")
    opportunity: Mapped["Opportunity"] = relationship("Opportunity", back_populates="invoice_applications")
    payment_plan: Mapped["PaymentPlan"] = relationship("PaymentPlan", back_populates="invoice_applications")
    payment_record: Mapped["PaymentRecord | None"] = relationship(
        "PaymentRecord", back_populates="invoice_applications"
    )
    invoice_title: Mapped["InvoiceTitle | None"] = relationship("InvoiceTitle", back_populates="invoice_applications")
    reissue_applications: Mapped[list["InvoiceReissueApplication"]] = relationship(
        "InvoiceReissueApplication", back_populates="original_invoice_application"
    )
    red_offsets: Mapped[list["InvoiceRedOffset"]] = relationship(
        "InvoiceRedOffset", back_populates="invoice_application"
    )

    if TYPE_CHECKING:
        # Optional request-time enrichment, not mapped attributes.
        contract_name: str
        contract_number: str
        stage_name: str
        planned_amount: float
        applicant: User | None
        applicant_name: str

    __table_args__ = (
        Index("idx_invoice_application_team_id", "team_id"),
        Index("idx_invoice_application_deal_journey_id", "deal_journey_id"),
    )

    def __repr__(self) -> str:
        return f"<InvoiceApplication(id={self.id}, application_number={self.application_number}, status={self.status})>"


class InvoiceReissueApplication(Base):
    __tablename__ = "crm_invoice_reissue_applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    application_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment="重开申请单号")
    original_invoice_application_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_invoice_applications.id", ondelete="CASCADE"),
        nullable=False,
        comment="原发票申请ID",
    )
    applicant_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="申请人系统用户ID")
    reason: Mapped[str] = mapped_column(String(500), nullable=False, comment="重开原因")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvoiceReissueApplicationStatus.DRAFT, comment="重开申请状态"
    )
    approval_phase: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT.value,
        comment="审批流程状态\uff1adraft/pending_review/approved/rejected",
    )

    invoice_title_type: Mapped[str] = mapped_column(String(10), nullable=False, comment="新发票抬头类型快照")
    invoice_title_text: Mapped[str] = mapped_column(String(255), nullable=False, comment="新发票开票抬头快照")
    invoice_taxpayer_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="新发票纳税人识别号快照")
    invoice_bank_name: Mapped[str | None] = mapped_column(String(255), comment="新发票开户行快照")
    invoice_bank_account: Mapped[str | None] = mapped_column(String(100), comment="新发票开户账号快照")
    invoice_address: Mapped[str | None] = mapped_column(String(500), comment="新发票开票地址快照")
    invoice_phone: Mapped[str | None] = mapped_column(String(50), comment="新发票电话快照")
    invoice_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="新发票金额")
    invoice_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="新发票类型")

    red_invoice_file_path: Mapped[str | None] = mapped_column(String(500), comment="红字发票文件路径")
    red_invoice_number: Mapped[str | None] = mapped_column(String(100), comment="红字发票号码")
    red_issued_time: Mapped[datetime | None] = mapped_column(DateTime, comment="红字发票开具时间")
    new_invoice_file_path: Mapped[str | None] = mapped_column(String(500), comment="新蓝字发票文件路径")
    new_invoice_number: Mapped[str | None] = mapped_column(String(100), comment="新蓝字发票号码")
    new_issued_time: Mapped[datetime | None] = mapped_column(DateTime, comment="新蓝字发票开具时间")
    completed_time: Mapped[datetime | None] = mapped_column(DateTime, comment="重开完成时间")

    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    original_invoice_application: Mapped["InvoiceApplication"] = relationship(
        "InvoiceApplication", back_populates="reissue_applications"
    )
    red_offset: Mapped["InvoiceRedOffset | None"] = relationship(
        "InvoiceRedOffset", back_populates="reissue_application", uselist=False
    )

    __table_args__ = (
        Index("idx_invoice_reissue_team_id", "team_id"),
        Index("idx_invoice_reissue_original_invoice", "original_invoice_application_id"),
        Index("idx_invoice_reissue_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<InvoiceReissueApplication(id={self.id}, application_number={self.application_number}, "
            f"status={self.status})>"
        )


class InvoiceRedOffset(Base):
    __tablename__ = "crm_invoice_red_offsets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    invoice_application_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_invoice_applications.id", ondelete="CASCADE"),
        nullable=False,
        comment="被冲红的原发票申请ID",
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="冲红来源\uff1aMANUAL/REISSUE")
    reissue_application_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_invoice_reissue_applications.id", ondelete="SET NULL"),
        nullable=True,
        comment="来源重开申请ID",
    )
    red_invoice_file_path: Mapped[str] = mapped_column(String(500), nullable=False, comment="红字发票文件路径")
    red_invoice_number: Mapped[str | None] = mapped_column(String(100), comment="红字发票号码")
    reason: Mapped[str | None] = mapped_column(String(500), comment="冲红原因")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, comment="操作人系统用户ID")
    red_offset_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, comment="冲红时间"
    )
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    invoice_application: Mapped["InvoiceApplication"] = relationship("InvoiceApplication", back_populates="red_offsets")
    reissue_application: Mapped["InvoiceReissueApplication | None"] = relationship(
        "InvoiceReissueApplication", back_populates="red_offset"
    )

    __table_args__ = (
        Index("idx_invoice_red_offset_team_id", "team_id"),
        Index("idx_invoice_red_offset_invoice", "invoice_application_id"),
        Index("idx_invoice_red_offset_reissue", "reissue_application_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<InvoiceRedOffset(id={self.id}, invoice_application_id={self.invoice_application_id}, "
            f"source_type={self.source_type})>"
        )
