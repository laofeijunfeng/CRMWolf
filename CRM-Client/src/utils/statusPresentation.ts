export type StatusTone = 'neutral' | 'info' | 'warning' | 'success' | 'danger'

export type StatusDomain =
  | 'lead'
  | 'customer'
  | 'customerDerived'
  | 'opportunity'
  | 'contract'
  | 'invoice'
  | 'invoiceApplication'
  | 'licenseApplication'
  | 'approval'
  | 'paymentPlan'
  | 'paymentRecord'
  | 'generic'
  | 'source'
  | 'authorizationMode'
  | 'procurementType'
  | 'industry'
  | 'companyScale'

interface StatusConfig {
  readonly label: string
  readonly tone: StatusTone
}

export interface StatusPresentation extends StatusConfig {
  readonly traceValue?: string
}

export interface StatusOption {
  readonly value: string
  readonly label: string
}

const invoiceApplicationStatusMap: Record<string, StatusConfig> = {
  DRAFT: { label: '草稿', tone: 'neutral' },
  PENDING_REVIEW: { label: '待审批', tone: 'warning' },
  APPROVED: { label: '已批准', tone: 'success' },
  REJECTED: { label: '已驳回', tone: 'danger' },
  ISSUED: { label: '已开票', tone: 'success' },
  CANCELLED: { label: '已取消', tone: 'neutral' },
}

const statusMaps: Partial<Record<StatusDomain, Record<string, StatusConfig>>> = {
  lead: {
    new: { label: '新建', tone: 'neutral' },
    following: { label: '跟进中', tone: 'warning' },
    converted: { label: '已转化', tone: 'success' },
    invalid: { label: '无效', tone: 'danger' },
  },
  customer: {
    following: { label: '跟进中', tone: 'warning' },
    won: { label: '已赢单', tone: 'success' },
    lost: { label: '已输单', tone: 'danger' },
    expired: { label: '已失效', tone: 'danger' },
  },
  customerDerived: {
    not_started: { label: '未启动', tone: 'neutral' },
    following: { label: '跟进中', tone: 'info' },
    repurchasing: { label: '复购中', tone: 'success' },
    won: { label: '已成交', tone: 'success' },
    lost: { label: '已流失', tone: 'danger' },
    public_pool: { label: '公海', tone: 'neutral' },
  },
  opportunity: {
    active: { label: '跟进中', tone: 'warning' },
    won: { label: '已赢单', tone: 'success' },
    lost: { label: '已输单', tone: 'danger' },
  },
  contract: {
    draft: { label: '草稿', tone: 'neutral' },
    pending_review: { label: '审批中', tone: 'warning' },
    signed: { label: '已签署', tone: 'success' },
    expired: { label: '已到期', tone: 'danger' },
    terminated: { label: '已终止', tone: 'neutral' },
  },
  invoice: Object.fromEntries(
    Object.entries(invoiceApplicationStatusMap).map(([value, config]) => [value.toLowerCase(), config]),
  ),
  invoiceApplication: invoiceApplicationStatusMap,
  licenseApplication: {
    DRAFT: { label: '草稿', tone: 'neutral' },
    PENDING: { label: '待审批', tone: 'warning' },
    PENDING_REVIEW: { label: '待审批', tone: 'warning' },
    APPROVED: { label: '已批准', tone: 'success' },
    REJECTED: { label: '已驳回', tone: 'danger' },
    ISSUED: { label: '已签发', tone: 'info' },
  },
  approval: {
    PENDING: { label: '审批中', tone: 'warning' },
    APPROVED: { label: '已通过', tone: 'success' },
    REJECTED: { label: '已驳回', tone: 'danger' },
    CANCELLED: { label: '已撤回', tone: 'neutral' },
  },
  paymentPlan: {
    pending: { label: '待登记', tone: 'warning' },
    partial: { label: '部分回款', tone: 'warning' },
    completed: { label: '已登记', tone: 'success' },
    overdue: { label: '已逾期', tone: 'danger' },
  },
  paymentRecord: {
    pending: { label: '待确认', tone: 'warning' },
    confirmed: { label: '已确认', tone: 'success' },
    rejected: { label: '已驳回', tone: 'danger' },
  },
  generic: {
    active: { label: '启用', tone: 'success' },
    inactive: { label: '禁用', tone: 'neutral' },
    pending: { label: '待处理', tone: 'warning' },
    success: { label: '成功', tone: 'success' },
    warning: { label: '警告', tone: 'warning' },
    danger: { label: '危险', tone: 'danger' },
  },
  authorizationMode: {
    SUBSCRIPTION: { label: '订阅制', tone: 'warning' },
    PERPETUAL: { label: '买断制', tone: 'success' },
  },
  procurementType: {
    NEW: { label: '新购', tone: 'warning' },
    RENEWAL: { label: '续购', tone: 'success' },
    EXPANSION: { label: '增购', tone: 'info' },
  },
  companyScale: {
    '1-50人': { label: '1-50人', tone: 'neutral' },
    '51-200人': { label: '51-200人', tone: 'warning' },
    '201-500人': { label: '201-500人', tone: 'warning' },
    '501-1000人': { label: '501-1000人', tone: 'success' },
    '1000人以上': { label: '1000人以上', tone: 'success' },
  },
}

const unknownPresentation = (value: string | null | undefined): StatusPresentation => ({
  label: '未知状态',
  tone: 'neutral',
  ...(value === undefined || value === null ? {} : { traceValue: value }),
})

export const getStatusPresentation = (
  domain: StatusDomain,
  value: string | null | undefined,
): StatusPresentation => {
  if (domain === 'source' || domain === 'industry') {
    return value === undefined || value === null || value === ''
      ? unknownPresentation(value)
      : { label: value, tone: 'neutral' }
  }

  const map = statusMaps[domain]
  const known = value === undefined || value === null ? undefined : map && Object.prototype.hasOwnProperty.call(map, value) ? map[value] : undefined
  return known ?? unknownPresentation(value)
}

export const getStatusOptions = (domain: StatusDomain): StatusOption[] => {
  const map = statusMaps[domain]
  return map ? Object.entries(map).map(([value, config]) => ({ value, label: config.label })) : []
}
