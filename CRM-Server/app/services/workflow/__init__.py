"""
Workflow 模块

业务流程定义层（代码硬编码，AI 无法干预）

保留组件：
- WorkflowDefinitions: 流程定义（LangGraph nodes/workflow.py 使用）
- Guardrails: 置信度拦截（LangGraph nodes/workflow.py 使用）
- BusinessInvariants: 业务不变式
- StateMachine: 状态机校验
- TraceContext: 全链路追踪
- EntityRenderer: 实体渲染
- UndoService: 撤销机制

已删除组件：
- WorkflowOrchestrator: 已迁移到 LangGraph nodes/workflow.py
- session_store: 已迁移到 LangGraph checkpointer.py
"""

from app.services.workflow.workflow_definitions import WorkflowDefinitions
from app.services.workflow.state_machine import CRMStateMachine
from app.services.workflow.business_invariants import BusinessInvariants
from app.services.workflow.guardrails import (
    DecisionType,
    ExceptionType,
    GuardrailDecision,
    ExceptionStrategy,
    ConfidenceGuardrail,
    ExceptionHandler,
    GuardrailsService,
    guardrails_service,
)
from app.services.workflow.trace_context import (
    TraceContext,
    TraceLogger,
    Span,
    AIDecision,
    generate_trace_id,
    generate_span_id,
    start_trace,
    end_trace,
    get_current_trace_context,
    trace_logger,
)
from app.services.workflow.agent_executor_pool import (
    AgentExecutorPool,
    AgentRateLimiter,
    get_agent_pool,
    shutdown_agent_pool,
)

# Phase F: 撤销机制 + EntityRenderer
from app.services.workflow.undo_service import undo_service, UndoService
from app.services.workflow.undo_handlers import (
    UndoHandler,
    UndoResult,
    UndoImpact,
)
from app.services.workflow.entity_renderer import entity_renderer, EntityRenderer

# 全局实例（保留）
workflow_definitions = WorkflowDefinitions()
state_machine = CRMStateMachine()
business_invariants = BusinessInvariants()

__all__ = [
    # 保留组件
    "WorkflowDefinitions",
    "CRMStateMachine",
    "BusinessInvariants",
    "workflow_definitions",
    "state_machine",
    "business_invariants",
    # Phase C: Guardrails
    "DecisionType",
    "ExceptionType",
    "GuardrailDecision",
    "ExceptionStrategy",
    "ConfidenceGuardrail",
    "ExceptionHandler",
    "GuardrailsService",
    "guardrails_service",
    # Phase D: TraceContext
    "TraceContext",
    "TraceLogger",
    "Span",
    "AIDecision",
    "generate_trace_id",
    "generate_span_id",
    "start_trace",
    "end_trace",
    "get_current_trace_context",
    "trace_logger",
    # Phase E: AgentExecutorPool
    "AgentExecutorPool",
    "AgentRateLimiter",
    "get_agent_pool",
    "shutdown_agent_pool",
    # Phase F: Undo + EntityRenderer
    "UndoService",
    "undo_service",
    "UndoHandler",
    "UndoResult",
    "UndoImpact",
    "EntityRenderer",
    "entity_renderer",
]