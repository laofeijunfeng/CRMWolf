from sqlalchemy import Column, BigInteger, String, DateTime, Date, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class LicenseApplicationStatus:
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"


class LicenseType:
    TRIAL = "TRIAL"
    OFFICIAL = "OFFICIAL"


class LicenseApplication(Base):
    """License 申请表"""
    __tablename__ = "crm_license_applications"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    application_number = Column(String(50), nullable=False, unique=True, comment="申请单号（自动生成）")

    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="关联客户ID")
    deployment_info_id = Column(BigInteger, ForeignKey('crm_deployment_infos.id', ondelete='SET NULL'), nullable=True, comment="关联部署信息ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='SET NULL'), nullable=True, comment="关联合同ID")

    expiry_date = Column(Date, nullable=False, comment="到期时间")
    license_type = Column(String(20), nullable=False, comment="License 类型")

    # 审批人回填的 License 详细信息（补充需求）
    enterprise_id = Column(String(50), nullable=True, comment="企业编号（审批人回填，如：15739）")
    supported_modules = Column(String(500), nullable=True, comment="支持模块（审批人回填，如：desktop,web,branch）")
    server_license_code = Column(Text, nullable=True, comment="服务端 License（审批人回填）")
    client_license_code = Column(Text, nullable=True, comment="客户端 License（审批人回填）")

    # 申请人备注（补充需求）
    remark = Column(Text, nullable=True, comment="备注（申请时填写，如：需要开通 desktop,web,branch）")

    # 原有授权码字段（兼容保留）
    license_code = Column(Text, nullable=True, comment="授权码（审批人回填，旧字段）")

    status = Column(String(20), nullable=False, default=LicenseApplicationStatus.DRAFT, comment="申请状态")
    applicant_id = Column(String(100), nullable=False, comment="申请人飞书用户ID")
    approver_id = Column(String(100), nullable=True, comment="审批人飞书用户ID")
    approved_time = Column(DateTime, nullable=True, comment="审批时间")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    customer = relationship("Customer", back_populates="license_applications")
    deployment_info = relationship("DeploymentInfo", back_populates="license_applications")
    contract = relationship("Contract", back_populates="license_applications")

    __table_args__ = (
        Index('idx_license_customer_id', 'customer_id'),
        Index('idx_license_contract_id', 'contract_id'),
        Index('idx_license_status', 'status'),
        {'comment': 'License 申请表'}
    )