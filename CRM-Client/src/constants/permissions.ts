import type { PermissionResponse } from '@/schemas/role'

/**
 * 已停用的历史权限编码。
 *
 * 这些编码来自旧的开放 API 授权模型。它们仍可能存在于历史角色关联中，
 * 因此只从新的权限配置目录中隐藏，不在前端静默删除已有授权。
 */
export const DEPRECATED_PERMISSION_CODES: ReadonlySet<string> = new Set([
  'apikey:manage',
  'lead:api:list',
  'lead:api:read',
  'customer:api:list',
  'customer:api:read',
  'opportunity:api:list',
  'opportunity:api:read',
  'contract:api:list',
  'contract:api:read',
  'payment:api:create',
  'payment:api:list',
  'payment:api:read',
  'invoice:api:list',
])

/**
 * 判断权限是否仍可用于新角色授权。
 * resource=api/apikey 是对历史数据的兜底识别，避免遗漏未登记的旧编码。
 */
export const isDeprecatedPermission = (permission: Pick<PermissionResponse, 'code' | 'resource' | 'is_active'>): boolean => (
  permission.is_active === false
  || DEPRECATED_PERMISSION_CODES.has(permission.code)
  || permission.resource === 'api'
  || permission.resource === 'apikey'
)

export const isAssignablePermission = (permission: Pick<PermissionResponse, 'code' | 'resource' | 'is_active'>): boolean => (
  !isDeprecatedPermission(permission)
)

export const mergePermissionIdsPreservingDeprecated = (
  selectedPermissionIds: readonly number[],
  currentPermissions: readonly Pick<PermissionResponse, 'id' | 'code' | 'resource' | 'is_active'>[],
): number[] => {
  const preservedIds = currentPermissions
    .filter(permission => isDeprecatedPermission(permission))
    .map(permission => permission.id)

  return [...new Set([...selectedPermissionIds, ...preservedIds])]
}


/** 权限配置弹窗中的资源分组名称。权限编码保持英文，展示层统一使用中文。 */
export const PERMISSION_RESOURCE_NAMES: Readonly<Record<string, string>> = {
  acquisition_source: '获客来源',
  ai: 'AI 配置',
  approval_flow: '审批流程',
  contract: '合同',
  customer: '客户',
  customer_activity: '客户活动',
  customer_contact: '客户联系人',
  customer_follow_up: '客户跟进',
  customer_profile: '客户档案',
  finance: '财务',
  invoice: '发票',
  invoice_reissue: '发票重开',
  invoice_title: '发票抬头',
  lead: '线索',
  lead_follow_up: '线索跟进',
  license: 'License',
  opportunity: '商机',
  opportunity_stage: '商机阶段',
  payment: '回款',
  payment_plan: '回款计划',
  payment_record: '回款记录',
  permission: '权限',
  product: '产品',
  procurement_method: '采购方式',
  report: '报表',
  role: '角色',
  sales_dashboard: '销售看板',
  score: '热力值',
  statistics: '统计数据',
  system: '系统',
  user: '用户',
}

/** 权限动作的展示名称。后端 action 是稳定的权限码组成部分，不直接展示给用户。 */
export const PERMISSION_ACTION_NAMES: Readonly<Record<string, string>> = {
  analytics: '分析',
  approve: '审批',
  assign: '分配',
  audit: '审计',
  cancel: '撤回',
  claim: '领取',
  config: '配置',
  confirm: '确认',
  convert: '转化',
  correct: '纠正',
  create: '创建',
  delete: '删除',
  edit: '编辑',
  history: '历史',
  import: '导入',
  issue: '发放',
  lose: '标记输单',
  manage: '管理',
  mark_issued: '标记已开票',
  rebuild: '重建',
  receivables: '应收账款',
  refresh: '刷新',
  register: '登记',
  reports: '报表',
  return: '退回',
  set_default: '设为默认',
  stage: '推进阶段',
  submit: '提交',
  update: '更新',
  view: '查看',
  win: '标记赢单',
  withdraw: '撤回',
}

export const getPermissionResourceName = (resource: string): string => (
  PERMISSION_RESOURCE_NAMES[resource] ?? resource
)

export const getPermissionActionName = (action: string): string => (
  PERMISSION_ACTION_NAMES[action] ?? action
)
