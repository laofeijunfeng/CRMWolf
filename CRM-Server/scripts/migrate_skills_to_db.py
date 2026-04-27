"""
将现有硬编码的 Skill 配置迁移到数据库

迁移内容：
- 6 个 Skill（LeadSkill, CustomerSkill, OpportunitySkill, ContractSkill, PaymentSkill, InvoiceSkill）
- 17 个 Action
- 26 个 CRUD 映射
- 4 个 Enum 映射

运行方式：
  python scripts/migrate_skills_to_db.py          # 执行迁移
  python scripts/migrate_skills_to_db.py --verify # 验证数据完整性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from app.crud.ai_crud_mapping import ai_crud_mapping_crud
from app.crud.ai_enum_mapping import ai_enum_mapping_crud
from app.models.ai_skill import AISkill, AISkillAction, AICRUDMapping, AIEnumMapping


# ============================================================================
# Skill 迁移数据（6 个 Skill）
# ============================================================================
SKILL_MIGRATION_DATA = [
    {
        "skill_name": "LeadSkill",
        "display_name": "线索管理",
        "description": "线索管理相关操作",
        "module_type": "lead",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "CustomerSkill",
        "display_name": "客户管理",
        "description": "客户管理相关操作",
        "module_type": "customer",
        "sort_order": 2,
        "is_active": 1
    },
    {
        "skill_name": "OpportunitySkill",
        "display_name": "商机管理",
        "description": "商机管理相关操作",
        "module_type": "opportunity",
        "sort_order": 3,
        "is_active": 1
    },
    {
        "skill_name": "ContractSkill",
        "display_name": "合同管理",
        "description": "合同管理相关操作",
        "module_type": "contract",
        "sort_order": 4,
        "is_active": 1
    },
    {
        "skill_name": "PaymentSkill",
        "display_name": "回款管理",
        "description": "回款管理相关操作",
        "module_type": "payment",
        "sort_order": 5,
        "is_active": 1
    },
    {
        "skill_name": "InvoiceSkill",
        "display_name": "发票管理",
        "description": "发票管理相关操作",
        "module_type": "invoice",
        "sort_order": 6,
        "is_active": 1
    },
]


# ============================================================================
# Action 迁移数据（17 个 Action）
# ============================================================================
ACTION_MIGRATION_DATA = [
    # LeadSkill - 4 个 Action
    {
        "skill_name": "LeadSkill",
        "action_name": "list",
        "display_name": "查询线索列表",
        "description": "查询线索列表",
        "handler_type": "QueryListHandler",
        "handler_config": {
            "crud_mapping": "lead",
            "owner_filter": True,
            "status_exclude": ["CONVERTED"],
            "display_fields": ["id", "lead_name", "contact_name", "contact_phone", "status"],
            "status_mapping": {
                "0": "新建",
                "1": "跟进中",
                "2": "已转化",
                "3": "无效"
            },
            "template": "共有 {total} 条线索，以下是最近10条：\n{items}"
        },
        "required_params": [],
        "optional_params": [],
        "permission_code": "lead:list",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "LeadSkill",
        "action_name": "detail",
        "display_name": "查询线索详情",
        "description": "查询线索详情",
        "handler_type": "QueryDetailHandler",
        "handler_config": {
            "crud_mapping": "lead",
            "display_fields": ["id", "lead_name", "contact_name", "contact_phone", "source", "status", "city", "created_time"],
            "status_mapping": {
                "0": "新线索",
                "1": "跟进中",
                "2": "已转化",
                "3": "无效"
            },
            "template": "【线索详情】\n线索ID：{id}\n线索名称：{lead_name}\n联系人：{contact_name}\n联系电话：{contact_phone}\n来源：{source}\n状态：{status_text}\n城市：{city}\n创建时间：{created_time}"
        },
        "required_params": ["lead_id"],
        "optional_params": [],
        "permission_code": "lead:read",
        "sort_order": 2,
        "is_active": 1
    },
    {
        "skill_name": "LeadSkill",
        "action_name": "create",
        "display_name": "创建新线索",
        "description": "创建新线索",
        "handler_type": "CreateHandler",
        "handler_config": {
            "crud_mapping": "lead",
            "schema_class": "LeadCreate",
            "enum_mappings": {
                "source": "lead_source",
                "company_scale": "company_scale"
            },
            "unique_check": {
                "field": "contact_phone",
                "message": "电话号码已存在"
            },
            "auto_fields": {
                "owner_id": "user_feishu_open_id"
            },
            "result_template": "线索创建成功\n线索ID：{id}\n线索名称：{lead_name}\n联系电话：{contact_phone}"
        },
        "required_params": ["lead_name", "source", "city", "contact_name", "contact_phone"],
        "optional_params": ["company_scale"],
        "permission_code": "lead:create",
        "sort_order": 3,
        "is_active": 1
    },
    {
        "skill_name": "LeadSkill",
        "action_name": "follow_up",
        "display_name": "添加线索跟进记录",
        "description": "添加线索跟进记录",
        "handler_type": "FollowUpHandler",
        "handler_config": {
            "crud_mapping": "lead_follow_up",
            "parent_crud_mapping": "lead",
            "parent_lookup_field": "lead_name",
            "parent_name_field": "lead_name",
            "enum_mappings": {
                "method": "follow_up_method"
            },
            "update_parent_status": {
                "from_status": "NEW",
                "to_status": "FOLLOWING"
            },
            "result_template": "跟进记录添加成功\n线索：{parent_name}\n跟进内容：{content}\n跟进方式：{method}"
        },
        "required_params": ["lead_name", "content", "method"],
        "optional_params": ["next_follow_time"],
        "permission_code": "lead:follow_up:create",
        "sort_order": 4,
        "is_active": 1
    },

    # CustomerSkill - 3 个 Action
    {
        "skill_name": "CustomerSkill",
        "action_name": "list",
        "display_name": "查询客户列表",
        "description": "查询客户列表",
        "handler_type": "QueryListHandler",
        "handler_config": {
            "crud_mapping": "customer",
            "owner_filter": True,
            "display_fields": ["id", "account_name", "industry", "status"],
            "status_mapping": {
                "0": "跟进中",
                "1": "赢单",
                "2": "输单",
                "3": "暂停跟进"
            },
            "template": "共有 {total} 个客户，以下是最近10个：\n{items}"
        },
        "required_params": [],
        "optional_params": [],
        "permission_code": "customer:list",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "CustomerSkill",
        "action_name": "detail",
        "display_name": "查询客户详情",
        "description": "查询客户详情",
        "handler_type": "QueryDetailHandler",
        "handler_config": {
            "crud_mapping": "customer",
            "display_fields": ["id", "account_name", "industry", "city", "status", "created_time"],
            "status_mapping": {
                "0": "跟进中",
                "1": "赢单",
                "2": "输单",
                "3": "暂停跟进"
            },
            "template": "【客户详情】\n客户ID：{id}\n客户名称：{account_name}\n行业：{industry}\n城市：{city}\n状态：{status_text}\n创建时间：{created_time}"
        },
        "required_params": ["customer_id"],
        "optional_params": [],
        "permission_code": "customer:read",
        "sort_order": 2,
        "is_active": 1
    },
    {
        "skill_name": "CustomerSkill",
        "action_name": "follow_up",
        "display_name": "添加客户跟进记录",
        "description": "添加客户跟进记录",
        "handler_type": "FollowUpHandler",
        "handler_config": {
            "crud_mapping": "customer_follow_up",
            "parent_crud_mapping": "customer",
            "parent_lookup_field": "customer_name",
            "parent_name_field": "account_name",
            "enum_mappings": {
                "method": "follow_up_method"
            },
            "result_template": "跟进记录添加成功\n客户：{parent_name}\n跟进内容：{content}\n跟进方式：{method}"
        },
        "required_params": ["customer_name", "content", "method"],
        "optional_params": ["next_follow_time"],
        "permission_code": "customer:follow_up:create",
        "sort_order": 3,
        "is_active": 1
    },

    # OpportunitySkill - 3 个 Action
    {
        "skill_name": "OpportunitySkill",
        "action_name": "list",
        "display_name": "查询商机列表",
        "description": "查询商机列表",
        "handler_type": "QueryListHandler",
        "handler_config": {
            "crud_mapping": "opportunity",
            "owner_filter": True,
            "display_fields": ["id", "opportunity_name", "customer_name", "amount", "stage", "status"],
            "stage_mapping": {
                "1": "初步接洽",
                "2": "需求确认",
                "3": "方案报价",
                "4": "商务谈判",
                "5": "合同签订"
            },
            "template": "共有 {total} 个商机，以下是最近10个：\n{items}"
        },
        "required_params": [],
        "optional_params": [],
        "permission_code": "opportunity:list",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "OpportunitySkill",
        "action_name": "detail",
        "display_name": "查询商机详情",
        "description": "查询商机详情",
        "handler_type": "QueryDetailHandler",
        "handler_config": {
            "crud_mapping": "opportunity",
            "display_fields": ["id", "opportunity_name", "customer_name", "amount", "stage", "status", "expected_closing_date", "created_time"],
            "stage_mapping": {
                "1": "初步接洽",
                "2": "需求确认",
                "3": "方案报价",
                "4": "商务谈判",
                "5": "合同签订"
            },
            "template": "【商机详情】\n商机ID：{id}\n商机名称：{opportunity_name}\n客户：{customer_name}\n金额：{amount}\n阶段：{stage_text}\n状态：{status}\n预计成交日期：{expected_closing_date}\n创建时间：{created_time}"
        },
        "required_params": ["opportunity_id"],
        "optional_params": [],
        "permission_code": "opportunity:read",
        "sort_order": 2,
        "is_active": 1
    },
    {
        "skill_name": "OpportunitySkill",
        "action_name": "win",
        "display_name": "标记商机赢单",
        "description": "标记商机赢单",
        "handler_type": "StatusChangeHandler",
        "handler_config": {
            "crud_mapping": "opportunity",
            "status_field": "status",
            "target_status": "WON",
            "update_fields": ["actual_amount", "actual_closing_date"],
            "result_template": "商机赢单成功\n商机ID：{opportunity_id}\n实际金额：{actual_amount}\n成交日期：{actual_closing_date}"
        },
        "required_params": ["opportunity_id", "actual_amount", "actual_closing_date"],
        "optional_params": [],
        "permission_code": "opportunity:win",
        "sort_order": 3,
        "is_active": 1
    },

    # ContractSkill - 3 个 Action
    {
        "skill_name": "ContractSkill",
        "action_name": "list",
        "display_name": "查询合同列表",
        "description": "查询合同列表",
        "handler_type": "QueryListHandler",
        "handler_config": {
            "crud_mapping": "contract",
            "owner_filter": True,
            "display_fields": ["id", "contract_name", "customer_name", "contract_amount", "status"],
            "status_mapping": {
                "DRAFT": "草稿",
                "PENDING_APPROVAL": "待审批",
                "APPROVED": "已审批",
                "EXECUTING": "执行中",
                "COMPLETED": "已完成",
                "TERMINATED": "已终止"
            },
            "template": "共有 {total} 个合同，以下是最近10个：\n{items}"
        },
        "required_params": [],
        "optional_params": [],
        "permission_code": "contract:list",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "ContractSkill",
        "action_name": "detail",
        "display_name": "查询合同详情",
        "description": "查询合同详情",
        "handler_type": "QueryDetailHandler",
        "handler_config": {
            "crud_mapping": "contract",
            "display_fields": ["id", "contract_name", "customer_name", "contract_amount", "status", "signing_date", "created_time"],
            "status_mapping": {
                "DRAFT": "草稿",
                "PENDING_APPROVAL": "待审批",
                "APPROVED": "已审批",
                "EXECUTING": "执行中",
                "COMPLETED": "已完成",
                "TERMINATED": "已终止"
            },
            "template": "【合同详情】\n合同ID：{id}\n合同名称：{contract_name}\n客户：{customer_name}\n金额：{contract_amount}\n状态：{status_text}\n签约日期：{signing_date}\n创建时间：{created_time}"
        },
        "required_params": ["contract_id"],
        "optional_params": [],
        "permission_code": "contract:read",
        "sort_order": 2,
        "is_active": 1
    },
    {
        "skill_name": "ContractSkill",
        "action_name": "create",
        "display_name": "从商机创建合同",
        "description": "从商机创建合同",
        "handler_type": "CreateHandler",
        "handler_config": {
            "crud_mapping": "contract",
            "schema_class": "ContractCreate",
            "parent_crud_mapping": "opportunity",
            "parent_required_status": "WON",
            "auto_fields": {
                "opportunity_id": "opportunity_id",
                "owner_id": "user_feishu_open_id"
            },
            "result_template": "合同创建成功\n合同ID：{id}\n合同名称：{contract_name}\n金额：{contract_amount}"
        },
        "required_params": ["opportunity_id", "contract_name", "signing_contact_id"],
        "optional_params": [],
        "permission_code": "contract:create",
        "sort_order": 3,
        "is_active": 1
    },

    # PaymentSkill - 2 个 Action
    {
        "skill_name": "PaymentSkill",
        "action_name": "plan_list",
        "display_name": "查询回款计划列表",
        "description": "查询回款计划列表",
        "handler_type": "QueryListHandler",
        "handler_config": {
            "crud_mapping": "payment_plan",
            "owner_filter": True,
            "display_fields": ["id", "contract_name", "plan_amount", "plan_date", "status"],
            "status_mapping": {
                "PENDING": "待回款",
                "PARTIAL": "部分回款",
                "COMPLETED": "已回款",
                "OVERDUE": "逾期"
            },
            "template": "共有 {total} 个回款计划，以下是最近10个：\n{items}"
        },
        "required_params": [],
        "optional_params": [],
        "permission_code": "payment:list",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "PaymentSkill",
        "action_name": "summary",
        "display_name": "查询合同回款汇总",
        "description": "查询合同回款汇总",
        "handler_type": "AggregateHandler",
        "handler_config": {
            "crud_mapping": "payment_record",
            "parent_crud_mapping": "contract",
            "aggregate_fields": ["total_amount", "paid_amount", "remaining_amount"],
            "template": "【回款汇总】\n合同ID：{contract_id}\n合同金额：{total_amount}\n已回款：{paid_amount}\n待回款：{remaining_amount}"
        },
        "required_params": ["contract_id"],
        "optional_params": [],
        "permission_code": "payment:read",
        "sort_order": 2,
        "is_active": 1
    },

    # InvoiceSkill - 2 个 Action
    {
        "skill_name": "InvoiceSkill",
        "action_name": "list",
        "display_name": "查询发票申请列表",
        "description": "查询发票申请列表",
        "handler_type": "QueryListHandler",
        "handler_config": {
            "crud_mapping": "invoice_application",
            "owner_filter": True,
            "display_fields": ["id", "contract_name", "invoice_amount", "invoice_type", "status"],
            "status_mapping": {
                "PENDING": "待审批",
                "APPROVED": "已审批",
                "ISSUED": "已开票",
                "REJECTED": "已拒绝"
            },
            "template": "共有 {total} 个发票申请，以下是最近10个：\n{items}"
        },
        "required_params": [],
        "optional_params": [],
        "permission_code": "invoice:list",
        "sort_order": 1,
        "is_active": 1
    },
    {
        "skill_name": "InvoiceSkill",
        "action_name": "detail",
        "display_name": "查询发票申请详情",
        "description": "查询发票申请详情",
        "handler_type": "QueryDetailHandler",
        "handler_config": {
            "crud_mapping": "invoice_application",
            "display_fields": ["id", "contract_name", "invoice_amount", "invoice_type", "status", "created_time"],
            "status_mapping": {
                "PENDING": "待审批",
                "APPROVED": "已审批",
                "ISSUED": "已开票",
                "REJECTED": "已拒绝"
            },
            "template": "【发票申请详情】\n申请ID：{id}\n合同：{contract_name}\n发票金额：{invoice_amount}\n发票类型：{invoice_type}\n状态：{status_text}\n创建时间：{created_time}"
        },
        "required_params": ["application_id"],
        "optional_params": [],
        "permission_code": "invoice:read",
        "sort_order": 2,
        "is_active": 1
    },
]


# ============================================================================
# CRUD 映射数据（26 个映射）
# ============================================================================
CRUD_MAPPING_DATA = [
    # Lead 相关
    {
        "mapping_name": "lead",
        "crud_module": "app.crud.lead",
        "crud_instance_name": "lead_crud",
        "model_class": "Lead",
        "schema_create_class": "LeadCreate",
        "schema_update_class": "LeadUpdate",
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "lead_name"
    },
    {
        "mapping_name": "lead_follow_up",
        "crud_module": "app.crud.lead",
        "crud_instance_name": "lead_follow_up_crud",
        "model_class": "LeadFollowUp",
        "schema_create_class": "LeadFollowUpCreate",
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None
    },

    # Customer 相关
    {
        "mapping_name": "customer",
        "crud_module": "app.crud.customer",
        "crud_instance_name": "customer_crud",
        "model_class": "Customer",
        "schema_create_class": "CustomerCreate",
        "schema_update_class": "CustomerUpdate",
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "account_name"
    },
    {
        "mapping_name": "customer_follow_up",
        "crud_module": "app.crud.customer_follow_up",
        "crud_instance_name": "customer_follow_up_crud",
        "model_class": "CustomerFollowUp",
        "schema_create_class": "CustomerFollowUpCreate",
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None
    },

    # Opportunity 相关
    {
        "mapping_name": "opportunity",
        "crud_module": "app.crud.opportunity",
        "crud_instance_name": "opportunity_crud",
        "model_class": "Opportunity",
        "schema_create_class": "OpportunityCreate",
        "schema_update_class": "OpportunityUpdate",
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "opportunity_name"
    },
    {
        "mapping_name": "opportunity_follow_up",
        "crud_module": "app.crud.opportunity",
        "crud_instance_name": "opportunity_follow_up_crud",
        "model_class": "OpportunityFollowUp",
        "schema_create_class": "OpportunityFollowUpCreate",
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None
    },

    # Contract 相关
    {
        "mapping_name": "contract",
        "crud_module": "app.crud.contract",
        "crud_instance_name": "contract_crud",
        "model_class": "Contract",
        "schema_create_class": "ContractCreate",
        "schema_update_class": "ContractUpdate",
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "contract_name"
    },

    # Payment 相关
    {
        "mapping_name": "payment_plan",
        "crud_module": "app.crud.payment",
        "crud_instance_name": "payment_plan_crud",
        "model_class": "PaymentPlan",
        "schema_create_class": "PaymentPlanCreate",
        "schema_update_class": "PaymentPlanUpdate",
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": None
    },
    {
        "mapping_name": "payment_record",
        "crud_module": "app.crud.payment",
        "crud_instance_name": "payment_record_crud",
        "model_class": "PaymentRecord",
        "schema_create_class": "PaymentRecordCreate",
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None
    },

    # Invoice 相关
    {
        "mapping_name": "invoice_application",
        "crud_module": "app.crud.invoice",
        "crud_instance_name": "invoice_application_crud",
        "model_class": "InvoiceApplication",
        "schema_create_class": "InvoiceApplicationCreate",
        "schema_update_class": "InvoiceApplicationUpdate",
        "owner_field": "creator_id",
        "status_field": "status",
        "name_field": None
    },
    {
        "mapping_name": "invoice_title",
        "crud_module": "app.crud.invoice",
        "crud_instance_name": "invoice_title_crud",
        "model_class": "InvoiceTitle",
        "schema_create_class": "InvoiceTitleCreate",
        "schema_update_class": "InvoiceTitleUpdate",
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": "title_name"
    },

    # User 相关
    {
        "mapping_name": "user",
        "crud_module": "app.crud.user",
        "crud_instance_name": "user_crud",
        "model_class": "User",
        "schema_create_class": None,
        "schema_update_class": None,
        "owner_field": None,
        "status_field": "status",
        "name_field": "name"
    },

    # Permission 相关
    {
        "mapping_name": "permission",
        "crud_module": "app.crud.permission",
        "crud_instance_name": "permission_crud",
        "model_class": "Permission",
        "owner_field": None,
        "status_field": None,
        "name_field": "name"
    },
    {
        "mapping_name": "role",
        "crud_module": "app.crud.role",
        "crud_instance_name": "role_crud",
        "model_class": "Role",
        "owner_field": None,
        "status_field": None,
        "name_field": "name"
    },

    # API Key 相关
    {
        "mapping_name": "api_key",
        "crud_module": "app.crud.api_key",
        "crud_instance_name": "api_key_crud",
        "model_class": "ApiKey",
        "owner_field": "creator_id",
        "status_field": "status",
        "name_field": "name"
    },
    {
        "mapping_name": "api_call_log",
        "crud_module": "app.crud.api_call_log",
        "crud_instance_name": "api_call_log_crud",
        "model_class": "ApiCallLog",
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None
    },

    # AI Config 相关
    {
        "mapping_name": "ai_config",
        "crud_module": "app.crud.ai_config",
        "crud_instance_name": "ai_config_crud",
        "model_class": "AIConfig",
        "owner_field": "creator_id",
        "status_field": "is_active",
        "name_field": "config_key"
    },
    {
        "mapping_name": "conversation_log",
        "crud_module": "app.crud.conversation_log",
        "crud_instance_name": "conversation_log_crud",
        "model_class": "ConversationLog",
        "owner_field": "user_id",
        "status_field": None,
        "name_field": None
    },

    # Approval 相关
    {
        "mapping_name": "approval",
        "crud_module": "app.crud.approval",
        "crud_instance_name": "approval_crud",
        "model_class": "Approval",
        "owner_field": "applicant_id",
        "status_field": "status",
        "name_field": None
    },

    # Operation Log 相关
    {
        "mapping_name": "operation_log",
        "crud_module": "app.crud.operation_log",
        "crud_instance_name": "operation_log_crud",
        "model_class": "OperationLog",
        "owner_field": "operator_id",
        "status_field": None,
        "name_field": None
    },
]


# ============================================================================
# Enum 映射数据（4 个映射）
# ============================================================================
ENUM_MAPPING_DATA = [
    {
        "enum_name": "lead_source",
        "display_name": "线索来源",
        "enum_class": "app.models.lead:LeadSource",
        "values": {
            "线上注册": "ONLINE_REGISTER",
            "市场活动": "MARKETING_ACTIVITY",
            "客户推荐": "REFERRAL",
            "电话营销": "COLD_CALL",
            "网站咨询": "WEBSITE_INQUIRY",
            "展会": "EXHIBITION",
            "其他": "OTHER"
        }
    },
    {
        "enum_name": "follow_up_method",
        "display_name": "跟进方式",
        "enum_class": "app.models.lead:FollowUpMethod",
        "values": {
            "电话": "PHONE",
            "微信": "WECHAT",
            "拜访": "VISIT",
            "邮件": "EMAIL",
            "其他": "OTHER"
        }
    },
    {
        "enum_name": "company_scale",
        "display_name": "团队规模",
        "enum_class": "app.models.lead:CompanyScale",
        "values": {
            "1-50人": "SCALE_1_50",
            "51-200人": "SCALE_51_200",
            "201-500人": "SCALE_201_500",
            "501-1000人": "SCALE_501_1000",
            "1000人以上": "SCALE_1000_PLUS"
        }
    },
    {
        "enum_name": "lead_status",
        "display_name": "线索状态",
        "enum_class": "app.models.lead:LeadStatus",
        "values": {
            "新建": "NEW",
            "跟进中": "FOLLOWING",
            "已转化": "CONVERTED",
            "无效": "INVALID"
        }
    },
]


def migrate_skills(db):
    """迁移 Skill 数据"""
    print("\n=== 开始迁移 Skill 数据 ===")

    migrated_count = 0
    for skill_data in SKILL_MIGRATION_DATA:
        existing = ai_skill_crud.get_by_name(db, skill_data["skill_name"])
        if existing:
            print(f"  Skill {skill_data['skill_name']} 已存在，跳过")
            continue

        ai_skill_crud.create(db, skill_data)
        migrated_count += 1
        print(f"  ✓ 创建 Skill: {skill_data['skill_name']}")

    print(f"=== Skill 迁移完成: {migrated_count}/{len(SKILL_MIGRATION_DATA)} ===")
    return migrated_count


def migrate_actions(db):
    """迁移 Action 数据"""
    print("\n=== 开始迁移 Action 数据 ===")

    migrated_count = 0
    for action_data in ACTION_MIGRATION_DATA:
        skill_name = action_data["skill_name"]
        skill = ai_skill_crud.get_by_name(db, skill_name)
        if not skill:
            print(f"  ✗ Skill {skill_name} 不存在，跳过 Action {action_data['action_name']}")
            continue

        existing = ai_skill_action_crud.get_by_skill_and_action(
            db, skill.id, action_data["action_name"]
        )
        if existing:
            print(f"  Action {skill_name}.{action_data['action_name']} 已存在，跳过")
            continue

        # 添加 skill_id
        action_create_data = {k: v for k, v in action_data.items() if k != "skill_name"}
        action_create_data["skill_id"] = skill.id

        ai_skill_action_crud.create(db, action_create_data)
        migrated_count += 1
        print(f"  ✓ 创建 Action: {skill_name}.{action_data['action_name']}")

    print(f"=== Action 迁移完成: {migrated_count}/{len(ACTION_MIGRATION_DATA)} ===")
    return migrated_count


def migrate_crud_mappings(db):
    """迁移 CRUD 映射数据"""
    print("\n=== 开始迁移 CRUD 映射数据 ===")

    migrated_count = 0
    for mapping_data in CRUD_MAPPING_DATA:
        existing = ai_crud_mapping_crud.get_by_name(db, mapping_data["mapping_name"])
        if existing:
            print(f"  CRUD 映射 {mapping_data['mapping_name']} 已存在，跳过")
            continue

        ai_crud_mapping_crud.create(db, mapping_data)
        migrated_count += 1
        print(f"  ✓ 创建 CRUD 映射: {mapping_data['mapping_name']}")

    print(f"=== CRUD 映射迁移完成: {migrated_count}/{len(CRUD_MAPPING_DATA)} ===")
    return migrated_count


def migrate_enum_mappings(db):
    """迁移 Enum 映射数据"""
    print("\n=== 开始迁移 Enum 映射数据 ===")

    migrated_count = 0
    for enum_data in ENUM_MAPPING_DATA:
        existing = ai_enum_mapping_crud.get_by_name(db, enum_data["enum_name"])
        if existing:
            print(f"  Enum 映射 {enum_data['enum_name']} 已存在，跳过")
            continue

        ai_enum_mapping_crud.create(db, enum_data)
        migrated_count += 1
        print(f"  ✓ 创建 Enum 映射: {enum_data['enum_name']}")

    print(f"=== Enum 映射迁移完成: {migrated_count}/{len(ENUM_MAPPING_DATA)} ===")
    return migrated_count


def verify_migration(db):
    """验证迁移数据完整性"""
    print("\n=== 开始验证迁移数据 ===")

    errors = []

    # 验证 Skills
    skills = ai_skill_crud.get_all_active(db)
    if len(skills) != len(SKILL_MIGRATION_DATA):
        errors.append(f"Skills 数量不匹配: 期望 {len(SKILL_MIGRATION_DATA)}, 实际 {len(skills)}")
    else:
        print(f"  ✓ Skills: {len(skills)} 个")

    # 验证 Actions
    actions = ai_skill_action_crud.get_all_active(db)
    if len(actions) != len(ACTION_MIGRATION_DATA):
        errors.append(f"Actions 数量不匹配: 期望 {len(ACTION_MIGRATION_DATA)}, 实际 {len(actions)}")
    else:
        print(f"  ✓ Actions: {len(actions)} 个")

    # 验证 CRUD 映射
    crud_mappings = ai_crud_mapping_crud.get_all(db)
    expected_crud_count = len(CRUD_MAPPING_DATA)
    if len(crud_mappings) < expected_crud_count:
        errors.append(f"CRUD 映射数量不足: 期望至少 {expected_crud_count}, 实际 {len(crud_mappings)}")
    else:
        print(f"  ✓ CRUD 映射: {len(crud_mappings)} 个")

    # 验证 Enum 映射
    enum_mappings = ai_enum_mapping_crud.get_all(db)
    if len(enum_mappings) != len(ENUM_MAPPING_DATA):
        errors.append(f"Enum 映射数量不匹配: 期望 {len(ENUM_MAPPING_DATA)}, 实际 {len(enum_mappings)}")
    else:
        print(f"  ✓ Enum 映射: {len(enum_mappings)} 个")

    if errors:
        print("\n=== 验证失败 ===")
        for error in errors:
            print(f"  ✗ {error}")
        return False
    else:
        print("\n=== 验证成功：所有数据已正确迁移 ===")
        return True


def main():
    """执行迁移"""
    import argparse

    parser = argparse.ArgumentParser(description="迁移 Skill 配置到数据库")
    parser.add_argument("--verify", action="store_true", help="仅验证数据完整性")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        if args.verify:
            success = verify_migration(db)
            sys.exit(0 if success else 1)
        else:
            print("=" * 50)
            print("CRMWolf Skill 配置迁移脚本")
            print("=" * 50)

            # 执行迁移
            skill_count = migrate_skills(db)
            action_count = migrate_actions(db)
            crud_count = migrate_crud_mappings(db)
            enum_count = migrate_enum_mappings(db)

            # 验证迁移
            print("\n" + "=" * 50)
            verify_migration(db)

            print("\n" + "=" * 50)
            print(f"迁移完成:")
            print(f"  Skills: {skill_count} 个")
            print(f"  Actions: {action_count} 个")
            print(f"  CRUD 映射: {crud_count} 个")
            print(f"  Enum 映射: {enum_count} 个")
            print("=" * 50)

    except Exception as e:
        print(f"\n✗ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()