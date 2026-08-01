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
