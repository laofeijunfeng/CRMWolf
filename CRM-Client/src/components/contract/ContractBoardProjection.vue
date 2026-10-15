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
import type { ContractBoardResponse } from '@/schemas/contractBoard'
import { formatLocalDate } from '@/utils/format'

const props = withDefaults(defineProps<{
  response?: ContractBoardResponse | null
  loading?: boolean
  refreshing?: boolean
  stale?: boolean
  error?: Error | null
  canDrillThrough?: boolean
  drillThroughColumnKeys?: readonly string[] | null
}>(), {
  response: null,
  loading: false,
  refreshing: false,
  stale: false,
  error: null,
  canDrillThrough: true,
  drillThroughColumnKeys: null,
})

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
  retry: []
}>()

type ContractColumn = ContractBoardResponse['columns'][number]
type ContractItem = ContractColumn['items'][number]
type ContractTrend = ContractBoardResponse['trends'][number]

const trendSeries: BoardTrendSeriesPresentation[] = [
  {
    key: 'count',
    label: '合同数',
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

function metadataRows(item: ContractItem): BoardMetadataRow[] {
  const rows: Array<[string, string, string | null]> = [
    ['customer_name', '客户', item.metadata.customer_name],
    ['opportunity_name', '商机', item.metadata.opportunity_name],
    ['license_type', '授权类型', item.metadata.license_type],
    ['purchase_type', '采购类型', item.metadata.purchase_type],
    ['signing_date', '签署日期', item.metadata.signing_date === null ? null : localDateLabel(item.metadata.signing_date)],
    ['effective_date', '生效日期', item.metadata.effective_date === null ? null : localDateLabel(item.metadata.effective_date)],
    ['expiry_date', '到期日期', item.metadata.expiry_date === null ? null : localDateLabel(item.metadata.expiry_date)],
    ['license_expiry_date', '授权到期', item.metadata.license_expiry_date === null ? null : localDateLabel(item.metadata.license_expiry_date)],
    ['authorized_users', '授权人数', item.metadata.authorized_users === null ? null : String(item.metadata.authorized_users)],
    ['contract_id', '合同编号', String(item.id)],
  ]
  return rows.flatMap(([key, label, value]) => (value === null ? [] : [{ key, label, value }]))
}

function presentCard(column: ContractColumn, item: ContractItem): BoardCardPresentation {
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

function contractChartPoint(source: ContractTrend): BoardTrendPointPresentation {
  return {
    month: source.date,
    values: {
      count: source.count,
      amount: chartAmount(source.amount),
    },
  }
}

function columnDrillEnabled(columnKey: string): boolean {
  const allowed = props.drillThroughColumnKeys
  return allowed === null || allowed.includes(columnKey)
}

const projection = computed<BoardProjection | null>(() => {
  const response = props.response
  if (response === null) return null
  return {
    metrics: response.summary.map((metric) => ({
      key: metric.key,
      label: metric.label,
      value: metric.value_type === 'amount' ? metric.value : String(metric.value),
      valueType: metric.value_type,
      ...(metric.secondary_label == null || metric.secondary_value == null
        ? {}
        : {
            secondaryLabel: metric.secondary_label,
            secondaryValue: metric.value_type === 'amount' ? metric.secondary_value : String(metric.secondary_value),
          }),
    })),
    columns: response.columns.map((column) => ({
      key: column.key,
      label: column.label,
      tone: column.tone,
      countLabel: String(column.count),
      amountLabel: column.amount,
      hasMore: column.has_more,
      remainingCount: column.remaining_count,
      drillThroughEnabled: columnDrillEnabled(column.key),
      cards: column.items.map((item) => presentCard(column, item)),
    })),
    trend: response.trends.length === 0
      ? null
      : {
          title: '合同趋势',
          description: '按完整月份统计合同数和金额',
          series: trendSeries,
          points: response.trends.map(contractChartPoint),
        },
  }
})
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
  />
</template>
