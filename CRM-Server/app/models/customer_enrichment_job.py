"""Durable jobs for customer initial enrichment."""

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base
from app.services.customer_enrichment_contracts import CustomerEnrichmentJobStatus
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class CustomerEnrichmentJob(Base):
    """One durable execution stream for a customer enrichment plan."""

    __tablename__ = "crm_customer_enrichment_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("cej"),
        comment="对外任务ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, nullable=False, index=True, comment="客户ID")
    purpose = Column(String(32), nullable=False, index=True, comment="登记用途")
    plan_version = Column(String(64), nullable=False, comment="补全计划版本")
    requested_fields_json = Column(JSON, nullable=False, comment="请求补全字段")
    status = Column(
        String(20),
        nullable=False,
        default=CustomerEnrichmentJobStatus.QUEUED.value,
        index=True,
        comment="任务状态",
    )
    available_at = Column(DateTime, nullable=False, index=True, comment="最早可执行时间")
    profile_gate_deadline_at = Column(DateTime, nullable=True, index=True, comment="档案等待截止时间")
    profile_gate_timed_out_at = Column(DateTime, nullable=True, comment="档案等待超时实际发生时间")
    attempt_count = Column(Integer, nullable=False, default=0, comment="执行次数")
    max_attempts = Column(Integer, nullable=False, default=3, comment="最大执行次数")
    next_attempt_at = Column(DateTime, nullable=True, index=True, comment="下次恢复时间")
    lease_token = Column(String(64), nullable=True, index=True, comment="当前执行租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="当前执行租约过期时间")
    run_id = Column(String(100), nullable=False, index=True, comment="稳定运行ID")
    graph_thread_id = Column(String(240), nullable=False, index=True, comment="LangGraph线程ID")
    first_attempt_finished_at = Column(DateTime, nullable=True, index=True, comment="首次执行结束时间")
    profile_refresh_request_id = Column(String(120), nullable=True, index=True, comment="档案刷新请求ID")
    profile_refresh_enqueued_at = Column(DateTime, nullable=True, comment="档案刷新入队时间")
    requeue_count = Column(Integer, nullable=False, default=0, comment="人工重新入队次数")
    result_json = Column(JSON, nullable=True, comment="执行结果")
    error_message = Column(Text, nullable=True, comment="最近错误")
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'RETRY_PENDING', 'COMPLETED', 'SKIPPED', 'EXHAUSTED')",
            name="ck_customer_enrichment_job_status",
        ),
        CheckConstraint(
            "purpose IN ('INITIAL_CREATION', 'HISTORICAL_BACKFILL')",
            name="ck_customer_enrichment_job_purpose",
        ),
        UniqueConstraint("team_id", "customer_id", "plan_version", name="uq_customer_enrichment_job_plan"),
        Index(
            "idx_customer_enrichment_job_recovery",
            "status",
            "available_at",
            "next_attempt_at",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index(
            "idx_customer_enrichment_job_customer_plan",
            "team_id",
            "customer_id",
            "plan_version",
        ),
        {"comment": "客户首次信息补全持久任务表"},
    )
