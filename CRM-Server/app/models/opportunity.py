from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.approval_phase import ApprovalPhase
from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.invoice import InvoiceApplication
    from app.models.product import Product, ProductModule


class PurchaseType(PyEnum):
    NEW = "NEW"
    RENEWAL = "RENEWAL"
    EXPANSION = "EXPANSION"


class LicenseType(PyEnum):
    SUBSCRIPTION = "SUBSCRIPTION"
    PERPETUAL = "PERPETUAL"


class OpportunityStatus(PyEnum):
    FOLLOWING = 0
    WON = 1
    LOST = 2


class OpportunityStage(Base):
    """
    销售阶段配置表

    支持团队隔离\uff1a不同团队可配置不同的销售阶段
    """
    __tablename__ = "crm_opportunity_stages"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID\uff08NULL表示系统默认模板\uff09")
    procurement_method_id = Column(BigInteger, nullable=True, comment="采购方式ID")
    stage_code = Column(String(100), nullable=False, comment="阶段编码")
    stage_name = Column(String(100), nullable=False, comment="阶段名称")
    win_probability = Column(Integer, nullable=False, default=0, comment="赢率\uff080-100\uff09")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序序号")
    description = Column(String(500), nullable=True, comment="阶段描述")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用\uff1a0:否, 1:是")
    is_default_start = Column(Integer, nullable=False, default=0, comment="是否默认起始阶段\uff1a0:否, 1:是")
    can_skip = Column(Integer, nullable=False, default=0, comment="是否可跳过\uff1a0:否, 1:是")

    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间",
    )

    __table_args__ = (
        Index('idx_stage_code', 'stage_code'),
        Index('idx_sort_order', 'sort_order'),
        Index('idx_is_active', 'is_active'),
        Index('idx_procurement_method_id', 'procurement_method_id'),
        Index('idx_crm_opportunity_stages_team_id', 'team_id'),
        {'comment': '销售阶段配置表'}
    )


class Opportunity(Base):
    __tablename__ = "crm_opportunities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
        default=lambda: generate_public_id("opp"), comment="对外商机ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    opportunity_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="商机编号\uff08系统自动生成\uff09",
    )
    opportunity_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="商机名称")
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID",
    )
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey('crm_products.id', ondelete='RESTRICT'), nullable=True, comment="关联产品ID",
    )
    procurement_method_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="采购方式ID")
    current_stage_snapshot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="当前阶段快照ID")
    current_stage_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="当前阶段名称")
    current_win_probability: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="当前阶段赢率")
    current_stage_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="当前阶段进入时间",
    )
    deal_journey_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey('crm_customer_deal_journeys.id', ondelete='SET NULL'),
        nullable=True, comment="成交旅程ID\uff08系统自动关联\uff09",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="预计总金额")
    user_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="采购用户数")
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="标准单价\uff08系统自动计算\uff09"
    )
    license_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="授权模式\uff1aSUBSCRIPTION:订阅, PERPETUAL:买断",
    )
    subscription_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="订阅年限\uff08订阅制时必填\uff09"
    )
    purchase_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="采购类型\uff1aNEW:新购, RENEWAL:续购, EXPANSION:增购",
    )
    decision_maker_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="采购决策人数")
    expected_closing_date: Mapped[date] = mapped_column(Date, nullable=False, comment="预计成交日期")
    procurement_stage_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="采购阶段ID\uff08已废弃\uff0c保留用于兼容\uff09",
    )
    win_probability: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="当前阶段赢率\uff080-100\uff09"
    )
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="负责人系统用户ID")
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="商机状态\uff1a0:跟进中, 1:已赢单, 2:已输单",
    )
    approval_phase: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalPhase.DRAFT.value,
        comment="审批流程状态\uff1adraft/pending_review/approved/rejected",
    )
    loss_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="输单原因")
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, comment="实际成交金额")
    actual_closing_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="实际成交日期")

    creator_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="创建人")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号\uff08乐观锁\uff09")

    contracts: Mapped[list["Contract"]] = relationship(
        "Contract", back_populates="opportunity", cascade="all, delete-orphan",
    )
    invoice_applications: Mapped[list["InvoiceApplication"]] = relationship(
        "InvoiceApplication", back_populates="opportunity", cascade="all, delete-orphan",
    )
    product: Mapped["Product | None"] = relationship("Product")
    module_links: Mapped[list["OpportunityProductModule"]] = relationship(
        "OpportunityProductModule",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )

    @property
    def updated_time(self) -> datetime:
        return self.last_modified_time

    @property
    def selected_modules(self) -> list["ProductModule"]:
        links = list(self.module_links or [])
        return [link.module for link in links if link.module is not None]

    __table_args__ = (
        Index('idx_customer_id', 'customer_id'),
        Index('idx_opportunity_product_id', 'product_id'),
        Index('idx_procurement_stage_id', 'procurement_stage_id'),
        Index('idx_owner_id', 'owner_id'),
        Index('idx_status', 'status'),
        Index('idx_purchase_type', 'purchase_type'),
        Index('idx_license_type', 'license_type'),
        Index('idx_expected_closing_date', 'expected_closing_date'),
        Index('idx_created_time', 'created_time'),
        Index('idx_team_id', 'team_id'),
        Index('idx_opportunity_public_id', 'public_id'),
        Index('idx_opportunity_deal_journey_id', 'deal_journey_id'),
        {'comment': '商机表'}
    )


class OpportunityProductModule(Base):
    __tablename__ = "crm_opportunity_product_modules"

    opportunity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_opportunities.id", ondelete="CASCADE"), primary_key=True, comment="商机ID",
    )
    product_module_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_product_modules.id", ondelete="RESTRICT"), primary_key=True, comment="产品模块ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")

    opportunity: Mapped[Opportunity] = relationship("Opportunity", back_populates="module_links")
    module: Mapped["ProductModule | None"] = relationship("ProductModule")

    __table_args__ = (
        UniqueConstraint("opportunity_id", "product_module_id", name="uq_opportunity_product_module"),
        Index("idx_opportunity_product_modules_team", "team_id"),
        {"comment": "商机所选产品模块"},
    )
