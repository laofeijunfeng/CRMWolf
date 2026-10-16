<script setup lang="ts">
import { computed, ref } from 'vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { AmountText, TableToolbarButton } from '@/components/crmwolf'
import type {
  BusinessJourneyChartCard,
  BusinessJourneyChartPreview,
  BusinessJourneyChartResponse,
  BusinessJourneyChartSegment
} from '@/schemas/dealJourney'

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
  'update:segment-open': [value: boolean]
  'open-journey': [payload: { customerId: string; journeyPublicId: string }]
}>()

const summary = computed(() => props.chart?.summary ?? null)
const cards = computed(() => props.chart?.cards ?? [])
const pieCard = computed(() => cards.value.find(card => card.graphic === 'pie') ?? null)
const pieTotal = computed(() => pieCard.value?.segments.reduce((sum, segment) => sum + segment.amount, 0) ?? 0)
const largestPie = computed(() => pieCard.value?.segments.reduce<BusinessJourneyChartSegment | null>(
  (current, segment) => current === null || segment.amount > current.amount ? segment : current,
  null
) ?? null)

function formatWan(value: number): string {
  const amount = Number.isFinite(value) ? value : 0
  if (Math.abs(amount) >= 10000) {
    return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(amount / 10000)} 万`
  }
  return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(amount)}`
}

function share(segment: BusinessJourneyChartSegment): string {
  if (pieTotal.value <= 0) return '0%'
  return `${Math.round(segment.amount / pieTotal.value * 100)}%`
}

function barWidth(card: BusinessJourneyChartCard, segment: BusinessJourneyChartSegment): string {
  const maximum = Math.max(...card.segments.map(item => item.amount), 1)
  return `${segment.amount / maximum * 100}%`
}

function columnHeight(card: BusinessJourneyChartCard, segment: BusinessJourneyChartSegment): string {
  const maximum = Math.max(...card.segments.map(item => item.amount), 1)
  return `${Math.max(segment.amount / maximum * 100, segment.amount > 0 ? 8 : 0)}%`
}

const pieSlices = computed(() => {
  const segments = pieCard.value?.segments ?? []
  let cursor = -Math.PI / 2
  return segments.flatMap(segment => {
    const sweep = pieTotal.value <= 0 ? 0 : segment.amount / pieTotal.value * Math.PI * 2
    const start = cursor
    cursor += sweep
    if (sweep <= 0) return []
    const arc = (angle: number): [number, number] => [50 + Math.cos(angle) * 34, 50 + Math.sin(angle) * 34]
    const [x1, y1] = arc(start)
    const [x2, y2] = arc(cursor)
    const path = sweep >= Math.PI * 2 - 0.0001
      ? 'M50 16 A34 34 0 1 1 49.99 16 Z'
      : `M50 50 L${x1} ${y1} A34 34 0 ${sweep > Math.PI ? 1 : 0} 1 ${x2} ${y2} Z`
    return [{ key: segment.key, path }]
  })
})

const selectedKey = ref<string | null>(null)
const selectedSegment = computed(() => cards.value.flatMap(card => card.segments.map(segment => ({ card, segment }))).find(item => `${item.card.key}:${item.segment.key}` === selectedKey.value) ?? null)

function selectSegment(card: BusinessJourneyChartCard, segment: BusinessJourneyChartSegment): void {
  selectedKey.value = `${card.key}:${segment.key}`
  emit('select-segment', { card, segment })
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
        <Card v-for="card in cards" :key="card.key" class="journey-chart-card" :data-graphic="card.graphic">
          <CardHeader>
            <CardTitle>{{ card.title }}</CardTitle>
            <CardDescription>{{ card.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="card.graphic === 'pie'" class="journey-chart-pie">
              <svg viewBox="0 0 100 100" role="img" aria-label="采购类型金额占比">
                <path v-for="slice in pieSlices" :key="slice.key" :d="slice.path" />
              </svg>
              <strong v-if="largestPie">{{ largestPie.label }} {{ share(largestPie) }}</strong>
              <div class="journey-chart-legend">
                <button v-for="segment in card.segments" :key="segment.key" type="button" @click="selectSegment(card, segment)">
                  <b>{{ segment.label }}</b>
                  <small>{{ segment.count }} 条 · {{ formatWan(segment.amount) }}</small>
                </button>
              </div>
            </div>
            <div v-else-if="card.graphic === 'vertical_bar'" class="journey-chart-columns">
              <button v-for="segment in card.segments" :key="segment.key" type="button" :data-segment="segment.key" @click="selectSegment(card, segment)">
                <b>{{ formatWan(segment.amount) }}</b>
                <span><i :style="{ height: columnHeight(card, segment) }"></i></span>
                <small>{{ segment.label }} · {{ segment.count }} 条</small>
              </button>
            </div>
            <div v-else class="journey-chart-bars">
              <button v-for="segment in card.segments" :key="segment.key" type="button" @click="selectSegment(card, segment)">
                <b>{{ segment.label }}</b>
                <span><i :style="{ width: barWidth(card, segment) }"></i></span>
                <small>{{ segment.count }} 条 · {{ formatWan(segment.amount) }}</small>
              </button>
            </div>
            <div v-if="selectedSegment?.card.key === card.key" class="journey-chart-preview">
              <button v-for="item in selectedSegment.segment.preview" :key="item.public_id" type="button" @click="openJourney(item)">
                <b>{{ item.name }}</b><small>{{ item.customer_name }}</small>
              </button>
              <button v-if="selectedSegment.segment.count > selectedSegment.segment.preview.length" type="button" @click="openSelected">查看详情</button>
            </div>
          </CardContent>
        </Card>
      </div>
      <p v-if="errorMessage" class="journey-chart-note" role="alert">{{ errorMessage }}</p>
    </template>

    <Sheet :open="segmentOpen" @update:open="emit('update:segment-open', $event)">
      <SheetContent side="right" class="journey-chart-sheet">
        <SheetHeader>
          <SheetTitle>{{ segmentLabel }}</SheetTitle>
          <SheetDescription>这一段共 {{ segmentTotal }} 条旅程。</SheetDescription>
        </SheetHeader>
        <div v-if="segmentLoading" class="journey-chart-state">正在读取这一段…</div>
        <div v-else-if="segmentError" class="journey-chart-state" role="alert">{{ segmentError }}</div>
        <div v-else class="journey-chart-segment-list">
          <button v-for="item in segmentItems" :key="item.public_id" type="button" @click="openJourney(item)">
            <span><b>{{ item.name }}</b><small>{{ item.customer_name }}</small></span>
            <AmountText :value="item.amount" size="sm" />
          </button>
        </div>
      </SheetContent>
    </Sheet>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.journey-chart { display: flex; min-height: 0; flex: 1; flex-direction: column; gap: 16px; overflow: auto; }
.journey-chart-summary h2 { margin: 0; color: $wolf-text-primary-v2; font-size: 28px; line-height: 1.3; }
.journey-chart-summary p, .journey-chart-note { margin: 4px 0 0; color: $wolf-text-tertiary-v2; }
.journey-chart-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px; }
.journey-chart-card { grid-column: span 2; min-width: 0; }
.journey-chart-card:nth-child(4), .journey-chart-card:nth-child(5) { grid-column: span 3; }
.journey-chart-card[data-graphic='vertical_bar'] { grid-column: 1 / -1; }
.journey-chart-bars, .journey-chart-columns, .journey-chart-legend, .journey-chart-segment-list { display: grid; gap: 8px; }
.journey-chart-bars button, .journey-chart-legend button, .journey-chart-segment-list button { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 4px 10px; border: 0; border-radius: 8px; background: transparent; padding: 4px; text-align: left; }
.journey-chart-bars button span, .journey-chart-columns button span { height: 8px; overflow: hidden; border-radius: 999px; background: $wolf-bg-muted-v2; }
.journey-chart-bars i, .journey-chart-columns i { display: block; height: 100%; border-radius: inherit; background: #2563eb; }
.journey-chart-bars small, .journey-chart-columns small, .journey-chart-legend small { grid-column: 2; color: $wolf-text-tertiary-v2; }
.journey-chart-legend button { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.journey-chart-legend small { white-space: nowrap; }
.journey-chart-pie { display: grid; justify-items: center; gap: 12px; }
.journey-chart-legend { width: 100%; }
.journey-chart-pie svg { width: 132px; height: 132px; fill: #2563eb; }
.journey-chart-columns { grid-template-columns: repeat(7, minmax(0, 1fr)); align-items: end; }
.journey-chart-columns button { display: flex; min-height: 180px; flex-direction: column; justify-content: flex-end; gap: 6px; border: 0; background: transparent; text-align: center; }
.journey-chart-columns button span { display: flex; height: 112px; align-items: flex-end; background: transparent; }
.journey-chart-columns i { width: 100%; }
.journey-chart-columns button[data-segment='unscheduled'] i { background: #94a3b8; }
.journey-chart-state, .journey-chart-refreshing { display: flex; min-height: 48px; align-items: center; justify-content: center; gap: 8px; color: $wolf-text-tertiary-v2; }
.journey-chart-segment-list button { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
@media (max-width: 1100px) { .journey-chart-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .journey-chart-card, .journey-chart-card:nth-child(4), .journey-chart-card:nth-child(5), .journey-chart-card[data-graphic='vertical_bar'] { grid-column: span 1; } }
@media (max-width: 720px) { .journey-chart-grid, .journey-chart-pie, .journey-chart-columns { grid-template-columns: 1fr; } }
</style>
