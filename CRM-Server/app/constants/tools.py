"""
工具与 Handler 的映射

定义 ReAct agent 各工具对应的 Handler 配置（TOOL_HANDLER_MAP）。
OpenAI Function Calling 格式的 TOOLS 列表已移除（孤儿，仅测试引用）。
"""
from typing import Dict, Any

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
