from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class CustomerIntelligenceRunStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    CANCELLED = "CANCELLED"


class CustomerIntelligenceRun(Base):
    """Persistent runtime audit for customer intelligence graph runs."""

    __tablename__ = "crm_customer_intelligence_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    run_key = Column(String(64), nullable=False, unique=True, index=True, comment="运行幂等键")
    request_id = Column(String(120), nullable=False, index=True, comment="刷新请求ID")
    event_key = Column(String(120), nullable=False, index=True, comment="客户智能事件键")
    event_json = Column(JSON, nullable=True, comment="客户智能事件快照")
    tenant_id = Column(BigInteger, nullable=False, index=True, comment="租户ID，当前与团队ID一致")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, nullable=False, index=True, comment="客户ID")
    actor_id = Column(String(80), nullable=True, index=True, comment="触发人ID")
    trigger_type = Column(String(60), nullable=False, index=True, comment="触发类型")
    scope = Column(String(20), nullable=False, index=True, comment="刷新范围")
    status = Column(String(20), nullable=False, default=CustomerIntelligenceRunStatus.PENDING, index=True, comment="运行状态")
    attempt_count = Column(Integer, nullable=False, default=0, comment="已尝试次数")
    max_attempts = Column(Integer, nullable=False, default=3, comment="最大尝试次数")
    last_duration_ms = Column(Integer, nullable=True, comment="最近一次运行耗时毫秒")
    next_retry_at = Column(DateTime, nullable=True, index=True, comment="下次可重试时间")
    started_time = Column(DateTime, nullable=True, index=True, comment="开始时间")
    finished_time = Column(DateTime, nullable=True, index=True, comment="结束时间")
    route = Column(String(50), nullable=True, index=True, comment="Graph 路由")
    result_json = Column(JSON, nullable=True, comment="Graph 结果摘要")
    visible_trace_json = Column(JSON, nullable=True, comment="用户可见执行轨迹")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        UniqueConstraint("run_key", name="uq_customer_intelligence_run_key"),
        Index("idx_customer_intelligence_run_customer", "team_id", "customer_id", "created_time"),
        Index("idx_customer_intelligence_run_retry", "status", "next_retry_at"),
        Index("idx_customer_intelligence_run_event", "team_id", "event_key"),
        {"comment": "客户智能 LangGraph 运行审计表"},
    )
