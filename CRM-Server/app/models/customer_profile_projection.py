"""Versioned customer-profile read model.

The customer profile is a published projection, not a second source of truth for
CRM business state.  A version is immutable after publication; ``Current`` only
points readers at the latest successful version and tracks freshness.
"""

from datetime import datetime  # SQLAlchemy resolves this annotation at runtime.

from sqlalchemy import CHAR, JSON, BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class CustomerProfilePublicationStatus:
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    PUBLISHED_WITH_WARNINGS = "PUBLISHED_WITH_WARNINGS"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


CUSTOMER_PROFILE_READABLE_PUBLICATION_STATUSES = (
    CustomerProfilePublicationStatus.PUBLISHED,
    CustomerProfilePublicationStatus.PUBLISHED_WITH_WARNINGS,
    CustomerProfilePublicationStatus.SUPERSEDED,
)


class CustomerProfileStatus:
    NOT_READY = "NOT_READY"
    READY = "READY"
    UPDATING = "UPDATING"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class CustomerProfileProjectionVersion(Base):
    """Immutable customer profile snapshot."""

    __tablename__ = "crm_customer_profile_projection_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("cpv"),
        comment="档案版本对外ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    customer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        comment="客户ID",
    )
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, comment="档案Schema版本")
    profile_version: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="客户内单调递增版本号")
    publication_status: Mapped[str] = mapped_column(String(32), nullable=False, comment="发布状态")
    current_situation_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, comment="当前情况")
    current_journeys_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, comment="当前业务旅程")
    important_changes_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, comment="重要变化")
    long_term_context_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, comment="长期情况")
    follow_up_process_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, comment="跟进过程")
    recorded_follow_ups_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, comment="已记录后续事项"
    )
    evidence_refs_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, comment="证据引用")
    quality_report_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, comment="内部内容质量诊断, 不展示在档案正文"
    )
    source_watermark_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, comment="来源水位")
    source_watermark_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, comment="来源水位哈希")
    fact_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="事实水位")
    journey_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="旅程水位")
    task_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="任务水位")
    commitment_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="承诺水位")
    source_event_key: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="主要触发事件")
    run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_customer_intelligence_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成运行ID",
    )
    graph_version: Mapped[str] = mapped_column(String(40), nullable=False, comment="Graph/规则版本")
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, comment="内容哈希")
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="生成时间")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="发布时间")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("team_id", "customer_id", "profile_version", name="uq_customer_profile_projection_version"),
        UniqueConstraint(
            "team_id",
            "customer_id",
            "content_hash",
            "source_watermark_hash",
            name="uq_customer_profile_projection_content_watermark",
        ),
        Index("idx_customer_profile_projection_team_customer", "team_id", "customer_id"),
        Index(
            "idx_customer_profile_projection_lookup",
            "team_id",
            "customer_id",
            "publication_status",
            "profile_version",
        ),
        Index("idx_customer_profile_projection_created", "team_id", "customer_id", "created_time"),
        Index("idx_customer_profile_projection_run", "run_id"),
        Index("idx_customer_profile_projection_event", "source_event_key"),
        Index("idx_customer_profile_projection_published", "published_at"),
        {"comment": "客户档案不可变投影版本表"},
    )


class CustomerProfileCurrent(Base):
    """Current pointer and freshness state for one customer."""

    __tablename__ = "crm_customer_profile_current"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")
    customer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        comment="客户ID",
    )
    current_profile_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_customer_profile_projection_versions.id", ondelete="RESTRICT"),
        nullable=True,
        comment="当前档案版本ID",
    )
    profile_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CustomerProfileStatus.NOT_READY,
        comment="档案状态",
    )
    last_successful_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="最近成功版本号")
    last_successful_published_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近成功发布时间"
    )
    latest_source_watermark_json: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, comment="已知来源水位"
    )
    latest_fact_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="已知事实水位")
    latest_journey_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="已知旅程水位")
    latest_task_watermark: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="已知任务水位")
    latest_commitment_watermark: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="已知承诺水位"
    )
    stale_reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="新鲜度说明")
    active_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("crm_customer_intelligence_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="当前活跃运行ID",
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间"
    )

    __table_args__ = (
        UniqueConstraint("team_id", "customer_id", name="uq_customer_profile_current_team_customer"),
        Index("idx_customer_profile_current_team", "team_id"),
        Index("idx_customer_profile_current_status", "team_id", "profile_status", "updated_time"),
        Index("idx_customer_profile_current_version", "current_profile_version_id"),
        Index("idx_customer_profile_current_run", "active_run_id"),
        {"comment": "客户档案当前指针和新鲜度表"},
    )
