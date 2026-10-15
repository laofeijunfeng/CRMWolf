<script setup lang="ts">
import { computed } from 'vue'
import BoardView from '@/components/crmwolf/BoardView.vue'
import type {
  BoardCardActivation,
  BoardCardPresentation,
  BoardMetadataRow,
  BoardProjection,
  BoardTrendPointPresentation,
  BoardTrendSeriesPresentation,
} from '@/components/crmwolf/boardTypes'
import type { PaymentPlanBoardResponse } from '@/schemas/paymentPlanBoard'
import { formatCurrency, formatLocalDate } from '@/utils/format'

const props = defineProps<{ response: PaymentPlanBoardResponse }>()

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
}>()

type PaymentPlanColumn = PaymentPlanBoardResponse['columns'][number]
type PaymentPlanItem = PaymentPlanColumn['items'][number]
type PaymentPlanTrend = PaymentPlanBoardResponse['trends'][number]

const trendSeries: BoardTrendSeriesPresentation[] = [
  {
    key: 'count',
    label: '计划数',
    color: 'hsl(var(--primary))',
    fillColor: 'hsl(var(--primary) / 0.16)',
  },
  {
    key: 'planned_amount',
    label: '计划金额',
    color: 'hsl(var(--chart-2, 199 89% 48%))',
    fillColor: 'hsl(var(--chart-2, 199 89% 48%) / 0.16)',
  },
  {
    key: 'paid_amount',
    label: '已回款',
    color: 'hsl(var(--chart-3, 142 71% 45%))',
    fillColor: 'hsl(var(--chart-3, 142 71% 45%) / 0.16)',
  },
  {
    key: 'remaining_amount',
    label: '待回款',
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

function planOverdueRemaining(item: PaymentPlanItem): BoardMetadataRow | null {
  if (item.status !== 'OVERDUE') return null
  const amount = Number(item.remaining_amount)
  if (!Number.isFinite(amount) || amount === 0) return null
  return {
    key: 'overdue_remaining_amount',
    label: '逾期待回款',
    value: formatCurrency(item.remaining_amount),
  }
}


function metadataRows(column: PaymentPlanColumn, item: PaymentPlanItem): BoardMetadataRow[] {
  const rows: Array<BoardMetadataRow | null> = [
    { key: 'planned_amount', label: '计划金额', value: formatCurrency(item.planned_amount) },
    { key: 'paid_amount', label: '已回款', value: formatCurrency(item.paid_amount) },
    { key: 'remaining_amount', label: '待回款', value: formatCurrency(item.remaining_amount) },
    planOverdueRemaining(item),
    { key: 'customer_name', label: '客户', value: item.metadata.customer_name ?? '-' },
    { key: 'contract_name', label: '合同', value: item.metadata.contract_name ?? '-' },
    { key: 'opportunity_name', label: '商机', value: item.metadata.opportunity_name ?? '-' },
    { key: 'stage', label: '阶段', value: column.label },
    { key: 'owner', label: '负责人', value: item.owner?.name ?? '-' },
    { key: 'status_text', label: '状态', value: column.label },
    { key: 'plan_id', label: '计划编号', value: String(item.id) },
  ]
  return rows.filter((row): row is BoardMetadataRow => row !== null)
}

function presentCard(column: PaymentPlanColumn, item: PaymentPlanItem): BoardCardPresentation {
  return {
    id: item.id,
    title: item.title,
    subtitle: item.subtitle,
    primaryValue: item.planned_amount,
    dateLabel: item.date === null ? null : localDateLabel(item.date),
    ownerLabel: item.owner?.name ?? null,
    statusLabel: column.label,
    metadata: metadataRows(column, item),
  }
}

function planChartPoint(source: PaymentPlanTrend): BoardTrendPointPresentation {
  return {
    month: source.date,
    values: {
      count: source.count,
      planned_amount: chartAmount(source.planned_amount),
      paid_amount: chartAmount(source.paid_amount),
      remaining_amount: chartAmount(source.remaining_amount),
    },
  }
}

const projection = computed<BoardProjection>(() => ({
  metrics: props.response.summary.map((metric) => ({
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
  columns: props.response.columns.map((column) => ({
    key: column.key,
    label: column.label,
    tone: column.tone,
    countLabel: String(column.count),
    amountLabel: column.overdue_remaining_amount,
    hasMore: column.has_more,
    remainingCount: column.remaining_count,
    cards: column.items.map((item) => presentCard(column, item)),
  })),
  trend: props.response.trends.length === 0
    ? null
    : {
        title: '回款计划趋势',
        description: '按完整月份统计计划、已回款和待回款',
        series: trendSeries,
        points: props.response.trends.map(planChartPoint),
      },
}))
</script>

<template>
  <BoardView
    :projection="projection"
    :can-drill-through="true"
    @activate-card="emit('activate-card', $event)"
    @view-all="emit('view-all', $event)"
  />
</template>
