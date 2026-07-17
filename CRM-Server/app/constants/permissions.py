"""
系统权限定义

所有权限的完整列表，用于初始化新数据库
"""

# 所有系统权限定义
ALL_PERMISSIONS = [
    # 客户相关权限
    {"name": "查看所有客户", "code": "customer:view:all", "resource": "customer", "action": "view", "scope": "all"},
    {"name": "查看自己的客户", "code": "customer:view:own", "resource": "customer", "action": "view", "scope": "own"},
    {"name": "创建客户", "code": "customer:create", "resource": "customer", "action": "create"},
    {"name": "编辑自己的客户", "code": "customer:edit:own", "resource": "customer", "action": "edit", "scope": "own"},
    {"name": "编辑所有客户", "code": "customer:edit:all", "resource": "customer", "action": "edit", "scope": "all"},
    {"name": "删除自己的客户", "code": "customer:delete:own", "resource": "customer", "action": "delete", "scope": "own"},
    {"name": "退回客户到公海", "code": "customer:return", "resource": "customer", "action": "return"},
    {"name": "领取客户", "code": "customer:claim", "resource": "customer", "action": "claim"},
    {"name": "分配客户", "code": "customer:assign", "resource": "customer", "action": "assign"},
    {"name": "创建客户联系人", "code": "customer:contact:create", "resource": "customer_contact", "action": "create"},
    {"name": "编辑客户联系人", "code": "customer:contact:edit", "resource": "customer_contact", "action": "edit"},
    {"name": "删除客户联系人", "code": "customer:contact:delete", "resource": "customer_contact", "action": "delete"},
    {"name": "创建客户跟进", "code": "customer:follow_up:create", "resource": "customer_follow_up", "action": "create"},
    {"name": "编辑客户跟进", "code": "customer:follow_up:edit", "resource": "customer_follow_up", "action": "edit"},
    {"name": "删除客户跟进", "code": "customer:follow_up:delete", "resource": "customer_follow_up", "action": "delete"},

    # 线索相关权限
    {"name": "查看所有线索", "code": "lead:view:all", "resource": "lead", "action": "view", "scope": "all"},
    {"name": "查看自己的线索", "code": "lead:view:own", "resource": "lead", "action": "view", "scope": "own"},
    {"name": "创建线索", "code": "lead:create", "resource": "lead", "action": "create"},
    {"name": "编辑自己的线索", "code": "lead:edit:own", "resource": "lead", "action": "edit", "scope": "own"},
    {"name": "编辑所有线索", "code": "lead:edit:all", "resource": "lead", "action": "edit", "scope": "all"},
    {"name": "删除自己的线索", "code": "lead:delete:own", "resource": "lead", "action": "delete", "scope": "own"},
    {"name": "分配线索", "code": "lead:assign", "resource": "lead", "action": "assign"},
    {"name": "领取线索", "code": "lead:claim", "resource": "lead", "action": "claim"},
    {"name": "退回线索到公海", "code": "lead:return", "resource": "lead", "action": "return"},
    {"name": "转化线索", "code": "lead:convert", "resource": "lead", "action": "convert"},
    {"name": "创建线索跟进", "code": "lead:follow_up:create", "resource": "lead_follow_up", "action": "create"},
    {"name": "导入线索", "code": "lead:import", "resource": "lead", "action": "import"},

    # 商机相关权限
    {"name": "查看所有商机", "code": "opportunity:view:all", "resource": "opportunity", "action": "view", "scope": "all"},
    {"name": "查看自己的商机", "code": "opportunity:view:own", "resource": "opportunity", "action": "view", "scope": "own"},
    {"name": "创建商机", "code": "opportunity:create", "resource": "opportunity", "action": "create"},
    {"name": "编辑自己的商机", "code": "opportunity:edit:own", "resource": "opportunity", "action": "edit", "scope": "own"},
    {"name": "编辑所有商机", "code": "opportunity:edit:all", "resource": "opportunity", "action": "edit", "scope": "all"},
    {"name": "删除自己的商机", "code": "opportunity:delete:own", "resource": "opportunity", "action": "delete", "scope": "own"},
    {"name": "推进商机阶段", "code": "opportunity:stage", "resource": "opportunity", "action": "stage"},
    {"name": "标记商机赢单", "code": "opportunity:win", "resource": "opportunity", "action": "win"},
    {"name": "标记商机输单", "code": "opportunity:lose", "resource": "opportunity", "action": "lose"},
    {"name": "分配商机", "code": "opportunity:assign", "resource": "opportunity", "action": "assign"},
    {"name": "管理商机阶段", "code": "opportunity:stage:manage", "resource": "opportunity_stage", "action": "manage"},
    {"name": "创建商机阶段", "code": "opportunity:stage:create", "resource": "opportunity_stage", "action": "create"},
    {"name": "编辑商机阶段", "code": "opportunity:stage:edit", "resource": "opportunity_stage", "action": "edit"},
    {"name": "删除商机阶段", "code": "opportunity:stage:delete", "resource": "opportunity_stage", "action": "delete"},
    {"name": "查看商机分析", "code": "opportunity:analytics:view", "resource": "opportunity", "action": "analytics"},

    # 合同相关权限
    {"name": "查看所有合同", "code": "contract:view:all", "resource": "contract", "action": "view", "scope": "all"},
    {"name": "查看自己的合同", "code": "contract:view:own", "resource": "contract", "action": "view", "scope": "own"},
    {"name": "创建合同", "code": "contract:create", "resource": "contract", "action": "create"},
    {"name": "编辑自己的合同", "code": "contract:edit:own", "resource": "contract", "action": "edit", "scope": "own"},
    {"name": "编辑所有合同", "code": "contract:edit:all", "resource": "contract", "action": "edit", "scope": "all"},
    {"name": "删除自己的合同", "code": "contract:delete:own", "resource": "contract", "action": "delete", "scope": "own"},
    {"name": "提交合同审批", "code": "contract:submit", "resource": "contract", "action": "submit"},
    {"name": "撤回合同审批", "code": "contract:cancel", "resource": "contract", "action": "cancel"},

    # 发票相关权限
    {"name": "查看所有发票", "code": "invoice:view:all", "resource": "invoice", "action": "view", "scope": "all"},
    {"name": "查看自己的发票", "code": "invoice:view:own", "resource": "invoice", "action": "view", "scope": "own"},
    {"name": "创建发票申请", "code": "invoice:create", "resource": "invoice", "action": "create"},

    # 回款相关权限
    {"name": "查看所有回款", "code": "payment:view:all", "resource": "payment", "action": "view", "scope": "all"},
    {"name": "查看自己的回款", "code": "payment:view:own", "resource": "payment", "action": "view", "scope": "own"},
    {"name": "登记回款", "code": "payment:register", "resource": "payment", "action": "register"},
    {"name": "创建回款计划", "code": "payment:plan:create", "resource": "payment_plan", "action": "create"},
    {"name": "编辑回款计划", "code": "payment:plan:edit", "resource": "payment_plan", "action": "edit"},
    {"name": "删除回款计划", "code": "payment:plan:delete", "resource": "payment_plan", "action": "delete"},
    {"name": "查看所有回款计划", "code": "payment:plan:view:all", "resource": "payment_plan", "action": "view", "scope": "all"},

    # 审批流程权限
    {"name": "创建审批流程", "code": "approval:flow:create", "resource": "approval_flow", "action": "create"},
    {"name": "编辑审批流程", "code": "approval:flow:edit", "resource": "approval_flow", "action": "edit"},

    # 采购配置权限
    {"name": "查看采购方式", "code": "procurement_method:view", "resource": "procurement_method", "action": "view"},
    {"name": "创建采购方式", "code": "procurement_method:create", "resource": "procurement_method", "action": "create"},

    # 系统管理权限
    {"name": "管理用户", "code": "user:manage", "resource": "user", "action": "manage"},
    {"name": "管理角色", "code": "role:manage", "resource": "role", "action": "manage"},
    {"name": "管理权限", "code": "permission:manage", "resource": "permission", "action": "manage"},
    {"name": "系统配置", "code": "system:config", "resource": "system", "action": "config"},

    # API Key 权限
    {"name": "管理 API Key", "code": "apikey:manage", "resource": "apikey", "action": "manage"},

    # API 访问权限
    {"name": "API 线索列表", "code": "lead:api:list", "resource": "api", "action": "list"},
    {"name": "API 线索详情", "code": "lead:api:read", "resource": "api", "action": "read"},
    {"name": "API 客户列表", "code": "customer:api:list", "resource": "api", "action": "list"},
    {"name": "API 客户详情", "code": "customer:api:read", "resource": "api", "action": "read"},
    {"name": "API 商机列表", "code": "opportunity:api:list", "resource": "api", "action": "list"},
    {"name": "API 商机详情", "code": "opportunity:api:read", "resource": "api", "action": "read"},
    {"name": "API 合同列表", "code": "contract:api:list", "resource": "api", "action": "list"},
    {"name": "API 合同详情", "code": "contract:api:read", "resource": "api", "action": "read"},
    {"name": "API 创建回款", "code": "payment:api:create", "resource": "api", "action": "create"},
    {"name": "API 回款列表", "code": "payment:api:list", "resource": "api", "action": "list"},
    {"name": "API 回款详情", "code": "payment:api:read", "resource": "api", "action": "read"},
    {"name": "API 发票列表", "code": "invoice:api:list", "resource": "api", "action": "list"},

    # AI 相关权限
    {"name": "AI 配置管理", "code": "ai:manage", "resource": "ai", "action": "manage"},
    {"name": "AI 配置查看", "code": "ai:view", "resource": "ai", "action": "view"},

    # 统计和报表权限
    {"name": "查看统计数据", "code": "statistics:view", "resource": "statistics", "action": "view"},
    {"name": "查看报表", "code": "report:view:own", "resource": "report", "action": "view", "scope": "own"},
    {"name": "查看团队报表", "code": "report:view:team", "resource": "report", "action": "view", "scope": "team"},

    # 热力值权限
    {"name": "查看热力值配置", "code": "score:config:view", "resource": "score", "action": "config", "scope": "view"},
    {"name": "编辑热力值配置", "code": "score:config:edit", "resource": "score", "action": "config", "scope": "edit"},

    # ===== 补充缺失的权限定义 =====

    # 客户 - 补充 delete:all
    {"name": "删除所有客户", "code": "customer:delete:all", "resource": "customer", "action": "delete", "scope": "all"},

    # 线索 - 补充 delete:all
    {"name": "删除所有线索", "code": "lead:delete:all", "resource": "lead", "action": "delete", "scope": "all"},

    # 商机 - 补充 delete:all
    {"name": "删除所有商机", "code": "opportunity:delete:all", "resource": "opportunity", "action": "delete", "scope": "all"},

    # 合同 - 补充 delete:all 和审批权限
    {"name": "删除所有合同", "code": "contract:delete:all", "resource": "contract", "action": "delete", "scope": "all"},
    {"name": "审批所有合同", "code": "contract:approve:all", "resource": "contract", "action": "approve", "scope": "all"},
    {"name": "审批自己的合同", "code": "contract:approve:own", "resource": "contract", "action": "approve", "scope": "own"},

    # 发票 - 补充完整权限集
    {"name": "审批发票申请", "code": "invoice:approve", "resource": "invoice", "action": "approve"},
    {"name": "审批自己的发票", "code": "invoice:approve:own", "resource": "invoice", "action": "approve", "scope": "own"},
    {"name": "审批所有发票", "code": "invoice:approve:all", "resource": "invoice", "action": "approve", "scope": "all"},
    {"name": "标记已开票", "code": "invoice:mark_issued", "resource": "invoice", "action": "mark_issued"},
    {"name": "编辑发票申请", "code": "invoice:edit:own", "resource": "invoice", "action": "edit", "scope": "own"},
    {"name": "删除发票申请", "code": "invoice:delete:own", "resource": "invoice", "action": "delete", "scope": "own"},
    {"name": "创建发票抬头", "code": "invoice:title:create", "resource": "invoice_title", "action": "create"},
    {"name": "编辑发票抬头", "code": "invoice:title:edit", "resource": "invoice_title", "action": "edit"},
    {"name": "删除发票抬头", "code": "invoice:title:delete", "resource": "invoice_title", "action": "delete"},
    {"name": "设置默认抬头", "code": "invoice:title:set_default", "resource": "invoice_title", "action": "set_default"},
    {"name": "提交发票申请", "code": "invoice:submit", "resource": "invoice", "action": "submit"},
    {"name": "撤回发票申请", "code": "invoice:withdraw", "resource": "invoice", "action": "withdraw"},

    # 回款 - 补充完整权限集
    {"name": "提交回款审批", "code": "payment:submit", "resource": "payment", "action": "submit"},
    {"name": "撤回回款审批", "code": "payment:withdraw", "resource": "payment", "action": "withdraw"},
    {"name": "审批回款", "code": "payment:approve", "resource": "payment", "action": "approve"},
    {"name": "审批自己的回款", "code": "payment:approve:own", "resource": "payment", "action": "approve", "scope": "own"},
    {"name": "审批所有回款", "code": "payment:approve:all", "resource": "payment", "action": "approve", "scope": "all"},
    {"name": "编辑回款记录", "code": "payment:record:edit", "resource": "payment_record", "action": "edit"},
    {"name": "删除回款记录", "code": "payment:record:delete", "resource": "payment_record", "action": "delete"},
    {"name": "确认回款入账", "code": "payment:confirm", "resource": "payment", "action": "confirm"},

    # License - 补充审批权限集
    {"name": "审批License申请", "code": "license:approve", "resource": "license", "action": "approve"},
    {"name": "审批自己的License申请", "code": "license:approve:own", "resource": "license", "action": "approve", "scope": "own"},
    {"name": "审批所有License申请", "code": "license:approve:all", "resource": "license", "action": "approve", "scope": "all"},

    # 财务权限
    {"name": "查看财务审计日志", "code": "finance:audit:view", "resource": "finance", "action": "audit", "scope": "view"},
    {"name": "查看应收账款", "code": "finance:receivables:view", "resource": "finance", "action": "receivables", "scope": "view"},
    {"name": "查看财务报表", "code": "finance:reports:view", "resource": "finance", "action": "reports", "scope": "view"},
]

# 角色定义
ROLES_DATA = [
    {"name": "团队所有者", "code": "TEAM_ADMIN", "description": "团队所有者，拥有团队内所有权限"},
    {"name": "销售总监", "code": "SALES_DIRECTOR", "description": "销售总监，可查看团队所有数据"},
    {"name": "销售成员", "code": "SALES_MEMBER", "description": "销售成员，仅查看和操作自己的数据"},
    {"name": "财务人员", "code": "FINANCE", "description": "财务人员，发票审批、回款确认"},
]

# 角色权限映射
ROLE_PERMISSIONS_MAPPING = {
    "TEAM_ADMIN": "all",  # 所有权限
    "SALES_DIRECTOR": [
        "customer:view:all", "customer:view:own", "customer:create",
        "customer:edit:own", "customer:edit:all", "customer:delete:own", "customer:delete:all",
        "customer:return", "customer:claim", "customer:assign",
        "customer:contact:create", "customer:contact:edit", "customer:contact:delete",
        "customer:follow_up:create", "customer:follow_up:edit", "customer:follow_up:delete",
        "opportunity:view:all", "opportunity:view:own", "opportunity:create",
        "opportunity:edit:own", "opportunity:edit:all", "opportunity:delete:own", "opportunity:delete:all",
        "opportunity:stage", "opportunity:win", "opportunity:lose", "opportunity:assign",
        "opportunity:analytics:view", "opportunity:stage:manage",
        "opportunity:stage:create", "opportunity:stage:edit", "opportunity:stage:delete",
        "lead:view:all", "lead:view:own", "lead:create",
        "lead:edit:own", "lead:edit:all", "lead:delete:own", "lead:delete:all",
        "lead:assign", "lead:claim", "lead:return", "lead:convert",
        "lead:follow_up:create", "lead:import",
        "contract:view:all", "contract:view:own", "contract:create",
        "contract:edit:own", "contract:edit:all", "contract:delete:own", "contract:delete:all",
        "contract:submit", "contract:cancel", "contract:approve:own",
        "invoice:view:all", "invoice:view:own", "invoice:create",
        "invoice:approve:own",  # ← 审自己提交的发票
        "payment:view:all", "payment:view:own", "payment:register",
        "payment:approve:own",  # ← 审自己提交的回款
        "payment:plan:create", "payment:plan:edit", "payment:plan:delete", "payment:plan:view:all",
        "statistics:view", "report:view:own", "report:view:team",
        "score:config:view", "score:config:edit",
    ],
    "SALES_MEMBER": [
        "customer:view:own", "customer:create", "customer:edit:own",
        "customer:delete:own",  # ← 补充删除权限
        "customer:return", "customer:claim",
        "customer:contact:create", "customer:contact:edit", "customer:contact:delete",
        "customer:follow_up:create", "customer:follow_up:edit", "customer:follow_up:delete",
        "opportunity:view:own", "opportunity:create", "opportunity:edit:own",
        "opportunity:delete:own",  # ← 补充删除权限
        "opportunity:stage", "opportunity:win", "opportunity:lose",
        "lead:view:own", "lead:create", "lead:edit:own",
        "lead:delete:own",  # ← 补充删除权限
        "lead:claim", "lead:return", "lead:convert",
        "lead:follow_up:create", "lead:import",  # ← 补充导入权限
        "contract:view:own", "contract:create", "contract:edit:own",
        "contract:delete:own",  # ← 补充删除权限
        "contract:submit",
        "invoice:view:own", "invoice:create", "invoice:edit:own", "invoice:delete:own",
        "invoice:submit", "invoice:withdraw",
        "invoice:title:create", "invoice:title:edit", "invoice:title:delete", "invoice:title:set_default",
        "payment:view:own", "payment:register",
        "payment:plan:view:all", "payment:plan:create", "payment:plan:edit", "payment:plan:delete",
        "statistics:view", "score:config:view", "report:view:own",
    ],
    "FINANCE": [
        "invoice:view:all", "invoice:view:own", "invoice:create",
        "invoice:approve", "invoice:mark_issued",  # ← 补充核心财务权限
        "invoice:submit", "invoice:withdraw",  # ← 补充发票提交/撤回
        "invoice:title:create", "invoice:title:edit", "invoice:title:delete", "invoice:title:set_default",
        "payment:view:all", "payment:view:own", "payment:register",
        "payment:confirm",  # ← 补充回款确认权限
        "payment:submit", "payment:approve",  # ← 补充回款提交/审批
        "payment:plan:view:all", "payment:plan:create", "payment:plan:edit", "payment:plan:delete",
        "contract:view:all", "contract:view:own",
        "finance:audit:view", "finance:receivables:view", "finance:reports:view",  # ← 补充财务报表权限
        "statistics:view", "report:view:own",
    ],
}
