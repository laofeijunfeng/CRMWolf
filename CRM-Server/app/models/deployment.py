from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class DeploymentInfo(Base):
    """客户部署信息表"""
    __tablename__ = "crm_deployment_infos"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")

    deployment_name = Column(String(100), nullable=False, comment="部署名称（如：生产环境、测试环境）")
    server_address = Column(String(500), nullable=False, comment="服务器地址（http:// 或 https:// 开头）")
    authorized_users = Column(Integer, nullable=False, comment="授权人数")
    is_default = Column(Boolean, nullable=False, default=False, comment="是否默认部署")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="deployment_infos")
    license_applications = relationship("LicenseApplication", back_populates="deployment_info")

    __table_args__ = (
        Index('idx_deployment_customer_id', 'customer_id'),
        Index('idx_deployment_team_id', 'team_id'),
        {'comment': '客户部署信息表'}
    )