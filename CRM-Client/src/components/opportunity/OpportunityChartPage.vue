<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Donut } from '@unovis/ts'
import { VisDonut, VisSingleContainer } from '@unovis/vue'
import ChartBucketActionList, { type ChartBucketAction } from '@/components/crmwolf/chart/ChartBucketActionList.vue'
import ChartBucketDialog from '@/components/crmwolf/chart/ChartBucketDialog.vue'
import ChartCardFrame from '@/components/crmwolf/chart/ChartCardFrame.vue'
import ChartPageShell from '@/components/crmwolf/chart/ChartPageShell.vue'
import { Button } from '@/components/ui/button'
import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { formatCurrency } from '@/utils/format'
import type {
  OpportunityChartBucket,
  OpportunityChartBucketOpportunities,
  OpportunityChartCard,
  OpportunityChartPreview,
  OpportunityChartResponse,
} from '@/schemas/opportunity'

const props = defineProps<{
  chart: OpportunityChartResponse | null
  loading: boolean
  error: string
  bucketOpportunities: OpportunityChartBucketOpportunities | null
  bucketLoading: boolean
  bucketError: string
  bucketResetToken?: number
}>()

const emit = defineEmits<{
  retry: []
  'retry-bucket': [card: OpportunityChartCard, bucket: OpportunityChartBucket]
  'open-opportunity': [opportunityId: string]
  'view-bucket': [card: OpportunityChartCard, bucket: OpportunityChartBucket]
  'load-more': []
  'close-bucket': []
}>()

type CardKey = 'status' | 'purchase_type' | 'license_type' | 'amount_band' | 'product' | 'win_probability' | 'expected_closing_month'
type CardPresentation = 'donut' | 'bar' | 'forecast'

interface CardMeta {
  title: string
  description: string
  presentation: CardPresentation
}

const cardOrder: CardKey[] = [
  'status',
  'win_probability',
  'purchase_type',
  'license_type',
  'amount_band',
  'product',
  'expected_closing_month',
]

const cardMeta: Record<CardKey, CardMeta> = {
  status: { title: '状态', description: '跟进中、已赢单、已输单。', presentation: 'donut' },
  purchase_type: { title: '采购类型', description: '按预计金额占比。', presentation: 'donut' },
  license_type: { title: '授权模式', description: '订阅和买断各占多少金额。', presentation: 'donut' },
  amount_band: { title: '金额档', description: '按预计金额分档。', presentation: 'bar' },
  product: { title: '产品', description: '数量最多的 8 个，其余并进其他。', presentation: 'bar' },
  win_probability: { title: '赢率', description: '按商机上的赢率分档，不是采购阶段。', presentation: 'bar' },
  expected_closing_month: { title: '预计成交', description: '本月起 6 个月；窗口外日期不纳入本卡片，未填写日期单独列为未排期。', presentation: 'forecast' },
}

const chartConfig = { count: { label: '商机数' }, amount: { label: '金额' } } satisfies ChartConfig
const chartColors = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
]

function bucketColor(index: number, bucket: OpportunityChartBucket): string {
  if (bucket.key === 'blank' || bucket.key === 'other' || bucket.key === 'unscheduled' || bucket.label === '未排期') return 'hsl(var(--muted-foreground))'
  return chartColors[index % chartColors.length] ?? 'hsl(var(--chart-1))'
}

const selectedCard = ref<OpportunityChartCard | null>(null)
const selectedBucket = ref<OpportunityChartBucket | null>(null)
const dialogOpen = ref(false)

const cards = computed(() => cardOrder.map((key) => props.chart?.cards.find((card) => card.key === key) ?? { key, buckets: [] }))
const pageState = computed(() => {
  if (props.loading && props.chart === null) return 'loading' as const
  if (props.error !== '' && props.chart === null) return 'error' as const
  if (props.chart === null) return 'empty' as const
  return 'ready' as const
})

function isUnscheduledBucket(bucket: OpportunityChartBucket): boolean {
  return bucket.key === 'unscheduled' || bucket.label === '未排期'
}

function isMutedBucket(bucket: OpportunityChartBucket): boolean {
  return bucket.key === 'blank' || bucket.key === 'other' || bucket.key === 'unscheduled'
}

function maxForecastAmount(card: OpportunityChartCard): number {
  return Math.max(...card.buckets.map((bucket) => Number.isFinite(bucket.amount) ? Math.max(bucket.amount, 0) : 0), 0)
}

function forecastBarStyle(card: OpportunityChartCard, bucket: OpportunityChartBucket): Record<string, string> {
  const amount = Number.isFinite(bucket.amount) ? Math.max(bucket.amount, 0) : 0
  const maximum = maxForecastAmount(card)
  return { height: `${Math.round((maximum > 0 ? Math.max(0, Math.min(amount / maximum, 1)) : 0) * 100)}%` }
}

function formatAxisAmount(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '¥0'
  if (value >= 10000) return `¥${(value / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}万`
  return `¥${Math.round(value).toLocaleString('zh-CN')}`
}

function hasData(card: OpportunityChartCard): boolean { return card.buckets.some((bucket) => bucket.count > 0) }

function resetDialogLocally(): void {
  dialogOpen.value = false
  selectedCard.value = null
  selectedBucket.value = null
}

watch(() => props.bucketResetToken, () => {
  if (dialogOpen.value) resetDialogLocally()
})

const bucketMatches = computed(() => props.bucketOpportunities !== null && selectedCard.value !== null && selectedBucket.value !== null
  && props.bucketOpportunities.chart === selectedCard.value.key && props.bucketOpportunities.bucket === selectedBucket.value.key)
const dialogItems = computed<OpportunityChartPreview[]>(() => {
  if (bucketMatches.value && props.bucketOpportunities !== null) return props.bucketOpportunities.opportunities
  if (props.bucketError !== '') return []
  return selectedBucket.value?.preview ?? []
})
const dialogTotal = computed(() => bucketMatches.value && props.bucketOpportunities !== null ? props.bucketOpportunities.total : selectedBucket.value?.count ?? 0)

function isCardKey(value: string): value is CardKey { return value in cardMeta }
function metaFor(card: OpportunityChartCard): CardMeta { return isCardKey(card.key) ? cardMeta[card.key] : cardMeta.status }
type MetricMode = 'count' | 'amount'
function metricModeFor(card: OpportunityChartCard): MetricMode { return card.key === 'purchase_type' || card.key === 'license_type' || card.key === 'expected_closing_month' ? 'amount' : 'count' }
function normalizeRatio(value: number): number { return Number.isFinite(value) ? Math.max(0, Math.min(value / 100, 1)) : 0 }
function bucketRatio(bucket: OpportunityChartBucket, mode: MetricMode): number { return normalizeRatio(mode === 'count' ? bucket.ratio : bucket.amount_ratio) }
function isWideCard(card: OpportunityChartCard): boolean { return card.key === 'amount_band' || card.key === 'product' || card.key === 'expected_closing_month' }
function cardClass(card: OpportunityChartCard): string {
  const presentation = metaFor(card).presentation
  return ['opportunity-chart-card', presentation === 'bar' ? 'opportunity-chart-card--bar' : '', presentation === 'forecast' ? 'opportunity-chart-card--forecast' : '', isWideCard(card) ? 'opportunity-chart-card--wide' : ''].filter(Boolean).join(' ')
}

interface DonutDatum { key: string, label: string, value: number, fill: string }
interface OpportunityBucketAction extends ChartBucketAction { card: OpportunityChartCard, bucket: OpportunityChartBucket }

function donutData(card: OpportunityChartCard): DonutDatum[] {
  const mode = metricModeFor(card)
  return card.buckets.map((bucket, index) => ({ bucket, index })).filter(({ bucket }) => bucket.count > 0).map(({ bucket, index }) => ({ key: bucket.key, label: bucket.label, value: bucketRatio(bucket, mode), fill: bucketColor(index, bucket) }))
}
function maxRatio(card: OpportunityChartCard): number { return Math.max(...card.buckets.map((bucket) => bucketRatio(bucket, metricModeFor(card))), 0.01) }
function barWidth(card: OpportunityChartCard, bucket: OpportunityChartBucket): string { return `${Math.round(Math.min(bucketRatio(bucket, metricModeFor(card)) / maxRatio(card), 1) * 100)}%` }
function formatCount(value: number): string { return `${value.toLocaleString('zh-CN')} 条` }
function formatSummaryAmount(value: number): string { return Number.isFinite(value) ? `¥ ${(value / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万` : '¥ 0' }

function actionsFor(card: OpportunityChartCard): OpportunityBucketAction[] {
  const presentation = metaFor(card).presentation
  return card.buckets.map((bucket, index) => ({
    key: bucket.key,
    label: bucket.label,
    ariaLabel: `${bucket.label}，${formatCount(bucket.count)} · ${formatCurrency(bucket.amount)}`,
    value: `${formatCount(bucket.count)} · ${formatCurrency(bucket.amount)}`,
    color: bucketColor(index, bucket),
    disabled: bucket.count <= 0,
    class: presentation === 'donut'
      ? 'opportunity-chart-legend-row'
      : presentation === 'bar'
        ? 'opportunity-chart-bar-row'
        : `opportunity-chart-bar-row--forecast opportunity-chart-forecast-column ${isUnscheduledBucket(bucket) ? 'opportunity-chart-forecast-column--unscheduled' : ''}`,
    card,
    bucket,
  }))
}

function openDonutDatum(card: OpportunityChartCard, datum: DonutDatum): void {
  const bucket = card.buckets.find((item) => item.key === datum.key)
  if (bucket !== undefined) openBucket(card, bucket)
}

function activateAction(action: OpportunityBucketAction): void { openBucket(action.card, action.bucket) }
function handleDialogChange(open: boolean): void {
  dialogOpen.value = open
  if (!open) {
    selectedCard.value = null
    selectedBucket.value = null
    emit('close-bucket')
  }
}
function openOpportunity(id: string): void { emit('open-opportunity', id) }
function retryBucket(): void {
  if (selectedCard.value !== null && selectedBucket.value !== null) emit('retry-bucket', selectedCard.value, selectedBucket.value)
}
function openBucket(card: OpportunityChartCard, bucket: OpportunityChartBucket): void {
  if (bucket.count <= 0) return
  selectedCard.value = card
  selectedBucket.value = bucket
  dialogOpen.value = true
  emit('view-bucket', card, bucket)
}
</script>

<template>
  <ChartPageShell :state="pageState" aria-label="商机分析" class="opportunity-chart-page">
    <template #loading>
      <div class="opportunity-chart-state" role="status">正在整理商机分析…</div>
    </template>
    <template #error>
      <div class="opportunity-chart-state" role="alert">
        <strong>{{ error }}</strong>
        <Button type="button" variant="outline" :disabled="loading" @click="emit('retry')">重新加载</Button>
      </div>
    </template>
    <template #empty>
      <div class="opportunity-chart-state">
        <strong>暂无可展示的商机数据</strong>
        <Button v-if="error" type="button" variant="outline" :disabled="loading" @click="emit('retry')">重试</Button>
      </div>
    </template>
    <template #summary>
      <header class="opportunity-chart-summary">
        <h2>{{ chart?.population.toLocaleString('zh-CN') }} 条 · {{ formatSummaryAmount(chart?.total_amount ?? 0) }}</h2>
        <p>当前筛选范围内的完整商机集合。金额按预计金额汇总。</p>
      </header>
    </template>
    <template #refreshing>
      <div v-if="loading" class="opportunity-chart-refreshing" role="status">正在更新图表…</div>
    </template>
    <template #inline-error>
      <p v-if="error" class="opportunity-chart-inline-error" role="alert">
        {{ error }}
        <Button type="button" variant="outline" size="sm" :disabled="loading" @click="emit('retry')">重试</Button>
      </p>
    </template>
    <template #ready>
      <div class="opportunity-chart-grid">
        <ChartCardFrame
          v-for="card in cards"
          :key="card.key"
          :card-key="card.key"
          :title="metaFor(card).title"
          :description="metaFor(card).description"
          :wide="isWideCard(card)"
          test-id-prefix="opportunity-chart-card"
          :class="cardClass(card)"
          :content-class="metaFor(card).presentation === 'donut' ? 'grid min-w-0 grid-cols-1 items-center gap-6 pb-6 md:grid-cols-[220px_minmax(0,1fr)]' : ''"
        >
          <template #content>
            <template v-if="metaFor(card).presentation === 'donut'">
              <ChartContainer
                :config="chartConfig"
                class="opportunity-chart-donut-chart aspect-square h-[220px] w-[220px]"
                :style="{
                  '--vis-donut-central-label-font-size': '22px',
                  '--vis-donut-central-label-font-weight': '600',
                  '--vis-donut-central-label-text-color': 'hsl(var(--foreground))',
                  '--vis-donut-central-sub-label-text-color': 'hsl(var(--muted-foreground))',
                }"
              >
                <div v-if="hasData(card)" class="opportunity-chart-donut">
                  <VisSingleContainer :data="donutData(card)" :margin="{ top: 8, bottom: 8 }">
                    <VisDonut
                      :data="donutData(card)"
                      :value="(datum: DonutDatum) => datum.value"
                      :color="(datum: DonutDatum) => datum.fill"
                      :arc-width="30"
                      :central-label="String(chart?.population ?? 0)"
                      central-sub-label="条"
                      :central-label-offset-y="10"
                      :events="{ [Donut.selectors.segment]: { click: (datum: DonutDatum) => openDonutDatum(card, datum) } }"
                    />
                  </VisSingleContainer>
                </div>
                <div v-else class="opportunity-chart-card-empty">暂无分布数据</div>
              </ChartContainer>
              <ChartBucketActionList
                v-if="hasData(card)"
                :actions="actionsFor(card)"
                :aria-label="`${metaFor(card).title}分组`"
                :test-id-prefix="`opportunity-chart-bucket-${card.key}`"
                class="opportunity-chart-legend"
                @activate="activateAction"
              >
                <template #default="{ action }">
                  <i :style="{ backgroundColor: action.color }" aria-hidden="true"></i>
                  <span class="opportunity-chart-legend-label">{{ action.label }}</span>
                  <span class="opportunity-chart-legend-value">{{ action.value }}</span>
                </template>
              </ChartBucketActionList>
            </template>
            <template v-else-if="metaFor(card).presentation === 'bar'">
              <ChartBucketActionList
                v-if="hasData(card)"
                :actions="actionsFor(card)"
                :aria-label="`${metaFor(card).title}分组`"
                :test-id-prefix="`opportunity-chart-bucket-${card.key}`"
                class="opportunity-chart-bar-actions"
                @activate="activateAction"
              >
                <template #default="{ action }">
                  <span class="truncate">{{ action.label }}</span>
                  <span class="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <span class="opportunity-chart-bar-fill h-full rounded-full" :class="isMutedBucket(action.bucket) ? 'bg-muted-foreground' : 'bg-primary'" :style="{ width: barWidth(action.card, action.bucket) }" />
                  </span>
                  <span class="text-muted-foreground tabular-nums">{{ action.value }}</span>
                </template>
              </ChartBucketActionList>
              <div v-else class="opportunity-chart-card-empty">暂无分布数据</div>
            </template>
            <ChartContainer v-else :config="chartConfig" class="opportunity-chart-forecast-chart aspect-auto h-[240px]">
              <div v-if="hasData(card)" class="opportunity-chart-forecast" :aria-label="`${metaFor(card).title}，按预计金额比较`">
                <div class="opportunity-chart-forecast-plot">
                  <div class="opportunity-chart-forecast-y-axis" aria-hidden="true">
                    <span>{{ formatAxisAmount(maxForecastAmount(card)) }}</span>
                    <span>{{ formatAxisAmount(maxForecastAmount(card) / 2) }}</span>
                    <span>¥0</span>
                  </div>
                  <div class="opportunity-chart-forecast-plot-area">
                    <div class="opportunity-chart-forecast-grid" aria-hidden="true"><span></span><span></span><span></span></div>
                    <ChartBucketActionList
                      :actions="actionsFor(card)"
                      :aria-label="`${metaFor(card).title}分组`"
                      :test-id-prefix="`opportunity-chart-bucket-${card.key}`"
                      class="opportunity-chart-forecast-columns"
                      @activate="activateAction"
                    >
                      <template #default="{ action }">
                        <span class="opportunity-chart-forecast-track">
                          <span class="opportunity-chart-bar-fill opportunity-chart-forecast-fill" :style="{ backgroundColor: action.color, ...forecastBarStyle(action.card, action.bucket) }" />
                        </span>
                        <span class="opportunity-chart-forecast-label">{{ action.label }}</span>
                      </template>
                    </ChartBucketActionList>
                    <span class="opportunity-chart-forecast-baseline" aria-hidden="true"></span>
                  </div>
                </div>
              </div>
              <div v-else class="opportunity-chart-card-empty">暂无预测数据</div>
            </ChartContainer>
          </template>
        </ChartCardFrame>
      </div>
    </template>
    <template #overlays>
      <ChartBucketDialog
        :open="dialogOpen"
        :title="selectedBucket?.label ?? '商机明细'"
        :description="`${selectedCard === null ? '' : metaFor(selectedCard).title} · 共 ${dialogTotal} 条`"
        :loading="bucketLoading"
        :error="bucketError || null"
        :has-items="dialogItems.length > 0"
        :has-more="dialogItems.length < dialogTotal"
        :reset-key="bucketResetToken"
        test-id-prefix="opportunity-chart-bucket"
        @update:open="handleDialogChange"
        @retry="retryBucket"
        @load-more="emit('load-more')"
      >
        <template #loading><div class="opportunity-chart-dialog-state" role="status">正在加载商机明细…</div></template>
        <template #error><div class="opportunity-chart-dialog-state" role="alert"><span>{{ bucketError }}</span></div></template>
        <template #empty><div class="opportunity-chart-dialog-state">这一段没有商机。</div></template>
        <template #items>
          <div class="opportunity-chart-opportunity-list">
            <Button v-for="item in dialogItems" :key="item.id" type="button" variant="ghost" class="opportunity-chart-opportunity" @click="openOpportunity(item.id)">
              <span><strong>{{ item.name }}</strong><small>{{ item.customer_name ?? '未关联客户' }} · {{ item.owner_name ?? '未分配负责人' }}</small></span>
              <span>{{ formatCurrency(item.amount) }}</span>
            </Button>
          </div>
        </template>
        <template #load-more-label>{{ bucketError || '查看更多' }}</template>
      </ChartBucketDialog>
    </template>
  </ChartPageShell>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.opportunity-chart-page { display: flex; flex: 1 1 auto; min-width: 0; min-height: 0; flex-direction: column; gap: $wolf-space-md-v2; overflow: auto; padding: $wolf-space-md-v2; }
.opportunity-chart-summary h2 { margin: 0; color: $wolf-text-primary-v2; font-size: $wolf-font-size-title-v2; line-height: 1.25; }
.opportunity-chart-summary p { margin: $wolf-space-xs-v2 0 0; color: $wolf-text-tertiary-v2; }
.opportunity-chart-state, .opportunity-chart-refreshing, .opportunity-chart-dialog-state { display: flex; align-items: center; justify-content: center; gap: $wolf-space-sm-v2; color: $wolf-text-tertiary-v2; }
.opportunity-chart-state { min-height: 320px; flex-direction: column; text-align: center; }
.opportunity-chart-refreshing { justify-content: flex-start; min-height: 28px; font-size: 13px; }
.opportunity-chart-inline-error { display: flex; align-items: center; gap: $wolf-space-sm-v2; margin: 0; color: $wolf-danger-text-v2; font-size: 13px; }
.opportunity-chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: $wolf-space-md-v2; }
.opportunity-chart-card { min-width: 0; }
.opportunity-chart-card--wide { grid-column: 1 / -1; }
.opportunity-chart-donut-chart { width: 220px; height: 220px; min-height: 0; aspect-ratio: 1; }
.opportunity-chart-donut { width: 220px; height: 220px; }
.opportunity-chart-donut [data-vis-single-container] { width: 100%; height: 100%; }
.opportunity-chart-legend { display: grid; gap: $wolf-space-sm-v2; }
.opportunity-chart-bar-actions { gap: $wolf-space-sm-v2; }
.opportunity-chart-bar-actions :deep(.opportunity-chart-bar-row) { display: grid; grid-template-columns: 88px minmax(0, 1fr) auto; align-items: center; gap: 12px; text-align: left; }
.opportunity-chart-legend :deep(.opportunity-chart-legend-row) { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; align-items: center; column-gap: $wolf-space-sm-v2; width: 100%; border: 0; border-radius: $wolf-radius-control-v2; background: transparent; padding: 2px 0; font-size: 14px; text-align: left; }
.opportunity-chart-legend :deep(.opportunity-chart-legend-row:not(:disabled):hover) { background: $wolf-bg-muted-v2; }
.opportunity-chart-legend :deep(.opportunity-chart-legend-row:disabled) { cursor: default; opacity: .65; }
.opportunity-chart-legend :deep(.opportunity-chart-legend-row i) { width: 8px; height: 8px; border-radius: 50%; }
.opportunity-chart-legend-label { overflow: hidden; color: $wolf-text-primary-v2; text-overflow: ellipsis; white-space: nowrap; }
.opportunity-chart-legend-value { color: $wolf-text-tertiary-v2; font-variant-numeric: tabular-nums; white-space: nowrap; }
.opportunity-chart-bar-fill { display: block; min-width: 0; }
.opportunity-chart-card-empty { padding: 12px 0; color: $wolf-text-tertiary-v2; font-size: 13px; text-align: center; }
.opportunity-chart-dialog-state { min-height: 120px; }
.opportunity-chart-opportunity-list { display: grid; max-height: min(55vh, 440px); gap: 2px; overflow-y: auto; }
.opportunity-chart-opportunity { display: flex; width: 100%; min-height: 52px; justify-content: space-between; gap: 16px; padding: 8px 10px; text-align: left; }
.opportunity-chart-opportunity > span:first-child { min-width: 0; }
.opportunity-chart-opportunity strong, .opportunity-chart-opportunity small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opportunity-chart-opportunity strong { color: $wolf-text-primary-v2; }
.opportunity-chart-opportunity small { margin-top: 3px; color: $wolf-text-tertiary-v2; font-size: 12px; }

.opportunity-chart-forecast-chart { width: 100%; height: 240px; min-height: 240px; }
.opportunity-chart-forecast { min-height: 0; padding: 0; }
.opportunity-chart-forecast-plot { display: grid; grid-template-columns: 58px minmax(0, 1fr); min-height: 0; }
.opportunity-chart-forecast-y-axis { display: flex; flex-direction: column; justify-content: space-between; padding: 4px 10px 18px 0; color: $wolf-text-tertiary-v2; font-size: 11px; line-height: 1; text-align: right; }
.opportunity-chart-forecast-plot-area { position: relative; min-width: 0; padding: 4px 0 0; }
.opportunity-chart-forecast-grid { position: absolute; inset: 4px 0 18px; display: flex; flex-direction: column; justify-content: space-between; pointer-events: none; }
.opportunity-chart-forecast-grid span { border-top: 1px solid $wolf-border-light-v2; }
.opportunity-chart-forecast-columns { position: relative; z-index: 1; display: flex; height: 220px; align-items: flex-end; gap: $wolf-space-sm-v2; }
.opportunity-chart-forecast-columns :deep(.opportunity-chart-forecast-column) { display: grid; height: 100%; min-width: 0; flex: 1 1 0; grid-template-rows: minmax(0, 1fr) 16px; align-items: stretch; gap: 2px; padding: 0 4px; text-align: center; }
.opportunity-chart-forecast-columns :deep(.opportunity-chart-forecast-column--unscheduled) { margin-left: $wolf-space-sm-v2; border-left: 1px dashed $wolf-border-default-v2; border-radius: 0; padding-left: $wolf-space-md-v2; }
.opportunity-chart-forecast-track { display: flex; min-height: 0; height: 100%; flex-direction: column; align-items: center; justify-content: flex-end; }
.opportunity-chart-forecast-fill { display: block; width: min(42px, 72%); min-width: 0; min-height: 0; border-radius: $wolf-radius-sm-v2 $wolf-radius-sm-v2 0 0; transition: height .2s ease; }
.opportunity-chart-forecast-columns :deep(.opportunity-chart-forecast-column:disabled .opportunity-chart-forecast-fill) { background: $wolf-bg-muted-v2 !important; }
.opportunity-chart-forecast-label { overflow: hidden; color: $wolf-text-primary-v2; font-size: 12px; font-weight: 500; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.opportunity-chart-forecast-baseline { position: absolute; right: 0; bottom: 18px; left: 0; z-index: 2; border-top: 1px solid $wolf-border-default-v2; pointer-events: none; }
.opportunity-chart-forecast-columns :deep(.opportunity-chart-bar-row--forecast:not(:disabled):hover) { background: $wolf-bg-muted-v2; }
.opportunity-chart-forecast-columns :deep(.opportunity-chart-bar-row--forecast:focus-visible) { outline: 2px solid $wolf-focus-ring-color-v2; outline-offset: 2px; }

@media (max-width: 900px) {
  .opportunity-chart-grid { grid-template-columns: minmax(0, 1fr); }
}

@media (max-width: 600px) {
  .opportunity-chart-forecast-plot { grid-template-columns: 44px minmax(0, 1fr); }
  .opportunity-chart-forecast-y-axis { padding-right: 6px; font-size: 10px; }
  .opportunity-chart-forecast-columns :deep(.opportunity-chart-forecast-column) { padding-right: 2px; padding-left: 2px; }
  .opportunity-chart-forecast-columns :deep(.opportunity-chart-forecast-column--unscheduled) { margin-left: 0; padding-left: $wolf-space-sm-v2; }
}
</style>
