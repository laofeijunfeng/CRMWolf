<script setup lang="ts">
import { computed, ref } from 'vue'
import { Donut, GroupedBar } from '@unovis/ts'
import { VisAxis, VisDonut, VisGroupedBar, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChartContainer, ChartTooltip, ChartTooltipContent, componentToString, type ChartConfig } from '@/components/ui/chart'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { AmountText, TableToolbarButton } from '@/components/crmwolf'
import type {
  BusinessJourneyChartCard,
  BusinessJourneyChartPreview,
  BusinessJourneyChartResponse,
  BusinessJourneyChartSegment
} from '@/schemas/dealJourney'

const CHART_COLOR = 'hsl(var(--primary))'
const MUTED_COLOR = 'hsl(var(--muted-foreground))'
const CHART_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))'
]

interface PieDatum {
  key: string
  label: string
  count: number
  amount: number
  fill: string
  [key: string]: string | number
}

interface ClosingDatum {
  index: number
  key: string
  label: string
  count: number
  amount: number
  fill: string
}

const props = withDefaults(defineProps<{
  chart: BusinessJourneyChartResponse | null
  loading?: boolean
  errorMessage?: string
  segmentOpen?: boolean
  segmentLoading?: boolean
  segmentError?: string
  segmentLabel?: string
  segmentTotal?: number
  segmentItems?: BusinessJourneyChartPreview[]
}>(), {
  loading: false,
  errorMessage: '',
  segmentOpen: false,
  segmentLoading: false,
  segmentError: '',
  segmentLabel: '',
  segmentTotal: 0,
  segmentItems: () => []
})

const emit = defineEmits<{
  retry: []
  'select-segment': [payload: { card: BusinessJourneyChartCard; segment: BusinessJourneyChartSegment }]
  'open-segment': [payload: { card: BusinessJourneyChartCard; segment: BusinessJourneyChartSegment }]
  'load-more': []
  'update:segment-open': [value: boolean]
  'open-journey': [payload: { customerId: string; journeyPublicId: string }]
}>()

const summary = computed(() => props.chart?.summary ?? null)
const selectedCardTitle = computed(() => selectedSegment.value?.card.title ?? '')
const cards = computed(() => props.chart?.cards ?? [])
const displayCardOrder: BusinessJourneyChartCard['key'][] = ['purchase_type', 'recent_activity', 'stage', 'amount_band', 'product', 'expected_closing']
const pairedCardKeys = new Set<BusinessJourneyChartCard['key']>(['purchase_type', 'recent_activity'])
const displayCards = computed(() => {
  const byKey = new Map(cards.value.map(card => [card.key, card]))
  const ordered = displayCardOrder.flatMap((key) => {
    const card = byKey.get(key)
    return card === undefined ? [] : [card]
  })
  return [...ordered, ...cards.value.filter(card => !displayCardOrder.includes(card.key))]
})

function isWideCard(card: BusinessJourneyChartCard): boolean {
  return !pairedCardKeys.has(card.key)
}

const closingConfig = {
  amount: { label: '金额', color: CHART_COLOR }
} satisfies ChartConfig

function formatWan(value: number): string {
  const amount = Number.isFinite(value) ? value : 0
  if (Math.abs(amount) >= 10000) {
    return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(amount / 10000)} 万`
  }
  return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(amount)}`
}

function formatAxisAmount(value: number): string {
  return formatWan(value)
}

function isMutedKey(key: string): boolean {
  return key === 'unset' || key === 'other' || key === 'unscheduled'
}

function sliceColor(index: number, key: string): string {
  if (key === 'unset' || key === 'other') return MUTED_COLOR
  return CHART_COLORS[index % CHART_COLORS.length] ?? CHART_COLOR
}

function pieData(card: BusinessJourneyChartCard): PieDatum[] {
  return card.segments.map((segment, index) => {
    const datum = {
      key: segment.key,
      label: segment.label,
      count: segment.count,
      amount: segment.amount,
      fill: sliceColor(index, segment.key)
    } as PieDatum
    datum[segment.key] = segment.amount
    return datum
  })
}

function pieConfig(card: BusinessJourneyChartCard): ChartConfig {
  return Object.fromEntries(card.segments.map((segment, index) => [
    segment.key,
    { label: segment.label, color: sliceColor(index, segment.key) }
  ]))
}

function donutPayload(datum: unknown): PieDatum | null {
  if (typeof datum !== 'object' || datum === null) return null
  const candidate = 'data' in datum ? (datum as { data?: unknown }).data : datum
  if (typeof candidate !== 'object' || candidate === null || !('key' in candidate) || typeof candidate.key !== 'string') return null
  return candidate as PieDatum
}

function closingData(card: BusinessJourneyChartCard): ClosingDatum[] {
  return card.segments.map((segment, index) => ({
    index,
    key: segment.key,
    label: segment.label,
    count: segment.count,
    amount: segment.amount,
    fill: segment.key === 'unscheduled' ? MUTED_COLOR : CHART_COLOR
  }))
}

function barWidth(card: BusinessJourneyChartCard, segment: BusinessJourneyChartSegment): string {
  const maximum = Math.max(...card.segments.map(item => item.amount), 1)
  return `${segment.amount / maximum * 100}%`
}

function segmentText(segment: BusinessJourneyChartSegment): string {
  return `${segment.count} 条 · ${formatWan(segment.amount)}`
}

function isSelected(card: BusinessJourneyChartCard, segment: BusinessJourneyChartSegment): boolean {
  return selectedKey.value === `${card.key}:${segment.key}`
}

const selectedKey = ref<string | null>(null)
const selectedSegment = computed(() => cards.value.flatMap(card => card.segments.map(segment => ({ card, segment }))).find(item => `${item.card.key}:${item.segment.key}` === selectedKey.value) ?? null)

function selectSegment(card: BusinessJourneyChartCard, segment: BusinessJourneyChartSegment): void {
  if (segment.count === 0) return
  selectedKey.value = `${card.key}:${segment.key}`
  emit('open-segment', { card, segment })
}

function openSelected(): void {
  if (selectedSegment.value === null) return
  emit('open-segment', selectedSegment.value)
}

function openJourney(item: BusinessJourneyChartPreview): void {
  emit('open-journey', { customerId: item.customer_id, journeyPublicId: item.public_id })
}
</script>

<template>
  <section class="journey-chart" aria-label="业务旅程图表">
    <div v-if="loading && chart === null" class="journey-chart-state">正在整理业务旅程图表…</div>
    <div v-else-if="errorMessage && chart === null" class="journey-chart-state" role="alert">
      <AlertCircle class="h-5 w-5" aria-hidden="true" />
      <strong>{{ errorMessage }}</strong>
      <TableToolbarButton :disabled="loading" @click="emit('retry')">重新加载</TableToolbarButton>
    </div>
    <template v-else-if="summary">
      <div v-if="loading" class="journey-chart-refreshing" role="status">
        <RefreshCw class="h-4 w-4 animate-spin" aria-hidden="true" />
        <span>正在刷新，当前显示上次成功加载的数据</span>
      </div>
      <header class="journey-chart-summary">
        <h2>{{ summary.total_count }} 条 · {{ formatWan(summary.total_amount) }}</h2>
        <p>当前筛选范围内的业务旅程。</p>
      </header>
      <div class="journey-chart-grid">
        <Card
          v-for="card in displayCards"
          :key="card.key"
          :class="isWideCard(card) ? 'journey-chart-card journey-chart-card--wide' : 'journey-chart-card'"
          :data-graphic="card.graphic"
        >
          <CardHeader v-bind="card.graphic === 'pie' ? { class: 'items-start pb-0' } : {}">
            <CardTitle>{{ card.title }}</CardTitle>
            <CardDescription>{{ card.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="card.graphic === 'pie'" class="grid grid-cols-[220px_minmax(0,1fr)] items-center gap-6">
              <ChartContainer
                :config="pieConfig(card)"
                class="aspect-square h-[220px] w-[220px]"
                role="img"
                aria-label="采购类型金额占比"
                :style="{
                  '--vis-donut-central-label-font-size': '22px',
                  '--vis-donut-central-label-font-weight': '600',
                  '--vis-donut-central-label-text-color': 'hsl(var(--foreground))',
                  '--vis-donut-central-sub-label-text-color': 'hsl(var(--muted-foreground))'
                }"
              >
                <VisSingleContainer :data="pieData(card)" :margin="{ top: 8, bottom: 8 }">
                  <VisDonut
                    :value="(datum: PieDatum) => datum.amount"
                    :color="(datum: PieDatum) => datum.fill"
                    :arc-width="30"
                    :central-label="String(summary.total_count)"
                    central-sub-label="条"
                    :central-label-offset-y="10"
                    :events="{
                      [Donut.selectors.segment]: {
                        click: (datum: unknown) => {
                          const payload = donutPayload(datum)
                          const segment = payload === null ? undefined : card.segments.find(item => item.key === payload.key)
                          if (segment) selectSegment(card, segment)
                        }
                      }
                    }"
                  />
                  <ChartTooltip
                    :triggers="{
                      [Donut.selectors.segment]: componentToString(pieConfig(card), ChartTooltipContent, { hideLabel: true })!
                    }"
                  />
                </VisSingleContainer>
              </ChartContainer>
              <div class="journey-chart-legend">
                <button
                  v-for="(segment, index) in card.segments"
                  :key="segment.key"
                  type="button"
                  class="grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-2 text-left text-sm disabled:cursor-default"
                  :class="{ 'is-selected': isSelected(card, segment) }"
                  :disabled="segment.count === 0"
                  @click="selectSegment(card, segment)"
                >
                  <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: sliceColor(index, segment.key) }" />
                  <span class="truncate">{{ segment.label }}</span>
                  <span class="whitespace-nowrap text-muted-foreground tabular-nums">{{ segmentText(segment) }}</span>
                </button>
              </div>
            </div>
            <div v-else-if="card.graphic === 'vertical_bar'" class="journey-chart-closing">
              <ChartContainer :config="closingConfig" class="journey-chart-closing-plot" role="img" aria-label="预计成交金额柱状图">
                <VisXYContainer
                  :data="closingData(card)"
                  :height="220"
                  :margin="{ top: 20, right: 12, bottom: 36, left: 56 }"
                  :auto-margin="false"
                >
                  <VisGroupedBar
                    :x="(datum: ClosingDatum) => datum.index"
                    :y="(datum: ClosingDatum) => datum.amount"
                    :color="(datum: ClosingDatum) => datum.fill"
                    :group-max-width="64"
                    :bar-min-height="1"
                    :rounded-corners="4"
                    :events="{
                      [GroupedBar.selectors.bar]: {
                        click: (datum: ClosingDatum) => {
                          const segment = card.segments[datum.index]
                          if (segment) selectSegment(card, segment)
                        }
                      }
                    }"
                  />
                  <VisAxis
                    type="x"
                    :tick-line="false"
                    :domain-line="false"
                    :grid-line="false"
                    :tick-values="closingData(card).map(datum => datum.index)"
                    :tick-format="(value: number) => closingData(card)[Math.round(value)]?.label ?? ''"
                  />
                  <VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" :tick-format="formatAxisAmount" />
                  <ChartTooltip
                    :triggers="{
                      [GroupedBar.selectors.bar]: componentToString(closingConfig, ChartTooltipContent, { hideLabel: true })!
                    }"
                  />
                </VisXYContainer>
              </ChartContainer>
            </div>
            <div v-else class="journey-chart-bars">
              <button
                v-for="segment in card.segments"
                :key="segment.key"
                type="button"
                class="grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm disabled:cursor-default"
                :class="{ 'is-selected': isSelected(card, segment) }"
                :disabled="segment.count === 0"
                :title="segment.label"
                @click="selectSegment(card, segment)"
              >
                <span class="truncate">{{ segment.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-muted">
                  <span
                    class="block h-full rounded-full"
                    :class="isMutedKey(segment.key) ? 'bg-muted-foreground' : 'bg-primary'"
                    :style="{ width: barWidth(card, segment) }"
                  />
                </span>
                <span class="whitespace-nowrap text-muted-foreground tabular-nums">{{ segmentText(segment) }}</span>
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
      <p v-if="errorMessage" class="journey-chart-note" role="alert">{{ errorMessage }}</p>
    </template>

    <Dialog :open="segmentOpen ?? false" @update:open="emit('update:segment-open', $event)">
      <DialogContent class="w-[calc(100%-2rem)] max-w-lg">
        <DialogHeader>
          <DialogTitle>{{ segmentLabel }}</DialogTitle>
          <DialogDescription>{{ selectedCardTitle }} · 共 {{ segmentTotal }} 条</DialogDescription>
        </DialogHeader>
        <div v-if="segmentLoading && (segmentItems?.length ?? 0) === 0" class="journey-chart-state">正在读取这一段…</div>
        <div v-else-if="segmentError && (segmentItems?.length ?? 0) === 0" class="journey-chart-state" role="alert">
          <span>{{ segmentError }}</span>
          <Button type="button" variant="outline" size="sm" @click="openSelected">重试</Button>
        </div>
        <div v-else class="journey-chart-segment-list">
          <button v-for="item in segmentItems" :key="item.public_id" type="button" @click="openJourney(item)">
            <span class="min-w-0">
              <span class="block">{{ item.name }}</span>
              <small class="block">{{ item.customer_name }}</small>
            </span>
            <AmountText :value="item.amount" size="sm" />
          </button>
          <button
            v-if="(segmentItems?.length ?? 0) < (segmentTotal ?? 0)"
            type="button"
            class="journey-chart-preview__more"
            :disabled="segmentLoading"
            @click="emit('load-more')"
          >
            {{ segmentLoading ? '正在读取…' : segmentError || '查看更多' }}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.journey-chart {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  overflow: auto;
  padding: $wolf-space-md-v2;
}

.journey-chart-summary h2 {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  line-height: 1.25;
}

.journey-chart-summary p,
.journey-chart-note {
  margin: $wolf-space-xs-v2 0 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-body-v2;
}

.journey-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.journey-chart-card {
  min-width: 0;
}

.journey-chart-card--wide {
  grid-column: 1 / -1;
}

.journey-chart-bars,
.journey-chart-legend {
  display: grid;
  gap: $wolf-space-sm-v2;
}

.journey-chart-bars button,
.journey-chart-legend button,
.journey-chart-preview button,
.journey-chart-segment-list button {
  border: 0;
  background: transparent;
}

.journey-chart-bars button.is-selected,
.journey-chart-legend button.is-selected {
  border-radius: $wolf-radius-v2;
  background: hsl(var(--primary) / 0.08);
}

.journey-chart-closing-plot {
  width: 100%;
  height: 240px;
}

.journey-chart-preview small,
.journey-chart-segment-list small {
  color: $wolf-text-tertiary-v2;
  font-size: 12px;
}

.journey-chart-state,
.journey-chart-refreshing {
  display: flex;
  min-height: 48px;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-tertiary-v2;
}

.journey-chart-preview,
.journey-chart-segment-list {
  display: flex;
  flex-direction: column;
}

.journey-chart-preview {
  margin-top: $wolf-space-md-v2;
  border-top: 1px solid $wolf-border-default-v2;
}

.journey-chart-preview button,
.journey-chart-segment-list button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  width: 100%;
  border-bottom: 1px solid $wolf-border-default-v2;
  padding: $wolf-space-sm-v2 0;
  text-align: left;
  font-size: $wolf-font-size-body-v2;
}

.journey-chart-preview__more {
  color: hsl(var(--primary));
}

.journey-chart-sheet {
  display: flex;
  width: min(28rem, 100vw);
  flex-direction: column;
}

.journey-chart-segment-list {
  min-height: 0;
  overflow: auto;
}

@media (max-width: 900px) {
  .journey-chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
