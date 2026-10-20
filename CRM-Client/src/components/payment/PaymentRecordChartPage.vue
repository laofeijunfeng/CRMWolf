<script setup lang="ts">
import { computed, ref } from 'vue'
import { Area, Donut } from '@unovis/ts'
import { VisArea, VisAxis, VisDonut, VisLine, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartCrosshair,
  ChartTooltip,
  ChartTooltipContent,
  componentToString,
  type ChartConfig,
} from '@/components/ui/chart'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type {
  PaymentRecordChartBucket,
  PaymentRecordChartBucketRecords,
  PaymentRecordChartCard,
  PaymentRecordChartResponse,
} from '@/schemas/paymentRecordChart'
import { formatCurrency } from '@/utils/format'

const CHART_COLOR = 'hsl(var(--chart-1))'
const CHART_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
]

const props = defineProps<{
  chart: PaymentRecordChartResponse | null
  loading: boolean
  error: string
  bucketRecords: PaymentRecordChartBucketRecords | null
  bucketLoading: boolean
  bucketError: string
}>()

const emit = defineEmits<{
  retry: []
  'open-record': [recordId: number]
  'view-bucket': [card: PaymentRecordChartCard, bucket: PaymentRecordChartBucket]
  'close-bucket': []
  'retry-bucket': [card: PaymentRecordChartCard, bucket: PaymentRecordChartBucket]
}>()

interface PieDatum {
  key: string
  label: string
  count: number
  amount: number
  fill: string
  summary: string
}

interface MonthDatum {
  index: number
  label: string
  count: number
  amount: number
  summary: string
}

const selectedCard = ref<PaymentRecordChartCard | null>(null)
const selectedBucket = ref<PaymentRecordChartBucket | null>(null)
const showingAll = ref(false)

const population = computed(() => props.chart?.population ?? 0)
const totalAmount = computed(() => props.chart?.total_amount ?? 0)
const licenseCard = computed(() => props.chart?.cards.find((card) => card.key === 'license_type') ?? null)
const purchaseCard = computed(() => props.chart?.cards.find((card) => card.key === 'purchase_type') ?? null)
const amountCard = computed(() => props.chart?.cards.find((card) => card.key === 'amount_band') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'payment_month') ?? null)
const pieCards = computed(() => [licenseCard.value, purchaseCard.value].filter((card) => card !== null))

const dialogOpen = computed(() => selectedBucket.value !== null)
const fullRecordsMatch = computed(() => (
  props.bucketRecords !== null
  && selectedCard.value !== null
  && selectedBucket.value !== null
  && props.bucketRecords.chart === selectedCard.value.key
  && props.bucketRecords.bucket === selectedBucket.value.key
))
const dialogItems = computed(() => {
  if (showingAll.value && fullRecordsMatch.value && props.bucketRecords !== null) {
    return props.bucketRecords.records
  }
  return selectedBucket.value?.preview ?? []
})
const dialogTotal = computed(() => {
  if (showingAll.value && fullRecordsMatch.value && props.bucketRecords !== null) {
    return props.bucketRecords.total
  }
  return selectedBucket.value?.preview_total ?? 0
})
const canViewAll = computed(() => {
  const bucket = selectedBucket.value
  if (bucket === null || showingAll.value) return false
  return bucket.preview_total > bucket.preview.length
})

function formatSummaryAmount(value: number): string {
  if (!Number.isFinite(value)) return '¥ 0'
  const wan = value / 10000
  return `¥ ${wan.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万`
}

function legendValue(bucket: PaymentRecordChartBucket): string {
  return `${bucket.count.toLocaleString('zh-CN')} 笔 · ${formatCurrency(bucket.amount)}`
}

function sliceColor(index: number, key: string): string {
  if (key === 'blank') return 'hsl(var(--muted-foreground))'
  const color = CHART_COLORS[index % CHART_COLORS.length]
  return color ?? CHART_COLOR
}

function pieData(card: PaymentRecordChartCard): PieDatum[] {
  return card.buckets
    .filter((bucket) => bucket.count > 0 && bucket.amount > 0)
    .map((bucket) => {
      const summary = legendValue(bucket)
      const datum: PieDatum = {
        key: bucket.key,
        label: bucket.label,
        count: bucket.count,
        amount: bucket.amount,
        fill: `var(--color-${bucket.key})`,
        summary,
      }
      return Object.assign(datum, { [bucket.key]: summary })
    })
}

function pieConfig(card: PaymentRecordChartCard): ChartConfig {
  return Object.fromEntries(card.buckets.map((bucket, index) => [
    bucket.key,
    { label: bucket.label, color: sliceColor(index, bucket.key) },
  ]))
}

function donutTriggers(card: PaymentRecordChartCard): Record<string, (datum: unknown, x: number | Date) => string> {
  const template = componentToString(pieConfig(card), ChartTooltipContent, { hideLabel: true })
  if (template === undefined) return {}
  return { [Donut.selectors.segment]: template }
}

const monthConfig = {
  count: { label: '笔数', color: CHART_COLOR },
  summary: { label: '金额', color: CHART_COLOR },
} satisfies ChartConfig

function monthData(card: PaymentRecordChartCard): MonthDatum[] {
  return card.buckets.map((bucket, index) => ({
    index,
    label: bucket.label,
    count: bucket.count,
    amount: bucket.amount,
    summary: formatCurrency(bucket.amount),
  }))
}

function monthTooltip(): Record<string, (datum: unknown, x: number | Date) => string> {
  const template = componentToString(monthConfig, ChartTooltipContent, { labelKey: 'label' })
  if (template === undefined) return {}
  return { [Area.selectors.area]: template }
}

function barWidth(card: PaymentRecordChartCard, bucket: PaymentRecordChartBucket): string {
  const maxAmount = Math.max(...card.buckets.map((item) => Math.max(item.amount, 0)), 0)
  if (maxAmount <= 0) return '0%'
  return `${Math.round((Math.max(bucket.amount, 0) / maxAmount) * 100)}%`
}

function openBucket(card: PaymentRecordChartCard, bucket: PaymentRecordChartBucket): void {
  if (bucket.count <= 0 && card.key !== 'payment_month') return
  selectedCard.value = card
  selectedBucket.value = bucket
  showingAll.value = false
  emit('close-bucket')
}

function openMonth(card: PaymentRecordChartCard | null, datum: MonthDatum): void {
  if (card === null) return
  const bucket = card.buckets[datum.index]
  if (bucket === undefined) return
  openBucket(card, bucket)
}

function openPie(card: PaymentRecordChartCard, datum: PieDatum): void {
  const bucket = card.buckets.find((item) => item.key === datum.key)
  if (bucket === undefined || bucket.count <= 0) return
  openBucket(card, bucket)
}

function handleDialogChange(open: boolean): void {
  if (open) return
  selectedCard.value = null
  selectedBucket.value = null
  showingAll.value = false
  emit('close-bucket')
}

function viewAll(): void {
  if (selectedCard.value === null || selectedBucket.value === null || !canViewAll.value) return
  showingAll.value = true
  emit('view-bucket', selectedCard.value, selectedBucket.value)
}

function retryBucket(): void {
  if (selectedCard.value === null || selectedBucket.value === null) return
  emit('retry-bucket', selectedCard.value, selectedBucket.value)
}
</script>

<template>
  <section class="payment-record-chart" aria-label="回款图表" data-testid="payment-record-chart">
    <div v-if="loading && !chart" class="payment-record-chart__state">正在整理回款图表…</div>
    <div v-else-if="error && !chart" class="payment-record-chart__state" role="alert">
      <span>{{ error }}</span>
      <Button type="button" variant="outline" size="sm" @click="emit('retry')">重试</Button>
    </div>
    <template v-else-if="chart">
      <header class="payment-record-chart__heading">
        <h2 data-testid="payment-record-chart-title">{{ population.toLocaleString('zh-CN') }} 笔 · {{ formatSummaryAmount(totalAmount) }}</h2>
        <p>当前筛选范围内的回款。一页同时看，没有审批和确认状态。金额按回款金额汇总。</p>
      </header>
      <p v-if="error" class="payment-record-chart__state" role="alert">{{ error }}</p>
      <div class="payment-record-chart__grid">
        <Card v-for="card in pieCards" :key="card.key" class="flex flex-col" :data-testid="`payment-chart-card-${card.key}`">
          <CardHeader class="items-start pb-0">
            <CardTitle>{{ card.title }}</CardTitle>
            <CardDescription>{{ card.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="payment-record-chart__donut">
              <div class="payment-record-chart__donut-body">
                <ChartContainer
                  v-if="pieData(card).length > 0"
                  :config="pieConfig(card)"
                  class="aspect-square h-[220px] w-[220px]"
                  :style="{
                    '--vis-donut-central-label-font-size': '22px',
                    '--vis-donut-central-label-font-weight': '600',
                    '--vis-donut-central-label-text-color': 'hsl(var(--foreground))',
                    '--vis-donut-central-sub-label-text-color': 'hsl(var(--muted-foreground))',
                  }"
                >
                  <VisSingleContainer :data="pieData(card)" :margin="{ top: 8, bottom: 8 }">
                    <VisDonut
                      :value="(datum: PieDatum) => datum.amount"
                      :color="(datum: PieDatum) => datum.fill"
                      :arc-width="30"
                      :central-label-offset-y="10"
                      :central-label="String(population)"
                      central-sub-label="笔"
                      :events="{
                        [Donut.selectors.segment]: {
                          click: (datum: PieDatum) => openPie(card, datum),
                        },
                      }"
                    />
                    <ChartTooltip :triggers="donutTriggers(card)" />
                  </VisSingleContainer>
                </ChartContainer>
                <div v-else class="payment-record-chart__empty-donut">
                  <strong>{{ population.toLocaleString('zh-CN') }}</strong>
                  <span>笔</span>
                </div>
                <div class="payment-record-chart__legend">
                  <button
                    v-for="(bucket, index) in card.buckets"
                    :key="bucket.key"
                    type="button"
                    :disabled="bucket.count === 0"
                    :data-testid="`payment-chart-legend-${card.key}-${bucket.key}`"
                    @click="openBucket(card, bucket)"
                  >
                    <i :style="{ backgroundColor: sliceColor(index, bucket.key) }" />
                    <span>{{ bucket.label }}</span>
                    <span>{{ legendValue(bucket) }}</span>
                  </button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card v-if="amountCard" class="payment-record-chart__wide" data-testid="payment-chart-card-amount_band">
          <CardHeader>
            <CardTitle>{{ amountCard.title }}</CardTitle>
            <CardDescription>{{ amountCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="payment-record-chart__bars">
              <button
                v-for="bucket in amountCard.buckets"
                :key="bucket.key"
                type="button"
                :disabled="bucket.count === 0"
                :data-testid="`payment-chart-bar-${bucket.key}`"
                @click="openBucket(amountCard, bucket)"
              >
                <span>{{ bucket.label }}</span>
                <span class="payment-record-chart__track">
                  <span class="payment-record-chart__fill bg-primary" :style="{ width: barWidth(amountCard, bucket) }" />
                </span>
                <span>{{ legendValue(bucket) }}</span>
              </button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card v-if="monthCard" class="payment-record-chart__month" data-testid="payment-chart-card-payment_month">
        <CardHeader>
          <CardTitle>{{ monthCard.title }}</CardTitle>
          <CardDescription>{{ monthCard.description }}</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer :config="monthConfig" class="aspect-auto h-[240px]">
            <VisXYContainer :data="monthData(monthCard)" :height="220">
              <VisArea
                :x="(datum: MonthDatum) => datum.index"
                :y="(datum: MonthDatum) => datum.amount"
                :color="monthConfig.summary.color"
                :opacity="0.4"
                :events="{
                  [Area.selectors.area]: {
                    click: (datum: MonthDatum) => openMonth(monthCard, datum),
                  },
                }"
              />
              <VisLine
                :x="(datum: MonthDatum) => datum.index"
                :y="(datum: MonthDatum) => datum.amount"
                :color="monthConfig.summary.color"
                :line-width="1"
              />
              <VisAxis
                type="x"
                :tick-line="false"
                :domain-line="false"
                :grid-line="false"
                :num-ticks="monthCard.buckets.length"
                :tick-values="monthData(monthCard).map((datum) => datum.index)"
                :tick-format="(value: number) => monthCard?.buckets[Math.round(value)]?.label ?? ''"
              />
              <VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" />
              <ChartTooltip />
              <ChartCrosshair :template="monthTooltip()[Area.selectors.area]" :color="monthConfig.summary.color" />
            </VisXYContainer>
          </ChartContainer>
        </CardContent>
      </Card>

      <Dialog :open="dialogOpen" @update:open="handleDialogChange">
        <DialogContent class="w-[calc(100%-2rem)] max-w-lg">
          <DialogHeader>
            <DialogTitle>{{ selectedBucket?.label ?? '回款' }}</DialogTitle>
            <DialogDescription>
              {{ selectedCard?.title ?? '' }} · 共 {{ dialogTotal }} 笔 · {{ formatCurrency(selectedBucket?.amount ?? 0) }}
            </DialogDescription>
          </DialogHeader>
          <div v-if="bucketLoading" class="payment-record-chart__state" role="status">正在读取这一段回款…</div>
          <div v-else-if="bucketError" class="payment-record-chart__state" role="alert">
            <span>{{ bucketError }}</span>
            <Button type="button" variant="outline" size="sm" @click="retryBucket">重试</Button>
          </div>
          <div v-else class="payment-record-chart__dialog-list">
            <button
              v-for="item in dialogItems"
              :key="item.id"
              type="button"
              @click="emit('open-record', item.id)"
            >
              <span>
                <strong>{{ item.record_number || `#${item.id}` }}</strong>
                <small>{{ item.customer_name || '未关联客户' }} · {{ item.payment_date || '-' }}</small>
              </span>
              <span>{{ formatCurrency(item.amount) }}</span>
            </button>
            <p v-if="dialogItems.length === 0">这一段没有回款。</p>
            <Button v-if="canViewAll" type="button" variant="outline" size="sm" data-testid="payment-chart-view-all" @click="viewAll">
              查看详情
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </template>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.payment-record-chart {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  min-width: 0;
  padding: $wolf-space-md-v2;
}

.payment-record-chart__state {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-secondary-v2;
}

.payment-record-chart__heading h2 {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  line-height: 1.25;
}

.payment-record-chart__heading p {
  margin: $wolf-space-xs-v2 0 0;
  color: $wolf-text-tertiary-v2;
}

.payment-record-chart__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.payment-record-chart__wide {
  grid-column: 1 / -1;
}

.payment-record-chart__month {
  width: 100%;
}

.payment-record-chart__donut-body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  align-items: center;
  gap: 24px;
}

.payment-record-chart__empty-donut {
  display: flex;
  width: 220px;
  height: 220px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: $wolf-text-primary-v2;
}

.payment-record-chart__empty-donut strong {
  font-size: 22px;
  font-weight: 600;
}

.payment-record-chart__empty-donut span,
.payment-record-chart__legend button span:last-child,
.payment-record-chart__bars button span:last-child {
  color: $wolf-text-tertiary-v2;
  font-variant-numeric: tabular-nums;
}

.payment-record-chart__legend,
.payment-record-chart__bars {
  display: grid;
  gap: 8px;
  width: 100%;
}

.payment-record-chart__legend button,
.payment-record-chart__bars button {
  display: grid;
  align-items: center;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 2px 0;
  color: $wolf-text-primary-v2;
  font-size: 14px;
  text-align: left;
}

.payment-record-chart__legend button {
  grid-template-columns: 8px minmax(0, 1fr) auto;
  column-gap: 8px;
}

.payment-record-chart__legend button i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.payment-record-chart__bars button {
  grid-template-columns: auto minmax(0, 1fr) auto;
  column-gap: 12px;
}

.payment-record-chart__legend button:disabled,
.payment-record-chart__bars button:disabled {
  cursor: default;
}

.payment-record-chart__track {
  display: block;
  height: 8px;
  overflow: hidden;
  border-radius: 9999px;
  background: $wolf-bg-muted-v2;
}

.payment-record-chart__fill {
  display: block;
  height: 100%;
  border-radius: 9999px;
}

.payment-record-chart__dialog-list {
  display: flex;
  flex-direction: column;
  max-height: 24rem;
  overflow: auto;
  gap: $wolf-space-sm-v2;
}

.payment-record-chart__dialog-list > button {
  display: flex;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  border: 0;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: transparent;
  padding: $wolf-space-sm-v2 0;
  text-align: left;
}

.payment-record-chart__dialog-list small {
  display: block;
  color: $wolf-text-tertiary-v2;
}

@media (max-width: 720px) {
  .payment-record-chart__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .payment-record-chart__wide {
    grid-column: auto;
  }

  .payment-record-chart__donut-body {
    grid-template-columns: minmax(0, 1fr);
    justify-items: center;
  }
}
</style>
