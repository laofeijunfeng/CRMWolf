"""
Guardrails - 护栏系统

置信度拦截 + 异常分层处理，确保 AI 操作安全可控。

用于 AI 操作执行前的风险判断和人工确认分层。
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class DecisionType(Enum):
    """护栏决策类型"""
    AUTO = "auto"                    # 自动执行
    WEAK_CONFIRM = "weak_confirm"    # 弱确认（Toast 提示）
    STRONG_CONFIRM = "strong_confirm"  # 强确认（Modal）
    HUMAN_LOOP = "human_loop"        # 人工介入
    BLOCK = "block"                  # 直接拦截


class ExceptionType(Enum):
    """异常类型"""
    # AI 侧异常
    HALLUCINATION = "hallucination"
    LOW_CONFIDENCE = "low_confidence"
    INVALID_OUTPUT = "invalid_output"

    # 系统侧异常
    DB_TIMEOUT = "db_timeout"
    LOCK_CONFLICT = "lock_conflict"
    REDIS_ERROR = "redis_error"

    # 业务侧异常
    INARIANT_VIOLATION = "invariant_violation"
    PERMISSION_DENIED = "permission_denied"
    ENTITY_NOT_FOUND = "entity_not_found"


@dataclass
class GuardrailDecision:
    """护栏决策结果"""
    decision: DecisionType
    reason: str
    confidence: float
    action_type: str
    requires_audit: bool = False
    max_retries: int = 0
    fallback_strategy: Optional[str] = None


@dataclass
class ExceptionStrategy:
    """异常处理策略"""
    action: str           # "retry" | "fallback" | "human_loop" | "block"
    max_retries: int = 3
    backoff: str = "exponential"
    fallback_strategy: Optional[str] = None
    requires_audit: bool = False


class ConfidenceGuardrail:
    """置信度护栏

    根据置信度和操作类型决定执行策略：
    - >= 0.95: 自动执行
    - >= 0.80: 弱确认（Toast）
    - >= 0.70: 强确认（Modal），高风险操作必须强确认
    - >= 0.50: 人工介入
    - <  0.50: 直接拦截

    设计原则（来自 Control Plane Requirements）：
    - Fail-Safe 默认：未知情况默认暂停等待人工
    - 防御性执行：高风险操作必须强确认
    """

    # 置信度阈值
    CONFIDENCE_THRESHOLDS = {
        "auto_execute": 0.95,
        "weak_confirm": 0.80,
        "strong_confirm": 0.70,
        "human_loop": 0.50,
        "block": 0.30
    }

    # 高风险操作（必须强确认）
    HIGH_RISK_ACTIONS = [
        "create_contract",
        "win_opportunity",
        "delete_customer",
        "delete_opportunity",
        "update_amount",
        "transfer_owner",
    ]

    # 只读操作（可放宽阈值）
    READ_ONLY_ACTIONS = [
        "get_customer",
        "get_opportunity",
        "search_customers",
        "search_opportunities",
        "get_context",
    ]

    def check(
        self,
        confidence: float,
        action_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> GuardrailDecision:
        """检查置信度

        Args:
            confidence: AI 置信度（0.0 - 1.0）
            action_type: 操作类型
            context: 操作上下文（可选）

        Returns:
            GuardrailDecision 决策结果
        """
        # 只读操作放宽阈值
        if action_type in self.READ_ONLY_ACTIONS:
            return self._check_read_only(confidence, action_type)

        # 高风险操作强制强确认
        if action_type in self.HIGH_RISK_ACTIONS:
            return self._check_high_risk(confidence, action_type)

        # 普通操作标准检查
        return self._check_standard(confidence, action_type)

    def _check_read_only(
        self,
        confidence: float,
        action_type: str
    ) -> GuardrailDecision:
        """只读操作检查（放宽阈值）"""
        if confidence >= 0.70:
            return GuardrailDecision(
                decision=DecisionType.AUTO,
                reason="只读操作，置信度足够",
                confidence=confidence,
                action_type=action_type
            )

        if confidence >= 0.50:
            return GuardrailDecision(
                decision=DecisionType.WEAK_CONFIRM,
                reason="只读操作，中等置信度，弱确认",
                confidence=confidence,
                action_type=action_type
            )

        return GuardrailDecision(
            decision=DecisionType.HUMAN_LOOP,
            reason="只读操作，置信度较低，需人工介入",
            confidence=confidence,
            action_type=action_type,
            requires_audit=True
        )

    def _check_high_risk(
        self,
        confidence: float,
        action_type: str
    ) -> GuardrailDecision:
        """高风险操作检查（强制强确认）"""
        # 高风险操作即使置信度高也需强确认
        if confidence >= 0.95:
            return GuardrailDecision(
                decision=DecisionType.STRONG_CONFIRM,
                reason="高风险操作，必须强确认",
                confidence=confidence,
                action_type=action_type,
                requires_audit=True
            )

        if confidence >= 0.70:
            return GuardrailDecision(
                decision=DecisionType.STRONG_CONFIRM,
                reason="高风险操作，置信度中等，强确认",
                confidence=confidence,
                action_type=action_type,
                requires_audit=True
            )

        if confidence >= 0.50:
            return GuardrailDecision(
                decision=DecisionType.HUMAN_LOOP,
                reason="高风险操作，置信度较低，需人工介入",
                confidence=confidence,
                action_type=action_type,
                requires_audit=True
            )

        return GuardrailDecision(
            decision=DecisionType.BLOCK,
            reason="高风险操作，置信度过低，直接拦截",
            confidence=confidence,
            action_type=action_type,
            requires_audit=True
        )

    def _check_standard(
        self,
        confidence: float,
        action_type: str
    ) -> GuardrailDecision:
        """普通操作检查"""
        if confidence >= self.CONFIDENCE_THRESHOLDS["auto_execute"]:
            return GuardrailDecision(
                decision=DecisionType.AUTO,
                reason="置信度高，自动执行",
                confidence=confidence,
                action_type=action_type
            )

        if confidence >= self.CONFIDENCE_THRESHOLDS["weak_confirm"]:
            return GuardrailDecision(
                decision=DecisionType.WEAK_CONFIRM,
                reason="置信度中等，弱确认",
                confidence=confidence,
                action_type=action_type
            )

        if confidence >= self.CONFIDENCE_THRESHOLDS["strong_confirm"]:
            return GuardrailDecision(
                decision=DecisionType.STRONG_CONFIRM,
                reason="置信度中等偏低，强确认",
                confidence=confidence,
                action_type=action_type,
                requires_audit=True
            )

        if confidence >= self.CONFIDENCE_THRESHOLDS["human_loop"]:
            return GuardrailDecision(
                decision=DecisionType.HUMAN_LOOP,
                reason="置信度较低，需人工介入",
                confidence=confidence,
                action_type=action_type,
                requires_audit=True
            )

        return GuardrailDecision(
            decision=DecisionType.BLOCK,
            reason="置信度过低，直接拦截",
            confidence=confidence,
            action_type=action_type,
            requires_audit=True
        )


class ExceptionHandler:
    """异常分层处理

    设计原则：
    - AI 侧异常：不信任，需人工介入
    - 系统侧异常：可重试或降级
    - 业务侧异常：严格拦截 + 审计
    """

    # 异常处理策略映射
    EXCEPTION_STRATEGIES: Dict[ExceptionType, str] = {
        # AI 侧异常 - 不信任
        ExceptionType.HALLUCINATION: "human_loop",
        ExceptionType.LOW_CONFIDENCE: "human_loop",
        ExceptionType.INVALID_OUTPUT: "retry",

        # 系统侧异常 - 可恢复
        ExceptionType.DB_TIMEOUT: "retry",
        ExceptionType.LOCK_CONFLICT: "retry",
        ExceptionType.REDIS_ERROR: "fallback",

        # 业务侧异常 - 严格拦截
        ExceptionType.INARIANT_VIOLATION: "block",
        ExceptionType.PERMISSION_DENIED: "block",
        ExceptionType.ENTITY_NOT_FOUND: "human_loop",
    }

    def handle(
        self,
        exception_type: ExceptionType,
        context: Optional[Dict[str, Any]] = None
    ) -> ExceptionStrategy:
        """处理异常

        Args:
            exception_type: 异常类型
            context: 异常上下文

        Returns:
            ExceptionStrategy 处理策略
        """
        strategy = self.EXCEPTION_STRATEGIES.get(
            exception_type,
            "block"  # 默认拦截（Fail-Safe）
        )

        if strategy == "retry":
            return ExceptionStrategy(
                action="retry",
                max_retries=3,
                backoff="exponential",
                requires_audit=True
            )

        if strategy == "fallback":
            return ExceptionStrategy(
                action="fallback",
                fallback_strategy="in_memory_session",
                requires_audit=True
            )

        if strategy == "human_loop":
            return ExceptionStrategy(
                action="human_loop",
                requires_audit=True
            )

        return ExceptionStrategy(
            action="block",
            requires_audit=True
        )

    def classify_exception(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> ExceptionType:
        """根据异常信息分类

        Args:
            error: 异常对象
            context: 异常上下文

        Returns:
            ExceptionType 分类结果
        """
        error_msg = str(error).lower()
        error_type = type(error).__name__

        # AI 侧异常识别
        if "hallucination" in error_msg or "幻觉" in error_msg:
            return ExceptionType.HALLUCINATION

        if "confidence" in error_msg or "置信度" in error_msg:
            return ExceptionType.LOW_CONFIDENCE

        if "invalid" in error_msg or "format" in error_msg or "parse" in error_msg:
            return ExceptionType.INVALID_OUTPUT

        # 系统侧异常识别
        if "timeout" in error_msg or error_type == "TimeoutError":
            return ExceptionType.DB_TIMEOUT

        if "lock" in error_msg or "conflict" in error_msg:
            return ExceptionType.LOCK_CONFLICT

        if "redis" in error_msg or "connection" in error_msg:
            return ExceptionType.REDIS_ERROR

        # 业务侧异常识别
        if "invariant" in error_msg or "constraint" in error_msg:
            return ExceptionType.INARIANT_VIOLATION

        if "permission" in error_msg or "forbidden" in error_msg:
            return ExceptionType.PERMISSION_DENIED

        if "not found" in error_msg or "不存在" in error_msg:
            return ExceptionType.ENTITY_NOT_FOUND

        # 默认返回人工介入（Fail-Safe）
        return ExceptionType.HALLUCINATION


class GuardrailsService:
    """Guardrails 综合服务

    整合置信度检查和异常处理。
    """

    def __init__(self):
        self.confidence_guardrail = ConfidenceGuardrail()
        self.exception_handler = ExceptionHandler()

    async def check_before_execute(
        self,
        confidence: float,
        action_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> GuardrailDecision:
        """执行前检查

        Args:
            confidence: AI 置信度
            action_type: 操作类型
            context: 操作上下文

        Returns:
            GuardrailDecision 决策结果
        """
        return self.confidence_guardrail.check(confidence, action_type, context)

    async def handle_exception(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[ExceptionStrategy, ExceptionType]:
        """处理异常

        Args:
            error: 异常对象
            context: 异常上下文

        Returns:
            (ExceptionStrategy, ExceptionType) 处理策略和分类
        """
        exception_type = self.exception_handler.classify_exception(error, context)
        strategy = self.exception_handler.handle(exception_type, context)
        return strategy, exception_type

    def is_allowed(self, decision: GuardrailDecision) -> bool:
        """检查是否允许执行

        Args:
            decision: 护栏决策

        Returns:
            是否允许执行（不包括强确认和人工介入）
        """
        return decision.decision in [
            DecisionType.AUTO,
            DecisionType.WEAK_CONFIRM
        ]

    def requires_confirmation(self, decision: GuardrailDecision) -> bool:
        """检查是否需要确认

        Args:
            decision: 护栏决策

        Returns:
            是否需要用户确认
        """
        return decision.decision in [
            DecisionType.WEAK_CONFIRM,
            DecisionType.STRONG_CONFIRM
        ]

    def requires_human_intervention(self, decision: GuardrailDecision) -> bool:
        """检查是否需要人工介入

        Args:
            decision: 护栏决策

        Returns:
            是否需要人工介入
        """
        return decision.decision == DecisionType.HUMAN_LOOP


# 全局单例
guardrails_service = GuardrailsService()


__all__ = [
    "DecisionType",
    "ExceptionType",
    "GuardrailDecision",
    "ExceptionStrategy",
    "ConfidenceGuardrail",
    "ExceptionHandler",
    "GuardrailsService",
    "guardrails_service",
]
