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
            "description": "添加线索跟进记录。根据用户描述的跟进情况，智能分析并填写跟进内容、跟进方式、下一步动作等",
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
                        "description": "跟进内容（必填，总结用户的跟进描述）"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["电话", "微信", "邮件", "拜访", "其他"],
                        "description": "跟进方式（根据描述判断，如'微信联系'则填'微信'，默认'其他'）"
                    },
                    "next_follow_time": {
                        "type": "string",
                        "description": "下次跟进时间（YYYY-MM-DD格式，如用户说'明天再联系'则填明天日期）"
                    },
                    "next_action": {
                        "type": "string",
                        "description": "下一步动作（根据用户描述分析下一步应该做什么，如：明天再联系客户、准备报价方案、发送产品资料等）"
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
                        "enum": ["跟进中", "已成交", "已流失", "非激活"],
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
            "description": "添加客户跟进记录。根据用户描述的跟进情况，智能分析并填写跟进内容、跟进方式、下一步动作等",
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
                        "description": "跟进内容（必填，总结用户的跟进描述）"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["电话", "微信", "邮件", "拜访", "其他"],
                        "description": "跟进方式（根据描述判断，如'微信联系'则填'微信'，默认'其他'）"
                    },
                    "next_follow_time": {
                        "type": "string",
                        "description": "下次跟进时间（YYYY-MM-DD格式，如用户说'明天再联系'则填明天日期）"
                    },
                    "next_action": {
                        "type": "string",
                        "description": "下一步动作（根据用户描述分析下一步应该做什么，如：明天再联系客户、准备报价方案、发送产品资料等）"
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
            "description": "创建新商机。根据用户描述的客户需求，智能生成商机名称、预估金额和预期成交日期",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（根据客户+需求自动生成，如「某某公司-采购系统项目」）"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "关联客户名称（必填，用于查找客户ID）"
                    },
                    "expected_amount": {
                        "type": "number",
                        "description": "预期金额（从用户描述中提取，如「预算50万」则填500000）"
                    },
                    "expected_closing_date": {
                        "type": "string",
                        "description": "预期成交日期（YYYY-MM-DD格式，从描述中解析，如「下季度」或「年底」）"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注（记录客户的核心需求、决策人信息等关键信息）"
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
            "description": "查询商机列表。支持按状态、阶段、负责人、关键词组合筛选，返回商机概览信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["跟进中", "赢单", "输单"],
                        "description": "商机状态筛选（跟进中=正在推进，赢单=已成交，输单=已失败）"
                    },
                    "stage": {
                        "type": "string",
                        "description": "商机阶段筛选（如「初步接洽」「需求确认」「方案报价」「商务谈判」）"
                    },
                    "owner_name": {
                        "type": "string",
                        "description": "负责人姓名（模糊匹配）"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（商机名称、客户名称）"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制（默认10，最大50）"
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
            "description": "获取商机详细信息，包括当前阶段、赢率、预期金额、负责人、创建时间等",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID（优先使用）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于模糊查找ID，如果提供ID则优先使用ID）"
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
            "description": "推进商机到下一阶段。每次推进会更新赢率，推进到最后阶段（100%赢率）会自动标记为赢单",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID（优先使用）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于查找ID）"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注说明（记录推进原因、关键进展、客户反馈等信息）"
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
            "description": "标记商机为赢单（成交）。记录实际成交金额和日期，从用户描述中智能提取金额信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID（优先使用）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于查找ID）"
                    },
                    "actual_amount": {
                        "type": "number",
                        "description": "实际成交金额（从描述提取，如「签了30万」填300000，如未提及可填预期金额）"
                    },
                    "actual_closing_date": {
                        "type": "string",
                        "description": "实际成交日期（YYYY-MM-DD格式，如未提及则默认今天）"
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
            "description": "标记商机为输单（失败）。记录失败原因，便于后续分析和改进",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID（优先使用）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于查找ID）"
                    },
                    "reason": {
                        "type": "string",
                        "description": "失败原因（从用户描述中分析，常见原因：价格竞争、客户预算不足、选择了竞品、需求变更、决策人变更等）"
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