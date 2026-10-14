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
import type { CustomerBoardResponse } from '@/schemas/customerBoard'
import { formatDateRelative, formatLocalDate } from '@/utils/format'

const props = defineProps<{ response: CustomerBoardResponse }>()

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
}>()

type CustomerColumn = CustomerBoardResponse['columns'][number]
type CustomerItem = CustomerColumn['items'][number]
type CustomerTrend = CustomerBoardResponse['trends'][number]

interface CustomerColumnView {
  source: CustomerColumn
  cards: ReadonlyArray<{ source: CustomerItem; card: BoardCardPresentation }>
}

const licenseLabels: Record<'TRIAL' | 'OFFICIAL', string> = {
  TRIAL: '试用授权',
  OFFICIAL: '正式授权',
}

const countSeries: AreaTrendSeries = {
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

function customerChartPoint(source: CustomerTrend): AreaTrendDatum {
  return { month: source.date, count: source.count }
}

const columns = computed<CustomerColumnView[]>(() => props.response.columns.map((column) => ({
  source: column,
  cards: column.items.map((item) => ({ source: item, card: presentCard(column, item) })),
})))

const projection = computed<BoardProjection>(() => ({
  metrics: props.response.summary.map((metric) => ({
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
        title: '客户趋势',
        description: '按完整月份统计客户数',
        series: [countSeries],
        points: props.response.trends.map((source) => ({
          month: source.date,
          values: { count: source.count },
        })),
      },
}))

const chartData = computed(() => props.response.trends.map(customerChartPoint))

function activate(column: CustomerColumn, item: CustomerItem): void {
  emit('activate-card', { id: item.id, columnKey: column.key })
}
</script>

<template>
  <div class="domain-board-projection">
    <section v-if="projection.metrics.length > 0" class="board-metrics" aria-label="看板指标">
      <article v-for="metric in projection.metrics" :key="metric.key">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <span v-if="metric.secondaryLabel">{{ metric.secondaryLabel }} {{ metric.secondaryValue }}</span>
      </article>
    </section>

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
        <p v-if="column.source.amount !== null">
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
          <p v-if="entry.card.ownerLabel">{{ entry.card.ownerLabel }}</p>
          <dl v-if="entry.card.metadata.length > 0">
            <div v-for="row in entry.card.metadata" :key="row.key">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
        </article>
        <p v-if="column.cards.length === 0">暂无记录</p>
        <button type="button" @click.stop="emit('view-all', column.source.key)">查看全部</button>
      </section>
    </div>

    <AreaTrendChart
      v-if="projection.trend"
      :title="projection.trend.title"
      :description="projection.trend.description"
      :data="chartData"
      :series="[countSeries]"
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
