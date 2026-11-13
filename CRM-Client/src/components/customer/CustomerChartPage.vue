<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Area, Donut } from '@unovis/ts'
import { VisArea, VisAxis, VisDonut, VisLine, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { Button } from '@/components/ui/button'
import { ChartContainer, ChartCrosshair, ChartTooltip, ChartTooltipContent, componentToString, type ChartConfig } from '@/components/ui/chart'
import ChartBucketActionList, { type ChartBucketAction } from '@/components/crmwolf/chart/ChartBucketActionList.vue'
import ChartBucketDialog from '@/components/crmwolf/chart/ChartBucketDialog.vue'
import ChartCardFrame from '@/components/crmwolf/chart/ChartCardFrame.vue'
import ChartPageShell from '@/components/crmwolf/chart/ChartPageShell.vue'
import type { CustomerChartBucket, CustomerChartBucketCustomers, CustomerChartCard, CustomerChartResponse } from '@/schemas/customer'

const CHART_COLOR = 'hsl(var(--chart-1))'
const CHART_COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))']

const props = defineProps<{
  chart: CustomerChartResponse | null
  loading: boolean
  error: string
  bucketCustomers: CustomerChartBucketCustomers | null
  bucketLoading: boolean
  bucketError: string
  bucketResetToken?: number
}>()

const emit = defineEmits<{
  retry: []
  'open-customer': [customerId: string]
  'view-bucket': [card: CustomerChartCard, bucket: CustomerChartBucket]
  'load-more': []
  'close-bucket': []
}>()

interface PieDatum { key: string, label: string, count: number, ratio: number, fill: string }
interface RankDatum { index: number, label: string, count: number, ratio: number }
interface CustomerBucketAction extends ChartBucketAction { card: CustomerChartCard, bucket: CustomerChartBucket }

const population = computed(() => props.chart?.population ?? 0)
const pieCards = computed(() => (props.chart?.cards ?? []).filter((card) => card.key === 'status' || card.key === 'license' || card.key === 'scale'))
const industryCard = computed(() => props.chart?.cards.find((card) => card.key === 'industry') ?? null)
const cityCard = computed(() => props.chart?.cards.find((card) => card.key === 'city') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'created_month') ?? null)
const selectedCard = ref<CustomerChartCard | null>(null)
const selectedBucket = ref<CustomerChartBucket | null>(null)
const dialogOpen = ref(false)

watch(() => props.bucketResetToken, () => {
  selectedCard.value = null
  selectedBucket.value = null
  dialogOpen.value = false
})

const cardTitle = computed(() => selectedCard.value?.title ?? '')
const subtitle = computed(() => `${cardTitle.value} · 共 ${props.bucketCustomers?.total ?? selectedBucket.value?.count ?? 0} 家`)

function rememberBucket(card: CustomerChartCard, bucket: CustomerChartBucket): void {
  selectedCard.value = card
  selectedBucket.value = bucket
  dialogOpen.value = true
}

function viewBucket(card: CustomerChartCard, bucket: CustomerChartBucket): void {
  if (bucket.count === 0) return
  rememberBucket(card, bucket)
  emit('view-bucket', card, bucket)
}

function countText(bucket: CustomerChartBucket): string {
  return `${bucket.count} 家 · ${bucket.ratio}%`
}

function sliceColor(index: number, key: string): string {
  if (key === 'blank' || key === 'other') return 'hsl(var(--muted-foreground))'
  return CHART_COLORS[index % CHART_COLORS.length] ?? CHART_COLOR
}

function pieData(card: CustomerChartCard): PieDatum[] {
  return card.buckets.filter((bucket) => bucket.count > 0).map((bucket) => ({
    key: bucket.key,
    label: bucket.label,
    count: bucket.count,
    ratio: bucket.ratio,
    fill: `var(--color-${bucket.key})`,
    [bucket.key]: bucket.count,
  }))
}

function pieConfig(card: CustomerChartCard): ChartConfig {
  return Object.fromEntries(card.buckets.map((bucket, index) => [bucket.key, { label: bucket.label, color: sliceColor(index, bucket.key) }]))
}

function chartTriggers(selector: string, config: ChartConfig): Record<string, (datum: unknown, x: number | Date) => string> {
  const rendered = componentToString(config, ChartTooltipContent, { hideLabel: true })
  return rendered ? { [selector]: rendered } : {}
}

function namedBuckets(card: CustomerChartCard): CustomerChartBucket[] {
  return card.buckets.filter((bucket) => bucket.key !== 'other' && bucket.key !== 'blank')
}

function chartRows(card: CustomerChartCard): CustomerChartBucket[] {
  return card.key === 'created_month' ? card.buckets : namedBuckets(card)
}

function rankData(card: CustomerChartCard): RankDatum[] {
  return chartRows(card).map((bucket, index) => ({ index, label: bucket.label, count: bucket.count, ratio: bucket.ratio }))
}

function bucketActions(card: CustomerChartCard, includeFolded = false): CustomerBucketAction[] {
  const buckets = includeFolded ? card.buckets : namedBuckets(card)
  return buckets.map((bucket) => ({
    key: bucket.key,
    label: bucket.label,
    ariaLabel: `${bucket.label}，${countText(bucket)}`,
    value: countText(bucket),
    disabled: bucket.count === 0,
    card,
    bucket,
  }))
}

function activate(action: CustomerBucketAction): void {
  viewBucket(action.card, action.bucket)
}

const monthConfig = { count: { label: '客户', color: CHART_COLOR } } satisfies ChartConfig

function openRank(card: CustomerChartCard | null, datum: RankDatum): void {
  const bucket = card?.buckets[datum.index]
  if (card && bucket) viewBucket(card, bucket)
}
</script>

<template>
  <ChartPageShell :state="loading && !chart ? 'loading' : error && !chart ? 'error' : chart ? 'ready' : 'empty'" aria-label="客户图表">
    <template #loading>正在整理客户图表…</template>
    <template #error>
      <div class="customer-chart-page__state" role="alert">
        <span>{{ error }}</span>
        <Button type="button" variant="outline" size="sm" @click="emit('retry')">重试</Button>
      </div>
    </template>
    <template #empty><div class="customer-chart-page__state">暂无客户图表</div></template>
    <template #summary>
      <header class="customer-chart-page__heading">
        <h2>{{ population }} 家</h2>
        <p>当前筛选范围内的客户。一页同时看，没有负责人。行业、城市只留数量最多的 8 个，其余并进其他。</p>
      </header>
    </template>
    <template #inline-error><p v-if="error" class="customer-chart-page__refresh-error" role="alert">{{ error }}</p></template>
    <div v-if="chart" class="customer-chart-page__grid">
      <ChartCardFrame v-for="card in pieCards" :key="card.key" :card-key="card.key" :title="card.title" :description="card.description" content-class="customer-chart-page__donut-content">
        <template #content>
          <ChartContainer
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
                :value="(datum: PieDatum) => datum.count"
                :color="(datum: PieDatum) => datum.fill"
                :arc-width="30"
                :central-label-offset-y="10"
                :central-label="String(population)"
                central-sub-label="客户"
                :events="{ [Donut.selectors.segment]: { click: (datum: PieDatum) => { const bucket = card.buckets.find((item) => item.key === datum.key); if (bucket) viewBucket(card, bucket) } } }"
              />
              <ChartTooltip :triggers="chartTriggers(Donut.selectors.segment, pieConfig(card))" />
            </VisSingleContainer>
          </ChartContainer>
          <div class="grid gap-2 text-sm">
            <div v-for="bucket in card.buckets" :key="bucket.key" class="grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-2">
              <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: sliceColor(card.buckets.indexOf(bucket), bucket.key) }" />
              <span>{{ bucket.label }}</span>
              <span class="text-muted-foreground tabular-nums">{{ countText(bucket) }}</span>
            </div>
            <ChartBucketActionList :actions="bucketActions(card, true)" :aria-label="`${card.title}可访问分组`" :test-id-prefix="`customer-${card.key}-bucket`" @activate="activate" />
          </div>
        </template>
      </ChartCardFrame>

      <ChartCardFrame v-if="industryCard" :card-key="industryCard.key" :title="industryCard.title" :description="industryCard.description">
        <template #content>
          <ChartBucketActionList :actions="bucketActions(industryCard)" :aria-label="industryCard.title" test-id-prefix="customer-industry-bucket" @activate="activate">
            <template #default="{ action }">
              <span class="grid w-full grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm">
                <span class="truncate">{{ action.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-muted"><span class="block h-full rounded-full bg-primary" :style="{ width: `${Math.round((action.bucket.count / Math.max(...namedBuckets(industryCard).map((item) => item.count), 1)) * 100)}%` }" /></span>
                <span class="text-muted-foreground tabular-nums">{{ countText(action.bucket) }}</span>
              </span>
            </template>
          </ChartBucketActionList>
        </template>
      </ChartCardFrame>

      <ChartCardFrame v-if="cityCard" :card-key="cityCard.key" :title="cityCard.title" :description="cityCard.description" wide>
        <template #content>
          <ChartBucketActionList :actions="bucketActions(cityCard)" :aria-label="cityCard.title" test-id-prefix="customer-city-bucket" @activate="activate">
            <template #default="{ action }">
              <span class="grid w-full grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm">
                <span class="truncate">{{ action.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-muted"><span class="block h-full rounded-full bg-primary" :style="{ width: `${Math.round((action.bucket.count / Math.max(...namedBuckets(cityCard).map((item) => item.count), 1)) * 100)}%` }" /></span>
                <span class="text-muted-foreground tabular-nums">{{ countText(action.bucket) }}</span>
              </span>
            </template>
          </ChartBucketActionList>
        </template>
      </ChartCardFrame>

      <ChartCardFrame v-if="monthCard" :card-key="monthCard.key" :title="monthCard.title" :description="monthCard.description" wide>
        <template #content>
          <ChartContainer :config="monthConfig" class="aspect-auto h-[240px]">
            <VisXYContainer :data="rankData(monthCard)" :height="220">
              <VisArea :x="(datum: RankDatum) => datum.index" :y="(datum: RankDatum) => datum.count" :color="monthConfig.count.color" :opacity="0.4" :events="{ [Area.selectors.area]: { click: (datum: RankDatum) => openRank(monthCard, datum) } }" />
              <VisLine :x="(datum: RankDatum) => datum.index" :y="(datum: RankDatum) => datum.count" :color="monthConfig.count.color" :line-width="1" />
              <VisAxis type="x" :tick-line="false" :domain-line="false" :grid-line="false" :num-ticks="monthCard.buckets.length" :tick-values="rankData(monthCard).map((datum) => datum.index)" :tick-format="(value: number) => monthCard?.buckets[Math.round(value)]?.label ?? ''" />
              <VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" />
              <ChartTooltip />
              <ChartCrosshair :template="componentToString(monthConfig, ChartTooltipContent, { labelKey: 'label' })" :color="monthConfig.count.color" />
            </VisXYContainer>
          </ChartContainer>
          <ChartBucketActionList :actions="bucketActions(monthCard, true)" :aria-label="monthCard.title" test-id-prefix="customer-month-bucket" @activate="activate" />
        </template>
      </ChartCardFrame>
    </div>
    <template #overlays>
      <ChartBucketDialog
        :open="dialogOpen"
        :title="selectedBucket?.label ?? '客户'"
        :description="bucketLoading && !bucketCustomers ? '正在读取这一组客户…' : bucketError && !bucketCustomers ? bucketError : subtitle"
        :loading="bucketLoading"
        :error="bucketError || null"
        class="customer-chart-dialog"
        :has-items="Boolean(bucketCustomers)"
        :has-more="Boolean(bucketCustomers && bucketCustomers.customers.length < bucketCustomers.total)"
        :reset-key="bucketResetToken"
        test-id-prefix="customer-chart"
        @update:open="(open) => { if (!open) { dialogOpen = false; selectedCard = null; selectedBucket = null; emit('close-bucket') } }"
        @retry="() => { if (selectedCard && selectedBucket) emit('view-bucket', selectedCard, selectedBucket) }"
        @load-more="emit('load-more')"
      >
        <template #load-more-label>{{ bucketLoading ? '正在读取…' : bucketError || '查看更多' }}</template>
        <template #items>
          <div class="customer-chart-dialog-list">
            <button v-for="customer in bucketCustomers?.customers ?? []" :key="customer.id" type="button" @click="emit('open-customer', customer.id)">
              <span>{{ customer.name }}</span>
              <small>{{ customer.owner_name || '无负责人' }}</small>
            </button>
          </div>
        </template>
      </ChartBucketDialog>
    </template>
  </ChartPageShell>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customer-chart-page__state,
.customer-chart-page__refresh-error { display: flex; align-items: center; gap: $wolf-space-sm-v2; color: $wolf-text-secondary-v2; }
.customer-chart-page__heading h2 { margin: 0; font-size: $wolf-font-size-title-v2; line-height: 1.25; }
.customer-chart-page__heading p,
.customer-chart-page__refresh-error { margin: $wolf-space-xs-v2 0 0; color: $wolf-text-tertiary-v2; }
.customer-chart-page__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: $wolf-space-md-v2; }
.customer-chart-dialog-list { display: flex; max-height: 24rem; flex-direction: column; overflow: auto; }
.customer-chart-dialog-list button { display: flex; justify-content: space-between; gap: $wolf-space-md-v2; border: 0; border-bottom: 1px solid $wolf-border-default-v2; background: transparent; padding: $wolf-space-sm-v2 0; text-align: left; }
:deep(.customer-chart-page__donut-content) { display: grid; grid-template-columns: 220px minmax(0, 1fr); align-items: center; gap: 1.5rem; padding-bottom: 1.5rem; }
.customer-chart-dialog { max-width: 32rem; }
.customer-chart-page__grid :deep(.chart-bucket-actions__action) { min-width: 0; }
.customer-chart-page__grid :deep(.chart-bucket-actions__value) { white-space: normal; overflow-wrap: anywhere; }
@media (max-width: 600px) { :deep(.customer-chart-page__donut-content) { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 900px) { .customer-chart-page__grid { grid-template-columns: 1fr; } }
</style>
