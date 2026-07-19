from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Date, func, Index, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.core.database import Base
from app.constants.approval_phase import ApprovalPhase


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

    支持团队隔离：不同团队可配置不同的销售阶段
    """
    __tablename__ = "crm_opportunity_stages"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID（NULL表示系统默认模板）")
    procurement_method_id = Column(BigInteger, nullable=True, comment="采购方式ID")
    stage_code = Column(String(100), nullable=False, comment="阶段编码")
    stage_name = Column(String(100), nullable=False, comment="阶段名称")
    win_probability = Column(Integer, nullable=False, default=0, comment="赢率（0-100）")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序序号")
    description = Column(String(500), nullable=True, comment="阶段描述")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用：0:否, 1:是")
    is_default_start = Column(Integer, nullable=False, default=0, comment="是否默认起始阶段：0:否, 1:是")
    can_skip = Column(Integer, nullable=False, default=0, comment="是否可跳过：0:否, 1:是")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

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

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    opportunity_name = Column(String(255), nullable=False, comment="商机名称")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    procurement_method_id = Column(BigInteger, nullable=True, comment="采购方式ID")
    current_stage_snapshot_id = Column(BigInteger, nullable=True, comment="当前阶段快照ID")
    current_stage_name = Column(String(100), nullable=True, comment="当前阶段名称")
    current_win_probability = Column(Integer, nullable=True, comment="当前阶段赢率")
    current_stage_entered_at = Column(DateTime, nullable=True, comment="当前阶段进入时间")
    total_amount = Column(Numeric(12, 2), nullable=False, comment="预计总金额")
    user_count = Column(Integer, nullable=False, comment="采购用户数")
    unit_price = Column(Numeric(10, 2), nullable=False, comment="标准单价（系统自动计算）")
    license_type = Column(String(20), nullable=False, comment="授权模式：SUBSCRIPTION:订阅, PERPETUAL:买断")
    subscription_years = Column(Integer, nullable=True, comment="订阅年限（订阅制时必填）")
    purchase_type = Column(String(20), nullable=False, comment="采购类型：NEW:新购, RENEWAL:续购, EXPANSION:增购")
    decision_maker_count = Column(Integer, nullable=True, comment="采购决策人数")
    expected_closing_date = Column(Date, nullable=False, comment="预计成交日期")
    procurement_stage_id = Column(BigInteger, nullable=True, comment="采购阶段ID（已废弃，保留用于兼容）")
    win_probability = Column(Integer, nullable=False, default=0, comment="当前阶段赢率（0-100）")
    owner_id = Column(String(100), nullable=False, comment="负责人系统用户ID")
    status = Column(Integer, nullable=False, default=0, comment="商机状态：0:跟进中, 1:已赢单, 2:已输单")
    approval_phase = Column(String(20), nullable=False, default=ApprovalPhase.DRAFT, comment="审批流程状态：draft/pending_review/approved/rejected")
    loss_reason = Column(String(500), nullable=True, comment="输单原因")
    actual_amount = Column(Numeric(12, 2), nullable=True, comment="实际成交金额")
    actual_closing_date = Column(Date, nullable=True, comment="实际成交日期")

    creator_id = Column(String(100), nullable=False, comment="创建人")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")
    version = Column(Integer, nullable=False, default=1, comment="版本号（乐观锁）")

    contracts = relationship("Contract", back_populates="opportunity", cascade="all, delete-orphan")
    invoice_applications = relationship("InvoiceApplication", back_populates="opportunity", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_customer_id', 'customer_id'),
        Index('idx_procurement_stage_id', 'procurement_stage_id'),
        Index('idx_owner_id', 'owner_id'),
        Index('idx_status', 'status'),
        Index('idx_purchase_type', 'purchase_type'),
        Index('idx_license_type', 'license_type'),
        Index('idx_expected_closing_date', 'expected_closing_date'),
        Index('idx_created_time', 'created_time'),
        Index('idx_team_id', 'team_id'),
        {'comment': '商机表'}
    )
