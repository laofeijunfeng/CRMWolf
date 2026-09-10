from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship  # noqa: F401
from app.core.database import Base
from app.utils.time import business_now


class WorkflowStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"


VALID_TRANSITIONS = {
    WorkflowStatus.DRAFT: {WorkflowStatus.PUBLISHED},
    WorkflowStatus.PUBLISHED: {WorkflowStatus.PAUSED},
    WorkflowStatus.PAUSED: {WorkflowStatus.PUBLISHED},
}


class Workflow(Base):
    """CRMWolf 工作流（自有 DSL，schema_version 预留 Activepieces Adapter）"""
    __tablename__ = "crm_workflows"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID（NULL表示系统级）")
    name = Column(String(100), nullable=False, comment="工作流名称")
    description = Column(Text, nullable=True, comment="描述")
    status = Column(String(20), nullable=False, default=WorkflowStatus.DRAFT, comment="draft/published/paused")
    dsl = Column(JSON().with_variant(Text(), "sqlite"), nullable=False, comment="Workflow DSL JSON")
    created_by = Column(BigInteger, nullable=True, comment="创建人用户ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=business_now,
                                onupdate=business_now, comment="最后修改时间（兼乐观锁版本）")

    __table_args__ = (
        Index('idx_crm_workflows_team_id', 'team_id'),
        Index('idx_crm_workflows_status', 'status'),
        {'comment': 'CRMWolf 工作流定义表'}
    )
