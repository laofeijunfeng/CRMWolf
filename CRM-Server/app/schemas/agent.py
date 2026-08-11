"""CRM AI Agent schemas."""
from datetime import datetime
from typing import List, Optional, TypeAlias

from pydantic import BaseModel, Field


JsonDict: TypeAlias = dict[str, object]


class AgentSessionCreate(BaseModel):
    session_key: str = Field(..., min_length=1, max_length=64, description="Agent会话唯一标识")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    title: Optional[str] = Field(None, max_length=200, description="会话标题")
    context_json: Optional[JsonDict] = Field(None, description="会话上下文快照")


class AgentCreateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200, description="会话标题")
    context_json: Optional[JsonDict] = Field(None, description="会话上下文快照")


class AgentSessionUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200, description="会话标题")
    status: Optional[str] = Field(None, max_length=20, description="会话状态")
    summary: Optional[str] = Field(None, description="会话摘要")
    context_json: Optional[JsonDict] = Field(None, description="会话上下文快照")


class AgentSessionResponse(BaseModel):
    id: int = Field(..., description="主键")
    session_key: str = Field(..., description="Agent会话唯一标识")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    title: Optional[str] = Field(None, description="会话标题")
    status: str = Field(..., description="会话状态")
    summary: Optional[str] = Field(None, description="会话摘要")
    context_json: Optional[JsonDict] = Field(None, description="会话上下文快照")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class AgentMessageCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: int = Field(..., description="Agent会话ID")
    role: str = Field(..., max_length=20, description="消息角色")
    event_type: Optional[str] = Field(None, max_length=50, description="SSE或业务事件类型")
    content: Optional[str] = Field(None, description="消息正文")
    payload_json: Optional[JsonDict] = Field(None, description="结构化消息载荷")


class AgentMessageResponse(BaseModel):
    id: int = Field(..., description="主键")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: int = Field(..., description="Agent会话ID")
    role: str = Field(..., description="消息角色")
    event_type: Optional[str] = Field(None, description="SSE或业务事件类型")
    content: Optional[str] = Field(None, description="消息正文")
    payload_json: Optional[JsonDict] = Field(None, description="结构化消息载荷")
    created_time: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class AgentTaskCreate(BaseModel):
    task_key: str = Field(..., min_length=1, max_length=64, description="Agent任务唯一标识")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: int = Field(..., description="Agent会话ID")
    intent: Optional[str] = Field(None, max_length=80, description="识别出的意图")
    status: Optional[str] = Field(None, max_length=20, description="任务状态")
    target_type: Optional[str] = Field(None, max_length=50, description="目标业务对象类型")
    target_id: Optional[int] = Field(None, description="目标业务对象ID")
    summary: Optional[str] = Field(None, description="任务摘要")
    input_json: Optional[JsonDict] = Field(None, description="用户输入解析快照")
    state_json: Optional[JsonDict] = Field(None, description="LangGraph状态快照")


class AgentTaskUpdate(BaseModel):
    intent: Optional[str] = Field(None, max_length=80, description="识别出的意图")
    status: Optional[str] = Field(None, max_length=20, description="任务状态")
    target_type: Optional[str] = Field(None, max_length=50, description="目标业务对象类型")
    target_id: Optional[int] = Field(None, description="目标业务对象ID")
    summary: Optional[str] = Field(None, description="任务摘要")
    input_json: Optional[JsonDict] = Field(None, description="用户输入解析快照")
    state_json: Optional[JsonDict] = Field(None, description="LangGraph状态快照")
    result_json: Optional[JsonDict] = Field(None, description="任务结果快照")
    error_message: Optional[str] = Field(None, description="错误信息")


class AgentTaskResponse(BaseModel):
    id: int = Field(..., description="主键")
    task_key: str = Field(..., description="Agent任务唯一标识")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: int = Field(..., description="Agent会话ID")
    intent: Optional[str] = Field(None, description="识别出的意图")
    status: str = Field(..., description="任务状态")
    target_type: Optional[str] = Field(None, description="目标业务对象类型")
    target_id: Optional[int] = Field(None, description="目标业务对象ID")
    summary: Optional[str] = Field(None, description="任务摘要")
    input_json: Optional[JsonDict] = Field(None, description="用户输入解析快照")
    state_json: Optional[JsonDict] = Field(None, description="LangGraph状态快照")
    result_json: Optional[JsonDict] = Field(None, description="任务结果快照")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class AgentToolCallCreate(BaseModel):
    call_key: str = Field(..., min_length=1, max_length=64, description="Tool调用唯一标识")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: int = Field(..., description="Agent会话ID")
    task_id: Optional[int] = Field(None, description="Agent任务ID")
    tool_name: str = Field(..., min_length=1, max_length=100, description="Tool名称")
    request_json: Optional[JsonDict] = Field(None, description="Tool请求参数快照")


class AgentToolCallUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=20, description="调用状态")
    response_json: Optional[JsonDict] = Field(None, description="Tool响应结果快照")
    error_message: Optional[str] = Field(None, description="错误信息")
    started_time: Optional[datetime] = Field(None, description="开始时间")
    finished_time: Optional[datetime] = Field(None, description="结束时间")


class AgentToolCallResponse(BaseModel):
    id: int = Field(..., description="主键")
    call_key: str = Field(..., description="Tool调用唯一标识")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: int = Field(..., description="Agent会话ID")
    task_id: Optional[int] = Field(None, description="Agent任务ID")
    tool_name: str = Field(..., description="Tool名称")
    status: str = Field(..., description="调用状态")
    request_json: Optional[JsonDict] = Field(None, description="Tool请求参数快照")
    response_json: Optional[JsonDict] = Field(None, description="Tool响应结果快照")
    error_message: Optional[str] = Field(None, description="错误信息")
    started_time: Optional[datetime] = Field(None, description="开始时间")
    finished_time: Optional[datetime] = Field(None, description="结束时间")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class AgentIdempotencyKeyCreate(BaseModel):
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: Optional[int] = Field(None, description="Agent会话ID")
    task_id: Optional[int] = Field(None, description="Agent任务ID")
    action_key: str = Field(..., min_length=1, max_length=160, description="幂等动作键")
    request_hash: Optional[str] = Field(None, max_length=64, description="请求内容Hash")


class AgentIdempotencyKeyUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=20, description="幂等状态")
    result_json: Optional[JsonDict] = Field(None, description="执行结果快照")
    error_message: Optional[str] = Field(None, description="错误信息")


class AgentIdempotencyKeyResponse(BaseModel):
    id: int = Field(..., description="主键")
    team_id: int = Field(..., description="团队ID")
    user_id: int = Field(..., description="系统用户ID")
    session_id: Optional[int] = Field(None, description="Agent会话ID")
    task_id: Optional[int] = Field(None, description="Agent任务ID")
    action_key: str = Field(..., description="幂等动作键")
    status: str = Field(..., description="幂等状态")
    request_hash: Optional[str] = Field(None, description="请求内容Hash")
    result_json: Optional[JsonDict] = Field(None, description="执行结果快照")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class AgentWorkflowActionCreate(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=64, description="Agent工作流ID")
    action_id: str = Field(..., min_length=1, max_length=64, description="Agent动作ID")
    parent_action_id: Optional[str] = Field(None, max_length=64, description="父动作ID")
    team_id: int = Field(..., description="团队ID")
    user_id: Optional[int] = Field(None, description="系统用户ID")
    session_id: Optional[int] = Field(None, description="Agent会话ID")
    task_id: Optional[int] = Field(None, description="兼容挂起任务ID")
    source_message_id: Optional[int] = Field(None, description="来源消息ID")
    source_type: str = Field(..., min_length=1, max_length=80, description="动作来源")
    action_type: str = Field(..., min_length=1, max_length=100, description="动作类型")
    status: Optional[str] = Field(None, max_length=20, description="动作状态")
    scope: str = Field(..., min_length=1, max_length=50, description="动作范围")
    source: str = Field(..., min_length=1, max_length=80, description="业务来源策略")
    execution_policy: str = Field(..., min_length=1, max_length=80, description="执行策略")
    on_reject: str = Field(..., min_length=1, max_length=80, description="拒绝策略")
    blocking: bool = Field(..., description="是否阻塞工作流")
    target_type: Optional[str] = Field(None, max_length=50, description="目标业务对象类型")
    target_id: Optional[int] = Field(None, description="目标业务对象ID")
    dependency_json: Optional[JsonDict] = Field(None, description="动作依赖")
    payload_json: Optional[JsonDict] = Field(None, description="动作输入载荷")
    result_json: Optional[JsonDict] = Field(None, description="动作结果")
    decision_json: Optional[JsonDict] = Field(None, description="用户或路由决策")
    idempotency_key: Optional[str] = Field(None, max_length=160, description="业务幂等键")
    status_reason: Optional[str] = Field(None, description="状态原因")
    error_message: Optional[str] = Field(None, description="错误信息")


class AgentWorkflowActionUpdate(BaseModel):
    parent_action_id: Optional[str] = Field(None, max_length=64, description="父动作ID")
    task_id: Optional[int] = Field(None, description="兼容挂起任务ID")
    source_message_id: Optional[int] = Field(None, description="来源消息ID")
    status: Optional[str] = Field(None, max_length=20, description="动作状态")
    target_type: Optional[str] = Field(None, max_length=50, description="目标业务对象类型")
    target_id: Optional[int] = Field(None, description="目标业务对象ID")
    dependency_json: Optional[JsonDict] = Field(None, description="动作依赖")
    payload_json: Optional[JsonDict] = Field(None, description="动作输入载荷")
    result_json: Optional[JsonDict] = Field(None, description="动作结果")
    decision_json: Optional[JsonDict] = Field(None, description="用户或路由决策")
    idempotency_key: Optional[str] = Field(None, max_length=160, description="业务幂等键")
    status_reason: Optional[str] = Field(None, description="状态原因")
    error_message: Optional[str] = Field(None, description="错误信息")
    started_time: Optional[datetime] = Field(None, description="开始时间")
    finished_time: Optional[datetime] = Field(None, description="结束时间")


class AgentWorkflowActionResponse(BaseModel):
    id: int = Field(..., description="主键")
    workflow_id: str = Field(..., description="Agent工作流ID")
    action_id: str = Field(..., description="Agent动作ID")
    parent_action_id: Optional[str] = Field(None, description="父动作ID")
    team_id: int = Field(..., description="团队ID")
    user_id: Optional[int] = Field(None, description="系统用户ID")
    session_id: Optional[int] = Field(None, description="Agent会话ID")
    task_id: Optional[int] = Field(None, description="兼容挂起任务ID")
    source_message_id: Optional[int] = Field(None, description="来源消息ID")
    source_type: str = Field(..., description="动作来源")
    action_type: str = Field(..., description="动作类型")
    status: str = Field(..., description="动作状态")
    scope: str = Field(..., description="动作范围")
    source: str = Field(..., description="业务来源策略")
    execution_policy: str = Field(..., description="执行策略")
    on_reject: str = Field(..., description="拒绝策略")
    blocking: bool = Field(..., description="是否阻塞工作流")
    target_type: Optional[str] = Field(None, description="目标业务对象类型")
    target_id: Optional[int] = Field(None, description="目标业务对象ID")
    dependency_json: Optional[JsonDict] = Field(None, description="动作依赖")
    payload_json: Optional[JsonDict] = Field(None, description="动作输入载荷")
    result_json: Optional[JsonDict] = Field(None, description="动作结果")
    decision_json: Optional[JsonDict] = Field(None, description="用户或路由决策")
    idempotency_key: Optional[str] = Field(None, description="业务幂等键")
    status_reason: Optional[str] = Field(None, description="状态原因")
    error_message: Optional[str] = Field(None, description="错误信息")
    capability: JsonDict = Field(default_factory=dict, description="动作能力契约快照")
    started_time: Optional[datetime] = Field(None, description="开始时间")
    finished_time: Optional[datetime] = Field(None, description="结束时间")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    class Config:
        from_attributes = True


class AgentWorkflowActionRetryRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500, description="重试原因")
    retry_source: str = Field("manual_api", min_length=1, max_length=80, description="重试来源")


class AgentWorkflowRetryRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500, description="工作流恢复原因")
    retry_source: str = Field("manual_api", min_length=1, max_length=80, description="重试来源")


class AgentWorkflowRecoveryScanRequest(BaseModel):
    limit: int = Field(20, ge=1, le=200, description="扫描动作数量")
    safe_action_types: List[str] = Field(default_factory=list, description="允许后台恢复的动作类型白名单")


class AgentWorkflowRecoveryActionPolicyResponse(BaseModel):
    action_id: str = Field(..., description="Agent动作ID")
    action_type: str = Field(..., description="动作类型")
    allowed: bool = Field(..., description="是否允许后台恢复")
    reason: str = Field(..., description="策略判断原因")
    execution_mode: str = Field(..., description="恢复执行模式")
    requires_user_authorization: bool = Field(..., description="是否需要用户授权")
    allows_background_recovery: bool = Field(False, description="动作契约是否允许后台恢复")
    parallel_safe: bool = Field(False, description="动作契约是否允许并行执行")
    requires_idempotency_key: bool = Field(False, description="动作契约是否要求幂等键")
    capability_flags: List[str] = Field(default_factory=list, description="动作能力标记")


class AgentWorkflowRecoveryDecisionResponse(BaseModel):
    workflow_id: str = Field(..., description="Agent工作流ID")
    eligible: bool = Field(..., description="是否具备后台恢复条件")
    reason: str = Field(..., description="工作流级判断原因")
    action_count: int = Field(..., description="工作流动作总数")
    retryable_action_count: int = Field(..., description="可重试动作数量")
    safe_action_count: int = Field(..., description="策略允许恢复动作数量")
    policy_reasons: JsonDict = Field(default_factory=dict, description="动作策略拒绝原因聚合")
    retryable_action_policies: List[AgentWorkflowRecoveryActionPolicyResponse] = Field(
        default_factory=list,
        description="可重试动作的逐项策略判断",
    )


class AgentWorkflowRecoveryScanResponse(BaseModel):
    scanned_actions: int = Field(..., description="扫描到的失败/阻塞动作数量")
    scanned_workflows: int = Field(..., description="扫描到的工作流数量")
    eligible_workflows: int = Field(..., description="具备后台恢复条件的工作流数量")
    retried_workflows: int = Field(..., description="实际触发恢复的工作流数量")
    retried_actions: int = Field(..., description="实际触发恢复的动作数量")
    dry_run: bool = Field(..., description="是否仅诊断不执行")
    skipped: JsonDict = Field(default_factory=dict, description="工作流级跳过原因聚合")
    policy_reasons: JsonDict = Field(default_factory=dict, description="动作策略拒绝原因聚合")
    failed: int = Field(..., description="恢复过程中失败的工作流数量")
    decisions: List[AgentWorkflowRecoveryDecisionResponse] = Field(
        default_factory=list,
        description="工作流级恢复决策明细",
    )


class AgentSessionDetailResponse(AgentSessionResponse):
    messages: List[AgentMessageResponse] = Field(default_factory=list, description="会话消息")
    tasks: List[AgentTaskResponse] = Field(default_factory=list, description="会话任务")


class AgentChatRequest(BaseModel):
    content: str = Field(..., min_length=1, description="用户消息内容")
    session_id: Optional[int] = Field(None, description="Agent会话ID")
    session_key: Optional[str] = Field(None, max_length=64, description="Agent会话唯一标识")
    interaction_metadata: Optional[JsonDict] = Field(None, description="前端结构化交互提交上下文")


class AgentRuntimeCheckpointStateResponse(BaseModel):
    session_id: int = Field(..., description="Agent会话ID")
    session_key: str = Field(..., description="Agent会话唯一标识")
    checkpoint_id: Optional[str] = Field(None, description="LangGraph checkpoint ID")
    values: JsonDict = Field(default_factory=dict, description="LangGraph root checkpoint状态投影")


class AgentRuntimeActionSummaryResponse(BaseModel):
    total: int = Field(..., description="动作总数")
    by_status: JsonDict = Field(default_factory=dict, description="按动作状态聚合的数量")
    waiting_action_count: int = Field(0, description="等待用户决策的动作数量")
    failed_action_count: int = Field(0, description="失败动作数量")
    blocked_action_count: int = Field(0, description="阻塞动作数量")


class AgentRuntimeOverviewResponse(BaseModel):
    session_id: int = Field(..., description="Agent会话ID")
    session_key: str = Field(..., description="Agent会话唯一标识")
    runtime_status: Optional[str] = Field(None, description="LangGraph运行状态")
    checkpoint_id: Optional[str] = Field(None, description="LangGraph checkpoint ID")
    has_interrupt: bool = Field(False, description="当前是否存在待恢复interrupt")
    current_interrupt: Optional[JsonDict] = Field(None, description="当前interrupt投影")
    action_summary: AgentRuntimeActionSummaryResponse = Field(..., description="动作账本聚合")
    recent_actions: List[AgentWorkflowActionResponse] = Field(default_factory=list, description="最近动作")
    values: JsonDict = Field(default_factory=dict, description="LangGraph root checkpoint状态投影")


class AgentWorkflowGraphEdgeResponse(BaseModel):
    from_action_id: str = Field(..., description="上游动作ID")
    to_action_id: str = Field(..., description="下游动作ID")
    relation: str = Field(..., description="依赖关系类型")


class AgentWorkflowGraphNodeResponse(BaseModel):
    action_id: str = Field(..., description="Agent动作ID")
    action_type: str = Field(..., description="动作类型")
    status: str = Field(..., description="动作状态")
    status_reason: Optional[str] = Field(None, description="动作状态原因")
    error_message: Optional[str] = Field(None, description="动作错误信息")
    scope: str = Field(..., description="动作范围")
    blocking: bool = Field(..., description="是否阻塞工作流")
    parent_action_id: Optional[str] = Field(None, description="父动作ID")
    depends_on: List[str] = Field(default_factory=list, description="上游依赖动作ID")
    parallel_group: Optional[str] = Field(None, description="并行分组")


class AgentWorkflowDetailResponse(BaseModel):
    workflow_id: str = Field(..., description="Agent工作流ID")
    workflow_status: str = Field(..., description="工作流聚合状态")
    status_reason: Optional[str] = Field(None, description="工作流状态原因")
    action_summary: AgentRuntimeActionSummaryResponse = Field(..., description="动作状态聚合")
    nodes: List[AgentWorkflowGraphNodeResponse] = Field(default_factory=list, description="动作图节点")
    edges: List[AgentWorkflowGraphEdgeResponse] = Field(default_factory=list, description="动作图依赖边")
    actions: List[AgentWorkflowActionResponse] = Field(default_factory=list, description="动作明细")


class AgentRuntimeHistoryItemResponse(BaseModel):
    checkpoint_id: Optional[str] = Field(None, description="LangGraph checkpoint ID")
    parent_checkpoint_id: Optional[str] = Field(None, description="父checkpoint ID")
    thread_id: Optional[str] = Field(None, description="LangGraph thread ID")
    checkpoint_ns: Optional[str] = Field(None, description="LangGraph checkpoint命名空间")
    created_at: Optional[str] = Field(None, description="checkpoint创建时间")
    source: Optional[str] = Field(None, description="LangGraph checkpoint来源")
    step: Optional[int] = Field(None, description="LangGraph执行步序号")
    next_nodes: List[str] = Field(default_factory=list, description="下一批待执行节点")
    has_interrupt: bool = Field(False, description="该checkpoint是否存在待恢复interrupt")
    interrupts: List[JsonDict] = Field(default_factory=list, description="interrupt payload投影")
    values: JsonDict = Field(default_factory=dict, description="checkpoint状态投影")


class AgentRuntimeHistoryResponse(BaseModel):
    session_id: int = Field(..., description="Agent会话ID")
    session_key: str = Field(..., description="Agent会话唯一标识")
    items: List[AgentRuntimeHistoryItemResponse] = Field(default_factory=list, description="LangGraph checkpoint历史")
    total: int = Field(..., description="返回数量")
    before_checkpoint_id: Optional[str] = Field(None, description="本次查询的checkpoint游标")
    limit: int = Field(..., description="本次查询限制")
