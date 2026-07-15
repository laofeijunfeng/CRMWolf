<script setup lang="ts">
import { Eye, FilePenLine, ReceiptText } from 'lucide-vue-next'
import ListCard from '@/components/crmwolf/ListCard.vue'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle
} from '@/components/ui/empty'
import type { PaymentConfirmationStatus, PaymentRecordInfo } from '@/api/payment'
import { formatCurrency, formatLocalDate } from '@/utils/format'

interface Props {
  records: PaymentRecordInfo[]
  canRegister?: boolean
}

withDefaults(defineProps<Props>(), {
  canRegister: true
})

const emit = defineEmits<{
  register: []
  'record-click': [record: PaymentRecordInfo]
  'edit-record': [record: PaymentRecordInfo]
  'view-approval': [record: PaymentRecordInfo]
}>()

const getStatusLabel = (status: PaymentConfirmationStatus | undefined): string => {
  if (status === 'CONFIRMED') return '已确认'
  if (status === 'DISPUTED') return '有争议'
  return '待确认'
}

const getStatusClass = (status: PaymentConfirmationStatus | undefined): string => {
  if (status === 'CONFIRMED') return 'record-status-success'
  if (status === 'DISPUTED') return 'record-status-danger'
  return 'record-status-warning'
}

const formatDate = (dateStr: string | undefined): string => {
  if (dateStr === undefined || dateStr.trim() === '') return '-'
  const date = new Date(dateStr)
  return Number.isNaN(date.getTime()) ? '-' : formatLocalDate(date)
}

const formatCreator = (record: PaymentRecordInfo): string => {
  const creatorName = record.creator_name?.trim()
  return creatorName === undefined || creatorName === '' ? '未知登记人' : creatorName
}

const formatInvoiceCount = (record: PaymentRecordInfo): string => {
  const count = record.invoice_application_count ?? 0
  return count > 0 ? `${count} 张发票` : '未关联发票'
}

const hasApprovalSeam = (record: PaymentRecordInfo): boolean => {
  return record.confirmation_status === 'PENDING' || record.approval_id !== undefined || record.approval !== undefined
}

const handleRegister = (): void => {
  emit('register')
}

const handleRecordClick = (record: PaymentRecordInfo): void => {
  emit('record-click', record)
}

const handleEditRecord = (record: PaymentRecordInfo): void => {
  emit('edit-record', record)
}

const handleViewApproval = (record: PaymentRecordInfo): void => {
  emit('view-approval', record)
}
</script>

<template>
  <Card v-if="records.length === 0" class="record-empty-card">
    <CardHeader class="record-card-header">
      <CardTitle class="record-card-title">回款记录</CardTitle>
      <Button
        v-if="canRegister"
        size="sm"
        type="button"
        aria-label="登记回款"
        @click="handleRegister"
      >
        <ReceiptText data-icon="inline-start" aria-hidden="true" />
        登记回款
      </Button>
    </CardHeader>
    <CardContent>
      <Empty class="record-empty-state">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ReceiptText aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle>暂无回款记录</EmptyTitle>
          <EmptyDescription>登记实际到账金额后，可在这里跟踪审批与开票关联。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </CardContent>
  </Card>

  <ListCard
    v-else
    title="回款记录"
    :items="records"
    row-interactive
    empty-text="暂无回款记录"
    @row-click="handleRecordClick"
  >
    <template #headerActions>
      <Button
        v-if="canRegister"
        size="sm"
        type="button"
        aria-label="登记回款"
        @click="handleRegister"
      >
        <ReceiptText data-icon="inline-start" aria-hidden="true" />
        登记回款
      </Button>
    </template>

    <template #itemMain="{ item }">
      <div class="record-main">
        <div class="record-title-line">
          <span class="record-amount">{{ formatCurrency(item.actual_amount) }}</span>
          <Badge
            :class="['record-status-badge', getStatusClass(item.confirmation_status)]"
            role="status"
            :aria-label="getStatusLabel(item.confirmation_status)"
          >
            {{ getStatusLabel(item.confirmation_status) }}
          </Badge>
        </div>
        <div class="record-meta-grid" aria-label="回款记录属性">
          <span>回款日期：{{ formatDate(item.payment_date) }}</span>
          <span>登记人：{{ formatCreator(item) }}</span>
          <span>{{ formatInvoiceCount(item) }}</span>
        </div>
        <p v-if="item.notes" class="record-notes">{{ item.notes }}</p>
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        variant="outline"
        size="icon"
        type="button"
        :aria-label="`编辑 ${formatDate(item.payment_date)} 回款记录`"
        @click.stop="handleEditRecord(item)"
      >
        <FilePenLine aria-hidden="true" />
      </Button>
      <Button
        v-if="hasApprovalSeam(item)"
        variant="ghost"
        size="icon"
        type="button"
        :aria-label="`查看 ${formatDate(item.payment_date)} 回款审批`"
        @click.stop="handleViewApproval(item)"
      >
        <Eye aria-hidden="true" />
      </Button>
    </template>
  </ListCard>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.record-empty-card {
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-lg-v2;
}

.record-card-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-md-v2 $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-light-v2;
}

.record-card-title {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.record-empty-state {
  border: 0;
  padding: $wolf-space-xl-v2 $wolf-space-lg-v2;
}

.record-main {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-sm-v2;
  min-width: 0;
}

.record-title-line {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  flex-wrap: wrap;
}

.record-amount {
  font-family: $wolf-font-mono-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  color: $wolf-text-primary-v2;
  font-variant-numeric: tabular-nums;
}

.record-status-badge {
  border: 0;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.record-status-warning {
  background: $wolf-warning-bg-v2;
  color: $wolf-warning-text-v2;
}

.record-status-success {
  background: $wolf-success-bg-v2;
  color: $wolf-success-text-v2;
}

.record-status-danger {
  background: $wolf-danger-bg-v2;
  color: $wolf-danger-text-v2;
}

.record-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: $wolf-space-xs-v2 $wolf-space-md-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: $wolf-line-height-body-v2;

  @media (max-width: $wolf-breakpoint-sm-v2 - 1) {
    grid-template-columns: 1fr;
  }
}

.record-notes {
  margin: 0;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
  line-height: $wolf-line-height-body-v2;
  word-break: break-word;
}

@media (prefers-reduced-motion: reduce) {
  .record-main {
    transition-duration: $wolf-reduced-motion-duration-v2;
  }
}
</style>
