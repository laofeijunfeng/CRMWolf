from sqlalchemy import (
    JSON as GenericJSON,
)
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.business_types import BusinessType
from app.core.database import Base
from app.utils.time import business_now


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

    支持团队隔离\uff1a不同团队可配置不同的审批流程
    """
    __tablename__ = "crm_approval_flows"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID\uff08NULL表示系统默认模板\uff09")
    flow_name = Column(String(100), nullable=False, comment="审批流程名称")
    flow_code = Column(String(50), nullable=False, comment="流程编码")
    description = Column(Text, nullable=True, comment="流程描述")

    min_amount = Column(Numeric(12, 2), nullable=True, comment="最小金额\uff08条件\uff09")
    max_amount = Column(Numeric(12, 2), nullable=True, comment="最大金额\uff08条件\uff09")
    license_type = Column(String(20), nullable=True, comment="授权类型\uff08条件\uff09")

    # A5:流程适用单据类型,对齐 A3 迁移 012(crm_approval_flows.business_type)
    business_type = Column(
        String(20),
        nullable=False,
        default=BusinessType.CONTRACT,
        comment="流程适用单据类型\uff1aCONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY",
    )

    is_active = Column(Integer, nullable=False, default=1, comment="是否启用\uff1a0:否, 1:是")

    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )

    # 只含现役节点;被编辑删除的节点归档保留,在审单据仍可按提交时快照引用。
    nodes = relationship(
        "ApprovalNode",
        primaryjoin="and_(ApprovalFlow.id == ApprovalNode.flow_id, ApprovalNode.is_archived == 0)",
        order_by="ApprovalNode.node_order",
        viewonly=True,
    )
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

    支持团队隔离\uff1a跟随父表 ApprovalFlow 的 team_id
    """
    __tablename__ = "crm_approval_nodes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID\uff08NULL表示系统默认模板\uff09")
    flow_id = Column(
        BigInteger, ForeignKey('crm_approval_flows.id', ondelete='CASCADE'), nullable=False, comment="审批流程ID"
    )

    node_name = Column(String(100), nullable=False, comment="节点名称")
    node_code = Column(String(50), nullable=False, comment="节点编码")
    node_order = Column(Integer, nullable=False, comment="节点顺序")
    description = Column(Text, nullable=True, comment="节点描述")

    node_type = Column(String(20), nullable=False, default="APPROVAL", comment="节点类型\uff1aAPPROVAL 审批 / CC 抄送")
    approver_roles = Column(GenericJSON(), nullable=True, comment="整角色选择\uff1a角色编码列表")
    approver_users = Column(GenericJSON(), nullable=True, comment="指定成员\uff1a[{role, user_id}]")
    is_archived: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="是否已从流程移除\uff08保留给在审单据引用\uff09"
    )

    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    flow = relationship("ApprovalFlow")
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
    contract_id = Column(
        BigInteger,
        ForeignKey('crm_contracts.id', ondelete='SET NULL'),
        nullable=True,
        comment="关联合同ID\uff08合同删除后置空\uff0c审批记录保留\uff09",
    )
    business_type = Column(
        String(20),
        nullable=False,
        default=BusinessType.CONTRACT,
        comment="业务单据类型\uff1aCONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY",
    )
    business_id = Column(
        BigInteger, nullable=True, index=True, comment="业务单据ID\uff08与 business_type 联合定位单据\uff09"
    )
    flow_id = Column(
        BigInteger,
        ForeignKey('crm_approval_flows.id', ondelete='SET NULL'),
        nullable=True,
        comment="审批流程模板ID",
    )
    
    current_node_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey('crm_approval_nodes.id', ondelete='SET NULL'),
        nullable=True,
        comment="当前审批节点ID",
    )
    nodes_snapshot = Column(GenericJSON(), nullable=True, comment="提交时的节点配置快照")
    status = Column(
        String(20),
        nullable=False,
        default=ApprovalStatus.PENDING,
        comment="审批状态\uff1aPENDING, APPROVED, REJECTED, CANCELLED",
    )
    
    submitter_id = Column(String(100), nullable=False, comment="提交人系统用户ID")
    submitter_name = Column(String(100), nullable=True, comment="提交人姓名")
    
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后更新时间")
    
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
    approval_id = Column(
        BigInteger,
        ForeignKey('crm_contract_approvals.id', ondelete='CASCADE'),
        nullable=False,
        comment="审批实例ID",
    )
    node_id = Column(
        BigInteger, ForeignKey('crm_approval_nodes.id', ondelete='SET NULL'), nullable=True, comment="审批节点ID"
    )

    approver_id = Column(String(100), nullable=False, comment="审批人系统用户ID")
    approver_name = Column(String(100), nullable=True, comment="审批人姓名")
    action = Column(String(20), nullable=False, comment="操作\uff1aSUBMIT, APPROVE, REJECT, ROLLBACK")
    comment = Column(Text, nullable=True, comment="审批意见")

    created_time = Column(DateTime, nullable=False, default=business_now, comment="操作时间")

    approval = relationship("Approval", back_populates="records")
    node = relationship("ApprovalNode", back_populates="records")

    __table_args__ = (
        Index('idx_record_approval', 'approval_id'),
        Index('idx_record_node', 'node_id'),
        Index('idx_record_approver', 'approver_id'),
        Index('idx_crm_contract_approval_records_team_id', 'team_id'),
        {'comment': '合同审批记录表'}
    )


class ApprovalParticipantKind:
    APPROVER = "APPROVER"
    CC = "CC"


class ApprovalParticipant(Base):
    """审批实例参与人\uff1a提交时冻结的各审批节点审批人\uff1b流转到抄送节点时写入的被抄送人。"""
    __tablename__ = "crm_approval_participants"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    approval_id = Column(
        BigInteger,
        ForeignKey('crm_contract_approvals.id', ondelete='CASCADE'),
        nullable=False,
        comment="审批实例ID",
    )
    node_id = Column(BigInteger, nullable=False, comment="节点ID")
    node_name = Column(String(100), nullable=True, comment="节点名称")
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    kind = Column(String(20), nullable=False, comment="APPROVER / CC")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="写入时间\uff08抄送时间\uff09")

    __table_args__ = (
        Index('idx_participant_user', 'team_id', 'user_id', 'kind'),
        Index('idx_participant_approval', 'approval_id', 'node_id'),
        {'comment': '审批参与人表'}
    )
