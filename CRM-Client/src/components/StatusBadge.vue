/**
 * StatusBadge — shared workflow and attribute status presentation.
 *
 * Status text remains the primary cue. The dot and semantic tone provide
 * scanning support without making color the only indicator.
 */
<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import {
  getStatusPresentation,
  type StatusDomain,
  type StatusTone,
} from '@/utils/statusPresentation'

export type LeadStatus = 'new' | 'following' | 'converted' | 'invalid'
export type CustomerStatus = 'following' | 'won' | 'lost' | 'expired'
export type CustomerDerivedStatusKey = 'not_started' | 'following' | 'repurchasing' | 'won' | 'lost' | 'public_pool'
export type OpportunityStatus = 'active' | 'won' | 'lost'
export type ContractStatus = 'draft' | 'pending_review' | 'signed' | 'expired' | 'terminated'
export type InvoiceStatus = 'draft' | 'pending_review' | 'approved' | 'rejected' | 'issued' | 'cancelled'
export type PaymentPlanStatus = 'pending' | 'partial' | 'completed' | 'overdue'
export type PaymentRecordStatus = 'pending' | 'confirmed' | 'rejected'
export type GenericStatus = 'active' | 'inactive' | 'pending' | 'success' | 'warning' | 'danger'
export type SourceType = string
export type AuthorizationModeType = 'SUBSCRIPTION' | 'PERPETUAL'
export type ProcurementTypeType = 'NEW' | 'RENEWAL' | 'EXPANSION'
export type IndustryType = string
export type CompanyScaleType = '1-50人' | '51-200人' | '201-500人' | '501-1000人' | '1000人以上'

export type StatusType = StatusDomain

const props = defineProps<{
  status: string
  type?: StatusType
  size?: 'default' | 'small'
}>()

const domain = computed<StatusDomain>(() => props.type ?? 'generic')
const presentation = computed(() => getStatusPresentation(domain.value, props.status))
const size = computed(() => props.size ?? 'default')
const isUnknown = computed(() => presentation.value.traceValue !== undefined)
const statusClasses = computed(() => [
  'status-badge',
  size.value === 'small' ? 'status-badge--small' : '',
])
const statusTone = computed<StatusTone>(() => presentation.value.tone)
const statusTitle = computed(() => {
  if (!isUnknown.value) return undefined
  return `${domain.value}: ${presentation.value.traceValue}`
})
</script>

<template>
  <Badge
    variant="status"
    :class="statusClasses"
    :data-status-tone="statusTone"
    :data-status-domain="domain"
    :data-status-value="status"
    :title="statusTitle"
    role="status"
    :aria-label="presentation.label"
  >
    <span class="status-badge-dot" aria-hidden="true"></span>
    {{ presentation.label }}
  </Badge>
</template>

<style scoped lang="scss">
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 9999px;
  white-space: nowrap;
  border: none;
}

.status-badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
  margin-right: 6px;
}

.status-badge--small {
  padding: 2px 6px;
  font-size: 11px;
}
</style>
