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
            "description": """搜索查看线索列表。

适用于：用户明确要"查看/搜索/找"线索
示例：
- "看看有哪些线索"
- "查一下跟进中的线索"
- "找找某某公司的线索"

注意：如果用户描述的是沟通内容，请使用跟进工具。
""",
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
            "description": """记录与线索的沟通互动情况。

适用于：用户描述沟通内容、业务进展、下一步安排
示例：
- "微信联系了客户"
- "电话沟通了需求"
- "客户说有兴趣"

注意：如果用户明确要"查看/搜索"信息，请用查询工具。
""",
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
            "description": """搜索查看客户列表。

适用于：用户明确要"查看/搜索/找"客户
示例：
- "看看有哪些客户"
- "查一下某某公司"

注意：如果用户描述的是沟通内容，请使用跟进工具。
""",
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
            "description": """记录与客户的沟通互动情况。

适用于：用户描述沟通内容、业务进展、下一步安排
示例：
- "微信确认了采购意向"
- "电话讨论了报价方案"
- "客户说下周签约"
- "今天拜访客户，聊了需求"
- "后续会有采购联系人过来走合同流程"

注意：如果用户明确要"查看/搜索"信息，请用查询工具，而非跟进。
""",
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
            "description": """创建新的销售商机。

适用于：用户明确要"创建/新建/添加"商机
示例：
- "创建一个商机"
- "新建商机"
- "添加一个订阅商机"
- "帮我建个商机，50人1年"

【重要说明】
- 系统没有"产品"概念，商机名称由客户名+采购规模自动生成
- 商机名称格式：{客户名}-{用户数}人{年限}年订阅（如：某某公司-50人1年订阅）
- 不要询问"产品名称"，系统无此概念

【执行流程】
当用户要创建商机时，必须先调用 ask_user 工具让用户确认信息：

1. 调用 ask_user 工具（必须！不要直接在文本中询问）：
{
  "question": "请确认商机信息",
  "missing_fields": ["预计金额", "预期成交日期", "采购类型", "采购方式"],
  "field_options": {
    "采购类型": {"type": "select", "options": ["新购", "续购", "增购"], "default": "新购"},
    "采购方式": {"type": "select", "options": ["公开招标", "竞争性谈判", "单一来源采购", "询价采购", "其他"], "default": "公开招标"}
  }
}

2. 用户回复后，再调用 create_opportunity 工具执行创建

【自动提取的字段】（从用户描述提取，不询问）：
- user_count: 采购用户数（如"50人"→50）
- subscription_years: 订阅年限（如"1年"→1）
- license_type: 授权模式（默认订阅制）
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "关联客户名称（必填，用于查找客户ID）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（格式：{客户名称}-{用户数}人{订阅年限}年订阅，如：某某公司-50人1年订阅）"
                    },
                    "total_amount": {
                        "type": "number",
                        "description": "预计总金额（让用户确认金额）"
                    },
                    "user_count": {
                        "type": "integer",
                        "description": "采购用户数（从描述中自动提取，如「50人」→50）"
                    },
                    "license_type": {
                        "type": "string",
                        "enum": ["订阅制", "买断制"],
                        "description": "授权模式（默认订阅制）"
                    },
                    "subscription_years": {
                        "type": "integer",
                        "description": "订阅年限（从描述中自动提取，如「1年」→1，默认1年）"
                    },
                    "purchase_type": {
                        "type": "string",
                        "enum": ["新购", "续购", "增购"],
                        "description": "采购类型（让用户选择，默认新购）"
                    },
                    "expected_closing_date": {
                        "type": "string",
                        "description": "预期成交日期（YYYY-MM-DD格式，让用户填写）"
                    },
                    "procurement_method_name": {
                        "type": "string",
                        "description": "采购方式（让用户选择，默认继承客户的采购方式）"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注（记录客户的核心需求、决策人信息等关键信息）"
                    }
                },
                "required": ["customer_name", "total_amount", "expected_closing_date", "purchase_type", "procurement_method_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_opportunities",
            "description": """搜索查看商机列表。

适用于：用户明确要"查看/搜索/找"商机
示例：
- "看看有哪些商机"
- "查一下跟进中的商机"
- "找找这个客户的商机"
- "搜索 CRM 相关的商机"

注意：如果用户描述的是沟通内容而非查看需求，请使用跟进工具。
""",
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
            "description": """推进商机到下一阶段，更新赢率。

适用于：商机有进展，需要推进阶段
触发条件：
- 用户说"推进商机"、"推进阶段"
- 用户描述商机进展

示例：
- "推进商机到下一阶段"
- "推进阶段"

注意：每次推进会更新赢率，推进到最后阶段（100%赢率）会自动标记为赢单。
""",
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
            "description": """标记商机为赢单（成交），记录实际成交信息。

适用于：客户明确表示成交、签约、确认采购
触发条件：
- 用户说"赢单"、"成交"、"签约了"、"客户确认采购"
- 用户描述成交细节（如"签了合同，30万"）

示例：
- "赢单了，30万"
- "成交，客户签了合同"
- "客户确认采购了"
- "签了合同，标记赢单"

注意：记录实际成交金额和日期。从用户描述中智能提取金额信息。
""",
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
            "description": """标记商机为输单（失败），记录失败原因。

适用于：商机失败，客户选择竞品或放弃采购
触发条件：
- 用户说"输单"、"失败"、"客户选择了竞品"、"客户放弃了"
- 用户描述失败原因

示例：
- "输单了，客户选择了竞品"
- "客户放弃了，预算不足"
- "商机失败，价格竞争"

注意：记录失败原因，便于后续分析和改进。常见原因：价格竞争、客户预算不足、选择了竞品、需求变更、决策人变更等。
""",
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
    {
        "type": "function",
        "function": {
            "name": "set_procurement_method",
            "description": """为商机设置采购方式，自动进入对应阶段。

适用于：未设置采购方式的跟进中商机
触发条件：
- 用户说"设置采购方式"、"这个商机是公开招标"
- 用户描述采购方式

示例：
- "设置采购方式为公开招标"
- "这个商机是竞争性谈判"
- "采购方式是单一来源采购"

注意：采购方式如：公开招标、竞争性谈判、单一来源采购、询价采购等。设置后自动进入对应的起始阶段。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {
                        "type": "integer",
                        "description": "商机ID（优先使用）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于模糊查找ID）"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（用于查找该客户下的商机）"
                    },
                    "procurement_method_name": {
                        "type": "string",
                        "description": "采购方式名称（如：公开招标、竞争性谈判、单一来源采购、询价采购等。不填则列出可选采购方式）"
                    }
                },
                "required": []
            }
        }
    },

    # ==================== 合同管理 ====================
    {
        "type": "function",
        "function": {
            "name": "create_contract",
            "description": """创建合同，记录客户签约信息。

适用于：客户已签约，需要正式记录合同信息
触发条件：
- 用户说"签合同"、"创建合同"、"已签约"、"合同签了"
- 用户描述签约细节（如"今天签了合同，30万，50人1年订阅"）
- 商机赢单后需要创建合同

示例：
- "今天签了合同，30万，50人1年订阅"
- "创建合同"
- "已签约"
- "合同签好了，帮我录入系统"

注意：
- 合同需关联商机（通常商机先标记赢单）
- 合同名称格式建议：{客户名称}-{商机名称}-合同
- 如果客户有多个商机，AI 会询问用户选择哪个
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（用于查找客户ID，必填）"
                    },
                    "opportunity_name": {
                        "type": "string",
                        "description": "商机名称（用于查找商机ID，必填）"
                    },
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（建议格式：{客户名称}-{商机名称}-合同）"
                    },
                    "total_amount": {
                        "type": "number",
                        "description": "合同总金额（从用户描述中提取，如「30万」填300000）"
                    },
                    "user_count": {
                        "type": "integer",
                        "description": "采购用户数（人数，如「50人」则填50）"
                    },
                    "license_type": {
                        "type": "string",
                        "enum": ["订阅制", "买断制"],
                        "description": "授权模式（订阅制或买断制，默认订阅制）"
                    },
                    "subscription_years": {
                        "type": "integer",
                        "description": "订阅年限（订阅制时必填，如「1年」则填1，默认1年）"
                    },
                    "signing_date": {
                        "type": "string",
                        "description": "签署日期（YYYY-MM-DD格式，如未提及则默认今天）"
                    },
                    "effective_date": {
                        "type": "string",
                        "description": "生效日期（YYYY-MM-DD格式，如未提及则默认签署日期）"
                    },
                    "remarks": {
                        "type": "string",
                        "description": "备注（记录合同相关信息）"
                    }
                },
                "required": ["customer_name", "opportunity_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_contracts",
            "description": """搜索查看合同列表。

适用于：用户明确要"查看/搜索/找"合同
触发条件：用户使用"看看"、"查一下"、"找找"、"搜索"等查看类动词
示例：
- "看看有哪些合同"
- "查一下生效中的合同"
- "找找这个客户的合同"

注意：如果用户描述的是签约内容而非查看需求，请使用创建合同工具。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["草稿", "待审核", "已签署", "生效中", "已到期", "已终止"],
                        "description": "合同状态筛选"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "客户名称（模糊匹配）"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（合同名称、合同编号）"
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
            "name": "get_contract_detail",
            "description": """获取合同详细信息。

适用于：用户要查看具体合同的详情
触发条件：用户指定某个合同，要查看详情
示例：
- "看看这个合同的详情"
- "合同123的详细信息"

注意：返回合同的基本信息、客户、商机、金额、状态、签署日期等。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_id": {
                        "type": "integer",
                        "description": "合同ID（优先使用）"
                    },
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（用于模糊查找ID）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_contract_status",
            "description": """更新合同状态，推进合同生命周期。

适用于：合同状态变更（提交审批、签署、生效、到期、终止）
触发条件：
- 用户说"提交审批"、"合同已签署"、"合同生效"
- 用户要更新合同状态

示例：
- "提交合同审批"
- "合同已签署"
- "合同开始生效"

注意：合同生命周期：草稿→待审核→已签署→生效中→已到期/已终止
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_id": {
                        "type": "integer",
                        "description": "合同ID（优先使用）"
                    },
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（用于查找ID）"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["待审核", "已签署", "生效中", "已终止"],
                        "description": "目标状态（草稿→待审核→已签署→生效中）"
                    },
                    "effective_date": {
                        "type": "string",
                        "description": "生效日期（生效时填写，YYYY-MM-DD格式）"
                    }
                },
                "required": ["status"]
            }
        }
    },

    # ==================== 回款管理 ====================
    {
        "type": "function",
        "function": {
            "name": "create_payment_plan",
            "description": """创建回款计划，定义合同的回款阶段。

适用于：签订合同后设置回款阶段（首付款、中期款、尾款等）
触发条件：
- 用户说"设置回款计划"、"创建回款计划"
- 用户描述回款阶段（如"合同分三期付款，首付款10万"）

示例：
- "创建回款计划，首付款10万，下月支付"
- "设置回款计划，分3期"

注意：需关联合同，定义回款阶段名称、金额和日期。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（用于查找合同ID）"
                    },
                    "stage_name": {
                        "type": "string",
                        "description": "回款阶段名称（如：首付款、中期款、尾款）"
                    },
                    "planned_amount": {
                        "type": "number",
                        "description": "计划回款金额（从合同金额分解，如合同30万分3期，每期10万）"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "计划回款日期（YYYY-MM-DD格式）"
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注（记录回款条件、付款要求等）"
                    }
                },
                "required": ["contract_name", "stage_name", "planned_amount", "due_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_payment_record",
            "description": """登记回款，记录客户实际付款。

适用于：客户已付款，需要记录回款信息
触发条件：
- 用户说"客户付款了"、"收到回款"、"登记回款"
- 用户描述回款详情（如"收到首付款10万"）

示例：
- "客户付款了，10万"
- "登记回款，首付款已到账"
- "收到首付款"

注意：关联回款计划，记录实际金额和日期。这是财务操作，重要且需确认。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（用于查找合同和回款计划）"
                    },
                    "stage_name": {
                        "type": "string",
                        "description": "回款阶段名称（用于匹配回款计划）"
                    },
                    "actual_amount": {
                        "type": "number",
                        "description": "实际回款金额"
                    },
                    "payment_date": {
                        "type": "string",
                        "description": "实际回款日期（YYYY-MM-DD格式，如未提及则默认今天）"
                    },
                    "proof_attachment": {
                        "type": "string",
                        "description": "回款凭证附件URL"
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注"
                    }
                },
                "required": ["contract_name", "stage_name", "actual_amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_payment_records",
            "description": """搜索查看回款记录。

适用于：用户明确要"查看/搜索/找"回款记录
触发条件：用户使用"看看"、"查一下"、"找找"等查看类动词
示例：
- "看看回款记录"
- "查一下这个合同的回款情况"
- "找找待确认的回款"

注意：如果用户描述的是回款内容而非查看需求，请使用登记回款工具。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（模糊匹配）"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["待确认", "已确认", "有争议"],
                        "description": "确认状态筛选"
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
            "name": "confirm_payment",
            "description": """确认回款，财务人员确认回款已入账。

适用于：财务人员确认回款状态
触发条件：
- 用户说"确认回款"、"回款已入账"
- 用户要对回款记录进行确认或标记争议

示例：
- "确认回款已入账"
- "标记回款有争议"

注意：这是财务确认操作，重要且需权限。可确认入账或标记有争议。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_id": {
                        "type": "integer",
                        "description": "回款记录ID"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["确认", "争议"],
                        "description": "确认操作（确认入账或标记有争议）"
                    },
                    "notes": {
                        "type": "string",
                        "description": "确认备注或争议说明"
                    }
                },
                "required": ["record_id", "action"]
            }
        }
    },

    # ==================== 发票管理 ====================
    {
        "type": "function",
        "function": {
            "name": "create_invoice_application",
            "description": """申请开票，为客户开具发票。

适用于：客户要求开具发票
触发条件：
- 用户说"申请开票"、"开具发票"、"要发票"
- 用户描述开票需求（如"客户要开票，10万"）

示例：
- "申请开票"
- "客户要开票，10万，专票"
- "开具发票"

注意：关联回款计划，填写开票金额和发票类型（增值税专用发票或普通发票）。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（用于查找合同和回款计划）"
                    },
                    "stage_name": {
                        "type": "string",
                        "description": "回款阶段名称（用于匹配回款计划）"
                    },
                    "invoice_amount": {
                        "type": "number",
                        "description": "开票金额（通常与回款金额一致）"
                    },
                    "invoice_type": {
                        "type": "string",
                        "enum": ["增值税专用发票", "普通发票"],
                        "description": "发票类型"
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注"
                    }
                },
                "required": ["contract_name", "stage_name", "invoice_amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_invoice_applications",
            "description": """搜索查看开票申请。

适用于：用户明确要"查看/搜索/找"开票申请
触发条件：用户使用"看看"、"查一下"、"找找"等查看类动词
示例：
- "看看开票申请"
- "查一下待审批的开票申请"

注意：如果用户描述的是开票需求而非查看需求，请使用申请开票工具。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_name": {
                        "type": "string",
                        "description": "合同名称（模糊匹配）"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["草稿", "待审批", "已批准", "已拒绝", "已开票"],
                        "description": "申请状态筛选"
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
            "name": "get_invoice_application_detail",
            "description": """获取开票申请详细信息。

适用于：用户要查看具体开票申请的详情
触发条件：用户指定某个开票申请，要查看详情
示例：
- "看看开票申请123的详情"

注意：返回开票申请的详细信息。
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "integer",
                        "description": "开票申请ID"
                    }
                },
                "required": ["application_id"]
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
            "description": """获取销售漏斗数据，商机阶段分布统计。

适用于：用户要查看销售漏斗、商机分布
触发条件：用户说"销售漏斗"、"商机分布"、"阶段分布"
示例：
- "看看销售漏斗"
- "商机阶段分布"

注意：返回各阶段的商机数量和金额统计。
""",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },

    # ==================== Agent 核心工具 ====================
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": """向用户提问以获取缺失信息或确认操作。

适用于：
- 缺少必要字段时询问用户补充（如金额、日期）
- 重要操作前需要用户确认（如创建合同）
- 多个候选实体需要用户选择（如客户有多个商机）
- 需要用户决策的场景

触发条件：
- AI 判断当前信息不足以继续执行
- 需要执行高风险操作，需用户确认
- 发现多个候选实体，需用户选择

示例：
- 缺少商机信息 → question="请补充商机信息", missing_fields=["预计金额", "预期成交日期", "采购类型", "采购方式"]
- 多个商机 → question="请选择签订合同的商机", options=["CRM项目-50人订阅", "OA项目-30人订阅"]
- 创建合同 → question="是否现在创建合同？", options=["是，创建合同", "稍后创建"]

注意：
- 此工具会暂停 Agent 循环，等待用户回复后继续
- 用户回复后，AI 会根据回复继续处理
- question 应简洁明确，让用户容易回答
- 只需返回 missing_fields，后端会动态查询数据库填充选项（如采购方式）
- 如果有多个候选实体，使用 options 参数让用户选择而非输入
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "向用户提出的问题（简洁明确）"
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选的选项列表（用于选择场景，用户点击选择而非输入）"
                    },
                    "missing_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "缺失的字段列表（后端会自动填充下拉选项，如采购类型、采购方式）"
                    },
                    "context_hint": {
                        "type": "string",
                        "description": "上下文提示（可选，告知用户为什么需要此信息）"
                    }
                },
                "required": ["question"]
            },
            "halts_loop": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_context",
            "description": """获取实体的完整上下文信息，用于决策判断。

适用于：
- 执行业务操作前，需要了解实体状态（如客户是否有商机）
- 判断是否需要创建新实体（如客户无商机，是否需要创建）
- 查询关联信息（如商机的合同状态、回款进度）

触发条件：
- 用户提到某个实体，AI 需要知道其详细信息
- AI 需要判断下一步操作（如"客户确认采购"需要知道是否有商机）
- 执行依赖其他实体的操作（如创建合同需要知道商机状态）

返回信息：
- 客户：基本信息、商机列表（ID、名称、状态、金额）、最近跟进、合同列表
- 商机：基本信息、关联客户、当前阶段、合同状态、回款进度
- 合同：基本信息、回款计划、发票申请状态

示例：
- 用户说"客户确认采购" → entity_type="customer" → 返回商机列表
- AI 发现客户无商机 → 调用 ask_user("是否创建商机？")
- 用户说"签合同" → entity_type="customer" → 发现多个商机 → ask_user("请选择商机")

注意：
- 此工具应在其他业务工具调用前调用，获取上下文帮助决策
- 返回的信息会添加到 AI 的消息上下文中
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["customer", "opportunity", "contract", "lead"],
                        "description": "实体类型"
                    },
                    "entity_name": {
                        "type": "string",
                        "description": "实体名称（用于查找，可以是名称或包含ID的格式）"
                    }
                },
                "required": ["entity_type"]
            },
            "returns_context": True
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
            "parent_name_field": "account_name",  # Customer 模型的名称字段
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
                "parent_name_field": "account_name",
                "parent_result_field": "customer_id",
                "inherit_fields": {
                    "procurement_method_id": "default_procurement_method_id"
                }
            },
            "auto_fields": {
                "owner_id": "user_id"
            },
            "name_auto_generate": {
                "name_field": "opportunity_name",
                "template": "{customer_name}-{user_count}人{subscription_years}年订阅",
                "field_mappings": {
                    "customer_name": "customer_name",
                    "user_count": "user_count",
                    "subscription_years": "subscription_years"
                },
                "default_values": {
                    "subscription_years": 1
                }
            },
            "enum_mappings": {
                "procurement_method": "procurement_method",
                "license_type": "license_type",
                "purchase_type": "purchase_type"
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
            "target_status": "WON",  # 目标状态
            "status_field": "status",  # 状态字段
            "update_fields": ["actual_amount", "actual_closing_date"],  # 需要更新的字段
            "result_template": "商机已标记为赢单\n商机: {opportunity_name}\nID: {opportunity_id}",
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
    "set_procurement_method": {
        "handler": "SetProcurementMethodHandler",
        "config": {
            "crud_mapping": "opportunity",
            "name_lookup_field": "opportunity_name",
            "name_field": "opportunity_name",
            "method_lookup_field": "procurement_method_name",
            "exclude_status": ["WON", "LOST"],
            "require_no_method": True,
            "customer_lookup": {
                "customer_lookup_field": "customer_name",
                "customer_name_field": "account_name"
            },
            "permission_code": "opportunity:edit:own"
        }
    },

    # 合同
    "create_contract": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "contract",
            "schema_class": "ContractCreate",
            "parent_lookup": {
                "parent_crud_mapping": "customer",
                "parent_lookup_field": "customer_name",
                "parent_name_field": "account_name",
                "parent_result_field": "customer_id"
            },
            "secondary_parent_lookup": {
                "parent_crud_mapping": "opportunity",
                "parent_lookup_field": "opportunity_name",
                "parent_name_field": "opportunity_name",
                "parent_result_field": "opportunity_id",
                "parent_filter_status": "WON"
            },
            "auto_fields": {
                "owner_id": "user_id"
            },
            "enum_mappings": {
                "license_type": "license_type"
            },
            "permission_code": "contract:create"
        }
    },
    "query_contracts": {
        "handler": "QueryListHandler",
        "config": {
            "crud_mapping": "contract",
            "owner_filter": True,
            "permission_code": "contract:view"
        }
    },
    "get_contract_detail": {
        "handler": "QueryDetailHandler",
        "config": {
            "crud_mapping": "contract",
            "permission_code": "contract:view"
        }
    },
    "update_contract_status": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "contract",
            "action_type": "update_status",
            "permission_code": "contract:edit"
        }
    },

    # 回款
    "create_payment_plan": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "payment_plan",
            "schema_class": "PaymentPlanCreate",
            "parent_lookup": {
                "parent_crud_mapping": "contract",
                "parent_lookup_field": "contract_name",
                "parent_name_field": "contract_name",
                "parent_result_field": "contract_id",
                "parent_filter_status": "EFFECTIVE"
            },
            "permission_code": "contract:edit"
        }
    },
    "create_payment_record": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "payment_record",
            "schema_class": "PaymentRecordCreate",
            "parent_lookup": {
                "parent_crud_mapping": "payment_plan",
                "parent_lookup_field": "stage_name",
                "parent_name_field": "stage_name",
                "parent_result_field": "payment_plan_id",
                "secondary_lookup_field": "contract_name",
                "secondary_name_field": "contract_name"
            },
            "auto_fields": {
                "creator_id": "user_id"
            },
            "permission_code": "payment:create"
        }
    },
    "query_payment_records": {
        "handler": "QueryListHandler",
        "config": {
            "crud_mapping": "payment_record",
            "owner_filter": True,
            "permission_code": "payment:view"
        }
    },
    "confirm_payment": {
        "handler": "StatusChangeHandler",
        "config": {
            "crud_mapping": "payment_record",
            "action_type": "confirm_payment",
            "permission_code": "payment:confirm"
        }
    },

    # 发票
    "create_invoice_application": {
        "handler": "CreateHandler",
        "config": {
            "crud_mapping": "invoice_application",
            "schema_class": "InvoiceApplicationCreate",
            "parent_lookup": {
                "parent_crud_mapping": "payment_plan",
                "parent_lookup_field": "stage_name",
                "parent_name_field": "stage_name",
                "parent_result_field": "payment_plan_id"
            },
            "auto_fields": {
                "applicant_id": "user_id"
            },
            "enum_mappings": {
                "invoice_type": "invoice_type"
            },
            "permission_code": "invoice:create"
        }
    },
    "query_invoice_applications": {
        "handler": "QueryListHandler",
        "config": {
            "crud_mapping": "invoice_application",
            "owner_filter": True,
            "permission_code": "invoice:view"
        }
    },
    "get_invoice_application_detail": {
        "handler": "QueryDetailHandler",
        "config": {
            "crud_mapping": "invoice_application",
            "permission_code": "invoice:view"
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

    # Agent 核心工具
    "ask_user": {
        "handler": "AskUserHandler",
        "config": {
            "permission_code": None,  # 无需权限检查
            "halts_loop": True
        }
    },
    "get_entity_context": {
        "handler": "GetContextHandler",
        "config": {
            "permission_code": None,  # 无需权限检查
            "returns_context": True
        }
    },
}


def get_tools_schema() -> List[Dict[str, Any]]:
    """获取工具定义 Schema（用于 AI API 调用）"""
    return TOOLS


def get_tool_handler_config(tool_name: str) -> Dict[str, Any]:
    """获取工具对应的 Handler 配置"""
    return TOOL_HANDLER_MAP.get(tool_name, {})