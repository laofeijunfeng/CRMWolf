"""
Handler 配置 - 硬编码版

所有 CRUD 映射和枚举映射配置集中在此文件，不依赖数据库。

使用方式：
    from app.constants.handler_configs import CRUD_MAPPINGS, ENUM_MAPPINGS

    # 获取 CRUD 配置
    config = CRUD_MAPPINGS["lead"]
    crud = config["crud"]  # lead_crud
    model = config["model"]  # Lead

    # 获取枚举配置
    enum_config = ENUM_MAPPINGS["lead_status"]
    enum_class = enum_config["enum_class"]  # LeadStatus
    values = enum_config["values"]  # {"新建": 0, ...}
"""
from typing import Dict, Any, Optional, List

# ============================================================================
# CRUD 实例导入
# ============================================================================
from app.crud.lead import lead_crud, lead_follow_up_crud
from app.crud.customer import customer_crud
from app.crud.customer_follow_up import customer_follow_up_crud
from app.crud.opportunity import opportunity_crud
from app.crud.contract import contract_crud
from app.crud.payment import payment_plan_crud, payment_record_crud
from app.crud.invoice import invoice_application_crud, invoice_title_crud
from app.crud.user import user_crud
from app.crud.permission import permission_crud
from app.crud.role import role_crud

# ============================================================================
# Model 类导入
# ============================================================================
from app.models.lead import Lead, LeadFollowUp
from app.models.customer import Customer
from app.models.customer_follow_up import CustomerFollowUp
from app.models.opportunity import Opportunity
from app.models.contract import Contract
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.invoice import InvoiceApplication, InvoiceTitle
from app.models.user import User
from app.models.permission import Permission
from app.models.role import Role

# ============================================================================
# Schema 类导入
# ============================================================================
from app.schemas.lead import LeadCreate, LeadUpdate
from app.schemas.lead_follow_up import LeadFollowUpCreate
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.schemas.customer_follow_up import CustomerFollowUpCreate
from app.schemas.opportunity import OpportunityCreate, OpportunityUpdate
from app.schemas.contract import ContractCreate, ContractUpdate
from app.schemas.payment import PaymentPlanCreate, PaymentPlanUpdate, PaymentRecordCreate
from app.schemas.invoice import InvoiceApplicationCreate, InvoiceApplicationUpdate, InvoiceTitleCreate, InvoiceTitleUpdate

# ============================================================================
# 枚举类导入
# ============================================================================
from app.models.lead import LeadSource, LeadStatus, CompanyScale, FollowUpMethod
from app.models.customer import CustomerStatus
from app.models.opportunity import OpportunityStatus, PurchaseType, LicenseType


# ============================================================================
# CRUD 映射配置
# ============================================================================
CRUD_MAPPINGS: Dict[str, Dict[str, Any]] = {
    # Lead 相关
    "lead": {
        "crud": lead_crud,
        "model": Lead,
        "schema_create": LeadCreate,
        "schema_update": LeadUpdate,
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "lead_name",
    },
    "lead_follow_up": {
        "crud": lead_follow_up_crud,
        "model": LeadFollowUp,
        "schema_create": LeadFollowUpCreate,
        "schema_update": None,
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None,
    },

    # Customer 相关
    "customer": {
        "crud": customer_crud,
        "model": Customer,
        "schema_create": CustomerCreate,
        "schema_update": CustomerUpdate,
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "account_name",
    },
    "customer_follow_up": {
        "crud": customer_follow_up_crud,
        "model": CustomerFollowUp,
        "schema_create": CustomerFollowUpCreate,
        "schema_update": None,
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None,
    },

    # Opportunity 相关
    "opportunity": {
        "crud": opportunity_crud,
        "model": Opportunity,
        "schema_create": OpportunityCreate,
        "schema_update": OpportunityUpdate,
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "opportunity_name",
    },

    # Contract 相关
    "contract": {
        "crud": contract_crud,
        "model": Contract,
        "schema_create": ContractCreate,
        "schema_update": ContractUpdate,
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": "contract_name",
    },

    # Payment 相关
    "payment_plan": {
        "crud": payment_plan_crud,
        "model": PaymentPlan,
        "schema_create": PaymentPlanCreate,
        "schema_update": PaymentPlanUpdate,
        "owner_field": "owner_id",
        "status_field": "status",
        "name_field": None,
    },
    "payment_record": {
        "crud": payment_record_crud,
        "model": PaymentRecord,
        "schema_create": PaymentRecordCreate,
        "schema_update": None,
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": None,
    },

    # Invoice 相关
    "invoice_application": {
        "crud": invoice_application_crud,
        "model": InvoiceApplication,
        "schema_create": InvoiceApplicationCreate,
        "schema_update": InvoiceApplicationUpdate,
        "owner_field": "creator_id",
        "status_field": "status",
        "name_field": None,
    },
    "invoice_title": {
        "crud": invoice_title_crud,
        "model": InvoiceTitle,
        "schema_create": InvoiceTitleCreate,
        "schema_update": InvoiceTitleUpdate,
        "owner_field": "creator_id",
        "status_field": None,
        "name_field": "title_name",
    },

    # User 相关
    "user": {
        "crud": user_crud,
        "model": User,
        "schema_create": None,
        "schema_update": None,
        "owner_field": None,
        "status_field": "status",
        "name_field": "name",
    },

    # Permission 相关
    "permission": {
        "crud": permission_crud,
        "model": Permission,
        "schema_create": None,
        "schema_update": None,
        "owner_field": None,
        "status_field": None,
        "name_field": "name",
    },
    "role": {
        "crud": role_crud,
        "model": Role,
        "schema_create": None,
        "schema_update": None,
        "owner_field": None,
        "status_field": None,
        "name_field": "name",
    },
}


# ============================================================================
# 枚举映射配置
# ============================================================================
ENUM_MAPPINGS: Dict[str, Dict[str, Any]] = {
    # 线索相关
    "lead_source": {
        "enum_class": LeadSource,
        "display_name": "线索来源",
        # 中文 -> 枚举成员名（用于从中文获取枚举）
        "values": {
            "线上注册": "ONLINE_REGISTER",
            "市场活动": "MARKETING_ACTIVITY",
            "客户推荐": "REFERRAL",
            "电话营销": "COLD_CALL",
            "网站咨询": "WEBSITE_INQUIRY",
            "展会": "EXHIBITION",
            "其他": "OTHER",
        },
    },
    "lead_status": {
        "enum_class": LeadStatus,
        "display_name": "线索状态",
        # 中文 -> 枚举值（LeadStatus 是 int enum）
        "values": {
            "新建": 0,
            "跟进中": 1,
            "已转化": 2,
            "无效": 3,
        },
        # 枚举成员名 -> 中文（反向映射）
        "reverse_values": {
            "NEW": "新建",
            "FOLLOWING": "跟进中",
            "CONVERTED": "已转化",
            "INVALID": "无效",
        },
    },
    "follow_up_method": {
        "enum_class": FollowUpMethod,
        "display_name": "跟进方式",
        "values": {
            "电话": "PHONE",
            "微信": "WECHAT",
            "拜访": "VISIT",
            "邮件": "EMAIL",
            "其他": "OTHER",
        },
    },
    "company_scale": {
        "enum_class": CompanyScale,
        "display_name": "公司规模",
        "values": {
            "1-50人": "SCALE_1_50",
            "51-200人": "SCALE_51_200",
            "201-500人": "SCALE_201_500",
            "501-1000人": "SCALE_501_1000",
            "1000人以上": "SCALE_1000_PLUS",
        },
    },

    # 客户相关
    "customer_status": {
        "enum_class": CustomerStatus,
        "display_name": "客户状态",
        "values": {
            "跟进中": 0,
            "已成交": 1,
            "已流失": 2,
            "非激活": 3,
        },
        "reverse_values": {
            "FOLLOWING": "跟进中",
            "WON": "已成交",
            "LOST": "已流失",
            "INACTIVE": "非激活",
        },
    },

    # 商机相关
    "opportunity_status": {
        "enum_class": OpportunityStatus,
        "display_name": "商机状态",
        "values": {
            "跟进中": 0,
            "赢单": 1,
            "输单": 2,
        },
        "reverse_values": {
            "FOLLOWING": "跟进中",
            "WON": "赢单",
            "LOST": "输单",
        },
    },
    "purchase_type": {
        "enum_class": PurchaseType,
        "display_name": "采购类型",
        "values": {
            "新购": "NEW",
            "续购": "RENEWAL",
            "增购": "EXPANSION",
        },
    },
    "license_type": {
        "enum_class": LicenseType,
        "display_name": "授权模式",
        "values": {
            "订阅": "SUBSCRIPTION",
            "买断": "PERPETUAL",
        },
    },
}


# ============================================================================
# 辅助函数
# ============================================================================
def get_crud_config(mapping_name: str) -> Optional[Dict[str, Any]]:
    """获取 CRUD 映射配置"""
    return CRUD_MAPPINGS.get(mapping_name)


def get_enum_config(enum_name: str) -> Optional[Dict[str, Any]]:
    """获取枚举映射配置"""
    return ENUM_MAPPINGS.get(enum_name)


def get_enum_value(enum_class: Any, chinese_name: str, enum_config: Dict[str, Any]) -> Any:
    """
    从中文名称获取枚举值

    Args:
        enum_class: 枚举类
        chinese_name: 中文名称（如 "电话"）
        enum_config: 枚举配置

    Returns:
        枚举成员
    """
    values = enum_config.get("values", {})
    enum_key = values.get(chinese_name)
    if enum_key:
        return getattr(enum_class, enum_key)
    return None


def get_status_display_name(enum_config: Dict[str, Any], status_value: Any) -> str:
    """
    从状态值获取中文显示名称

    Args:
        enum_config: 枚举配置
        status_value: 状态值（整数）

    Returns:
        中文显示名称
    """
    values = enum_config.get("values", {})
    for display_name, value in values.items():
        if value == status_value:
            return display_name
    return str(status_value)


def get_status_enum_values(enum_class: Any, status_keys: List[str]) -> List[Any]:
    """
    从枚举成员名列表获取枚举值列表

    Args:
        enum_class: 枚举类
        status_keys: 枚举成员名列表（如 ["NEW", "FOLLOWING"]）

    Returns:
        枚举值列表（返回 .value 属性）
    """
    values = []
    for key in status_keys:
        try:
            enum_value = getattr(enum_class, key)
            values.append(enum_value.value if hasattr(enum_value, 'value') else enum_value)
        except AttributeError:
            continue
    return values