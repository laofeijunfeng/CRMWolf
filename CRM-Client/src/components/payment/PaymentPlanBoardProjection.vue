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
import type { PaymentPlanBoardResponse } from '@/schemas/paymentPlanBoard'
import { formatLocalDate } from '@/utils/format'

const props = defineProps<{ response: PaymentPlanBoardResponse }>()

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
}>()

type PaymentPlanColumn = PaymentPlanBoardResponse['columns'][number]
type PaymentPlanItem = PaymentPlanColumn['items'][number]
type PaymentPlanTrend = PaymentPlanBoardResponse['trends'][number]

interface PaymentPlanColumnView {
  source: PaymentPlanColumn
  cards: ReadonlyArray<{ source: PaymentPlanItem; card: BoardCardPresentation }>
}

const trendSeries: AreaTrendSeries[] = [
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

function metadataRows(item: PaymentPlanItem): BoardMetadataRow[] {
  const rows: Array<[string, string, string | null]> = [
    ['customer_name', '客户', item.metadata.customer_name],
    ['contract_name', '合同', item.metadata.contract_name],
    ['opportunity_name', '商机', item.metadata.opportunity_name],
  ]
  return rows.flatMap(([key, label, value]) => (value === null ? [] : [{ key, label, value }]))
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
    metadata: metadataRows(item),
  }
}

function planChartPoint(source: PaymentPlanTrend): AreaTrendDatum {
  return {
    month: source.date,
    count: source.count,
    planned_amount: chartAmount(source.planned_amount),
    paid_amount: chartAmount(source.paid_amount),
    remaining_amount: chartAmount(source.remaining_amount),
  }
}

const columns = computed<PaymentPlanColumnView[]>(() => props.response.columns.map((column) => ({
  source: column,
  cards: column.items.map((item) => ({ source: item, card: presentCard(column, item) })),
})))

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
  columns: columns.value.map((column) => ({
    key: column.source.key,
    label: column.source.label,
    tone: column.source.tone,
    countLabel: String(column.source.count),
    amountLabel: column.source.overdue_remaining_amount,
    hasMore: column.source.has_more,
    remainingCount: column.source.remaining_count,
    cards: column.cards.map((entry) => entry.card),
  })),
  trend: props.response.trends.length === 0
    ? null
    : {
        title: '回款计划趋势',
        description: '按完整月份统计计划、已回款和待回款',
        series: trendSeries,
        points: props.response.trends.map((source) => ({
          month: source.date,
          values: {
            count: source.count,
            planned_amount: source.planned_amount,
            paid_amount: source.paid_amount,
            remaining_amount: source.remaining_amount,
          },
        })),
      },
}))

const chartData = computed(() => props.response.trends.map(planChartPoint))

function activate(column: PaymentPlanColumn, item: PaymentPlanItem): void {
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
        </header>
        <p class="plan-amounts">
          <span>计划金额 <AmountText :value="column.source.planned_amount" size="sm" /></span>
          <span>已回款 <AmountText :value="column.source.paid_amount" size="sm" /></span>
          <span>待回款 <AmountText :value="column.source.remaining_amount" size="sm" /></span>
          <span>逾期待回款 <AmountText :value="column.source.overdue_remaining_amount" size="sm" /></span>
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
          <span>{{ entry.card.statusLabel }}</span>
          <p v-if="entry.card.dateLabel">{{ entry.card.dateLabel }}</p>
          <p v-if="entry.card.ownerLabel">{{ entry.card.ownerLabel }}</p>
          <p>计划金额 <AmountText :value="entry.source.planned_amount" size="sm" /></p>
          <p>已回款 <AmountText :value="entry.source.paid_amount" size="sm" /></p>
          <p>待回款 <AmountText :value="entry.source.remaining_amount" size="sm" /></p>
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

.plan-amounts,
.board-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.board-column,
.board-card {
  border-radius: 8px;
}
</style>
