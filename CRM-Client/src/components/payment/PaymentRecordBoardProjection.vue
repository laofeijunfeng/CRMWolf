<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import AmountText from '@/components/crmwolf/AmountText.vue'
import AreaTrendChart from '@/components/crmwolf/AreaTrendChart.vue'
import type { AreaTrendDatum, AreaTrendSeries } from '@/components/crmwolf/AreaTrendChart.vue'
import type {
  BoardCardActivation,
  BoardCardPresentation,
  BoardMetadataRow,
  BoardProjection,
} from '@/components/crmwolf/boardTypes'
import type { PaymentRecordBoardResponse } from '@/schemas/paymentRecordBoard'
import { formatLocalDate } from '@/utils/format'

const props = defineProps<{ response: PaymentRecordBoardResponse }>()

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
}>()

type PaymentRecordColumn = PaymentRecordBoardResponse['columns'][number]
type PaymentRecordItem = PaymentRecordColumn['items'][number]
type PaymentRecordTrend = PaymentRecordBoardResponse['trends'][number]
type ApprovalKey = PaymentRecordColumn['key']
type ConfirmationStatus = NonNullable<PaymentRecordItem['metadata']['confirmation_status']>

interface PaymentRecordColumnView {
  source: PaymentRecordColumn
  cards: ReadonlyArray<{ source: PaymentRecordItem; card: BoardCardPresentation }>
}

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

const trendSeries: AreaTrendSeries[] = [
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
    ['confirmation_status', '确认状态', confirmation],
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
    statusLabel: approvalLabels[item.status],
    metadata: metadataRows(item),
  }
}

function recordChartPoint(source: PaymentRecordTrend): AreaTrendDatum {
  return {
    month: source.date,
    count: source.count,
    actual_amount: chartAmount(source.actual_amount),
    confirmed_amount: chartAmount(source.confirmed_amount),
    unconfirmed_amount: chartAmount(source.unconfirmed_amount),
  }
}

const columns = computed<PaymentRecordColumnView[]>(() => props.response.columns.map((column) => ({
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
    label: approvalLabels[column.source.key],
    tone: column.source.tone,
    countLabel: String(column.source.count),
    amountLabel: column.source.actual_amount,
    hasMore: column.source.has_more,
    remainingCount: column.source.remaining_count,
    cards: column.cards.map((entry) => entry.card),
  })),
  trend: props.response.trends.length === 0
    ? null
    : {
        title: '回款记录趋势',
        description: '按完整月份统计回款金额和确认金额',
        series: trendSeries,
        points: props.response.trends.map((source) => ({
          month: source.date,
          values: {
            count: source.count,
            actual_amount: source.actual_amount,
            confirmed_amount: source.confirmed_amount,
            unconfirmed_amount: source.unconfirmed_amount,
          },
        })),
      },
}))

const chartData = computed(() => props.response.trends.map(recordChartPoint))

function activate(column: PaymentRecordColumn, item: PaymentRecordItem): void {
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
          <h2>{{ approvalLabels[column.source.key] }}</h2>
        </header>
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
          <div class="record-badges">
            <Badge variant="outline">{{ approvalLabels[entry.source.status] }}</Badge>
            <Badge v-if="entry.source.metadata.confirmation_status" variant="outline">
              {{ confirmationLabels[entry.source.metadata.confirmation_status] }}
            </Badge>
          </div>
          <h3>{{ entry.card.title }}</h3>
          <AmountText :value="entry.source.actual_amount" size="lg" />
          <p v-if="entry.card.dateLabel">{{ entry.card.dateLabel }}</p>
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

.board-card,
.record-badges {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.record-badges {
  flex-direction: row;
  flex-wrap: wrap;
}

.board-column,
.board-card {
  border-radius: 8px;
}
</style>
