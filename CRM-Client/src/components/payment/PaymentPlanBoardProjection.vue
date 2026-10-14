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

function metadataRows(column: PaymentPlanColumn, item: PaymentPlanItem): BoardMetadataRow[] {
  const rows: Array<[string, string, string]> = [
    ['planned_amount', '计划金额', formatCurrency(item.planned_amount)],
    ['paid_amount', '已回款', formatCurrency(item.paid_amount)],
    ['remaining_amount', '待回款', formatCurrency(item.remaining_amount)],
    ['overdue_remaining_amount', '逾期待回款', formatCurrency(column.overdue_remaining_amount)],
    ['customer_name', '客户', item.metadata.customer_name ?? '-'],
    ['contract_name', '合同', item.metadata.contract_name ?? '-'],
    ['opportunity_name', '商机', item.metadata.opportunity_name ?? '-'],
    ['stage', '阶段', column.label],
    ['owner', '负责人', item.owner?.name ?? '-'],
    ['status_text', '状态', column.label],
    ['plan_id', '计划编号', String(item.id)],
  ]
  return rows.map(([key, label, value]) => ({ key, label, value }))
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
