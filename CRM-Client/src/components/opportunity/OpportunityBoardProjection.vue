<script setup lang="ts">
import { computed } from 'vue'
import AmountText from '@/components/crmwolf/AmountText.vue'
import AreaTrendChart from '@/components/crmwolf/AreaTrendChart.vue'
import type { AreaTrendDatum, AreaTrendSeries } from '@/components/crmwolf/AreaTrendChart.vue'
import type {
  BoardCardActivation,
  BoardCardPresentation,
  BoardMetadataRow,
  BoardProjection,
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

interface OpportunityColumnView {
  source: OpportunityColumn
  cards: ReadonlyArray<{ source: OpportunityItem; card: BoardCardPresentation }>
}

const trendSeries: AreaTrendSeries[] = [
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
  ]
  return rows.filter((row): row is BoardMetadataRow => row !== null)
}

function presentCard(column: OpportunityColumn, item: OpportunityItem): BoardCardPresentation {
  return {
    id: item.id,
    title: item.title,
    subtitle: item.subtitle,
    primaryValue: item.amount === null ? null : formatCurrency(item.amount),
    dateLabel: item.date === null ? null : localDateLabel(item.date),
    ownerLabel: item.owner?.name ?? null,
    statusLabel: column.label,
    metadata: metadataRows(item),
  }
}

function viewAllPayload(column: OpportunityColumn): string {
  if (column.procurement_method_id !== null && column.procurement_stage_template_id !== null) {
    return `method:${column.procurement_method_id}:template:${column.procurement_stage_template_id}`
  }
  return column.key
}

function opportunityChartPoint(source: OpportunityTrend): AreaTrendDatum {
  return {
    month: source.date,
    count: source.count,
    amount: chartAmount(source.amount),
  }
}

const columns = computed<OpportunityColumnView[]>(() => props.response.columns.map((column) => ({
  source: column,
  cards: column.items.map((item) => ({ source: item, card: presentCard(column, item) })),
})))

const projection = computed<BoardProjection>(() => ({
  metrics: props.response.summary.map((metric) => ({
    key: metric.key,
    label: metric.label,
    value: metric.value_type === 'amount' ? formatCurrency(metric.value) : String(metric.value),
    valueType: metric.value_type,
    ...(metric.secondary_label == null || metric.secondary_value == null
      ? {}
      : {
          secondaryLabel: metric.secondary_label,
          secondaryValue: metric.value_type === 'amount'
            ? formatCurrency(metric.secondary_value)
            : String(metric.secondary_value),
        }),
  })),
  columns: columns.value.map((column) => ({
    key: column.source.key,
    label: column.source.label,
    tone: column.source.tone,
    countLabel: String(column.source.count),
    amountLabel: column.source.amount,
    hasMore: column.source.has_more,
    remainingCount: column.source.remaining_count,
    cards: column.cards.map((entry) => entry.card),
  })),
  trend: props.response.trends.length === 0
    ? null
    : {
        title: '商机趋势',
        description: '按完整月份统计商机数和金额',
        series: trendSeries,
        points: props.response.trends.map((source) => ({
          month: source.date,
          values: { count: source.count, amount: source.amount },
        })),
      },
}))

const chartData = computed(() => props.response.trends.map(opportunityChartPoint))

function activate(column: OpportunityColumn, item: OpportunityItem): void {
  emit('activate-card', { id: item.id, columnKey: column.key })
}
</script>

<template>
  <div class="domain-board-projection">
    <div class="board-columns">
      <section
        v-for="column in columns"
        :key="column.source.key"
        class="board-column"
        :data-column-key="column.source.key"
        :data-tone="column.source.tone"
      >
        <header>
          <h2>{{ column.source.label }}</h2>
          <span>{{ column.source.count }}</span>
        </header>
        <p>
          <AmountText :value="column.source.amount" size="sm" />
        </p>
        <article
          v-for="entry in column.cards"
          :key="String(entry.card.id)"
          class="board-card"
          tabindex="0"
          role="button"
          @click="activate(column.source, entry.source)"
          @keydown.enter.prevent="activate(column.source, entry.source)"
          @keydown.space.prevent="activate(column.source, entry.source)"
        >
          <h3>{{ entry.card.title }}</h3>
          <AmountText v-if="entry.source.amount !== null" :value="entry.source.amount" size="lg" />
          <p v-if="entry.card.primaryValue && entry.source.amount === null">{{ entry.card.primaryValue }}</p>
          <dl v-if="entry.card.metadata.length > 0">
            <div v-for="row in entry.card.metadata" :key="row.key">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
        </article>
        <p v-if="column.cards.length === 0">暂无记录</p>
        <button type="button" @click.stop="emit('view-all', viewAllPayload(column.source))">查看全部</button>
      </section>
    </div>

    <AreaTrendChart
      v-if="projection.trend"
      :title="projection.trend.title"
      :description="projection.trend.description"
      :data="chartData"
      :series="trendSeries"
      x-key="month"
    />
  </div>
</template>

<style scoped lang="scss">
.domain-board-projection {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.board-columns {
  display: grid;
  min-width: 0;
  grid-auto-flow: column;
  grid-auto-columns: minmax(240px, 320px);
  gap: 12px;
  overflow-x: auto;
  overscroll-behavior: contain;
}

.board-column,
.board-card {
  border-radius: 8px;
}

.board-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.board-card dl {
  display: grid;
  gap: 4px;
  margin: 0;
}

.board-card dl div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
</style>
