from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Numeric, Text, ForeignKey, Index, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class ProcurementMethod(Base):
    __tablename__ = "crm_procurement_methods"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    code = Column(String(50), unique=True, nullable=False, comment="采购方式编码，如: PUBLIC_BIDDING")
    name = Column(String(100), nullable=False, comment="采购方式名称，如：公开招标")
    description = Column(String(500), nullable=True, comment="描述说明")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用: 1:启用, 0:停用")
    sort_order = Column(Integer, nullable=False, comment="排序号，用于前端展示排序")
    
    created_by = Column(String(100), nullable=False, comment="创建人飞书用户ID")
    updated_by = Column(String(100), nullable=True, comment="最后更新人飞书用户ID")
    created_time = Column(DateTime, default=func.now(), nullable=False, comment="创建时间")
    updated_time = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False, comment="最后更新时间")
    
    stage_templates = relationship("ProcurementStageTemplate", back_populates="procurement_method", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_procurement_methods_sort_order', 'sort_order'),
        Index('ix_procurement_methods_is_active', 'is_active'),
        {'comment': '采购方式表'}
    )


class ProcurementStageTemplate(Base):
    __tablename__ = "crm_procurement_stage_templates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    procurement_method_id = Column(BigInteger, ForeignKey('crm_procurement_methods.id'), nullable=False, comment="采购方式ID")
    template_code = Column(String(50), nullable=False, comment="模板阶段编码，同一方式下唯一")
    stage_name = Column(String(100), nullable=False, comment="阶段名称")
    win_probability = Column(Integer, nullable=False, comment="阶段赢率 0-100")
    sort_order = Column(Integer, nullable=False, comment="阶段顺序，同一方式下唯一，决定流程顺序")
    is_default_start = Column(Integer, nullable=False, default=0, comment="默认起始阶段: 1:是, 0:否")
    can_skip = Column(Integer, nullable=False, default=0, comment="是否可跳过: 1:是, 0:否")
    description = Column(String(500), nullable=True, comment="阶段描述")
    
    version = Column(Integer, nullable=False, default=1, comment="版本号，从1开始，每次修改递增")
    version_lock = Column(Integer, nullable=False, default=0, comment="乐观锁版本，每次更新递增")
    
    created_by = Column(String(100), nullable=False, comment="创建人飞书用户ID")
    updated_by = Column(String(100), nullable=True, comment="最后更新人飞书用户ID")
    created_time = Column(DateTime, default=func.now(), nullable=False, comment="创建时间")
    updated_time = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False, comment="最后更新时间")
    
    procurement_method = relationship("ProcurementMethod", back_populates="stage_templates")
    
    __table_args__ = (
        Index('ix_procurement_stage_templates_method_code', 'procurement_method_id', 'template_code', unique=True),
        Index('ix_procurement_stage_templates_sort_order', 'procurement_method_id', 'sort_order'),
        {'comment': '采购阶段模板表'}
    )


class OpportunityStageSnapshot(Base):
    __tablename__ = "crm_opportunity_stage_snapshots"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    opportunity_id = Column(BigInteger, ForeignKey('crm_opportunities.id'), nullable=False, comment="商机ID")
    procurement_stage_template_id = Column(BigInteger, ForeignKey('crm_procurement_stage_templates.id'), nullable=False, comment="阶段模板ID")
    
    stage_name = Column(String(100), nullable=False, comment="快照：阶段名称，记录进入时的名称")
    win_probability = Column(Integer, nullable=False, comment="快照：阶段赢率 0-100，记录进入时的赢率")
    template_sort_order = Column(Integer, nullable=False, comment="快照：阶段顺序，记录进入时模板的sort_order")
    template_code = Column(String(50), nullable=False, comment="快照：阶段编码，记录进入时模板的编码")
    snapshot_version = Column(Integer, nullable=False, comment="快照版本，对应模板版本")
    
    entered_at = Column(DateTime, default=func.now(), nullable=False, comment="进入该阶段的时间")
    exited_at = Column(DateTime, nullable=True, comment="离开该阶段的时间，NULL表示当前阶段")
    
    __table_args__ = (
        Index('ix_opportunity_stage_snapshots_opportunity_id', 'opportunity_id'),
        Index('ix_opportunity_stage_snapshots_entered_at', 'entered_at'),
        {'comment': '商机阶段快照表'}
    )


class StageTemplateChangeLog(Base):
    __tablename__ = "crm_stage_template_change_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    template_id = Column(BigInteger, ForeignKey('crm_procurement_stage_templates.id'), nullable=False, comment="阶段模板ID")
    change_type = Column(String(20), nullable=False, comment="变更类型: CREATE, UPDATE, DELETE")
    
    old_data = Column(Text, nullable=True, comment="变更前数据，旧值的JSON快照")
    new_data = Column(Text, nullable=True, comment="变更后数据，新值的JSON快照")
    
    changed_by = Column(String(100), nullable=False, comment="变更人飞书用户ID")
    changed_at = Column(DateTime, default=func.now(), nullable=False, comment="变更时间")
    reason = Column(String(500), nullable=True, comment="变更原因")
    
    __table_args__ = (
        Index('ix_stage_template_change_logs_template_id', 'template_id'),
        Index('ix_stage_template_change_logs_changed_at', 'changed_at'),
        {'comment': '阶段模板变更日志表'}
    )
