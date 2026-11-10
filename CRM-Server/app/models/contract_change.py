"""Persistence model for immutable contract change requests."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.constants.approval_phase import ApprovalPhase
from app.core.database import Base
from app.utils.time import business_now


class ContractChangeRequest(Base):
    __tablename__ = "crm_contract_changes"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    contract_id = Column(
        BigInteger,
        ForeignKey("crm_contracts.id", ondelete="CASCADE"),
        nullable=False,
        comment="原合同ID",
    )
    creator_id = Column(String(100), nullable=False, comment="申请人系统用户ID")
    change_items_json = Column(JSON, nullable=False, comment="不可变变更项目快照；金额值以字符串保存")
    reason = Column(Text, nullable=False, comment="变更原因")
    approval_phase = Column(
        String(20),
        nullable=False,
        default=ApprovalPhase.DRAFT.value,
        server_default=ApprovalPhase.DRAFT.value,
        comment="审批流程状态：draft/pending_review/approved/rejected",
    )
    pending_guard = Column(
        String(20),
        nullable=True,
        comment="待审批唯一性保护标记；待审批时由服务层设为 pending，终态置空",
    )
    attachment_path = Column(String(500), nullable=True, comment="变更附件路径（相对路径）")
    attachment_name = Column(String(255), nullable=True, comment="变更附件原始文件名")
    attachment_size = Column(BigInteger, nullable=True, comment="变更附件大小（字节）")
    attachment_mime_type = Column(String(100), nullable=True, comment="变更附件 MIME 类型")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间（软删除标记）")

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "contract_id",
            "pending_guard",
            name="uq_contract_change_pending_guard",
        ),
        Index("idx_contract_change_contract", "team_id", "contract_id"),
        Index("idx_contract_change_phase", "team_id", "approval_phase"),
        {"comment": "合同变更申请表"},
    )
