"""Durable evidence for the one-time customer-activity Workflow cutover."""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Integer, String, UniqueConstraint

from app.core.database import Base
from app.utils.time import business_now


class CustomerActivityCutoverRun(Base):
    """Cumulative, rerun-safe counters emitted by migration 122."""

    __tablename__ = "crm_customer_activity_cutover_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    run_key = Column(String(100), nullable=False, comment="迁移运行幂等键")
    cutover_watermark = Column(DateTime, nullable=False, comment="切换水位时间")
    status = Column(String(20), nullable=False, comment="迁移状态")
    active_activity_count = Column(Integer, nullable=False, default=0, comment="接管活动数")
    pending_activity_count = Column(Integer, nullable=False, default=0, comment="PENDING活动数")
    processing_activity_count = Column(Integer, nullable=False, default=0, comment="PROCESSING活动数")
    generating_activity_count = Column(Integer, nullable=False, default=0, comment="GENERATING活动数")
    agent_activity_reclassified_count = Column(
        Integer, nullable=False, default=0, comment="被切换接管的历史Agent活动数"
    )
    ai_jobs_created_count = Column(Integer, nullable=False, default=0, comment="新建AIJob数")
    ai_jobs_deleted_skipped_count = Column(Integer, nullable=False, default=0, comment="已删除活动AIJob跳过数")
    post_commit_replaced_count = Column(Integer, nullable=False, default=0, comment="被AIJob替代的PostCommitJob数")
    post_commit_preserved_count = Column(Integer, nullable=False, default=0, comment="保留待恢复PostCommitJob数")
    post_commit_deleted_skipped_count = Column(
        Integer, nullable=False, default=0, comment="已删除活动PostCommitJob跳过数"
    )
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("run_key", name="uq_customer_activity_cutover_run_key"),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED')",
            name="ck_customer_activity_cutover_run_status",
        ),
        {"comment": "客户活动 Workflow 切换迁移证据表"},
    )
