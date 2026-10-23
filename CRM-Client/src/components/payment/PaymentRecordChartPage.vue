<script setup lang="ts">
import { computed, ref } from 'vue'
import { Area, Donut } from '@unovis/ts'
import { VisArea, VisAxis, VisDonut, VisLine, VisScatter, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { arrCanOpen, arrLinePoints, arrShowsMarker } from '@/components/payment/paymentRecordArr'
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
  'load-more': []
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

interface ArrDatum {
  index: number
  key: string
  label: string
  ratio: number | null
  annualizedText: string
  buyoutText: string
  ratioText: string
}

const arrMargin = { top: 16, right: 8, bottom: 28, left: 48 }
const arrYDomain: [number, number] = [0, 100]

const selectedCard = ref<PaymentRecordChartCard | null>(null)
const selectedBucket = ref<PaymentRecordChartBucket | null>(null)

const population = computed(() => props.chart?.population ?? 0)
const totalAmount = computed(() => props.chart?.total_amount ?? 0)
const licenseCard = computed(() => props.chart?.cards.find((card) => card.key === 'license_type') ?? null)
const purchaseCard = computed(() => props.chart?.cards.find((card) => card.key === 'purchase_type') ?? null)
const amountCard = computed(() => props.chart?.cards.find((card) => card.key === 'amount_band') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'payment_month') ?? null)
const arrCard = computed(() => props.chart?.cards.find((card) => card.key === 'arr_ratio') ?? null)
const pieCards = computed(() => [licenseCard.value, purchaseCard.value].filter((card) => card !== null))

const dialogOpen = computed(() => selectedBucket.value !== null)
const fullRecordsMatch = computed(() => (
  props.bucketRecords !== null
  && selectedCard.value !== null
  && selectedBucket.value !== null
  && props.bucketRecords.chart === selectedCard.value.key
  && props.bucketRecords.bucket === selectedBucket.value.key
))
const dialogItems = computed(() => (
  fullRecordsMatch.value && props.bucketRecords !== null ? props.bucketRecords.records : []
))
const dialogTotal = computed(() => (
  fullRecordsMatch.value && props.bucketRecords !== null ? props.bucketRecords.total : 0
))
const awaitingPage = computed(() => dialogOpen.value && !fullRecordsMatch.value && props.bucketError === '')

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

const arrConfig = {
  annualizedText: { label: '年化订阅', color: CHART_COLOR },
  buyoutText: { label: '买断', color: CHART_COLOR },
  ratioText: { label: '占比', color: CHART_COLOR },
} satisfies ChartConfig

function arrData(card: PaymentRecordChartCard): ArrDatum[] {
  return card.buckets.map((bucket, index) => {
    const ratio = bucket.plotted_ratio ?? null
    const annualized = bucket.annualized_subscription ?? null
    const buyout = bucket.buyout_amount ?? null
    return {
      index,
      key: bucket.key,
      label: bucket.label,
      ratio,
      annualizedText: annualized === null ? '' : formatSummaryAmount(annualized),
      buyoutText: buyout === null ? '' : formatSummaryAmount(buyout),
      ratioText: ratio === null ? '' : `${ratio}%`,
    }
  })
}

const arrXDomain = computed((): [number, number] => {
  const count = arrCard.value?.buckets.length ?? 1
  return [0, Math.max(count - 1, 0)]
})

function arrLabelLeft(index: number, count: number): string {
  const span = Math.max(count - 1, 1)
  const horizontal = arrMargin.left + arrMargin.right
  return `calc(${arrMargin.left}px + (100% - ${horizontal}px) * ${index / span})`
}

function arrLabelTop(ratio: number): string {
  const vertical = arrMargin.top + arrMargin.bottom
  return `calc(${arrMargin.top}px + (100% - ${vertical}px) * ${(100 - ratio) / 100})`
}

function openArr(datum: ArrDatum): void {
  const card = arrCard.value
  if (card === null || !arrCanOpen(datum.ratio)) return
  const bucket = card.buckets[datum.index]
  if (bucket === undefined) return
  selectedCard.value = card
  selectedBucket.value = bucket
  emit('view-bucket', card, bucket)
}

const arrHover = ref<ArrDatum | null>(null)
const arrHoverStyle = ref({ left: '0px', top: '0px' })

function arrIndexFromClientX(clientX: number, plot: HTMLElement): number | null {
  const count = arrCard.value?.buckets.length ?? 0
  if (count <= 0) return null
  const rect = plot.getBoundingClientRect()
  const plotLeft = rect.left + arrMargin.left
  const plotWidth = rect.width - arrMargin.left - arrMargin.right
  if (plotWidth <= 0) return null
  const span = Math.max(count - 1, 1)
  const index = Math.round(((clientX - plotLeft) / plotWidth) * span)
  if (index < 0 || index >= count) return null
  return index
}

function arrPointAt(index: number): ArrDatum | null {
  const card = arrCard.value
  if (card === null) return null
  return arrData(card)[index] ?? null
}

function onArrMove(event: MouseEvent): void {
  const plot = event.currentTarget
  if (!(plot instanceof HTMLElement)) return
  const index = arrIndexFromClientX(event.clientX, plot)
  const point = index === null ? null : arrPointAt(index)
  if (point === null || point.ratio === null) {
    arrHover.value = null
    return
  }
  const rect = plot.getBoundingClientRect()
  const localX = event.clientX - rect.left
  const tooltipWidth = 168
  const left = localX + tooltipWidth + 16 > rect.width ? localX - tooltipWidth - 8 : localX + 12
  arrHover.value = point
  arrHoverStyle.value = {
    left: `${Math.max(left, 8)}px`,
    top: `${Math.max(event.clientY - rect.top - 72, 8)}px`,
  }
}

function onArrLeave(): void {
  arrHover.value = null
}

function onArrClick(event: MouseEvent): void {
  const plot = event.currentTarget
  if (!(plot instanceof HTMLElement)) return
  const index = arrIndexFromClientX(event.clientX, plot)
  if (index === null) return
  const point = arrPointAt(index)
  if (point === null) return
  openArr(point)
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
  emit('view-bucket', card, bucket)
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
  emit('close-bucket')
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

      <Card v-if="arrCard" class="payment-record-chart__month" data-testid="payment-chart-card-arr_ratio">
        <CardHeader>
          <CardTitle>{{ arrCard.title }}</CardTitle>
          <CardDescription>{{ arrCard.description }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            class="payment-record-chart__arr-plot"
            @mousemove="onArrMove"
            @mouseleave="onArrLeave"
            @click="onArrClick"
          >
            <ChartContainer :config="arrConfig" class="payment-record-chart__arr-layer payment-record-chart__arr-axis aspect-auto h-[240px]">
              <VisXYContainer
                :data="arrData(arrCard)"
                :height="220"
                :x-domain="arrXDomain"
                :y-domain="arrYDomain"
                :auto-margin="false"
                :margin="arrMargin"
              >
                <VisAxis
                  type="x"
                  :tick-line="false"
                  :domain-line="false"
                  :grid-line="false"
                  :num-ticks="arrCard.buckets.length"
                  :tick-values="arrData(arrCard).map((datum) => datum.index)"
                  :tick-format="(value: number) => arrCard?.buckets[Math.round(value)]?.label ?? ''"
                />
                <VisAxis
                  type="y"
                  :num-ticks="3"
                  :tick-line="false"
                  :domain-line="false"
                  :tick-format="(value: number) => `${Math.round(value)}%`"
                />
              </VisXYContainer>
            </ChartContainer>
            <ChartContainer
              v-if="arrLinePoints(arrData(arrCard)).length > 0"
              :config="arrConfig"
              class="payment-record-chart__arr-layer payment-record-chart__arr-series aspect-auto h-[240px]"
              :cursor="true"
            >
              <VisXYContainer
                :data="arrLinePoints(arrData(arrCard))"
                :height="220"
                :x-domain="arrXDomain"
                :y-domain="arrYDomain"
                :auto-margin="false"
                :margin="arrMargin"
              >
                <VisArea
                  :x="(datum: ArrDatum) => datum.index"
                  :y="(datum: ArrDatum) => datum.ratio ?? 0"
                  :color="arrConfig.ratioText.color"
                  :opacity="0.4"
                />
                <VisLine
                  :x="(datum: ArrDatum) => datum.index"
                  :y="(datum: ArrDatum) => datum.ratio ?? 0"
                  :color="arrConfig.ratioText.color"
                  :line-width="1"
                />
                <VisScatter
                  v-if="arrShowsMarker(arrData(arrCard))"
                  :x="(datum: ArrDatum) => datum.index"
                  :y="(datum: ArrDatum) => datum.ratio ?? 0"
                  :color="arrConfig.ratioText.color"
                  :size="8"
                />
              </VisXYContainer>
            </ChartContainer>
            <div
              v-if="arrHover"
              class="payment-record-chart__arr-tooltip"
              :style="arrHoverStyle"
              data-testid="payment-chart-arr-tooltip"
            >
              <strong>{{ arrHover.label }}</strong>
              <span><em>年化订阅</em><b>{{ arrHover.annualizedText }}</b></span>
              <span><em>买断</em><b>{{ arrHover.buyoutText }}</b></span>
              <span><em>占比</em><b>{{ arrHover.ratioText }}</b></span>
            </div>
            <span
              v-for="point in arrData(arrCard).filter((item) => item.ratio !== null)"
              :key="point.key"
              class="payment-record-chart__arr-label"
              :data-testid="`payment-chart-arr-label-${point.key}`"
              :style="{ left: arrLabelLeft(point.index, arrCard.buckets.length), top: arrLabelTop(point.ratio ?? 0) }"
            >{{ point.ratio }}%</span>
          </div>
        </CardContent>
      </Card>

      <Dialog :open="dialogOpen" @update:open="handleDialogChange">
        <DialogContent class="w-[calc(100%-2rem)] max-w-lg">
          <DialogHeader>
            <DialogTitle>{{ selectedBucket?.label ?? '回款' }}</DialogTitle>
            <DialogDescription>
              {{ selectedCard?.title ?? '' }} · 共 {{ dialogTotal }} 笔
            </DialogDescription>
          </DialogHeader>
          <div v-if="(bucketLoading || awaitingPage) && dialogItems.length === 0" class="payment-record-chart__state" role="status">正在读取这一段回款…</div>
          <div v-else-if="bucketError && dialogItems.length === 0" class="payment-record-chart__state" role="alert">
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
            <Button
              v-if="fullRecordsMatch && dialogItems.length < dialogTotal"
              type="button"
              variant="outline"
              size="sm"
              data-testid="payment-chart-view-more"
              :disabled="bucketLoading"
              @click="emit('load-more')"
            >
              {{ bucketLoading ? '正在读取…' : bucketError || '查看更多' }}
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
  flex: 1 1 auto;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  min-height: 0;
  min-width: 0;
  overflow: auto;
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

.payment-record-chart__arr-plot {
  position: relative;
  height: 240px;
}

.payment-record-chart__arr-layer {
  position: absolute;
  inset: 0;
}

.payment-record-chart__arr-axis,
.payment-record-chart__arr-series,
.payment-record-chart__arr-label {
  pointer-events: none;
}

.payment-record-chart__arr-series :deep(path),
.payment-record-chart__arr-series :deep(circle) {
  pointer-events: auto;
  cursor: pointer;
}

.payment-record-chart__arr-label {
  position: absolute;
  color: $wolf-text-primary-v2;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  transform: translate(-50%, -170%);
  white-space: nowrap;
}

.payment-record-chart__arr-tooltip {
  position: absolute;
  z-index: 2;
  display: grid;
  gap: 4px;
  min-width: 9rem;
  border: 1px solid $wolf-border-default-v2;
  border-radius: 8px;
  background: $wolf-bg-card-v2;
  padding: 8px 10px;
  color: $wolf-text-primary-v2;
  font-size: 12px;
  pointer-events: none;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
}

.payment-record-chart__arr-tooltip strong {
  font-weight: 600;
}

.payment-record-chart__arr-tooltip span {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.payment-record-chart__arr-tooltip em {
  color: $wolf-text-tertiary-v2;
  font-style: normal;
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
