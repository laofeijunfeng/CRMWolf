import { DEAL_JOURNEY_BOARD_STAGE_LABELS } from '@/utils/dealJourney'
import { LICENSE_PERMANENT_TEXT, LICENSE_STATUS_LABELS } from '@/utils/licenseStatus'

export type StatusTone = 'neutral' | 'info' | 'warning' | 'success' | 'danger'

export type StatusDomain =
  | 'lead'
  | 'customer'
  | 'customerDerived'
  | 'opportunity'
  | 'businessJourney'
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
  | 'approvalPhase'
  | 'invoiceEffectiveStatus'
  | 'licenseStatus'
  | 'paymentState'
  | 'paymentConfirmation'
  | 'agentInteraction'
  | 'agentFact'
  | 'agentDisposition'

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
  // 看板阶段只靠列标题与顺序表达；状态色只给结束态。
  businessJourney: {
    early_communication: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.early_communication, tone: 'neutral' },
    active_progress: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.active_progress, tone: 'neutral' },
    closing_soon: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.closing_soon, tone: 'neutral' },
    contract_processing: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.contract_processing, tone: 'neutral' },
    payment_processing: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.payment_processing, tone: 'neutral' },
    invoice_processing: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.invoice_processing, tone: 'neutral' },
    completed: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.completed, tone: 'success' },
    lost: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.lost, tone: 'danger' },
    approval_rejected: { label: DEAL_JOURNEY_BOARD_STAGE_LABELS.approval_rejected, tone: 'warning' },
  },
  approvalPhase: {
    draft: { label: '待提交', tone: 'neutral' },
    pending_review: { label: '审批中', tone: 'warning' },
    approved: { label: '审批通过', tone: 'success' },
    rejected: { label: '审批拒绝', tone: 'danger' },
  },
  contract: {
    draft: { label: '草稿', tone: 'neutral' },
    pending_review: { label: '审批中', tone: 'warning' },
    signed: { label: '已签署', tone: 'success' },
    effective: { label: '已签署', tone: 'success' },
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
  paymentState: {
    pending: { label: '未登记', tone: 'neutral' },
    registered: { label: '已登记', tone: 'info' },
    reviewing: { label: '审批中', tone: 'warning' },
    partial: { label: '部分回款', tone: 'warning' },
    completed: { label: '已回款', tone: 'success' },
    overdue: { label: '已逾期', tone: 'danger' },
  },
  paymentRecord: {
    pending: { label: '待确认', tone: 'warning' },
    confirmed: { label: '已确认', tone: 'success' },
    rejected: { label: '已驳回', tone: 'danger' },
  },
  paymentConfirmation: {
    PENDING: { label: '待确认', tone: 'warning' },
    CONFIRMED: { label: '已确认', tone: 'success' },
    DISPUTED: { label: '有争议', tone: 'danger' },
  },
  invoiceEffectiveStatus: {
    ACTIVE: { label: '有效', tone: 'success' },
    REISSUE_PENDING: { label: '重开中', tone: 'warning' },
    RED_OFFSET: { label: '已冲红', tone: 'danger' },
    REISSUED: { label: '已重开', tone: 'neutral' },
  },
  licenseStatus: {
    none: { label: LICENSE_STATUS_LABELS.none, tone: 'neutral' },
    expired: { label: LICENSE_STATUS_LABELS.expired, tone: 'danger' },
    trial: { label: LICENSE_STATUS_LABELS.trial, tone: 'warning' },
    official: { label: LICENSE_STATUS_LABELS.official, tone: 'success' },
    permanent: { label: `${LICENSE_STATUS_LABELS.official} · ${LICENSE_PERMANENT_TEXT}`, tone: 'success' },
  },
  agentInteraction: {
    pending: { label: '待处理', tone: 'info' },
    processing: { label: '处理中', tone: 'info' },
    done: { label: '已处理', tone: 'info' },
    updated: { label: '已更新', tone: 'success' },
    failed: { label: '提交失败', tone: 'danger' },
    expired: { label: '已过期', tone: 'neutral' },
    cancelled: { label: '已取消', tone: 'neutral' },
    history: { label: '历史', tone: 'neutral' },
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
  // 历史跟进任务处置：current / waiting 由前端定文案，其余文案由服务端 result_title 下发，这里只兜底。
  agentDisposition: {
    current: { label: '当前', tone: 'info' },
    waiting: { label: '待处理', tone: 'neutral' },
    complete: { label: '已完成', tone: 'success' },
    hold: { label: '先放着', tone: 'neutral' },
    skip: { label: '不管了', tone: 'neutral' },
    failed: { label: '未能完成', tone: 'danger' },
    unknown: { label: '结果待核对', tone: 'warning' },
  },
}

// 文本即标签的域：值原样显示。agentFact 为服务端给出的事实状态短语（≤40 字）。
const passThroughTones: Partial<Record<StatusDomain, StatusTone>> = {
  source: 'neutral',
  industry: 'neutral',
  agentFact: 'info',
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
  const passThroughTone = passThroughTones[domain]
  if (passThroughTone !== undefined) {
    return value === undefined || value === null || value === ''
      ? unknownPresentation(value)
      : { label: value, tone: passThroughTone }
  }

  const map = statusMaps[domain]
  const known = value === undefined || value === null ? undefined : map && Object.prototype.hasOwnProperty.call(map, value) ? map[value] : undefined
  return known ?? unknownPresentation(value)
}

export const getStatusOptions = (domain: StatusDomain): StatusOption[] => {
  const map = statusMaps[domain]
  return map ? Object.entries(map).map(([value, config]) => ({ value, label: config.label })) : []
}
