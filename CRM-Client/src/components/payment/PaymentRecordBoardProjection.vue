<script setup lang="ts">
import { computed } from 'vue'
import BoardView from '@/components/crmwolf/BoardView.vue'
import { Button } from '@/components/ui/button'
import type {
  BoardCardActivation,
  BoardCardPresentation,
  BoardMetadataRow,
  BoardProjection,
  BoardTrendPointPresentation,
  BoardTrendSeriesPresentation,
} from '@/components/crmwolf/boardTypes'
import type { PaymentRecordBoardResponse } from '@/schemas/paymentRecordBoard'
import { formatLocalDate } from '@/utils/format'

const props = withDefaults(defineProps<{
  response?: PaymentRecordBoardResponse | null
  loading?: boolean
  refreshing?: boolean
  stale?: boolean
  error?: Error | null
  canDrillThrough?: boolean
}>(), {
  response: null,
  loading: false,
  refreshing: false,
  stale: false,
  error: null,
  canDrillThrough: true,
})

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
  'card-action': [payload: { id: number, action: 'edit' | 'delete' | 'resubmit' }]
  retry: []
}>()

type PaymentRecordColumn = PaymentRecordBoardResponse['columns'][number]
type PaymentRecordItem = PaymentRecordColumn['items'][number]
type PaymentRecordTrend = PaymentRecordBoardResponse['trends'][number]
type ApprovalKey = PaymentRecordColumn['key']
type ConfirmationStatus = NonNullable<PaymentRecordItem['metadata']['confirmation_status']>

const approvalLabels: Record<ApprovalKey, string> = {
  pending_submit: '待提交',
  pending_approval: '审批中',
  rejected: '已驳回',
  approved: '已通过',
  unclassified: '未分类',
}

const confirmationLabels: Record<ConfirmationStatus, string> = {
  PENDING: '待确认',
  CONFIRMED: '已确认',
  DISPUTED: '有争议',
}

const trendSeries: BoardTrendSeriesPresentation[] = [
  {
    key: 'count',
    label: '回款笔数',
    color: 'hsl(var(--primary))',
    fillColor: 'hsl(var(--primary) / 0.16)',
  },
  {
    key: 'actual_amount',
    label: '回款金额',
    color: 'hsl(var(--chart-2, 199 89% 48%))',
    fillColor: 'hsl(var(--chart-2, 199 89% 48%) / 0.16)',
  },
  {
    key: 'confirmed_amount',
    label: '已确认金额',
    color: 'hsl(var(--chart-3, 142 71% 45%))',
    fillColor: 'hsl(var(--chart-3, 142 71% 45%) / 0.16)',
  },
  {
    key: 'unconfirmed_amount',
    label: '未确认金额',
    color: 'hsl(var(--chart-4, 38 92% 50%))',
    fillColor: 'hsl(var(--chart-4, 38 92% 50%) / 0.16)',
  },
]

function chartAmount(value: string): number {
  if (!/^-?\d+\.\d{2}$/.test(value)) throw new Error('invalid chart amount')
  return Number(value)
}

function localDateLabel(value: string): string {
  const [yearText, monthText, dayText] = value.split('-')
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return value
  return formatLocalDate(new Date(year, month - 1, day))
}

function confirmationLabel(item: PaymentRecordItem): string | null {
  const status = item.metadata.confirmation_status
  return status === null ? null : confirmationLabels[status]
}

function metadataRows(item: PaymentRecordItem): BoardMetadataRow[] {
  const confirmation = confirmationLabel(item)
  const rows: Array<[string, string, string | null]> = [
    ['customer_name', '客户', item.metadata.customer_name],
    ['contract_name', '合同', item.metadata.contract_name],
    ['actual_payer_name', '付款方', item.metadata.actual_payer_name],
    ['creator_name', '登记人', item.metadata.creator_name],
    ['owner_name', '负责人', item.metadata.owner_name],
    ['commission_member_name', '提成成员', item.metadata.commission_member_name],
    ['approval_status', '审批状态', approvalLabels[item.status]],
    ['confirmation_status', '确认状态', confirmation],
    ['record_id', '记录编号', String(item.id)],
  ]
  return rows.flatMap(([key, label, value]) => (value === null ? [] : [{ key, label, value }]))
}

function presentCard(column: PaymentRecordColumn, item: PaymentRecordItem): BoardCardPresentation {
  return {
    id: item.id,
    title: item.title,
    subtitle: item.subtitle,
    primaryValue: item.actual_amount,
    dateLabel: item.date === null ? null : localDateLabel(item.date),
    ownerLabel: item.owner?.name ?? null,
    statusLabel: approvalLabels[column.key],
    metadata: metadataRows(item),
  }
}

function recordChartPoint(source: PaymentRecordTrend): BoardTrendPointPresentation {
  return {
    month: source.date,
    values: {
      count: source.count,
      actual_amount: chartAmount(source.actual_amount),
      confirmed_amount: chartAmount(source.confirmed_amount),
      unconfirmed_amount: chartAmount(source.unconfirmed_amount),
    },
  }
}

const projection = computed<BoardProjection | null>(() => {
  const response = props.response
  if (response === null) return null
  return {
    metrics: response.summary.map((metric) => ({
      key: metric.key,
      label: metric.label,
      value: metric.value,
      valueType: metric.value_type,
      ...(metric.secondary_label == null || metric.secondary_value == null
        ? {}
        : {
            secondaryLabel: metric.secondary_label,
            secondaryValue: metric.secondary_value,
          }),
    })),
    columns: response.columns.map((column) => ({
      key: column.key,
      label: approvalLabels[column.key],
      tone: column.tone,
      countLabel: String(column.count),
      amountLabel: column.actual_amount,
      hasMore: column.has_more,
      remainingCount: column.remaining_count,
      cards: column.items.map((item) => presentCard(column, item)),
    })),
    trend: response.trends.length === 0
      ? null
      : {
          title: '回款记录趋势',
          description: '按完整月份统计回款金额和确认金额',
          series: trendSeries,
          points: response.trends.map(recordChartPoint),
        },
  }
})

function recordActions(cardId: string | number): Array<{ action: 'edit' | 'delete' | 'resubmit', label: string }> {
  const response = props.response
  if (response === null || typeof cardId !== 'number') return []
  for (const column of response.columns) {
    const item = column.items.find((candidate) => candidate.id === cardId)
    if (item === undefined) continue
    const actions: Array<{ action: 'edit' | 'delete' | 'resubmit', label: string }> = []
    if (item.action_state.can_edit) actions.push({ action: 'edit', label: '编辑' })
    if (item.action_state.can_delete) actions.push({ action: 'delete', label: '删除' })
    if (item.action_state.can_resubmit) actions.push({ action: 'resubmit', label: '重新提交' })
    return actions
  }
  return []
}
</script>

<template>
  <BoardView
    :projection="projection"
    :loading="props.loading"
    :refreshing="props.refreshing"
    :stale="props.stale"
    :error="props.error"
    :can-drill-through="props.canDrillThrough"
    @activate-card="emit('activate-card', $event)"
    @view-all="emit('view-all', $event)"
    @retry="emit('retry')"
  >
    <template #card-actions="{ card }">
      <Button
        v-for="action in recordActions(card.id)"
        :key="action.action"
        type="button"
        variant="outline"
        size="sm"
        :data-testid="`board-card-action-${action.action}`"
        @click="emit('card-action', { id: Number(card.id), action: action.action })"
      >
        {{ action.label }}
      </Button>
    </template>
  </BoardView>
</template>
