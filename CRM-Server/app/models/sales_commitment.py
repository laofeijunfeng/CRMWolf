from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class SalesCommitmentStatus:
    OPEN = "OPEN"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class FollowUpTaskStatus:
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class FollowUpTaskSourceType:
    CUSTOMER_ACTIVITY = "CUSTOMER_ACTIVITY"
    HISTORICAL_BACKFILL = "HISTORICAL_BACKFILL"


class FollowUpTaskEventType:
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REOPENED = "REOPENED"


class FollowUpTaskProjectionTrigger:
    ACTIVITY_CREATED_DETERMINISTIC = "ACTIVITY_CREATED_DETERMINISTIC"
    ACTIVITY_STRUCTURED_COMPLETED = "ACTIVITY_STRUCTURED_COMPLETED"
    ACTIVITY_UPDATED = "ACTIVITY_UPDATED"
    ACTIVITY_DELETED = "ACTIVITY_DELETED"
    HISTORICAL_BACKFILL = "HISTORICAL_BACKFILL"


class FollowUpTaskProjectionStatus:
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class FollowUpTaskReconciliationRunStatus:
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class FollowUpTaskLLMMatcherRunStatus:
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class FollowUpTaskReconciliationEvaluationRunStatus:
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FollowUpTaskConfirmationStatus:
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class FollowUpTaskConfirmationResolutionAction:
    COMPLETE = "COMPLETE"
    DELAY = "DELAY"
    CANCEL = "CANCEL"
    KEEP_OPEN = "KEEP_OPEN"
    UNKNOWN = "UNKNOWN"


class FollowUpTaskConfirmationPromptChannel:
    WEB = "web"
    IM = "im"


class FollowUpTaskConfirmationDeliveryPurpose:
    """Why a confirmation delivery exists and whether it is intrusive."""

    INBOX_VISIBILITY = "INBOX_VISIBILITY"
    AGENT_MESSAGE_CARD = "AGENT_MESSAGE_CARD"
    AGENT_TURN_PROMPT = "AGENT_TURN_PROMPT"
    IM_PROMPT = "IM_PROMPT"

    INTRUSIVE = frozenset({AGENT_TURN_PROMPT, IM_PROMPT})


class FollowUpTaskConfirmationPromptStatus:
    QUEUED = "QUEUED"
    PROJECTED = "PROJECTED"
    SENT = "SENT"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    EXHAUSTED = "EXHAUSTED"
    AMBIGUOUS = "AMBIGUOUS"

    TERMINAL = frozenset({SENT, SKIPPED, EXHAUSTED, AMBIGUOUS})


class DueAtGranularity:
    DATE = "DATE"
    DATETIME = "DATETIME"
    WEEK = "WEEK"
    MONTH = "MONTH"
    UNKNOWN = "UNKNOWN"


class SalesCommitment(Base):
    """Structured sales commitment extracted from customer activity evidence."""

    __tablename__ = "crm_sales_commitments"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("scm"),
        comment="对外承诺ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    owner_id = Column(String(100), nullable=False, index=True, comment="承诺归属人")
    creator_id = Column(String(100), nullable=False, index=True, comment="承诺创建人")
    title = Column(String(255), nullable=False, comment="承诺标题")
    content = Column(Text, nullable=False, comment="承诺内容")
    commitment_type = Column(String(50), nullable=False, default="FOLLOW_UP", index=True, comment="承诺类型")
    status = Column(String(20), nullable=False, default=SalesCommitmentStatus.OPEN, index=True, comment="承诺状态")
    confidence = Column(Float, nullable=False, default=1.0, comment="抽取置信度")
    source_type = Column(String(50), nullable=False, index=True, comment="来源类型")
    source_key = Column(String(128), nullable=False, index=True, comment="幂等来源键")
    source_activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源客户活动ID",
    )
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    due_at = Column(DateTime, nullable=True, index=True, comment="承诺到期时间")
    due_at_text = Column(String(255), nullable=True, comment="原始时间表达")
    due_at_granularity = Column(String(20), nullable=False, default=DueAtGranularity.UNKNOWN, comment="到期时间粒度")
    due_at_timezone = Column(String(64), nullable=False, default="Asia/Shanghai", comment="到期时间业务时区")
    evidence_json = Column(JSON, nullable=True, comment="抽取证据和上下文")
    commitment_hash = Column(String(64), nullable=False, index=True, comment="承诺幂等哈希")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "source_type",
            "source_key",
            "commitment_hash",
            name="uq_sales_commitment_source_hash",
        ),
        Index("idx_sales_commitment_owner_status_due", "team_id", "owner_id", "status", "due_at"),
        Index("idx_sales_commitment_customer_status_due", "team_id", "customer_id", "status", "due_at"),
        {"comment": "销售承诺表"},
    )


class FollowUpTask(Base):
    """Actionable follow-up task projected from sales commitments and activity next steps."""

    __tablename__ = "crm_follow_up_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("fut"),
        comment="对外跟进任务ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    commitment_id = Column(
        BigInteger,
        ForeignKey("crm_sales_commitments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联承诺ID",
    )
    owner_id = Column(String(100), nullable=False, index=True, comment="任务归属人")
    creator_id = Column(String(100), nullable=False, index=True, comment="任务创建人")
    title = Column(String(255), nullable=False, comment="任务标题")
    description = Column(Text, nullable=True, comment="任务描述")
    status = Column(String(20), nullable=False, default=FollowUpTaskStatus.OPEN, index=True, comment="任务状态")
    due_at = Column(DateTime, nullable=False, index=True, comment="任务到期时间")
    due_at_text = Column(String(255), nullable=True, comment="原始时间表达")
    due_at_granularity = Column(String(20), nullable=False, default=DueAtGranularity.DATETIME, comment="到期时间粒度")
    due_at_timezone = Column(String(64), nullable=False, default="Asia/Shanghai", comment="到期时间业务时区")
    source_type = Column(String(50), nullable=False, index=True, comment="来源类型")
    source_key = Column(String(128), nullable=False, index=True, comment="幂等来源键")
    source_activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源客户活动ID",
    )
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    confidence = Column(Float, nullable=False, default=1.0, comment="抽取置信度")
    evidence_json = Column(JSON, nullable=True, comment="抽取证据和上下文")
    task_hash = Column(String(64), nullable=False, index=True, comment="任务幂等哈希")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    cancelled_at = Column(DateTime, nullable=True, comment="取消时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "source_type",
            "source_key",
            "task_hash",
            name="uq_follow_up_task_source_hash",
        ),
        Index("idx_follow_up_task_owner_status_due", "team_id", "owner_id", "status", "due_at"),
        Index("idx_follow_up_task_customer_status_due", "team_id", "customer_id", "status", "due_at"),
        Index("idx_follow_up_task_source", "team_id", "source_type", "source_key"),
        {"comment": "客户跟进任务表"},
    )


class FollowUpTaskEvent(Base):
    """Audit event for follow-up task state and content changes."""

    __tablename__ = "crm_follow_up_task_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("fte"),
        comment="对外任务事件ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    task_id = Column(
        BigInteger,
        ForeignKey("crm_follow_up_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="跟进任务ID",
    )
    event_type = Column(String(30), nullable=False, index=True, comment="事件类型")
    actor_id = Column(String(100), nullable=True, index=True, comment="触发人")
    source_type = Column(String(50), nullable=True, index=True, comment="来源类型")
    source_activity_id = Column(BigInteger, nullable=True, index=True, comment="来源客户活动ID")
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    previous_status = Column(String(20), nullable=True, comment="变更前状态")
    new_status = Column(String(20), nullable=True, comment="变更后状态")
    payload_json = Column(JSON, nullable=True, comment="事件载荷")
    created_time = Column(DateTime, nullable=False, default=business_now, index=True, comment="创建时间")

    __table_args__ = (
        Index("idx_follow_up_task_event_task_time", "task_id", "created_time"),
        Index("idx_follow_up_task_event_source", "team_id", "source_type", "source_activity_id"),
        {"comment": "客户跟进任务事件表"},
    )


class FollowUpTaskProjectionRun(Base):
    """Observable projection run from activity input to commitment/task state."""

    __tablename__ = "crm_follow_up_task_projection_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("tpr"),
        comment="对外投影运行ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    trigger_type = Column(String(50), nullable=False, index=True, comment="投影触发类型")
    status = Column(
        String(20),
        nullable=False,
        default=FollowUpTaskProjectionStatus.RUNNING,
        index=True,
        comment="投影状态",
    )
    source_type = Column(String(50), nullable=False, index=True, comment="来源类型")
    source_key = Column(String(128), nullable=False, index=True, comment="幂等来源键")
    source_activity_id = Column(BigInteger, nullable=True, index=True, comment="来源客户活动ID")
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    actor_id = Column(String(100), nullable=True, index=True, comment="触发人")
    skip_reason = Column(String(80), nullable=True, index=True, comment="跳过原因")
    input_snapshot_hash = Column(String(64), nullable=True, index=True, comment="输入快照哈希")
    projection_hash = Column(String(64), nullable=True, index=True, comment="投影结果哈希")
    task_count = Column(Integer, nullable=False, default=0, comment="涉及任务数量")
    commitment_count = Column(Integer, nullable=False, default=0, comment="涉及承诺数量")
    created_task_ids_json = Column(JSON, nullable=True, comment="新建任务内部ID列表")
    updated_task_ids_json = Column(JSON, nullable=True, comment="更新任务内部ID列表")
    cancelled_task_ids_json = Column(JSON, nullable=True, comment="取消任务内部ID列表")
    created_commitment_ids_json = Column(JSON, nullable=True, comment="新建承诺内部ID列表")
    updated_commitment_ids_json = Column(JSON, nullable=True, comment="更新承诺内部ID列表")
    error_message = Column(Text, nullable=True, comment="错误摘要")
    attempt_count = Column(Integer, nullable=False, default=1, comment="尝试次数")
    duration_ms = Column(Integer, nullable=True, comment="耗时毫秒")
    started_at = Column(DateTime, nullable=False, default=business_now, comment="开始时间")
    finished_at = Column(DateTime, nullable=True, comment="结束时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        Index("idx_follow_up_projection_source", "team_id", "source_type", "source_key", "created_time"),
        Index("idx_follow_up_projection_status", "team_id", "status", "created_time"),
        {"comment": "客户跟进任务投影运行表"},
    )


class FollowUpTaskConfirmationCase(Base):
    """Pending user confirmation for an unsafe follow-up task transition."""

    __tablename__ = "crm_follow_up_task_confirmation_cases"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("fuc"),
        comment="对外确认Case ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    task_id = Column(
        BigInteger,
        ForeignKey("crm_follow_up_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="跟进任务ID",
    )
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="客户ID",
    )
    owner_id = Column(String(100), nullable=False, index=True, comment="确认归属人")
    creator_id = Column(String(100), nullable=False, index=True, comment="确认创建人")
    status = Column(
        String(20),
        nullable=False,
        default=FollowUpTaskConfirmationStatus.PENDING,
        index=True,
        comment="确认状态",
    )
    suggested_action = Column(String(30), nullable=False, index=True, comment="建议处理动作")
    confirmation_hash = Column(String(64), nullable=False, index=True, comment="确认Case幂等哈希")
    question_text = Column(Text, nullable=False, comment="确认问题")
    source_activity_id = Column(BigInteger, nullable=True, index=True, comment="来源客户活动ID")
    source_activity_revision = Column(Integer, nullable=True, comment="来源客户活动修订号")
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    source_plan_json = Column(JSON, nullable=True, comment="状态迁移计划快照")
    expires_at = Column(DateTime, nullable=True, index=True, comment="确认Case过期时间")
    last_prompted_at = Column(DateTime, nullable=True, comment="最近提醒时间")
    prompt_count = Column(Integer, nullable=False, default=0, comment="提醒次数")
    unresolved_reply_count = Column(Integer, nullable=False, default=0, comment="无法解析回复次数")
    last_unresolved_reply_text = Column(Text, nullable=True, comment="最近一次无法解析的用户回复")
    last_unresolved_reply_by_id = Column(String(100), nullable=True, index=True, comment="最近一次无法解析回复人")
    last_unresolved_reply_at = Column(DateTime, nullable=True, comment="最近一次无法解析回复时间")
    resolved_action = Column(String(30), nullable=True, index=True, comment="用户确认后的处理动作")
    resolved_due_at = Column(DateTime, nullable=True, comment="用户确认后的延期时间")
    resolved_due_at_text = Column(String(255), nullable=True, comment="用户确认后的原始时间表达")
    resolution_text = Column(Text, nullable=True, comment="用户原始回复")
    resolved_by_id = Column(String(100), nullable=True, index=True, comment="确认处理人")
    resolved_at = Column(DateTime, nullable=True, comment="确认处理时间")
    expired_at = Column(DateTime, nullable=True, comment="确认Case实际过期时间")
    cancelled_at = Column(DateTime, nullable=True, comment="确认Case取消时间")
    cancelled_by_id = Column(String(100), nullable=True, index=True, comment="确认Case取消人")
    cancelled_reason = Column(String(80), nullable=True, index=True, comment="确认Case取消原因")
    application_status = Column(String(20), nullable=True, index=True, comment="确认应用状态")
    application_skip_reason = Column(String(80), nullable=True, comment="确认应用跳过原因")
    application_result_json = Column(JSON, nullable=True, comment="确认应用结果快照")
    applied_by_id = Column(String(100), nullable=True, index=True, comment="确认应用执行人")
    applied_at = Column(DateTime, nullable=True, comment="确认应用时间")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        UniqueConstraint("team_id", "confirmation_hash", name="uq_follow_up_task_confirmation_hash"),
        Index("idx_follow_up_confirmation_owner_status", "team_id", "owner_id", "status", "created_time"),
        Index("idx_follow_up_confirmation_owner_status_expiry", "team_id", "owner_id", "status", "expires_at"),
        Index("idx_follow_up_confirmation_task_status", "team_id", "task_id", "status"),
        Index("idx_follow_up_confirmation_source", "team_id", "source_activity_id"),
        Index(
            "idx_follow_up_confirmation_source_revision",
            "team_id",
            "source_activity_id",
            "source_activity_revision",
        ),
        {"comment": "跟进任务确认Case表"},
    )


class FollowUpTaskConfirmationPromptDelivery(Base):
    """Audit log for proactive confirmation prompts delivered to any channel."""

    __tablename__ = "crm_follow_up_task_confirmation_prompt_deliveries"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("fcp"),
        comment="对外确认提示投递ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    case_id = Column(
        BigInteger,
        ForeignKey("crm_follow_up_task_confirmation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="确认Case ID",
    )
    owner_id = Column(String(100), nullable=False, index=True, comment="提示接收人")
    channel = Column(String(30), nullable=False, index=True, comment="渠道")
    purpose = Column(
        String(40),
        nullable=False,
        default=FollowUpTaskConfirmationDeliveryPurpose.INBOX_VISIBILITY,
        index=True,
        comment="投递用途/展示语义",
    )
    provider = Column(String(30), nullable=True, index=True, comment="渠道供应商")
    agent_session_id = Column(BigInteger, nullable=True, index=True, comment="Agent会话ID")
    interaction_id = Column(String(80), nullable=False, index=True, comment="Agent交互ID")
    prompt_key = Column(String(128), nullable=False, index=True, comment="提示幂等/归因键")
    status = Column(
        String(20),
        nullable=False,
        default=FollowUpTaskConfirmationPromptStatus.QUEUED,
        index=True,
        comment="投递状态",
    )
    payload_json = Column(JSON, nullable=True, comment="投递载荷快照")
    reason_code = Column(String(80), nullable=True, index=True, comment="投递状态原因码")
    error_message = Column(Text, nullable=True, comment="投递失败信息")
    thread_id = Column(String(160), nullable=True, index=True, comment="Agent线程ID")
    run_id = Column(String(100), nullable=True, index=True, comment="运行ID")
    provider_message_id = Column(String(160), nullable=True, index=True, comment="渠道返回的消息或可见对象ID")
    recipient_id = Column(String(160), nullable=True, index=True, comment="渠道接收人ID")
    origin_turn_id = Column(String(160), nullable=True, index=True, comment="来源Agent轮次ID")
    origin_message_id = Column(String(160), nullable=True, index=True, comment="来源消息ID")
    source_activity_id = Column(BigInteger, nullable=True, index=True, comment="来源客户活动ID")
    expected_activity_revision = Column(Integer, nullable=True, comment="投递绑定的客户活动修订号")
    attempt_count = Column(Integer, nullable=False, default=0, comment="实际投递尝试次数")
    next_attempt_at = Column(DateTime, nullable=True, index=True, comment="下次允许重试时间")
    lease_token = Column(String(64), nullable=True, index=True, comment="当前投递租约令牌")
    lease_expires_at = Column(DateTime, nullable=True, index=True, comment="当前投递租约过期时间")
    attempted_at = Column(DateTime, nullable=True, index=True, comment="最近投递尝试时间")
    delivered_at = Column(DateTime, nullable=True, index=True, comment="确认送达时间")
    prompted_at = Column(DateTime, nullable=True, index=True, comment="兼容提示时间，仅真实送达后写入")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    __table_args__ = (
        Index("idx_follow_up_confirmation_prompt_owner_time", "team_id", "owner_id", "prompted_at"),
        Index("idx_follow_up_confirmation_prompt_case_time", "team_id", "case_id", "prompted_at"),
        Index("idx_follow_up_confirmation_prompt_session", "team_id", "agent_session_id", "created_time"),
        Index(
            "idx_follow_up_confirmation_prompt_activity_revision",
            "team_id",
            "source_activity_id",
            "expected_activity_revision",
        ),
        Index("idx_follow_up_confirmation_prompt_purpose", "team_id", "purpose", "status", "created_time"),
        Index(
            "idx_follow_up_confirmation_prompt_recovery",
            "status",
            "next_attempt_at",
            "lease_expires_at",
            "attempt_count",
            "created_time",
        ),
        Index("uq_follow_up_confirmation_prompt_key", "team_id", "prompt_key", unique=True),
        {"comment": "跟进任务确认提示投递日志表"},
    )


class FollowUpTaskTransitionPolicyDecisionLog(Base):
    """Append-only audit log for automatic transition policy decisions."""

    __tablename__ = "crm_follow_up_task_transition_policy_decision_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("tpd"),
        comment="对外策略决策日志ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    owner_id = Column(String(100), nullable=True, index=True, comment="任务归属人")
    actor_id = Column(String(100), nullable=True, index=True, comment="触发人")
    task_id = Column(
        BigInteger,
        ForeignKey("crm_follow_up_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="跟进任务ID",
    )
    source_type = Column(String(50), nullable=True, index=True, comment="来源类型")
    source_activity_id = Column(BigInteger, nullable=True, index=True, comment="来源客户活动ID")
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    action = Column(String(30), nullable=True, index=True, comment="计划迁移动作")
    allowed = Column(Boolean, nullable=False, index=True, comment="是否允许自动执行")
    reason = Column(String(80), nullable=False, index=True, comment="策略决策原因")
    enabled = Column(Boolean, nullable=False, index=True, comment="团队自动迁移开关是否开启")
    owner_allowlist_configured = Column(Boolean, nullable=False, default=False, comment="是否配置归属人白名单")
    allowed_actions_json = Column(JSON, nullable=True, comment="命中的动作白名单快照")
    config_errors_json = Column(JSON, nullable=True, comment="配置错误快照")
    policy_result_json = Column(JSON, nullable=True, comment="完整策略决策快照")
    context_json = Column(JSON, nullable=True, comment="决策上下文快照")
    created_time = Column(DateTime, nullable=False, default=business_now, index=True, comment="创建时间")

    __table_args__ = (
        Index(
            "idx_follow_up_transition_policy_owner_time",
            "team_id",
            "owner_id",
            "created_time",
        ),
        Index(
            "idx_follow_up_transition_policy_reason_time",
            "team_id",
            "reason",
            "created_time",
        ),
        Index(
            "idx_follow_up_transition_policy_task_time",
            "team_id",
            "task_id",
            "created_time",
        ),
        {"comment": "跟进任务自动迁移策略决策日志表"},
    )


class FollowUpTaskReconciliationRun(Base):
    """Append-only trace for candidate retrieval and deterministic reconciliation inputs."""

    __tablename__ = "crm_follow_up_task_reconciliation_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("trr"),
        comment="对外reconciliation运行ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id = Column(
        BigInteger,
        ForeignKey("crm_customers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="客户ID",
    )
    owner_id = Column(String(100), nullable=True, index=True, comment="活动/任务归属人")
    actor_id = Column(String(100), nullable=True, index=True, comment="触发人")
    source_activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源客户活动ID",
    )
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    status = Column(String(20), nullable=False, index=True, comment="运行状态")
    skip_reason = Column(String(80), nullable=True, index=True, comment="跳过原因")
    include_cross_owner = Column(Boolean, nullable=False, default=False, index=True, comment="是否纳入跨owner候选")
    lookback_days = Column(Integer, nullable=False, default=90, comment="候选回看天数")
    lookahead_days = Column(Integer, nullable=False, default=30, comment="候选前看天数")
    limit = Column(Integer, nullable=False, default=20, comment="候选数量上限")
    candidate_count = Column(Integer, nullable=False, default=0, comment="候选任务数量")
    candidate_public_ids_json = Column(JSON, nullable=True, comment="候选任务对外ID快照")
    filters_json = Column(JSON, nullable=True, comment="候选过滤条件快照")
    usage_policy_json = Column(JSON, nullable=True, comment="使用策略快照")
    error_message = Column(Text, nullable=True, comment="错误摘要")
    duration_ms = Column(Integer, nullable=True, comment="耗时毫秒")
    anchor_at = Column(DateTime, nullable=True, index=True, comment="候选窗口锚点时间")
    started_at = Column(DateTime, nullable=False, default=business_now, comment="开始时间")
    finished_at = Column(DateTime, nullable=False, default=business_now, index=True, comment="结束时间")
    created_time = Column(DateTime, nullable=False, default=business_now, index=True, comment="创建时间")

    __table_args__ = (
        Index("idx_follow_up_reconciliation_owner_time", "team_id", "owner_id", "created_time"),
        Index("idx_follow_up_reconciliation_status_time", "team_id", "status", "created_time"),
        Index("idx_follow_up_reconciliation_activity_time", "team_id", "source_activity_id", "created_time"),
        {"comment": "跟进任务reconciliation运行日志表"},
    )


class FollowUpTaskLLMMatcherRun(Base):
    """Append-only trace for LLM semantic matching and structured-output failures."""

    __tablename__ = "crm_follow_up_task_llm_matcher_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("tlm"),
        comment="对外LLM匹配运行ID",
    )
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    owner_id = Column(String(100), nullable=True, index=True, comment="活动/任务归属人")
    actor_id = Column(String(100), nullable=True, index=True, comment="触发人")
    source_activity_id = Column(
        BigInteger,
        ForeignKey("crm_customer_activities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源客户活动ID",
    )
    source_public_id = Column(String(64), nullable=True, comment="来源对象对外ID")
    reconciliation_run_public_id = Column(String(64), nullable=True, index=True, comment="reconciliation运行对外ID")
    status = Column(String(20), nullable=False, index=True, comment="运行状态")
    source = Column(String(80), nullable=False, index=True, comment="匹配结果来源")
    decision = Column(String(30), nullable=True, index=True, comment="归一化决策")
    task_public_id = Column(String(64), nullable=True, index=True, comment="候选任务对外ID")
    candidate_public_ids_json = Column(JSON, nullable=True, comment="候选任务对外ID快照")
    confidence = Column(Float, nullable=True, comment="归一化置信度")
    needs_confirmation = Column(Boolean, nullable=False, default=False, index=True, comment="是否需要用户确认")
    forbid_auto_reasons_json = Column(JSON, nullable=True, comment="禁止自动迁移原因")
    evidence_terms_json = Column(JSON, nullable=True, comment="证据词快照")
    referenced_source_public_ids_json = Column(JSON, nullable=True, comment="引用来源对外ID")
    evaluation_failures_json = Column(JSON, nullable=True, comment="安全评测失败项")
    model_name = Column(String(120), nullable=True, comment="LLM模型名")
    structured_output_strategy = Column(String(40), nullable=True, comment="结构化输出策略")
    schema_error_type = Column(String(80), nullable=True, index=True, comment="结构化输出错误类型")
    schema_error_message = Column(Text, nullable=True, comment="结构化输出错误摘要")
    duration_ms = Column(Integer, nullable=True, comment="耗时毫秒")
    started_at = Column(DateTime, nullable=False, default=business_now, comment="开始时间")
    finished_at = Column(DateTime, nullable=False, default=business_now, index=True, comment="结束时间")
    created_time = Column(DateTime, nullable=False, default=business_now, index=True, comment="创建时间")

    __table_args__ = (
        Index("idx_follow_up_llm_matcher_owner_time", "team_id", "owner_id", "created_time"),
        Index("idx_follow_up_llm_matcher_status_time", "team_id", "status", "created_time"),
        Index("idx_follow_up_llm_matcher_decision_time", "team_id", "decision", "created_time"),
        Index("idx_follow_up_llm_matcher_schema_time", "team_id", "schema_error_type", "created_time"),
        {"comment": "跟进任务LLM语义匹配运行日志表"},
    )


class FollowUpTaskReconciliationEvaluationRun(Base):
    """Append-only quality gate result for reconciliation golden/evaluation suites."""

    __tablename__ = "crm_follow_up_task_reconciliation_evaluation_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: generate_public_id("ter"),
        comment="对外reconciliation评测运行ID",
    )
    team_id = Column(BigInteger, nullable=True, index=True, comment="团队ID；系统级评测可为空")
    suite_name = Column(String(120), nullable=False, index=True, comment="评测套件名称")
    fixture_path = Column(String(500), nullable=True, comment="评测样本路径")
    fixture_hash = Column(String(64), nullable=True, index=True, comment="评测样本内容hash")
    status = Column(String(20), nullable=False, index=True, comment="运行状态")
    ok = Column(Boolean, nullable=False, index=True, comment="质量门禁是否通过")
    total_cases = Column(Integer, nullable=False, default=0, comment="样本总数")
    passed_cases = Column(Integer, nullable=False, default=0, comment="通过样本数")
    failed_cases = Column(Integer, nullable=False, default=0, comment="失败样本数")
    false_close_count = Column(Integer, nullable=False, default=0, comment="误关闭样本数")
    false_close_rate = Column(Float, nullable=False, default=0.0, comment="误关闭率")
    false_delay_count = Column(Integer, nullable=False, default=0, comment="误延期样本数")
    false_delay_rate = Column(Float, nullable=False, default=0.0, comment="误延期率")
    missed_confirmation_count = Column(Integer, nullable=False, default=0, comment="该追问未追问样本数")
    missed_confirmation_rate = Column(Float, nullable=False, default=0.0, comment="该追问未追问率")
    over_confirmation_count = Column(Integer, nullable=False, default=0, comment="过度追问样本数")
    over_confirmation_rate = Column(Float, nullable=False, default=0.0, comment="过度追问率")
    metrics_json = Column(JSON, nullable=True, comment="完整指标快照")
    failure_cases_json = Column(JSON, nullable=True, comment="失败样本摘要")
    case_results_json = Column(JSON, nullable=True, comment="全部样本结果快照")
    thresholds_json = Column(JSON, nullable=True, comment="质量门禁阈值快照")
    error_message = Column(Text, nullable=True, comment="运行错误摘要")
    duration_ms = Column(Integer, nullable=True, comment="耗时毫秒")
    started_at = Column(DateTime, nullable=False, default=business_now, comment="开始时间")
    finished_at = Column(DateTime, nullable=False, default=business_now, index=True, comment="结束时间")
    created_time = Column(DateTime, nullable=False, default=business_now, index=True, comment="创建时间")

    __table_args__ = (
        Index("idx_follow_up_recon_eval_team_suite_time", "team_id", "suite_name", "created_time"),
        Index("idx_follow_up_recon_eval_status_time", "status", "created_time"),
        Index("idx_follow_up_recon_eval_ok_time", "ok", "created_time"),
        {"comment": "跟进任务reconciliation评测运行表"},
    )
