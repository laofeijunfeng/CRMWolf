"""AI OpenAPI 业务规则配置

定义意图枚举、风险分级、业务规则等。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from enum import Enum
from typing import Dict, Any, List


# ==================== 风险分级 ====================

class RiskLevel(Enum):
    """风险等级

    - LOW: 低风险，置信度 ≥ 0.85 自动执行
    - MEDIUM: 中风险，置信度 ≥ 0.90 自动执行
    - HIGH: 高风险，强制人工确认
    - CRITICAL: 极高风险，禁止执行（仅生成草稿）
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


RISK_CONFIG: Dict[RiskLevel, Dict[str, Any]] = {
    RiskLevel.LOW: {
        "auto_threshold": 0.85,
        "force_confirm": False,
        "description": "低风险操作（创建跟进、设置提醒）",
    },
    RiskLevel.MEDIUM: {
        "auto_threshold": 0.90,
        "force_confirm": False,
        "description": "中风险操作（更新金额/阶段、关联实体）",
    },
    RiskLevel.HIGH: {
        "auto_threshold": 1.0,
        "force_confirm": True,
        "description": "高风险操作（赢单/输单、线索转化）",
    },
    RiskLevel.CRITICAL: {
        "auto_threshold": 1.0,
        "force_confirm": True,
        "dry_run_only": True,
        "description": "极高风险（审批流、财务操作），禁止执行",
    },
}


def requires_confirmation(risk_level: RiskLevel, confidence: float) -> bool:
    """判断是否需要人工确认

    Args:
        risk_level: 风险等级
        confidence: 置信度

    Returns:
        True: 需要确认; False: 可自动执行
    """
    config = RISK_CONFIG[risk_level]

    # CRITICAL 永远禁止执行
    if config.get("dry_run_only"):
        return True

    # 强制确认的永远需确认
    if config["force_confirm"]:
        return True

    # 置信度低于阈值需确认
    return confidence < config["auto_threshold"]


# ==================== 意图枚举 ====================

class IntentType(Enum):
    """意图类型枚举池

    固定枚举，禁止 LLM 输出非标意图。
    新增意图必须先更新此枚举。
    """

    CREATE_FOLLOW_UP = "create_follow_up"
    CREATE_OPPORTUNITY = "create_opportunity"
    UPDATE_OPPORTUNITY = "update_opportunity"
    ADVANCE_STAGE = "advance_stage"
    WIN_OPPORTUNITY = "win_opportunity"
    LOSE_OPPORTUNITY = "lose_opportunity"
    CONVERT_LEAD = "convert_lead"
    SET_REMINDER = "set_reminder"
    QUERY_INFO = "query_info"
    UNKNOWN = "unknown"


INTENT_DESCRIPTIONS: Dict[IntentType, str] = {
    IntentType.CREATE_FOLLOW_UP: "创建跟进记录",
    IntentType.CREATE_OPPORTUNITY: "创建商机",
    IntentType.UPDATE_OPPORTUNITY: "更新商机信息",
    IntentType.ADVANCE_STAGE: "推进商机阶段",
    IntentType.WIN_OPPORTUNITY: "标记商机赢单",
    IntentType.LOSE_OPPORTUNITY: "标记商机输单",
    IntentType.CONVERT_LEAD: "转化线索为客户",
    IntentType.SET_REMINDER: "设置跟进提醒",
    IntentType.QUERY_INFO: "查询信息",
    IntentType.UNKNOWN: "未知意图",
}


# ==================== Action 风险映射 ====================

ACTION_RISK_MAPPING: Dict[str, RiskLevel] = {
    "create_follow_up": RiskLevel.LOW,
    "set_reminder": RiskLevel.LOW,
    "init_opportunity": RiskLevel.MEDIUM,
    "update_amount": RiskLevel.MEDIUM,
    "update_stage": RiskLevel.MEDIUM,
    "link_opportunity": RiskLevel.MEDIUM,
    "win_opportunity": RiskLevel.HIGH,
    "lose_opportunity": RiskLevel.HIGH,
    "convert_lead": RiskLevel.HIGH,
    "approve_contract": RiskLevel.CRITICAL,
    "approve_invoice": RiskLevel.CRITICAL,
    "payment_register": RiskLevel.CRITICAL,
}


def get_action_risk(action_type: str) -> RiskLevel:
    """获取 Action 的风险等级"""
    return ACTION_RISK_MAPPING.get(action_type, RiskLevel.MEDIUM)


# ==================== 业务规则 ====================

BUSINESS_RULES: List[Dict[str, Any]] = [
    {
        "trigger": "keyword",
        "keyword": "签合同",
        "action": "update_stage",
        "target": "合同谈判",
        "description": "用户提到签合同时，商机阶段自动推进到合同谈判",
    },
    {
        "trigger": "keyword",
        "keyword": "赢单",
        "action": "win_opportunity",
        "description": "用户提到赢单时，标记商机为赢单状态",
    },
    {
        "trigger": "keyword",
        "keyword": "输单",
        "action": "lose_opportunity",
        "description": "用户提到输单时，标记商机为输单状态",
    },
    {
        "trigger": "stage_change",
        "from_stage": "需求确认",
        "to_stage": "方案报价",
        "win_rate_change": 0.2,
        "description": "阶段从需求确认推进到方案报价，赢率自动从 20% 变为 40%",
    },
]


# ==================== 错误码常量 ====================

class AIErrorCode(Enum):
    """AI OpenAPI 错误码

    用于标准化错误响应，便于前端和 AI Agent 处理。
    """

    MISSING_FIELD = "AI_MISSING_FIELD"           # 缺失必填字段
    ENTITY_NOT_FOUND = "AI_ENTITY_NOT_FOUND"     # 实体不存在
    PERMISSION_DENIED = "AI_PERMISSION_DENIED"   # 无权限操作
    DUPLICATE_ACTION = "AI_DUPLICATE_ACTION"     # 重复 action_id
    RISK_REJECTED = "AI_RISK_REJECTED"           # 高风险被拒绝
    INVALID_PARAM = "AI_INVALID_PARAM"           # 参数格式无效
    EXECUTION_FAILED = "AI_EXECUTION_FAILED"     # 执行失败
    LOCKED = "AI_LOCKED"                         # action_id 被锁定


ERROR_CODE_MESSAGES: Dict[AIErrorCode, str] = {
    AIErrorCode.MISSING_FIELD: "缺少必填字段",
    AIErrorCode.ENTITY_NOT_FOUND: "实体不存在",
    AIErrorCode.PERMISSION_DENIED: "无权限执行此操作",
    AIErrorCode.DUPLICATE_ACTION: "操作已执行，请勿重复提交",
    AIErrorCode.RISK_REJECTED: "高风险操作被拒绝，需人工确认",
    AIErrorCode.INVALID_PARAM: "参数格式无效",
    AIErrorCode.EXECUTION_FAILED: "执行失败",
    AIErrorCode.LOCKED: "action_id 已被锁定，请稍后重试",
}


# ==================== 导出 ====================

__all__ = [
    "RiskLevel",
    "RISK_CONFIG",
    "requires_confirmation",
    "IntentType",
    "INTENT_DESCRIPTIONS",
    "ACTION_RISK_MAPPING",
    "get_action_risk",
    "BUSINESS_RULES",
    "AIErrorCode",
    "ERROR_CODE_MESSAGES",
]