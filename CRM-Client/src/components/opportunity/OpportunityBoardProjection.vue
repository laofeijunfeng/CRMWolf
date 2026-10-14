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
import type { OpportunityBoardResponse } from '@/schemas/opportunityBoard'
import { formatCurrency, formatLocalDate } from '@/utils/format'

const props = defineProps<{ response: OpportunityBoardResponse }>()

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [payload: string]
}>()

type OpportunityColumn = OpportunityBoardResponse['columns'][number]
type OpportunityItem = OpportunityColumn['items'][number]
type OpportunityTrend = OpportunityBoardResponse['trends'][number]

const trendSeries: BoardTrendSeriesPresentation[] = [
  {
    key: 'count',
    label: '商机数',
    color: 'hsl(var(--primary))',
    fillColor: 'hsl(var(--primary) / 0.16)',
  },
  {
    key: 'amount',
    label: '金额',
    color: 'hsl(var(--chart-2, 199 89% 48%))',
    fillColor: 'hsl(var(--chart-2, 199 89% 48%) / 0.16)',
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

function metadataRows(item: OpportunityItem): BoardMetadataRow[] {
  const probability = item.metadata.win_probability
  const closingDate = item.metadata.expected_closing_date
  const rows: Array<BoardMetadataRow | null> = [
    item.amount === null
      ? null
      : { key: 'amount', label: '金额', value: formatCurrency(item.amount) },
    item.metadata.customer_name === null
      ? null
      : { key: 'customer_name', label: '客户', value: item.metadata.customer_name },
    item.metadata.purchase_type === null
      ? null
      : { key: 'purchase_type', label: '采购类型', value: item.metadata.purchase_type },
    item.metadata.license_type === null
      ? null
      : { key: 'license_type', label: '授权类型', value: item.metadata.license_type },
    closingDate === null
      ? null
      : { key: 'expected_closing_date', label: '预计成交', value: localDateLabel(closingDate) },
    probability === null || !Number.isFinite(probability)
      ? null
      : { key: 'win_probability', label: '赢率', value: `${probability}%` },
    item.metadata.procurement_method_name === null
      ? null
      : { key: 'procurement_method_name', label: '采购方式', value: item.metadata.procurement_method_name },
    item.metadata.template_code === null
      ? null
      : { key: 'template_code', label: '模板', value: item.metadata.template_code },
    { key: 'public_id', label: '商机编号', value: item.id },
  ]
  return rows.filter((row): row is BoardMetadataRow => row !== null)
}

function presentCard(column: OpportunityColumn, item: OpportunityItem): BoardCardPresentation {
  return {
    id: item.id,
    title: item.title,
    subtitle: item.subtitle,
    primaryValue: item.amount,
    dateLabel: item.date === null ? null : localDateLabel(item.date),
    ownerLabel: item.owner?.name ?? null,
    statusLabel: column.label,
    metadata: metadataRows(item),
  }
}

function viewAllPayloadForKey(columnKey: string): string {
  const column = props.response.columns.find((item) => item.key === columnKey)
  if (
    column !== undefined
    && column.procurement_method_id !== null
    && column.procurement_stage_template_id !== null
  ) {
    return `method:${column.procurement_method_id}:template:${column.procurement_stage_template_id}`
  }
  return columnKey
}

function opportunityChartPoint(source: OpportunityTrend): BoardTrendPointPresentation {
  return {
    month: source.date,
    values: {
      count: source.count,
      amount: chartAmount(source.amount),
    },
  }
}

const projection = computed<BoardProjection>(() => ({
  metrics: props.response.summary.map((metric) => ({
    key: metric.key,
    label: metric.label,
    value: metric.value_type === 'amount' ? metric.value : String(metric.value),
    valueType: metric.value_type,
    ...(metric.secondary_label == null || metric.secondary_value == null
      ? {}
      : {
          secondaryLabel: metric.secondary_label,
          secondaryValue: metric.value_type === 'amount'
            ? metric.secondary_value
            : String(metric.secondary_value),
        }),
  })),
  columns: props.response.columns.map((column) => ({
    key: column.key,
    label: column.label,
    tone: column.tone,
    countLabel: String(column.count),
    amountLabel: column.amount,
    remainingCount: column.remaining_count,
    cards: column.items.map((item) => presentCard(column, item)),
  })),
  trend: props.response.trends.length === 0
    ? null
    : {
        title: '商机趋势',
        description: '按完整月份统计商机数和金额',
        series: trendSeries,
        points: props.response.trends.map(opportunityChartPoint),
      },
}))
</script>

<template>
  <BoardView
    :projection="projection"
    :can-drill-through="true"
    @activate-card="emit('activate-card', $event)"
    @view-all="emit('view-all', viewAllPayloadForKey($event))"
  />
</template>
