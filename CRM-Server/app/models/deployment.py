from typing import cast

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, event
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.utils.dedupe_normalizer import server_address_dedupe_key
from app.utils.time import business_now


class DeploymentInfo(Base):
    """客户部署信息表"""
    __tablename__ = "crm_deployment_infos"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID"
    )

    deployment_name = Column(String(100), nullable=False, comment="部署名称\uff08如\uff1a生产环境、测试环境\uff09")
    server_address = Column(String(500), nullable=False, comment="服务器地址\uff08http:// 或 https:// 开头\uff09")
    server_address_dedupe_key = Column(
        String(500), nullable=True, comment="服务器地址判重键\uff08ORM hook 维护\uff0c原值不改写\uff09"
    )
    authorized_users = Column(Integer, nullable=True, comment="历史授权人数\uff08新申请人数记录在 License 申请\uff09")
    is_default = Column(Boolean, nullable=False, default=False, comment="是否默认部署")

    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    customer = relationship("Customer", back_populates="deployment_infos")
    license_applications = relationship("LicenseApplication", back_populates="deployment_info")

    __table_args__ = (
        Index('idx_deployment_customer_id', 'customer_id'),
        Index('idx_deployment_team_id', 'team_id'),
        Index('uq_deployment_customer_address_key', 'customer_id', 'server_address_dedupe_key', unique=True),
        {'comment': '客户部署信息表'}
    )


@event.listens_for(DeploymentInfo, 'before_insert')
@event.listens_for(DeploymentInfo, 'before_update')
def deployment_info_server_address_key(_mapper: object, _connection: object, target: DeploymentInfo) -> None:
    """Keep the per-customer server-address dedupe key in sync; the raw address is stored as entered."""
    key = server_address_dedupe_key(cast("str | None", target.server_address))
    target.server_address_dedupe_key = key  # type: ignore[assignment]
