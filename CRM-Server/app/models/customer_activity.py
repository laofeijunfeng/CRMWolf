from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.services.customer_activity_contracts import (
    CustomerActivityEffectivenessStatus,
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)
from app.utils.time import business_now


class CustomerActivity(Base):
    __tablename__ = "crm_customer_activities"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), nullable=True, comment="关联客户ID")
    deal_journey_id = Column(BigInteger, ForeignKey("crm_customer_deal_journeys.id", ondelete="SET NULL"), nullable=True, comment="成交旅程ID")
    original_lead_id = Column(BigInteger, ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True, comment="原始线索ID")
    activity_kind = Column(String(50), nullable=False, comment="活动分类")
    title = Column(String(255), nullable=True, comment="活动标题")
    source_content = Column(Text, nullable=False, comment="原始输入内容")
    content_json = Column(Text, nullable=True, comment="结构化活动内容JSON")
    summary = Column(Text, nullable=True, comment="列表摘要缓存")
    submission_source = Column(
        String(30),
        nullable=False,
        default=CustomerActivitySubmissionSource.FORM.value,
        comment="活动提交来源：AGENT/FORM/CUTOVER_MIGRATION",
    )
    submission_id = Column(String(120), nullable=True, comment="页面提交幂等ID；Agent 使用 command 幂等")
    submission_fingerprint = Column(String(64), nullable=True, comment="页面提交请求指纹")
    processing_status = Column(
        String(20),
        nullable=False,
        default=CustomerActivityProcessingStatus.PENDING.value,
        comment="整理状态：PENDING/PROCESSING/COMPLETED/FAILED",
    )
    processing_error = Column(Text, nullable=True, comment="整理失败原因")
    processed_at = Column(DateTime, nullable=True, comment="整理完成时间")
    next_follow_time = Column(DateTime, nullable=True, comment="计划下次跟进时间")
    next_follow_time_source = Column(String(30), nullable=True, comment="下次跟进时间来源：UI_DEFAULT/USER/AI_EXTRACTED/AGENT/MIGRATED")
    next_action = Column(Text, nullable=True, comment="下一步动作内容")
    next_action_source = Column(String(30), nullable=True, comment="下一步动作来源: UI_DEFAULT/USER/AI_EXTRACTED/AGENT/MIGRATED")
    occurred_at = Column(DateTime, nullable=False, default=business_now, comment="活动发生时间")
    creator_id = Column(String(100), nullable=False, comment="记录创建人")
    owner_id = Column(String(100), nullable=False, comment="跟进归属人")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="记录创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")
    effectiveness_score = Column(Integer, nullable=True, comment="AI评估活动有效性得分，满分100")
    effectiveness_is_valid = Column(Boolean, nullable=True, comment="AI评估是否有效")
    effectiveness_reason = Column(Text, nullable=True, comment="AI评估原因摘要")
    effectiveness_detail_json = Column(Text, nullable=True, comment="AI评估分项明细JSON")
    effectiveness_status = Column(
        String(20),
        nullable=True,
        default=CustomerActivityEffectivenessStatus.PENDING.value,
        comment="AI评估状态：PENDING/GENERATING/COMPLETED/FAILED",
    )
    effectiveness_evaluated_time = Column(DateTime, nullable=True, comment="AI评估完成时间")
    effectiveness_error_message = Column(Text, nullable=True, comment="AI评估失败原因")
    activity_revision = Column(Integer, nullable=False, default=1, comment="活动语义修订号")

    __table_args__ = (
        CheckConstraint(
            "submission_source IN ('AGENT', 'FORM', 'CUTOVER_MIGRATION')",
            name="ck_customer_activity_submission_source",
        ),
        CheckConstraint(
            "processing_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_customer_activity_processing_status",
        ),
        CheckConstraint(
            "effectiveness_status IS NULL OR effectiveness_status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')",
            name="ck_customer_activity_effectiveness_status",
        ),
        UniqueConstraint("team_id", "submission_id", name="uq_customer_activity_submission"),
        Index("idx_customer_activity_customer", "customer_id"),
        Index("idx_customer_activity_deal_journey", "deal_journey_id"),
        Index("idx_customer_activity_original_lead", "original_lead_id"),
        Index("idx_customer_activity_creator", "creator_id"),
        Index("idx_customer_activity_owner", "owner_id"),
        Index("idx_customer_activity_kind", "activity_kind"),
        Index("idx_customer_activity_next_time", "next_follow_time"),
        Index("idx_customer_activity_occurred_at", "occurred_at"),
        Index("idx_customer_activity_created_time", "created_time"),
        Index("idx_customer_activity_team", "team_id"),
        Index("idx_customer_activity_team_owner_occurred", "team_id", "owner_id", "occurred_at"),
        {"comment": "客户活动表"},
    )
