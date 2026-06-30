# app/constants/approval_roles.py

"""
审批流程预定义角色常量

审批节点的 approve_role 必须使用系统预定义角色编码，
确保审批流程能正确匹配审批人。
"""

ALLOWED_APPROVAL_ROLES = [
    "TEAM_ADMIN",       # 团队所有者
    "SALES_DIRECTOR",   # 销售总监
    "FINANCE",          # 财务人员
    "SALES_MEMBER",     # 销售成员
]

ROLE_DISPLAY_NAMES = {
    "TEAM_ADMIN": "团队所有者",
    "SALES_DIRECTOR": "销售总监",
    "FINANCE": "财务人员",
    "SALES_MEMBER": "销售成员",
}

# 用户描述 → 角色编码映射（用于 System Prompt 示例）
ROLE_MAPPING_EXAMPLES = {
    "总经理审批": "TEAM_ADMIN",
    "老板审批": "TEAM_ADMIN",
    "最高审批": "TEAM_ADMIN",
    "部门经理审批": "SALES_DIRECTOR",
    "销售审批": "SALES_DIRECTOR",
    "总监审批": "SALES_DIRECTOR",
    "财务审批": "FINANCE",
    "财务审核": "FINANCE",
    "财务确认": "FINANCE",
    "普通审批": "SALES_MEMBER",
    "基础审批": "SALES_MEMBER",
}