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
import type { CustomerBoardResponse } from '@/schemas/customerBoard'
import { formatDateRelative, formatLocalDate } from '@/utils/format'

const props = withDefaults(defineProps<{
  response?: CustomerBoardResponse | null
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
  'card-action': [payload: { id: string | number, action: 'edit' | 'delete' | 'assign' | 'create-opportunity' }]
  retry: []
}>()

type CustomerColumn = CustomerBoardResponse['columns'][number]
type CustomerItem = CustomerColumn['items'][number]
type CustomerTrend = CustomerBoardResponse['trends'][number]

const licenseLabels: Record<'TRIAL' | 'OFFICIAL', string> = {
  TRIAL: '试用授权',
  OFFICIAL: '正式授权',
}

const countSeries: BoardTrendSeriesPresentation = {
  key: 'count',
  label: '客户数',
  color: 'hsl(var(--primary))',
  fillColor: 'hsl(var(--primary) / 0.16)',
}

function localDateLabel(value: string): string {
  const [yearText, monthText, dayText] = value.split('-')
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return value
  return formatLocalDate(new Date(year, month - 1, day))
}

function metadataRows(item: CustomerItem): BoardMetadataRow[] {
  const expiry = item.metadata.license_expiry_date
  const rows: Array<BoardMetadataRow | null> = [
    item.metadata.stage_hint === null
      ? null
      : { key: 'stage_hint', label: '阶段提示', value: item.metadata.stage_hint },
    item.metadata.industry === null
      ? null
      : { key: 'industry', label: '行业', value: item.metadata.industry },
    item.metadata.city === null
      ? null
      : { key: 'city', label: '城市', value: item.metadata.city },
    item.metadata.company_scale === null
      ? null
      : { key: 'company_scale', label: '公司规模', value: item.metadata.company_scale },
    item.metadata.license_type === null
      ? null
      : { key: 'license_type', label: '授权类型', value: licenseLabels[item.metadata.license_type] },
    expiry === null
      ? null
      : { key: 'license_expiry_date', label: '授权到期', value: localDateLabel(expiry) },
    { key: 'public_id', label: '客户编号', value: item.id },
  ]
  return rows.filter((row): row is BoardMetadataRow => row !== null)
}

function presentCard(column: CustomerColumn, item: CustomerItem): BoardCardPresentation {
  return {
    id: item.id,
    title: item.title,
    subtitle: item.subtitle,
    primaryValue: item.amount,
    dateLabel: item.date === null ? null : formatDateRelative(item.date),
    ownerLabel: item.owner?.name ?? null,
    statusLabel: column.label,
    metadata: metadataRows(item),
  }
}

function customerChartPoint(source: CustomerTrend): BoardTrendPointPresentation {
  return {
    month: source.date,
    values: { count: source.count },
  }
}

const projection = computed<BoardProjection | null>(() => {
  const response = props.response
  if (response === null) return null
  return {
    metrics: response.summary.map((metric) => ({
      key: metric.key,
      label: metric.label,
      value: metric.value_type === 'percentage'
        ? (metric.value === null ? '-' : `${metric.value}%`)
        : String(metric.value),
      valueType: metric.value_type,
      ...(metric.secondary_label == null || metric.secondary_value == null
        ? {}
        : {
            secondaryLabel: metric.secondary_label,
            secondaryValue: String(metric.secondary_value),
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
      cards: column.items.map((item) => presentCard(column, item)),
    })),
    trend: response.trends.length === 0
      ? null
      : {
          title: '客户趋势',
          description: '按完整月份统计客户数',
          series: [countSeries],
          points: response.trends.map(customerChartPoint),
        },
  }
})

function cardActions(cardId: string | number): Array<{ action: 'edit' | 'delete' | 'assign' | 'create-opportunity', label: string }> {
  const response = props.response
  if (response === null) return []
  const publicId = String(cardId)
  for (const column of response.columns) {
    const item = column.items.find((candidate) => candidate.id === publicId)
    if (item === undefined) continue
    const actions: Array<{ action: 'edit' | 'delete' | 'assign' | 'create-opportunity', label: string }> = []
    if (item.action_state.can_edit) actions.push({ action: 'edit', label: '编辑' })
    if (item.action_state.can_assign) actions.push({ action: 'assign', label: '分配' })
    if (item.action_state.can_create_opportunity) actions.push({ action: 'create-opportunity', label: '新建商机' })
    if (item.action_state.can_delete) actions.push({ action: 'delete', label: '删除' })
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
        v-for="action in cardActions(card.id)"
        :key="action.action"
        type="button"
        variant="outline"
        size="sm"
        :data-testid="`board-card-action-${action.action}`"
        @click="emit('card-action', { id: card.id, action: action.action })"
      >
        {{ action.label }}
      </Button>
    </template>
  </BoardView>
</template>
