<script setup lang="ts">
import { Eye, FilePenLine, ReceiptText, Trash2 } from 'lucide-vue-next'
import AmountText from '@/components/crmwolf/AmountText.vue'
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
import { formatLocalDate } from '@/utils/format'

type PaymentRecordDeletePredicate = (record: PaymentRecordInfo) => boolean

interface Props {
  records: PaymentRecordInfo[]
  canRegister?: boolean
  canDelete?: boolean | PaymentRecordDeletePredicate
  canEditRecord?: (record: PaymentRecordInfo) => boolean
}

const props = withDefaults(defineProps<Props>(), {
  canRegister: true,
  canDelete: false,
  canEditRecord: () => true
})

const emit = defineEmits<{
  register: []
  'record-click': [record: PaymentRecordInfo]
  'edit-record': [record: PaymentRecordInfo]
  'delete-record': [record: PaymentRecordInfo]
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

const hasApprovalState = (record: PaymentRecordInfo): boolean => {
  return record.confirmation_status === 'PENDING' || record.approval_id !== undefined || record.approval !== undefined
}

const canDeleteRecord = (record: PaymentRecordInfo): boolean => {
  if (typeof props.canDelete === 'function') return props.canDelete(record)
  return props.canDelete
}

const canEditPaymentRecord = (record: PaymentRecordInfo): boolean => props.canEditRecord(record)

const handleRegister = (): void => {
  emit('register')
}

const handleRecordClick = (record: PaymentRecordInfo): void => {
  emit('record-click', record)
}

const handleEditRecord = (record: PaymentRecordInfo): void => {
  emit('edit-record', record)
}

const handleDeleteRecord = (record: PaymentRecordInfo): void => {
  emit('delete-record', record)
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
          <AmountText class="record-amount" :value="item.actual_amount" size="lg" />
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
          <span>实际付款方：{{ item.actual_payer_name || '-' }}</span>
          <span>登记人：{{ formatCreator(item) }}</span>
          <span>{{ formatInvoiceCount(item) }}</span>
        </div>
        <p v-if="item.notes" class="record-notes">{{ item.notes }}</p>
      </div>
    </template>

    <template #itemActions="{ item }">
      <Button
        v-if="canEditPaymentRecord(item)"
        variant="outline"
        size="icon"
        type="button"
        :aria-label="`编辑 ${formatDate(item.payment_date)} 回款记录`"
        @click.stop="handleEditRecord(item)"
      >
        <FilePenLine aria-hidden="true" />
      </Button>
      <Button
        v-if="canDeleteRecord(item)"
        variant="ghost"
        size="icon"
        type="button"
        :aria-label="`删除 ${formatDate(item.payment_date)} 回款记录`"
        @click.stop="handleDeleteRecord(item)"
      >
        <Trash2 class="record-delete-icon" aria-hidden="true" />
      </Button>
      <Button
        v-if="hasApprovalState(item)"
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
@use '@/styles/tokens.scss' as *;

.record-empty-card {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-lg);
}

.record-card-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: $space-3;
  padding: $space-3 $space-4;
  border-bottom: 1px solid hsl(var(--border));
}

.record-card-title {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: var(--font-size-body);
  font-weight: 600;
}

.record-empty-state {
  border: 0;
  padding: $space-6 $space-4;
}

.record-main {
  display: flex;
  flex-direction: column;
  gap: $space-2;
  min-width: 0;
}

.record-title-line {
  display: flex;
  align-items: center;
  gap: $space-2;
  flex-wrap: wrap;
}

.record-status-badge {
  border: 0;
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.record-status-warning {
  background: color-mix(in srgb, hsl(var(--status-warning)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-warning));
}

.record-status-success {
  background: color-mix(in srgb, hsl(var(--status-success)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-success));
}

.record-status-danger {
  background: color-mix(in srgb, hsl(var(--status-danger)) var(--status-bg-mix), transparent);
  color: hsl(var(--status-danger));
}

.record-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: $space-1 $space-3;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-caption);
  line-height: 20px;

  @media (max-width: $bp-sm - 1) {
    grid-template-columns: 1fr;
  }
}

.record-notes {
  margin: 0;
  color: hsl(var(--muted-foreground));
  font-size: var(--font-size-body);
  line-height: 20px;
  word-break: break-word;
}

.record-delete-icon {
  color: hsl(var(--status-danger));
}

@media (prefers-reduced-motion: reduce) {
  .record-main {
    transition-duration: 0.01ms;
  }
}
</style>
