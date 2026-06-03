"""热力值权重配置模型

用于存储系统默认和团队自定义的权重配置。

表结构：
- crm_score_weight_configs: 权重配置表
- crm_score_details: 热力值计算明细表
"""
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, Index
from sqlalchemy.sql import func
from app.core.database import Base


class ScoreWeightConfig(Base):
    """热力值权重配置表

    支持分层配置：
    - team_id = NULL: 系统默认配置（不可删除）
    - team_id = 具体值: 团队自定义配置

    继承机制：新建团队时自动复制系统默认配置
    """
    __tablename__ = "crm_score_weight_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID（NULL表示系统默认）")
    module_type = Column(String(20), nullable=False, comment="模块类型：LEAD/CUSTOMER")
    factor_key = Column(String(50), nullable=False, comment="因子键名")
    factor_name = Column(String(100), nullable=False, comment="因子显示名称")
    weight_value = Column(Integer, nullable=False, comment="权重值（正负整数）")
    is_enabled = Column(Integer, nullable=False, default=1, comment="是否启用：1启用，0禁用")
    condition_rules = Column(Text, nullable=True, comment="条件规则JSON")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序序号")

    created_by = Column(String(100), nullable=False, comment="创建人")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_by = Column(String(100), nullable=True, comment="更新人")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_score_weight_team_module', 'team_id', 'module_type'),
        Index('idx_score_weight_factor_key', 'factor_key'),
        {'comment': '热力值权重配置表'}
    )


class ScoreDetail(Base):
    """热力值计算明细表

    记录每次计算各因子的贡献明细，支持可解释性。
    """
    __tablename__ = "crm_score_details"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    module_type = Column(String(20), nullable=False, comment="模块类型：LEAD/CUSTOMER")
    record_id = Column(BigInteger, nullable=False, comment="线索或客户ID")
    factor_key = Column(String(50), nullable=False, comment="因子键名")
    factor_name = Column(String(100), nullable=False, comment="因子名称")
    weight_value = Column(Integer, nullable=False, comment="权重值")
    actual_value = Column(String(200), nullable=True, comment="实际值")
    score_change = Column(Integer, nullable=False, comment="分数变化")
    reason = Column(String(500), nullable=True, comment="计算原因说明")

    calculated_time = Column(DateTime, nullable=False, default=func.now(), comment="计算时间")

    __table_args__ = (
        Index('idx_score_detail_record', 'module_type', 'record_id'),
        Index('idx_score_detail_calculated_time', 'calculated_time'),
        Index('idx_score_detail_team_id', 'team_id'),
        {'comment': '热力值计算明细表'}
    )