"""
AI 解析枚举映射配置

统一管理所有实体的枚举映射，避免硬编码散落各处
"""

# ==================== 线索枚举映射 ====================

# 线索来源枚举映射（用于 AI 解析）
LEAD_SOURCE_ENUM_MAP = {
    "线上注册": "ONLINE_REGISTER",
    "市场活动": "MARKETING_ACTIVITY",
    "客户推荐": "REFERRAL",
    "电话营销": "COLD_CALL",
    "网站咨询": "WEBSITE_INQUIRY",
    "展会": "EXHIBITION",
    "其他": "OTHER"
}

# ==================== 客户枚举映射 ====================

# 客户来源枚举映射（用于 AI 解析）
CUSTOMER_SOURCE_ENUM_MAP = {
    "线上注册": "ONLINE_REGISTER",
    "市场活动": "MARKETING_ACTIVITY",
    "客户推荐": "REFERRAL",
    "电话营销": "COLD_CALL",
    "网站咨询": "WEBSITE_INQUIRY",
    "展会": "EXHIBITION",
    "其他": "OTHER"
}

# ==================== 通用枚举映射 ====================

# 公司规模枚举映射（线索和客户共用）
COMPANY_SCALE_ENUM_MAP = {
    "1-50人": "SCALE_1_50",
    "51-200人": "SCALE_51_200",
    "201-500人": "SCALE_201_500",
    "501-1000人": "SCALE_501_1000",
    "1000人以上": "SCALE_1000_PLUS"
}