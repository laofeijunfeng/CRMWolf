"""
实体歧义消解规则配置

定义哪些场景需要歧义检测，以及检测逻辑
"""
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy.orm import Session


# 歧义检测规则定义
# 格式：tool_name -> 检测规则
DISAMBIGUATION_RULES: Dict[str, Dict[str, Any]] = {
    # 商机相关操作 - 当客户有多个跟进中商机时需要消解
    "win_opportunity": {
        "trigger_field": "opportunity_name",  # 触发歧义检测的字段
        "entity_type": "opportunity",          # 实体类型
        "search_context_field": "customer_name", # 用于限定搜索范围的字段（可选）
        "search_by_customer": True,            # 是否在客户范围内搜索
        "filter_status": ["跟进中"],           # 只搜索这些状态的实体
        "display_fields": ["opportunity_name", "total_amount"],  # 候选列表展示字段
        "message_template": "该客户有多个跟进中商机，请选择要标记赢单的商机"
    },
    "create_contract": {
        "trigger_field": "opportunity_name",
        "entity_type": "opportunity",
        "search_context_field": "customer_name",
        "search_by_customer": True,
        "filter_status": ["跟进中"],
        "display_fields": ["opportunity_name", "total_amount"],
        "message_template": "该客户有多个跟进中商机，请选择要创建合同的商机"
    },
    "create_payment_plan": {
        "trigger_field": "contract_name",
        "entity_type": "contract",
        "filter_status": ["生效中"],
        "display_fields": ["contract_name", "total_amount"],
        "message_template": "存在多个生效合同，请选择要创建回款计划的合同"
    },
    "create_payment_record": {
        "trigger_field": "stage_name",
        "entity_type": "payment_plan",
        "search_context_field": "contract_name",
        "search_by_contract": True,
        "filter_status": ["待回款", "部分回款"],
        "display_fields": ["stage_name", "planned_amount"],
        "message_template": "该合同有多个待回款阶段，请选择要登记回款的阶段"
    },
    "create_invoice_application": {
        "trigger_field": "stage_name",
        "entity_type": "payment_plan",
        "search_context_field": "contract_name",
        "search_by_contract": True,
        "filter_status": ["待回款", "部分回款", "已完成"],
        "display_fields": ["stage_name", "planned_amount"],
        "message_template": "该合同有多个回款阶段，请选择要申请开票的阶段"
    },
}


def get_disambiguation_rule(tool_name: str) -> Optional[Dict[str, Any]]:
    """获取工具的歧义检测规则"""
    return DISAMBIGUATION_RULES.get(tool_name)


def get_entity_display_info(entity: Any, entity_type: str, display_fields: List[str]) -> str:
    """
    生成实体的展示信息

    Args:
        entity: 实体对象
        entity_type: 实体类型
        display_fields: 要展示的字段列表

    Returns:
        展示字符串
    """
    info_parts = []
    for field in display_fields:
        if hasattr(entity, field):
            value = getattr(entity, field)
            if value is not None:
                # 格式化金额字段
                if "amount" in field.lower():
                    info_parts.append(f"{float(value)}元")
                else:
                    info_parts.append(str(value))

    return " (" + ", ".join(info_parts) + ")" if info_parts else ""