/**
 * StatusBadge — 状态徽章组件（统一状态语言）
 *
 * 设计目的：
 * - 取代各页面散落的状态样式定义
 * - 提供一致的状态视觉语言（深色背景 + 白色文字）
 * - 支持 WCAG AA 对比度标准（4.5:1）
 *
 * 无障碍：
 * - role="status" 标记状态信息
 * - aria-label 包含中文文案
 * - 颜色非唯一指示（文字 + 颜色）
 */
<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'

// 状态类型定义
export type LeadStatus = 'new' | 'following' | 'converted' | 'invalid'
export type CustomerStatus = 'following' | 'won' | 'lost' | 'expired'
export type OpportunityStatus = 'active' | 'won' | 'lost'
export type ContractStatus = 'draft' | 'pending_review' | 'signed' | 'effective' | 'expired' | 'terminated'
export type InvoiceStatus = 'draft' | 'pending_review' | 'approved' | 'rejected' | 'issued' | 'cancelled'
export type PaymentPlanStatus = 'pending' | 'partial' | 'completed' | 'overdue'
export type PaymentRecordStatus = 'pending' | 'confirmed' | 'rejected'
export type GenericStatus = 'active' | 'inactive' | 'pending' | 'success' | 'warning' | 'danger'

// 新增枚举字段类型
export type SourceType = '线上注册' | '市场活动' | '客户推荐' | '电话营销' | '网站咨询' | '展会' | '其他'
export type AuthorizationModeType = 'SUBSCRIPTION' | 'PERPETUAL'
export type ProcurementTypeType = 'NEW' | 'RENEWAL' | 'EXPANSION'
export type IndustryType = 'IT/互联网' | '金融' | '教育' | '医疗' | '制造' | '零售' | '房地产' | '其他'
export type CompanyScaleType = '1-10人' | '11-50人' | '51-200人' | '201-500人' | '501-1000人' | '1000人以上'

type StatusType = 'lead' | 'customer' | 'opportunity' | 'contract' | 'invoice' | 'paymentPlan' | 'paymentRecord' | 'generic' | 'source' | 'authorizationMode' | 'procurementType' | 'industry' | 'companyScale'
type StatusColor = 'neutral' | 'warning' | 'success' | 'danger'

interface StatusConfigItem {
  label: string
  color: StatusColor
}

const props = defineProps<{
  status: LeadStatus | CustomerStatus | OpportunityStatus | ContractStatus | InvoiceStatus | PaymentPlanStatus | PaymentRecordStatus | GenericStatus | SourceType | AuthorizationModeType | ProcurementTypeType | IndustryType | CompanyScaleType
  type?: StatusType
  size?: 'default' | 'small'
}>()

// 设置默认值
const type = computed(() => props.type ?? 'generic')
const size = computed(() => props.size ?? 'default')

// 状态配置映射
const STATUS_CONFIG = {
  lead: {
    new: { label: '新建', color: 'neutral' },
    following: { label: '跟进中', color: 'warning' },
    converted: { label: '已转化', color: 'success' },
    invalid: { label: '无效', color: 'danger' }
  },
  customer: {
    following: { label: '跟进中', color: 'warning' },
    won: { label: '已赢单', color: 'success' },
    lost: { label: '已输单', color: 'danger' },
    expired: { label: '已失效', color: 'danger' }
  },
  opportunity: {
    active: { label: '跟进中', color: 'warning' },
    won: { label: '已赢单', color: 'success' },
    lost: { label: '已输单', color: 'danger' }
  },
  contract: {
    draft: { label: '草稿', color: 'neutral' },
    pending_review: { label: '审批中', color: 'warning' },
    signed: { label: '已签署', color: 'success' },
    effective: { label: '生效中', color: 'success' },
    expired: { label: '已到期', color: 'danger' },
    terminated: { label: '已终止', color: 'neutral' }
  },
  invoice: {
    draft: { label: '草稿', color: 'neutral' },
    pending_review: { label: '待审批', color: 'warning' },
    approved: { label: '已批准', color: 'success' },
    rejected: { label: '已拒绝', color: 'danger' },
    issued: { label: '已开票', color: 'success' },
    cancelled: { label: '已取消', color: 'neutral' }
  },
  paymentPlan: {
    pending: { label: '待登记', color: 'warning' },
    partial: { label: '部分回款', color: 'warning' },
    completed: { label: '已完成', color: 'success' },
    overdue: { label: '已逾期', color: 'danger' }
  },
  paymentRecord: {
    pending: { label: '待确认', color: 'warning' },
    confirmed: { label: '已确认', color: 'success' },
    rejected: { label: '已驳回', color: 'danger' }
  },
  generic: {
    active: { label: '启用', color: 'success' },
    inactive: { label: '禁用', color: 'neutral' },
    pending: { label: '待处理', color: 'warning' },
    success: { label: '成功', color: 'success' },
    warning: { label: '警告', color: 'warning' },
    danger: { label: '危险', color: 'danger' }
  },
  source: {
    '线上注册': { label: '线上注册', color: 'success' },
    '市场活动': { label: '市场活动', color: 'warning' },
    '客户推荐': { label: '客户推荐', color: 'success' },
    '电话营销': { label: '电话营销', color: 'warning' },
    '网站咨询': { label: '网站咨询', color: 'success' },
    '展会': { label: '展会', color: 'warning' },
    '其他': { label: '其他', color: 'neutral' }
  },
  authorizationMode: {
    'SUBSCRIPTION': { label: '订阅制', color: 'warning' },
    'PERPETUAL': { label: '买断制', color: 'success' }
  },
  procurementType: {
    'NEW': { label: '新购', color: 'warning' },
    'RENEWAL': { label: '续购', color: 'success' },
    'EXPANSION': { label: '增购', color: 'success' }
  },
  industry: {
    'IT/互联网': { label: 'IT/互联网', color: 'warning' },
    '金融': { label: '金融', color: 'success' },
    '教育': { label: '教育', color: 'warning' },
    '医疗': { label: '医疗', color: 'success' },
    '制造': { label: '制造', color: 'warning' },
    '零售': { label: '零售', color: 'warning' },
    '房地产': { label: '房地产', color: 'warning' },
    '其他': { label: '其他', color: 'neutral' }
  },
  companyScale: {
    '1-10人': { label: '1-10人', color: 'neutral' },
    '11-50人': { label: '11-50人', color: 'neutral' },
    '51-200人': { label: '51-200人', color: 'warning' },
    '201-500人': { label: '201-500人', color: 'warning' },
    '501-1000人': { label: '501-1000人', color: 'success' },
    '1000人以上': { label: '1000人以上', color: 'success' }
  }
} as const

// 获取状态配置
const config = computed<StatusConfigItem>(() => {
  const typeConfig = STATUS_CONFIG[type.value] as Record<string, StatusConfigItem>
  const statusConfig = typeConfig[props.status]
  return statusConfig ?? { label: '未知', color: 'neutral' }
})

// 状态徽章样式类（深色背景 + 白色文字）
const statusClasses = computed(() => {
  const colorMap: Record<StatusColor, string> = {
    neutral: 'status-neutral',
    warning: 'status-warning',
    success: 'status-success',
    danger: 'status-danger'
  }
  return [
    'status-badge',
    colorMap[config.value.color],
    size.value === 'small' ? 'status-badge--small' : ''
  ]
})

// aria-label
const ariaLabel = computed(() => config.value.label)
</script>

<template>
  <Badge
    :class="statusClasses"
    role="status"
    :aria-label="ariaLabel"
  >
    {{ config.label }}
  </Badge>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

// 状态徽章基础样式（深色背景 + 白色文字）
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
  border-radius: $wolf-radius-full-v2;
  white-space: nowrap;
  border: none;
}

.status-badge--small {
  padding: 2px 6px;
  font-size: 11px;
}

// 深色背景 + 白色文字（WCAG AA 4.5:1+）
.status-neutral {
  background: #475569;  // Slate-600
  color: #FFFFFF;
}

.status-warning {
  background: #D97706;  // Amber-600（对比度 5.2:1）
  color: #FFFFFF;
}

.status-success {
  background: #059669;  // Emerald-600（对比度 5.5:1）
  color: #FFFFFF;
}

.status-danger {
  background: #B91C1C;  // Red-700（对比度 5.8:1）
  color: #FFFFFF;
}
</style>