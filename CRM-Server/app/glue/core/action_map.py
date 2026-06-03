"""显式意图到动作映射表

原则4：显式映射 > 隐式分发

所有 glue 层触发的写操作必须通过此映射表显式定义，
确保可审查、可 grep、可追溯。

参见: CRM-Docs/requirements/AI-GLUE-ROUTING-ALIGNMENT-RFC.md R-5
参见: CRM-Docs/plans/AI-GLUE-ROUTING-ALIGNMENT-PLAN.md Task 1.1
"""

from typing import Dict, Tuple, Optional


# 意图到 /ai/actions/ 端点的显式映射
# Key: (intent_type, action_variant)
# Value: /ai/actions/ endpoint path
INTENT_TO_ACTION_MAP: Dict[Tuple[str, str], str] = {
    # ==================== 创建类 ====================
    ("create_follow_up", "default"): "/ai/actions/create-follow-up",
    ("set_reminder", "default"): "/ai/actions/set-reminder",
    ("init_opportunity", "default"): "/ai/actions/init-opportunity",

    # ==================== 更新类 ====================
    ("update_amount", "default"): "/ai/actions/update-amount",
    ("update_stage", "next"): "/ai/actions/update-stage",
    ("update_stage", "prev"): "/ai/actions/update-stage",
    ("update_stage", "default"): "/ai/actions/update-stage",
    ("update_opportunity", "default"): "/ai/actions/update-stage",  # 兼容旧意图

    # ==================== 结单类 ====================
    ("win_opportunity", "default"): "/ai/actions/win-opportunity",
    ("lose_opportunity", "default"): "/ai/actions/lose-opportunity",

    # ==================== 线索转化 ====================
    ("convert_lead", "default"): "/ai/actions/init-opportunity",  # 转化线索 → 初始化商机
}


def get_action_endpoint(intent_type: str, action_variant: str = "default") -> Optional[str]:
    """获取动作端点路径

    Args:
        intent_type: 意图类型（create_follow_up, update_amount, ...）
        action_variant: 动作变体（default, next, prev, ...）

    Returns:
        /ai/actions/ 端点路径，如果未映射则返回 None
    """
    key = (intent_type, action_variant)
    return INTENT_TO_ACTION_MAP.get(key)


def get_intent_from_endpoint(endpoint: str) -> Optional[Tuple[str, str]]:
    """反向查询：从端点路径获取意图

    Args:
        endpoint: /ai/actions/ 端点路径

    Returns:
        (intent_type, action_variant) 元组，如果未找到则返回 None
    """
    for key, value in INTENT_TO_ACTION_MAP.items():
        if value == endpoint:
            return key
    return None


def list_all_mappings() -> Dict[Tuple[str, str], str]:
    """列出所有映射（用于调试和审查）

    Returns:
        完整的映射表
    """
    return INTENT_TO_ACTION_MAP.copy()


def validate_mapping_coverage(intent_types: list) -> Dict[str, bool]:
    """验证意图类型的映射覆盖情况

    Args:
        intent_types: 需要验证的意图类型列表

    Returns:
        {intent_type: is_mapped} 字典
    """
    coverage = {}
    for intent_type in intent_types:
        # 检查是否有任何变体被映射
        is_mapped = any(
            key[0] == intent_type
            for key in INTENT_TO_ACTION_MAP.keys()
        )
        coverage[intent_type] = is_mapped

    return coverage


__all__ = [
    "INTENT_TO_ACTION_MAP",
    "get_action_endpoint",
    "get_intent_from_endpoint",
    "list_all_mappings",
    "validate_mapping_coverage",
]