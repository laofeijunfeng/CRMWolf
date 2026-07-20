"""
TraceContext - 全链路追踪

实现 TraceId 生成、Span 管理、AI Decision 记录。

设计原则：
- 全链路 TraceId：串联 Nginx -> App -> AI Service -> Workflow Engine -> Database
- Decision Audit：记录 AI 为什么建议改数据（Thought + Evidence）
"""

import time
import random
import string
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from contextvars import ContextVar


def generate_trace_id(user_id: int = 0) -> str:
    """生成 TraceId

    格式: trace_{timestamp}_{user_id}_{random}

    Args:
        user_id: 用户 ID

    Returns:
        TraceId 字符串
    """
    timestamp = int(time.time())
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"trace_{timestamp}_{user_id}_{random_str}"


def generate_span_id() -> str:
    """生成 SpanId

    格式: span_{random}

    Returns:
        SpanId 字符串
    """
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"span_{random_str}"


@dataclass
class Span:
    """Span 数据结构"""

    trace_id: str
    span_id: str
    operation: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    parent_span_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    status: str = "running"  # running | success | error
    error: Optional[str] = None

    # AI Decision 记录（用于 Audit）
    ai_decision: Optional[Dict[str, Any]] = None


@dataclass
class AIDecision:
    """AI 决策记录

    用于 Decision Audit，记录 AI 的 Reasoning Process。
    """

    thought: str           # AI 思考过程
    evidence: str          # 证据/依据
    confidence: float      # 置信度
    action_type: str       # 操作类型
    params: Dict[str, Any] = field(default_factory=dict)  # 参数
    reasoning_trace: List[str] = field(default_factory=list)  # 推理步骤


class TraceContext:
    """全链路追踪上下文

    Features:
    - TraceId 生成和传递
    - Span 管理（开始/结束）
    - AI Decision 记录
    - 序列化输出（用于日志/审计）
    """

    def __init__(self, trace_id: Optional[str] = None, user_id: int = 0):
        self.trace_id = trace_id or generate_trace_id(user_id)
        self.spans: List[Span] = []
        self.current_span: Optional[Span] = None
        self.start_time = time.time()

    def start_span(
        self,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_span_id: Optional[str] = None
    ) -> Span:
        """开始 Span

        Args:
            operation: 操作名称（如 "ai_intent_recognition", "workflow_execute", "tool_call"）
            metadata: 元数据
            parent_span_id: 父 Span ID

        Returns:
            Span 对象
        """
        span = Span(
            trace_id=self.trace_id,
            span_id=generate_span_id(),
            operation=operation,
            start_time=time.time(),
            parent_span_id=parent_span_id or (self.current_span.span_id if self.current_span else None),
            metadata=metadata or {}
        )

        self.spans.append(span)
        self.current_span = span

        return span

    def end_span(
        self,
        span: Span,
        result: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error: Optional[str] = None
    ) -> Span:
        """结束 Span

        Args:
            span: Span 对象
            result: 执行结果
            status: 状态 (success | error)
            error: 错误信息

        Returns:
            更新后的 Span
        """
        span.end_time = time.time()
        span.duration_ms = (span.end_time - span.start_time) * 1000
        span.result = result
        span.status = status
        span.error = error

        # 更新 current_span 为父级
        if span == self.current_span:
            self.current_span = next(
                (s for s in reversed(self.spans) if s.span_id == span.parent_span_id),
                None
            )

        return span

    def record_ai_decision(
        self,
        span: Span,
        thought: str,
        evidence: str,
        confidence: float,
        action_type: str,
        params: Optional[Dict[str, Any]] = None,
        reasoning_trace: Optional[List[str]] = None
    ) -> None:
        """记录 AI 决策过程

        Args:
            span: Span 对象
            thought: AI 思考过程
            evidence: 证据/依据
            confidence: 置信度
            action_type: 操作类型
            params: 参数
            reasoning_trace: 推理步骤
        """
        span.ai_decision = {
            "thought": thought,
            "evidence": evidence,
            "confidence": confidence,
            "action_type": action_type,
            "params": params or {},
            "reasoning_trace": reasoning_trace or [],
            "timestamp": datetime.now().isoformat()
        }

    def get_total_duration_ms(self) -> float:
        """获取总耗时"""
        return (time.time() - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "trace_id": self.trace_id,
            "start_time": self.start_time,
            "total_duration_ms": self.get_total_duration_ms(),
            "spans": [asdict(s) for s in self.spans],
            "span_count": len(self.spans),
        }

    def to_json(self) -> str:
        """序列化为 JSON"""
        return json.dumps(self.to_dict(), indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """获取摘要（用于快速查看）"""
        return {
            "trace_id": self.trace_id,
            "total_duration_ms": round(self.get_total_duration_ms(), 2),
            "span_count": len(self.spans),
            "operations": [s.operation for s in self.spans],
            "has_ai_decisions": any(s.ai_decision for s in self.spans),
            "errors": [s.error for s in self.spans if s.error],
        }


# ContextVar 用于跨异步调用传递 TraceContext
_current_trace_context: ContextVar[Optional[TraceContext]] = ContextVar("trace_context", default=None)


def get_current_trace_context() -> Optional[TraceContext]:
    """获取当前 TraceContext"""
    return _current_trace_context.get()


def set_current_trace_context(ctx: TraceContext) -> None:
    """设置当前 TraceContext"""
    _current_trace_context.set(ctx)


def start_trace(user_id: int = 0, trace_id: Optional[str] = None) -> TraceContext:
    """开始新的 Trace

    Args:
        user_id: 用户 ID
        trace_id: 已有 TraceId（可选）

    Returns:
        TraceContext
    """
    ctx = TraceContext(trace_id=trace_id, user_id=user_id)
    set_current_trace_context(ctx)
    return ctx


def end_trace() -> Optional[Dict[str, Any]]:
    """结束当前 Trace

    Returns:
        Trace 数据字典
    """
    ctx = get_current_trace_context()
    if ctx:
        data = ctx.to_dict()
        _current_trace_context.set(None)
        return data
    return None


class TraceLogger:
    """Trace 日志器

    将 Trace 数据写入日志或存储。
    """

    def __init__(self):
        self.traces: List[Dict[str, Any]] = []

    def log_trace(self, ctx: TraceContext) -> None:
        """记录 Trace"""
        data = ctx.to_dict()
        self.traces.append(data)

        # 打印摘要日志
        summary = ctx.get_summary()
        print(f"[TRACE] {summary['trace_id']} | "
              f"duration={summary['total_duration_ms']}ms | "
              f"spans={summary['span_count']} | "
              f"ops={summary['operations']}")

    def log_ai_decision_audit(self, ctx: TraceContext) -> None:
        """记录 AI Decision Audit"""
        for span in ctx.spans:
            if span.ai_decision:
                decision = span.ai_decision
                print(f"[AUDIT] trace={ctx.trace_id} span={span.span_id} | "
                      f"action={decision['action_type']} | "
                      f"confidence={decision['confidence']} | "
                      f"thought={decision['thought'][:50]}...")

    def get_traces(self) -> List[Dict[str, Any]]:
        """获取所有 Trace"""
        return self.traces


# 全局 Trace Logger
trace_logger = TraceLogger()


__all__ = [
    "generate_trace_id",
    "generate_span_id",
    "Span",
    "AIDecision",
    "TraceContext",
    "TraceLogger",
    "trace_logger",
    "get_current_trace_context",
    "set_current_trace_context",
    "start_trace",
    "end_trace",
]
