"""
Function Calling 工具定义

定义所有可供 AI 助手调用的工具，使用 OpenAI Function Calling 格式
"""
from typing import Dict, Any, List

# 工具定义（OpenAI Function Calling 格式）
TOOLS: List[Dict[str, Any]] = [
    # ==================== 线索管理 ====================
    {
        "type": "function",
        "function": {
            "name": "create_lead",
            "description": "创建新的销售线索",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（公司名或客户名）"
                    },
                    "contact_phone": {
                        "type": "string",
                        "description": "联系电话（11位手机号）"
                    },
                    "source": {
                        "type": "string",
                        "enum": ["其他", "展会", "客户推荐", "市场活动", "电话营销", "线上注册", "网站咨询"],
                        "description": "线索来源"
                    },
                    "city": {
                        "type": "string",
                        "description": "所在城市"
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "联系人姓名"
                    },
                    "company_scale": {
                        "type": "string",
                        "enum": ["1-50人", "51-200人", "201-500人", "501-1000人", "1000人以上"],
                        "description": "公司规模"
                    }
                },
                "required": ["lead_name", "contact_phone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_leads",
            "description": "查询销售线索列表，可按状态、负责人、关键词筛选",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["新建", "跟进中", "已转化", "无效"],
                        "description": "线索状态筛选"
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "负责人姓名（模糊匹配）"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（线索名称、联系人、电话）"
                    },
                    "source": {
                        "type": "string",
                        "description": "来源筛选"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制（默认10）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_lead_detail",
            "description": "获取指定线索的详细信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID，如果提供ID则优先使用ID）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_lead",
            "description": "将线索分配给指定负责人",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID）"
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "负责人姓名（必填）"
                    }
                },
                "required": ["owner_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "claim_lead",
            "description": "领取线索，将其分配给自己",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "return_lead",
            "description": "将线索退回公海池",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "convert_lead",
            "description": "将线索转化为客户",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID）"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（默认使用线索名称）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "follow_up_lead",
            "description": "添加线索跟进记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID）"
                    },
                    "content": {
                        "type": "string",
                        "description": "跟进内容（必填）"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["电话", "微信", "邮件", "拜访", "其他"],
                        "description": "跟进方式（默认：其他）"
                    },
                    "next_follow_time": {
                        "type": "string",
                        "description": "下次跟进时间（YYYY-MM-DD格式，可选）"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mark_lead_invalid",
            "description": "将线索标记为无效",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {
                        "type": "integer",
                        "description": "线索ID"
                    },
                    "lead_name": {
                        "type": "string",
                        "description": "线索名称（用于查找ID）"
                    },
                    "reason": {
                        "type": "string",
                        "description": "无效原因"
                    }
                },
                "required": []
            }
        }
    },

    # ==================== 客户管理 ====================
    {
        "type": "function",
        "function": {
            "name": "create_customer",
            "description": "创建新客户",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（公司名）"
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "联系人姓名"
                    },
                    "contact_phone": {
                        "type": "string",
                        "description": "联系电话（11位手机号）"
                    },
                    "industry": {
                        "type": "string",
                        "description": "所属行业"
                    },
                    "address": {
                        "type": "string",
                        "description": "地址"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注"
                    }
                },
                "required": ["customer_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_customers",
            "description": "查询客户列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["赢单", "输单", "跟进中", "暂停跟进"],
                        "description": "客户状态筛选"
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "负责人姓名"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制（默认10）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_detail",
            "description": "获取客户详细信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "客户ID"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（用于查找ID）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "follow_up_customer",
            "description": "添加客户跟进记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "客户ID"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（用于查找ID）"
                    },
                    "content": {
                        "type": "string",
                        "description": "跟进内容（必填）"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["电话", "微信", "邮件", "拜访", "其他"],
                        "description": "跟进方式（默认：其他）"
                    },
                    "next_follow_time": {
                        "type": "string",
                        "description": "下次跟进时间（YYYY-MM-DD格式）"
                    }
                },
                "required": ["content"]
            }
        }
    },

    # ==================== 商机管理 ====================
    {
        "type": "function",
        "function": {
            "name": "create_opportunity",
            "description": "创建新商机",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "关联客户名称（必填）"
                    },
                    "expected_amount": {
                        "type": "number",
                        "description": "预期金额"
                    },
                    "expected_closing_date": {
                        "type": "string",
                        "description": "预期成交日期（YYYY-MM-DD格式）"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注"
                    }
                },
                "required": ["customer_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_opportunities",
            "description": "查询商机列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["跟进中", "赢单", "输单"],
                        "description": "商机状态"
                    },
                    "stage": {
                        "type": "string",
                        "description": "商机阶段"
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "负责人姓名"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_opportunity_detail",
            "description": "获取商机详细信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于查找ID）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "advance_opportunity_stage",
            "description": "推进商机到下一阶段",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注说明"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "win_opportunity",
            "description": "标记商机为成交（赢得）",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称"
                    },
                    "actual_amount": {
                        "type": "number",
                        "description": "实际成交金额"
                    },
                    "actual_closing_date": {
                        "type": "string",
                        "description": "实际成交日期（YYYY-MM-DD格式）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lose_opportunity",
            "description": "标记商机为失败（失去）",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称"
                    },
                    "reason": {
                        "type": "string",
                        "description": "失败原因"
                    }
                },
                "required": []
            }
        }
    },

    # ==================== 通用操作 ====================
    {
        "type": "function",
        "function": {
            "name": "set_next_follow_time",
            "description": "设置下次跟进时间（适用于线索、客户、商机）",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["lead", "customer", "opportunity"],
                        "description": "实体类型"
                    },
                    "entity_id": {
                        "type": "integer",
                        "description": "实体ID"
                    },
                    "entity_name": {
                        "type": "string",
                        "description": "实体名称（用于查找ID）"
                    },
                    "next_follow_time": {
                        "type": "string",
                        "description": "下次跟进时间（YYYY-MM-DD格式，必填）"
                    }
                },
                "required": ["entity_type", "next_follow_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_funnel",
            "description": "获取销售漏斗数据（商机阶段分布统计）",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]

# 工具与 Handler 的映射
TOOL_HANDLER_MAP: Dict[str, Dict[str, Any]] = {
    # 线索
    "create_lead": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "lead",
            "schema_class": "LeadCreate",
            "permission_code": "lead:create"
        }
    },
    "query_leads": {
        "handler": "QueryListHandler",
        "config": {
            "crud_mapping": "lead",
            "owner_filter": True,
            "status_exclude": ["CONVERTED", "INVALID"],
            "permission_code": "lead:view"
        }
    },
    "get_lead_detail": {
        "handler": "QueryDetailHandler",
        "config": {
            "crud_mapping": "lead",
            "permission_code": "lead:view"
        }
    },
    "assign_lead": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "lead",
            "action_type": "assign",
            "permission_code": "lead:assign"
        }
    },
    "claim_lead": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "lead",
            "action_type": "claim",
            "permission_code": "lead:claim"
        }
    },
    "return_lead": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "lead",
            "action_type": "return",
            "permission_code": "lead:return"
        }
    },
    "convert_lead": {
        "handler": "LeadConvertHandler",
        "config": {
            "permission_code": "lead:convert"
        }
    },
    "follow_up_lead": {
        "handler": "FollowUpHandler",
        "config": {
            "crud_mapping": "lead_follow_up",
            "parent_crud_mapping": "lead",
            "parent_lookup_field": "lead_name",
            "parent_name_field": "lead_name",
            "enum_mappings": {"method": "follow_up_method"},
            "update_parent_status": {"from_status": "NEW", "to_status": "FOLLOWING"},
            "permission_code": "lead:follow_up:create"
        }
    },
    "mark_lead_invalid": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "lead",
            "action_type": "mark_invalid",
            "permission_code": "lead:edit:own"
        }
    },

    # 客户
    "create_customer": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "customer",
            "schema_class": "CustomerCreate",
            "permission_code": "customer:create"
        }
    },
    "query_customers": {
        "handler": "QueryListHandler",
        "config": {
            "crud_mapping": "customer",
            "owner_filter": True,
            "permission_code": "customer:view"
        }
    },
    "get_customer_detail": {
        "handler": "QueryDetailHandler",
        "config": {
            "crud_mapping": "customer",
            "permission_code": "customer:view"
        }
    },
    "follow_up_customer": {
        "handler": "FollowUpHandler",
        "config": {
            "crud_mapping": "customer_follow_up",
            "parent_crud_mapping": "customer",
            "parent_lookup_field": "customer_name",
            "parent_name_field": "customer_name",
            "enum_mappings": {"method": "follow_up_method"},
            "permission_code": "customer:follow_up:create"
        }
    },

    # 商机
    "create_opportunity": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "opportunity",
            "schema_class": "OpportunityCreate",
            "parent_lookup": {
                "parent_crud_mapping": "customer",
                "parent_lookup_field": "customer_name",
                "parent_result_field": "customer_id"
            },
            "permission_code": "opportunity:create"
        }
    },
    "query_opportunities": {
        "handler": "QueryListHandler",
        "config": {
            "crud_mapping": "opportunity",
            "owner_filter": True,
            "permission_code": "opportunity:view"
        }
    },
    "get_opportunity_detail": {
        "handler": "QueryDetailHandler",
        "config": {
            "crud_mapping": "opportunity",
            "permission_code": "opportunity:view"
        }
    },
    "advance_opportunity_stage": {
        "handler": "StageAdvanceHandler",
        "config": {
            "crud_mapping": "opportunity",
            "permission_code": "opportunity:edit:own"
        }
    },
    "win_opportunity": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "opportunity",
            "action_type": "win",
            "permission_code": "opportunity:edit:own"
        }
    },
    "lose_opportunity": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "opportunity",
            "action_type": "lose",
            "permission_code": "opportunity:edit:own"
        }
    },

    # 通用
    "set_next_follow_time": {
        "handler": "SetNextFollowHandler",
        "config": {
            "permission_code": "lead:follow_up:create"
        }
    },
    "get_sales_funnel": {
        "handler": "AggregateHandler",
        "config": {
            "aggregation_type": "sales_funnel",
            "permission_code": "opportunity:view"
        }
    },
}


def get_tools_schema() -> List[Dict[str, Any]]:
    """获取工具定义 Schema（用于 AI API 调用）"""
    return TOOLS


def get_tool_handler_config(tool_name: str) -> Dict[str, Any]:
    """获取工具对应的 Handler 配置"""
    return TOOL_HANDLER_MAP.get(tool_name, {})