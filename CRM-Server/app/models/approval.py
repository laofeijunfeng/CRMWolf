from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, Numeric, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.constants.business_types import BusinessType


class ApprovalStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ApprovalAction:
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ROLLBACK = "ROLLBACK"


class ApprovalFlow(Base):
    """
    审批流程模板表

    支持团队隔离：不同团队可配置不同的审批流程
    """
    __tablename__ = "crm_approval_flows"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID（NULL表示系统默认模板）")
    flow_name = Column(String(100), nullable=False, comment="审批流程名称")
    flow_code = Column(String(50), nullable=False, comment="流程编码")
    description = Column(Text, nullable=True, comment="流程描述")

    min_amount = Column(Numeric(12, 2), nullable=True, comment="最小金额（条件）")
    max_amount = Column(Numeric(12, 2), nullable=True, comment="最大金额（条件）")
    license_type = Column(String(20), nullable=True, comment="授权类型（条件）")

    # A5：流程适用单据类型，对齐 A3 迁移 012（crm_approval_flows.business_type）
    business_type = Column(String(20), nullable=False, default=BusinessType.CONTRACT, comment="流程适用单据类型：CONTRACT/PAYMENT/INVOICE/LICENSE")

    is_active = Column(Integer, nullable=False, default=1, comment="是否启用：0:否, 1:是")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")

    nodes = relationship("ApprovalNode", back_populates="flow", order_by="ApprovalNode.node_order")
    approvals = relationship("Approval", back_populates="flow")

    __table_args__ = (
        Index('idx_flow_code', 'flow_code'),
        Index('idx_flow_active', 'is_active'),
        Index('idx_crm_approval_flows_team_id', 'team_id'),
        Index('idx_flow_business_type', 'business_type'),
        {'comment': '审批流程模板表'}
    )


class ApprovalNode(Base):
    """
    审批节点表

    支持团队隔离：跟随父表 ApprovalFlow 的 team_id
    """
    __tablename__ = "crm_approval_nodes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID（NULL表示系统默认模板）")
    flow_id = Column(BigInteger, ForeignKey('crm_approval_flows.id', ondelete='CASCADE'), nullable=False, comment="审批流程ID")

    node_name = Column(String(100), nullable=False, comment="节点名称")
    node_code = Column(String(50), nullable=False, comment="节点编码")
    node_order = Column(Integer, nullable=False, comment="节点顺序")
    description = Column(Text, nullable=True, comment="节点描述")

    approve_role = Column(String(50), nullable=True, comment="审批角色（TEAM_ADMIN, SALES_DIRECTOR等）")
    is_required = Column(Integer, nullable=False, default=1, comment="是否必须审批：0:否, 1:是")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")

    flow = relationship("ApprovalFlow", back_populates="nodes")
    records = relationship("ApprovalRecord", back_populates="node")

    __table_args__ = (
        Index('idx_node_flow', 'flow_id'),
        Index('idx_node_order', 'node_order'),
        Index('idx_crm_approval_nodes_team_id', 'team_id'),
        {'comment': '审批节点表'}
    )


class Approval(Base):
    __tablename__ = "crm_contract_approvals"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    contract_id = Column(BigInteger, ForeignKey('crm_contracts.id', ondelete='SET NULL'), nullable=True, comment="关联合同ID（合同删除后置空，审批记录保留）")
    business_type = Column(String(20), nullable=False, default=BusinessType.CONTRACT, comment="业务单据类型：CONTRACT/PAYMENT/INVOICE/LICENSE")
    business_id = Column(BigInteger, nullable=True, index=True, comment="业务单据ID（与 business_type 联合定位单据）")
    flow_id = Column(BigInteger, ForeignKey('crm_approval_flows.id', ondelete='SET NULL'), nullable=True, comment="审批流程模板ID")
    
    current_node_id = Column(BigInteger, ForeignKey('crm_approval_nodes.id', ondelete='SET NULL'), nullable=True, comment="当前审批节点ID")
    status = Column(String(20), nullable=False, default=ApprovalStatus.PENDING, comment="审批状态：PENDING, APPROVED, REJECTED, CANCELLED")
    
    submitter_id = Column(String(100), nullable=False, comment="提交人系统用户ID")
    submitter_name = Column(String(100), nullable=True, comment="提交人姓名")
    
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后更新时间")
    
    contract = relationship("Contract", foreign_keys=[contract_id])
    flow = relationship("ApprovalFlow", back_populates="approvals")
    current_node = relationship("ApprovalNode", foreign_keys=[current_node_id])
    records = relationship("ApprovalRecord", back_populates="approval", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_approval_contract', 'contract_id'),
        Index('idx_approval_business', 'business_type', 'business_id'),
        Index('idx_approval_status', 'status'),
        Index('idx_approval_flow', 'flow_id'),
        Index('idx_approval_team_id', 'team_id'),
        {'comment': '合同审批实例表'}
    )


class ApprovalRecord(Base):
    __tablename__ = "crm_contract_approval_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    approval_id = Column(BigInteger, ForeignKey('crm_contract_approvals.id', ondelete='CASCADE'), nullable=False, comment="审批实例ID")
    node_id = Column(BigInteger, ForeignKey('crm_approval_nodes.id', ondelete='SET NULL'), nullable=True, comment="审批节点ID")

    approver_id = Column(String(100), nullable=False, comment="审批人系统用户ID")
    approver_name = Column(String(100), nullable=True, comment="审批人姓名")
    action = Column(String(20), nullable=False, comment="操作：SUBMIT, APPROVE, REJECT, ROLLBACK")
    comment = Column(Text, nullable=True, comment="审批意见")

    created_time = Column(DateTime, nullable=False, default=func.now(), comment="操作时间")

    approval = relationship("Approval", back_populates="records")
    node = relationship("ApprovalNode", back_populates="records")

    __table_args__ = (
        Index('idx_record_approval', 'approval_id'),
        Index('idx_record_node', 'node_id'),
        Index('idx_record_approver', 'approver_id'),
        Index('idx_crm_contract_approval_records_team_id', 'team_id'),
        {'comment': '合同审批记录表'}
    )
