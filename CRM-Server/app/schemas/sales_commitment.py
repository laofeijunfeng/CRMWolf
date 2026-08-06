from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves datetime annotations at runtime.
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.sales_commitment import (
    DueAtGranularity,
    FollowUpTaskConfirmationResolutionAction,
    FollowUpTaskConfirmationStatus,
    FollowUpTaskEventType,
    FollowUpTaskLLMMatcherRunStatus,
    FollowUpTaskProjectionStatus,
    FollowUpTaskProjectionTrigger,
    FollowUpTaskReconciliationEvaluationRunStatus,
    FollowUpTaskReconciliationRunStatus,
    FollowUpTaskSourceType,
    FollowUpTaskStatus,
    SalesCommitmentStatus,
)

SALES_COMMITMENT_STATUSES = {
    SalesCommitmentStatus.OPEN,
    SalesCommitmentStatus.FULFILLED,
    SalesCommitmentStatus.CANCELLED,
    SalesCommitmentStatus.SUPERSEDED,
}
FOLLOW_UP_TASK_STATUSES = {
    FollowUpTaskStatus.OPEN,
    FollowUpTaskStatus.COMPLETED,
    FollowUpTaskStatus.CANCELLED,
}
FOLLOW_UP_TASK_SOURCE_TYPES = {
    FollowUpTaskSourceType.CUSTOMER_ACTIVITY,
    FollowUpTaskSourceType.HISTORICAL_BACKFILL,
}
FOLLOW_UP_TASK_EVENT_TYPES = {
    FollowUpTaskEventType.CREATED,
    FollowUpTaskEventType.UPDATED,
    FollowUpTaskEventType.COMPLETED,
    FollowUpTaskEventType.CANCELLED,
    FollowUpTaskEventType.REOPENED,
}
FOLLOW_UP_TASK_PROJECTION_TRIGGERS = {
    FollowUpTaskProjectionTrigger.ACTIVITY_CREATED_DETERMINISTIC,
    FollowUpTaskProjectionTrigger.ACTIVITY_STRUCTURED_COMPLETED,
    FollowUpTaskProjectionTrigger.ACTIVITY_UPDATED,
    FollowUpTaskProjectionTrigger.ACTIVITY_DELETED,
    FollowUpTaskProjectionTrigger.HISTORICAL_BACKFILL,
}
FOLLOW_UP_TASK_PROJECTION_STATUSES = {
    FollowUpTaskProjectionStatus.RUNNING,
    FollowUpTaskProjectionStatus.SUCCESS,
    FollowUpTaskProjectionStatus.SKIPPED,
    FollowUpTaskProjectionStatus.FAILED,
}
FOLLOW_UP_TASK_RECONCILIATION_RUN_STATUSES = {
    FollowUpTaskReconciliationRunStatus.SUCCESS,
    FollowUpTaskReconciliationRunStatus.SKIPPED,
    FollowUpTaskReconciliationRunStatus.FAILED,
}
FOLLOW_UP_TASK_LLM_MATCHER_RUN_STATUSES = {
    FollowUpTaskLLMMatcherRunStatus.SUCCESS,
    FollowUpTaskLLMMatcherRunStatus.SKIPPED,
    FollowUpTaskLLMMatcherRunStatus.FAILED,
}
FOLLOW_UP_TASK_RECONCILIATION_EVALUATION_RUN_STATUSES = {
    FollowUpTaskReconciliationEvaluationRunStatus.SUCCESS,
    FollowUpTaskReconciliationEvaluationRunStatus.FAILED,
}
FOLLOW_UP_TASK_CONFIRMATION_STATUSES = {
    FollowUpTaskConfirmationStatus.PENDING,
    FollowUpTaskConfirmationStatus.RESOLVED,
    FollowUpTaskConfirmationStatus.CANCELLED,
    FollowUpTaskConfirmationStatus.EXPIRED,
}
FOLLOW_UP_TASK_CONFIRMATION_RESOLUTION_ACTIONS = {
    FollowUpTaskConfirmationResolutionAction.COMPLETE,
    FollowUpTaskConfirmationResolutionAction.DELAY,
    FollowUpTaskConfirmationResolutionAction.CANCEL,
    FollowUpTaskConfirmationResolutionAction.KEEP_OPEN,
    FollowUpTaskConfirmationResolutionAction.UNKNOWN,
}
DUE_AT_GRANULARITIES = {
    DueAtGranularity.DATE,
    DueAtGranularity.DATETIME,
    DueAtGranularity.WEEK,
    DueAtGranularity.MONTH,
    DueAtGranularity.UNKNOWN,
}


class _PublicIdResponse(BaseModel):
    id: str = Field(..., description="对外ID")
    public_id: str = Field(..., description="对外ID")

    @classmethod
    def from_model(cls, db_obj: object) -> Self:
        internal_reference_fields = {
            "customer_id",
            "commitment_id",
            "source_key",
            "source_activity_id",
            "task_id",
            "created_task_ids_json",
            "updated_task_ids_json",
            "cancelled_task_ids_json",
            "created_commitment_ids_json",
            "updated_commitment_ids_json",
        }
        data = {
            column.name: getattr(db_obj, column.name)
            for column in db_obj.__table__.columns
            if column.name != "id" and column.name not in internal_reference_fields
        }
        data["id"] = db_obj.public_id
        return cls.model_validate(data)


class SalesCommitmentInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    customer_id: int = Field(..., description="客户内部ID")
    owner_id: str = Field(..., description="承诺归属人系统用户ID")
    creator_id: str = Field(..., description="承诺创建人系统用户ID")
    title: str = Field(..., min_length=1, max_length=255, description="承诺标题")
    content: str = Field(..., min_length=1, description="承诺内容")
    commitment_type: str = Field("FOLLOW_UP", max_length=50, description="承诺类型")
    status: str = Field(SalesCommitmentStatus.OPEN, description="承诺状态")
    confidence: float = Field(1.0, ge=0, le=1, description="抽取置信度")
    source_type: str = Field(..., description="来源类型")
    source_key: str | None = Field(None, min_length=1, max_length=128, description="幂等来源键")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    due_at: datetime | None = Field(None, description="承诺到期时间")
    due_at_text: str | None = Field(None, max_length=255, description="原始时间表达")
    due_at_granularity: str = Field(DueAtGranularity.UNKNOWN, description="到期时间粒度")
    due_at_timezone: str = Field("Asia/Shanghai", max_length=64, description="到期时间业务时区")
    evidence_json: dict[str, Any] | None = Field(None, description="抽取证据和上下文")
    commitment_hash: str = Field(..., min_length=1, max_length=64, description="承诺幂等哈希")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str) -> str:
        if value not in SALES_COMMITMENT_STATUSES:
            raise ValueError("未知承诺状态")
        return value

    @field_validator("source_type")
    @classmethod
    def source_type_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_SOURCE_TYPES:
            raise ValueError("未知来源类型")
        return value

    @field_validator("due_at_granularity")
    @classmethod
    def due_at_granularity_must_be_known(cls, value: str) -> str:
        if value not in DUE_AT_GRANULARITIES:
            raise ValueError("未知到期时间粒度")
        return value


class SalesCommitmentInternalUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255, description="承诺标题")
    content: str | None = Field(None, min_length=1, description="承诺内容")
    commitment_type: str | None = Field(None, max_length=50, description="承诺类型")
    status: str | None = Field(None, description="承诺状态")
    confidence: float | None = Field(None, ge=0, le=1, description="抽取置信度")
    due_at: datetime | None = Field(None, description="承诺到期时间")
    due_at_text: str | None = Field(None, max_length=255, description="原始时间表达")
    due_at_granularity: str | None = Field(None, description="到期时间粒度")
    due_at_timezone: str | None = Field(None, max_length=64, description="到期时间业务时区")
    evidence_json: dict[str, Any] | None = Field(None, description="抽取证据和上下文")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in SALES_COMMITMENT_STATUSES:
            raise ValueError("未知承诺状态")
        return value

    @field_validator("due_at_granularity")
    @classmethod
    def due_at_granularity_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in DUE_AT_GRANULARITIES:
            raise ValueError("未知到期时间粒度")
        return value


class SalesCommitmentResponse(_PublicIdResponse):
    team_id: int = Field(..., description="团队ID")
    customer_id: str | None = Field(None, description="客户对外ID")
    customer_public_id: str | None = Field(None, description="客户对外ID")
    owner_id: str = Field(..., description="承诺归属人系统用户ID")
    creator_id: str = Field(..., description="承诺创建人系统用户ID")
    title: str = Field(..., description="承诺标题")
    content: str = Field(..., description="承诺内容")
    commitment_type: str = Field(..., description="承诺类型")
    status: str = Field(..., description="承诺状态")
    confidence: float = Field(..., description="抽取置信度")
    source_type: str = Field(..., description="来源类型")
    source_public_id: str | None = Field(None, description="来源对象对外ID")
    due_at: datetime | None = Field(None, description="承诺到期时间")
    due_at_text: str | None = Field(None, description="原始时间表达")
    due_at_granularity: str = Field(..., description="到期时间粒度")
    due_at_timezone: str = Field(..., description="到期时间业务时区")
    evidence_json: dict[str, Any] | None = Field(None, description="抽取证据和上下文")
    commitment_hash: str = Field(..., description="承诺幂等哈希")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")


class FollowUpTaskInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    customer_id: int = Field(..., description="客户内部ID")
    commitment_id: int | None = Field(None, description="关联承诺内部ID")
    owner_id: str = Field(..., description="任务归属人系统用户ID")
    creator_id: str = Field(..., description="任务创建人系统用户ID")
    title: str = Field(..., min_length=1, max_length=255, description="任务标题")
    description: str | None = Field(None, description="任务描述")
    status: str = Field(FollowUpTaskStatus.OPEN, description="任务状态")
    due_at: datetime = Field(..., description="任务到期时间")
    due_at_text: str | None = Field(None, max_length=255, description="原始时间表达")
    due_at_granularity: str = Field(DueAtGranularity.DATETIME, description="到期时间粒度")
    due_at_timezone: str = Field("Asia/Shanghai", max_length=64, description="到期时间业务时区")
    source_type: str = Field(..., description="来源类型")
    source_key: str | None = Field(None, min_length=1, max_length=128, description="幂等来源键")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    confidence: float = Field(1.0, ge=0, le=1, description="抽取置信度")
    evidence_json: dict[str, Any] | None = Field(None, description="抽取证据和上下文")
    task_hash: str = Field(..., min_length=1, max_length=64, description="任务幂等哈希")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_STATUSES:
            raise ValueError("未知任务状态")
        return value

    @field_validator("source_type")
    @classmethod
    def source_type_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_SOURCE_TYPES:
            raise ValueError("未知来源类型")
        return value

    @field_validator("due_at_granularity")
    @classmethod
    def due_at_granularity_must_be_known(cls, value: str) -> str:
        if value not in DUE_AT_GRANULARITIES:
            raise ValueError("未知到期时间粒度")
        return value


class FollowUpTaskInternalUpdate(BaseModel):
    commitment_id: int | None = Field(None, description="关联承诺内部ID")
    title: str | None = Field(None, min_length=1, max_length=255, description="任务标题")
    description: str | None = Field(None, description="任务描述")
    status: str | None = Field(None, description="任务状态")
    due_at: datetime | None = Field(None, description="任务到期时间")
    due_at_text: str | None = Field(None, max_length=255, description="原始时间表达")
    due_at_granularity: str | None = Field(None, description="到期时间粒度")
    due_at_timezone: str | None = Field(None, max_length=64, description="到期时间业务时区")
    confidence: float | None = Field(None, ge=0, le=1, description="抽取置信度")
    evidence_json: dict[str, Any] | None = Field(None, description="抽取证据和上下文")
    completed_at: datetime | None = Field(None, description="完成时间")
    cancelled_at: datetime | None = Field(None, description="取消时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in FOLLOW_UP_TASK_STATUSES:
            raise ValueError("未知任务状态")
        return value

    @field_validator("due_at_granularity")
    @classmethod
    def due_at_granularity_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in DUE_AT_GRANULARITIES:
            raise ValueError("未知到期时间粒度")
        return value


class FollowUpTaskResponse(_PublicIdResponse):
    team_id: int = Field(..., description="团队ID")
    customer_id: str | None = Field(None, description="客户对外ID")
    customer_public_id: str | None = Field(None, description="客户对外ID")
    commitment_id: str | None = Field(None, description="关联承诺对外ID")
    commitment_public_id: str | None = Field(None, description="关联承诺对外ID")
    owner_id: str = Field(..., description="任务归属人系统用户ID")
    creator_id: str = Field(..., description="任务创建人系统用户ID")
    title: str = Field(..., description="任务标题")
    description: str | None = Field(None, description="任务描述")
    status: str = Field(..., description="任务状态")
    due_at: datetime = Field(..., description="任务到期时间")
    due_at_text: str | None = Field(None, description="原始时间表达")
    due_at_granularity: str = Field(..., description="到期时间粒度")
    due_at_timezone: str = Field(..., description="到期时间业务时区")
    source_type: str = Field(..., description="来源类型")
    source_public_id: str | None = Field(None, description="来源对象对外ID")
    confidence: float = Field(..., description="抽取置信度")
    evidence_json: dict[str, Any] | None = Field(None, description="抽取证据和上下文")
    task_hash: str = Field(..., description="任务幂等哈希")
    completed_at: datetime | None = Field(None, description="完成时间")
    cancelled_at: datetime | None = Field(None, description="取消时间")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")


class FollowUpTaskEventInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    task_id: int = Field(..., description="任务内部ID")
    event_type: str = Field(..., description="事件类型")
    actor_id: str | None = Field(None, description="触发人系统用户ID")
    source_type: str | None = Field(None, description="来源类型")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    previous_status: str | None = Field(None, description="变更前状态")
    new_status: str | None = Field(None, description="变更后状态")
    payload_json: dict[str, Any] | None = Field(None, description="事件载荷")

    @field_validator("event_type")
    @classmethod
    def event_type_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_EVENT_TYPES:
            raise ValueError("未知任务事件类型")
        return value


class FollowUpTaskEventResponse(BaseModel):
    id: str = Field(..., description="任务事件对外ID")
    public_id: str = Field(..., description="任务事件对外ID")
    team_id: int = Field(..., description="团队ID")
    task_id: str | None = Field(None, description="任务对外ID")
    task_public_id: str | None = Field(None, description="任务对外ID")
    event_type: str = Field(..., description="事件类型")
    actor_id: str | None = Field(None, description="触发人系统用户ID")
    source_type: str | None = Field(None, description="来源类型")
    source_public_id: str | None = Field(None, description="来源对象对外ID")
    previous_status: str | None = Field(None, description="变更前状态")
    new_status: str | None = Field(None, description="变更后状态")
    payload_json: dict[str, Any] | None = Field(None, description="事件载荷")
    created_time: datetime = Field(..., description="创建时间")

    @classmethod
    def from_model(
        cls,
        db_obj: object,
        *,
        task_public_id: str | None = None,
        source_public_id: str | None = None,
    ) -> Self:
        data = {
            column.name: getattr(db_obj, column.name)
            for column in db_obj.__table__.columns
            if column.name not in {"id", "task_id", "source_activity_id"}
        }
        data["id"] = db_obj.public_id
        public_task_id = task_public_id or None
        data["task_id"] = public_task_id
        data["task_public_id"] = public_task_id
        if source_public_id is not None:
            data["source_public_id"] = source_public_id
        return cls.model_validate(data)


class FollowUpTaskTransitionPolicyDecisionLogInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    owner_id: str | None = Field(None, max_length=100, description="任务归属人系统用户ID")
    actor_id: str | None = Field(None, max_length=100, description="触发人系统用户ID")
    task_id: int | None = Field(None, description="跟进任务内部ID")
    source_type: str | None = Field(None, max_length=50, description="来源类型")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    action: str | None = Field(None, max_length=30, description="计划迁移动作")
    allowed: bool = Field(..., description="是否允许自动执行")
    reason: str = Field(..., min_length=1, max_length=80, description="策略决策原因")
    enabled: bool = Field(..., description="团队自动迁移开关是否开启")
    owner_allowlist_configured: bool = Field(False, description="是否配置归属人白名单")
    allowed_actions_json: list[str] | None = Field(None, description="命中的动作白名单快照")
    config_errors_json: list[str] | None = Field(None, description="配置错误快照")
    policy_result_json: dict[str, Any] | None = Field(None, description="完整策略决策快照")
    context_json: dict[str, Any] | None = Field(None, description="决策上下文快照")

    @field_validator("source_type")
    @classmethod
    def source_type_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in FOLLOW_UP_TASK_SOURCE_TYPES:
            raise ValueError("未知来源类型")
        return value


class FollowUpTaskReconciliationRunInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    customer_id: int | None = Field(None, description="客户内部ID")
    owner_id: str | None = Field(None, max_length=100, description="活动/任务归属人系统用户ID")
    actor_id: str | None = Field(None, max_length=100, description="触发人系统用户ID")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    status: str = Field(..., description="运行状态")
    skip_reason: str | None = Field(None, max_length=80, description="跳过原因")
    include_cross_owner: bool = Field(False, description="是否纳入跨owner候选")
    lookback_days: int = Field(90, ge=0, description="候选回看天数")
    lookahead_days: int = Field(30, ge=0, description="候选前看天数")
    limit: int = Field(20, ge=1, description="候选数量上限")
    candidate_count: int = Field(0, ge=0, description="候选任务数量")
    candidate_public_ids_json: list[str] | None = Field(None, description="候选任务对外ID快照")
    filters_json: dict[str, Any] | None = Field(None, description="候选过滤条件快照")
    usage_policy_json: dict[str, Any] | None = Field(None, description="使用策略快照")
    error_message: str | None = Field(None, description="错误摘要")
    duration_ms: int | None = Field(None, ge=0, description="耗时毫秒")
    anchor_at: datetime | None = Field(None, description="候选窗口锚点时间")
    started_at: datetime | None = Field(None, description="开始时间")
    finished_at: datetime | None = Field(None, description="结束时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_RECONCILIATION_RUN_STATUSES:
            raise ValueError("未知reconciliation运行状态")
        return value


class FollowUpTaskLLMMatcherRunInternalCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    team_id: int = Field(..., description="团队ID")
    owner_id: str | None = Field(None, max_length=100, description="活动/任务归属人系统用户ID")
    actor_id: str | None = Field(None, max_length=100, description="触发人系统用户ID")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    reconciliation_run_public_id: str | None = Field(None, max_length=64, description="reconciliation运行对外ID")
    status: str = Field(..., description="运行状态")
    source: str = Field(..., min_length=1, max_length=80, description="匹配结果来源")
    decision: str | None = Field(None, max_length=30, description="归一化决策")
    task_public_id: str | None = Field(None, max_length=64, description="候选任务对外ID")
    candidate_public_ids_json: list[str] | None = Field(None, description="候选任务对外ID快照")
    confidence: float | None = Field(None, ge=0, le=1, description="归一化置信度")
    needs_confirmation: bool = Field(False, description="是否需要用户确认")
    forbid_auto_reasons_json: list[str] | None = Field(None, description="禁止自动迁移原因")
    evidence_terms_json: list[str] | None = Field(None, description="证据词快照")
    referenced_source_public_ids_json: list[str] | None = Field(None, description="引用来源对外ID")
    evaluation_failures_json: list[str] | None = Field(None, description="安全评测失败项")
    model_name: str | None = Field(None, max_length=120, description="LLM模型名")
    structured_output_strategy: str | None = Field(None, max_length=40, description="结构化输出策略")
    schema_error_type: str | None = Field(None, max_length=80, description="结构化输出错误类型")
    schema_error_message: str | None = Field(None, description="结构化输出错误摘要")
    duration_ms: int | None = Field(None, ge=0, description="耗时毫秒")
    started_at: datetime | None = Field(None, description="开始时间")
    finished_at: datetime | None = Field(None, description="结束时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_LLM_MATCHER_RUN_STATUSES:
            raise ValueError("未知LLM匹配运行状态")
        return value


class FollowUpTaskReconciliationEvaluationRunInternalCreate(BaseModel):
    team_id: int | None = Field(None, description="团队ID；系统级评测可为空")
    suite_name: str = Field(..., min_length=1, max_length=120, description="评测套件名称")
    fixture_path: str | None = Field(None, max_length=500, description="评测样本路径")
    fixture_hash: str | None = Field(None, max_length=64, description="评测样本内容hash")
    status: str = Field(..., description="运行状态")
    ok: bool = Field(..., description="质量门禁是否通过")
    total_cases: int = Field(0, ge=0, description="样本总数")
    passed_cases: int = Field(0, ge=0, description="通过样本数")
    failed_cases: int = Field(0, ge=0, description="失败样本数")
    false_close_count: int = Field(0, ge=0, description="误关闭样本数")
    false_close_rate: float = Field(0.0, ge=0, le=1, description="误关闭率")
    false_delay_count: int = Field(0, ge=0, description="误延期样本数")
    false_delay_rate: float = Field(0.0, ge=0, le=1, description="误延期率")
    missed_confirmation_count: int = Field(0, ge=0, description="该追问未追问样本数")
    missed_confirmation_rate: float = Field(0.0, ge=0, le=1, description="该追问未追问率")
    over_confirmation_count: int = Field(0, ge=0, description="过度追问样本数")
    over_confirmation_rate: float = Field(0.0, ge=0, le=1, description="过度追问率")
    metrics_json: dict[str, Any] | None = Field(None, description="完整指标快照")
    failure_cases_json: list[dict[str, Any]] | None = Field(None, description="失败样本摘要")
    case_results_json: list[dict[str, Any]] | None = Field(None, description="全部样本结果快照")
    thresholds_json: dict[str, Any] | None = Field(None, description="质量门禁阈值快照")
    error_message: str | None = Field(None, description="运行错误摘要")
    duration_ms: int | None = Field(None, ge=0, description="耗时毫秒")
    started_at: datetime | None = Field(None, description="开始时间")
    finished_at: datetime | None = Field(None, description="结束时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_RECONCILIATION_EVALUATION_RUN_STATUSES:
            raise ValueError("未知reconciliation评测运行状态")
        return value


class FollowUpTaskProjectionRunInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    trigger_type: str = Field(..., description="投影触发类型")
    source_type: str = Field(..., description="来源类型")
    source_key: str | None = Field(None, min_length=1, max_length=128, description="幂等来源键")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    actor_id: str | None = Field(None, description="触发人系统用户ID")
    input_snapshot_hash: str | None = Field(None, max_length=64, description="输入快照哈希")
    attempt_count: int = Field(1, ge=1, description="尝试次数")

    @field_validator("trigger_type")
    @classmethod
    def trigger_type_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_PROJECTION_TRIGGERS:
            raise ValueError("未知投影触发类型")
        return value

    @field_validator("source_type")
    @classmethod
    def source_type_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_SOURCE_TYPES:
            raise ValueError("未知来源类型")
        return value


class FollowUpTaskProjectionRunInternalUpdate(BaseModel):
    status: str | None = Field(None, description="投影状态")
    skip_reason: str | None = Field(None, max_length=80, description="跳过原因")
    projection_hash: str | None = Field(None, max_length=64, description="投影结果哈希")
    task_count: int | None = Field(None, ge=0, description="涉及任务数量")
    commitment_count: int | None = Field(None, ge=0, description="涉及承诺数量")
    created_task_ids_json: list[int] | None = Field(None, description="新建任务内部ID列表")
    updated_task_ids_json: list[int] | None = Field(None, description="更新任务内部ID列表")
    cancelled_task_ids_json: list[int] | None = Field(None, description="取消任务内部ID列表")
    created_commitment_ids_json: list[int] | None = Field(None, description="新建承诺内部ID列表")
    updated_commitment_ids_json: list[int] | None = Field(None, description="更新承诺内部ID列表")
    error_message: str | None = Field(None, description="错误摘要")
    duration_ms: int | None = Field(None, ge=0, description="耗时毫秒")
    finished_at: datetime | None = Field(None, description="结束时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in FOLLOW_UP_TASK_PROJECTION_STATUSES:
            raise ValueError("未知投影状态")
        return value


class FollowUpTaskProjectionRunResponse(_PublicIdResponse):
    team_id: int = Field(..., description="团队ID")
    trigger_type: str = Field(..., description="投影触发类型")
    status: str = Field(..., description="投影状态")
    source_type: str = Field(..., description="来源类型")
    source_public_id: str | None = Field(None, description="来源对象对外ID")
    actor_id: str | None = Field(None, description="触发人系统用户ID")
    skip_reason: str | None = Field(None, description="跳过原因")
    input_snapshot_hash: str | None = Field(None, description="输入快照哈希")
    projection_hash: str | None = Field(None, description="投影结果哈希")
    task_count: int = Field(..., description="涉及任务数量")
    commitment_count: int = Field(..., description="涉及承诺数量")
    created_task_ids: list[str] | None = Field(None, description="新建任务对外ID列表")
    updated_task_ids: list[str] | None = Field(None, description="更新任务对外ID列表")
    cancelled_task_ids: list[str] | None = Field(None, description="取消任务对外ID列表")
    created_commitment_ids: list[str] | None = Field(None, description="新建承诺对外ID列表")
    updated_commitment_ids: list[str] | None = Field(None, description="更新承诺对外ID列表")
    error_message: str | None = Field(None, description="错误摘要")
    attempt_count: int = Field(..., description="尝试次数")
    duration_ms: int | None = Field(None, description="耗时毫秒")
    started_at: datetime = Field(..., description="开始时间")
    finished_at: datetime | None = Field(None, description="结束时间")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")

    @classmethod
    def from_model(
        cls,
        db_obj: object,
        *,
        created_task_public_ids: list[str] | None = None,
        updated_task_public_ids: list[str] | None = None,
        cancelled_task_public_ids: list[str] | None = None,
        created_commitment_public_ids: list[str] | None = None,
        updated_commitment_public_ids: list[str] | None = None,
    ) -> Self:
        data = {
            column.name: getattr(db_obj, column.name)
            for column in db_obj.__table__.columns
            if column.name
            not in {
                "id",
                "source_key",
                "source_activity_id",
                "created_task_ids_json",
                "updated_task_ids_json",
                "cancelled_task_ids_json",
                "created_commitment_ids_json",
                "updated_commitment_ids_json",
            }
        }
        data["id"] = db_obj.public_id
        data["created_task_ids"] = created_task_public_ids
        data["updated_task_ids"] = updated_task_public_ids
        data["cancelled_task_ids"] = cancelled_task_public_ids
        data["created_commitment_ids"] = created_commitment_public_ids
        data["updated_commitment_ids"] = updated_commitment_public_ids
        return cls.model_validate(data)


class FollowUpTaskConfirmationCaseInternalCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    task_id: int = Field(..., description="跟进任务内部ID")
    customer_id: int = Field(..., description="客户内部ID")
    owner_id: str = Field(..., description="确认归属人系统用户ID")
    creator_id: str = Field(..., description="确认创建人系统用户ID")
    status: str = Field(FollowUpTaskConfirmationStatus.PENDING, description="确认状态")
    suggested_action: str = Field(..., max_length=30, description="建议处理动作")
    confirmation_hash: str = Field(..., min_length=1, max_length=64, description="确认Case幂等哈希")
    question_text: str = Field(..., min_length=1, description="确认问题")
    source_activity_id: int | None = Field(None, description="来源客户活动内部ID")
    source_public_id: str | None = Field(None, max_length=64, description="来源对象对外ID")
    source_plan_json: dict[str, Any] | None = Field(None, description="状态迁移计划快照")
    expires_at: datetime | None = Field(None, description="确认Case过期时间")
    last_prompted_at: datetime | None = Field(None, description="最近提醒时间")
    prompt_count: int = Field(0, ge=0, description="提醒次数")
    unresolved_reply_count: int = Field(0, ge=0, description="无法解析回复次数")
    last_unresolved_reply_text: str | None = Field(None, description="最近一次无法解析的用户回复")
    last_unresolved_reply_by_id: str | None = Field(None, description="最近一次无法解析回复人")
    last_unresolved_reply_at: datetime | None = Field(None, description="最近一次无法解析回复时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str) -> str:
        if value not in FOLLOW_UP_TASK_CONFIRMATION_STATUSES:
            raise ValueError("未知确认状态")
        return value


class FollowUpTaskConfirmationCaseInternalUpdate(BaseModel):
    status: str | None = Field(None, description="确认状态")
    question_text: str | None = Field(None, min_length=1, description="确认问题")
    expires_at: datetime | None = Field(None, description="确认Case过期时间")
    last_prompted_at: datetime | None = Field(None, description="最近提醒时间")
    prompt_count: int | None = Field(None, ge=0, description="提醒次数")
    unresolved_reply_count: int | None = Field(None, ge=0, description="无法解析回复次数")
    last_unresolved_reply_text: str | None = Field(None, description="最近一次无法解析的用户回复")
    last_unresolved_reply_by_id: str | None = Field(None, description="最近一次无法解析回复人")
    last_unresolved_reply_at: datetime | None = Field(None, description="最近一次无法解析回复时间")
    resolved_action: str | None = Field(None, description="用户确认后的处理动作")
    resolved_due_at: datetime | None = Field(None, description="用户确认后的延期时间")
    resolved_due_at_text: str | None = Field(None, max_length=255, description="用户确认后的原始时间表达")
    resolution_text: str | None = Field(None, description="用户原始回复")
    resolved_by_id: str | None = Field(None, description="确认处理人")
    resolved_at: datetime | None = Field(None, description="确认处理时间")
    expired_at: datetime | None = Field(None, description="确认Case实际过期时间")
    cancelled_at: datetime | None = Field(None, description="确认Case取消时间")
    cancelled_by_id: str | None = Field(None, description="确认Case取消人")
    cancelled_reason: str | None = Field(None, max_length=80, description="确认Case取消原因")
    application_status: str | None = Field(None, description="确认应用状态")
    application_skip_reason: str | None = Field(None, max_length=80, description="确认应用跳过原因")
    application_result_json: dict[str, Any] | None = Field(None, description="确认应用结果快照")
    applied_by_id: str | None = Field(None, description="确认应用执行人")
    applied_at: datetime | None = Field(None, description="确认应用时间")

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in FOLLOW_UP_TASK_CONFIRMATION_STATUSES:
            raise ValueError("未知确认状态")
        return value

    @field_validator("resolved_action")
    @classmethod
    def resolved_action_must_be_known(cls, value: str | None) -> str | None:
        if value is not None and value not in FOLLOW_UP_TASK_CONFIRMATION_RESOLUTION_ACTIONS:
            raise ValueError("未知确认处理动作")
        return value


class FollowUpTaskConfirmationCaseResponse(_PublicIdResponse):
    team_id: int = Field(..., description="团队ID")
    task_id: str | None = Field(None, description="跟进任务对外ID")
    task_public_id: str | None = Field(None, description="跟进任务对外ID")
    customer_id: str | None = Field(None, description="客户对外ID")
    customer_public_id: str | None = Field(None, description="客户对外ID")
    owner_id: str = Field(..., description="确认归属人系统用户ID")
    creator_id: str = Field(..., description="确认创建人系统用户ID")
    status: str = Field(..., description="确认状态")
    suggested_action: str = Field(..., description="建议处理动作")
    confirmation_hash: str = Field(..., description="确认Case幂等哈希")
    question_text: str = Field(..., description="确认问题")
    source_public_id: str | None = Field(None, description="来源对象对外ID")
    expires_at: datetime | None = Field(None, description="确认Case过期时间")
    last_prompted_at: datetime | None = Field(None, description="最近提醒时间")
    prompt_count: int = Field(..., description="提醒次数")
    unresolved_reply_count: int = Field(..., description="无法解析回复次数")
    last_unresolved_reply_text: str | None = Field(None, description="最近一次无法解析的用户回复")
    last_unresolved_reply_by_id: str | None = Field(None, description="最近一次无法解析回复人")
    last_unresolved_reply_at: datetime | None = Field(None, description="最近一次无法解析回复时间")
    resolved_action: str | None = Field(None, description="用户确认后的处理动作")
    resolved_due_at: datetime | None = Field(None, description="用户确认后的延期时间")
    resolved_due_at_text: str | None = Field(None, description="用户确认后的原始时间表达")
    resolution_text: str | None = Field(None, description="用户原始回复")
    resolved_by_id: str | None = Field(None, description="确认处理人")
    resolved_at: datetime | None = Field(None, description="确认处理时间")
    expired_at: datetime | None = Field(None, description="确认Case实际过期时间")
    cancelled_at: datetime | None = Field(None, description="确认Case取消时间")
    cancelled_by_id: str | None = Field(None, description="确认Case取消人")
    cancelled_reason: str | None = Field(None, description="确认Case取消原因")
    application_status: str | None = Field(None, description="确认应用状态")
    application_skip_reason: str | None = Field(None, description="确认应用跳过原因")
    applied_by_id: str | None = Field(None, description="确认应用执行人")
    applied_at: datetime | None = Field(None, description="确认应用时间")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")

    @classmethod
    def from_model(
        cls,
        db_obj: object,
        *,
        task_public_id: str | None = None,
        customer_public_id: str | None = None,
    ) -> Self:
        data = {
            column.name: getattr(db_obj, column.name)
            for column in db_obj.__table__.columns
            if column.name
            not in {
                "id",
                "task_id",
                "customer_id",
                "source_activity_id",
                "source_plan_json",
                "application_result_json",
            }
        }
        data["id"] = db_obj.public_id
        data["task_id"] = task_public_id
        data["task_public_id"] = task_public_id
        data["customer_id"] = customer_public_id
        data["customer_public_id"] = customer_public_id
        return cls.model_validate(data)
