"""
系统配置模型

用于存储团队级别的系统配置，如飞书通知配置等。
"""
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class ConfigType(str, enum.Enum):
    """配置类型枚举"""
    NOTIFICATION = "notification"  # 通知配置
    SECURITY = "security"          # 安全配置
    INTEGRATION = "integration"    # 集成配置


class SystemConfig(Base):
    """系统配置模型（团队级配置存储）"""
    __tablename__ = "crm_system_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID（团队隔离）")
    config_key = Column(String(100), nullable=False, comment="配置键")
    config_value = Column(Text, nullable=False, comment="配置值")
    config_type = Column(String(50), nullable=False, comment="配置类型（notification/security/integration）")
    description = Column(String(200), comment="配置描述")
    created_time = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        UniqueConstraint('team_id', 'config_key', name='uk_team_config_key'),
        Index('idx_crm_system_configs_team_id', 'team_id'),
        Index('idx_crm_system_configs_config_type', 'config_type'),
        {'comment': '系统配置表'}
    )

    def __repr__(self):
        return f"<SystemConfig(id={self.id}, team_id={self.team_id}, config_key={self.config_key}, config_type={self.config_type})>"