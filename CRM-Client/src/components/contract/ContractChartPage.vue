<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Donut, GroupedBar } from '@unovis/ts'
import { VisAxis, VisDonut, VisGroupedBar, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { Button } from '@/components/ui/button'
import { ChartContainer, ChartTooltip, ChartTooltipContent, componentToString, type ChartConfig } from '@/components/ui/chart'
import ChartBucketActionList, { type ChartBucketAction } from '@/components/crmwolf/chart/ChartBucketActionList.vue'
import ChartBucketDialog from '@/components/crmwolf/chart/ChartBucketDialog.vue'
import ChartCardFrame from '@/components/crmwolf/chart/ChartCardFrame.vue'
import ChartPageShell from '@/components/crmwolf/chart/ChartPageShell.vue'
import type { ContractChartBucket, ContractChartBucketContracts, ContractChartCard, ContractChartResponse } from '@/api/contract'

const props = defineProps<{
  chart: ContractChartResponse | null
  loading: boolean
  error: string
  bucketContracts: ContractChartBucketContracts | null
  bucketLoading: boolean
  bucketError: string
  bucketResetToken?: number
}>()
const emit = defineEmits<{
  retry: []
  'retry-bucket': []
  'open-contract': [contractId: number]
  'view-bucket': [card: ContractChartCard, bucket: ContractChartBucket]
  'load-more': []
  'close-bucket': []
}>()
interface PieDatum { key: string, label: string, amount: number, fill: string }
interface MonthDatum { index: number, label: string, count: number, amount: number, key: string }
interface ContractBucketAction extends ChartBucketAction { card: ContractChartCard, bucket: ContractChartBucket }
const CHART_COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))']
const MONTH_COLOR = 'hsl(var(--chart-1))'
const population = computed(() => props.chart?.population ?? 0)
const totalAmount = computed(() => props.chart?.total_amount ?? 0)
const donutCards = computed(() => (props.chart?.cards ?? []).filter((card) => card.key === 'license_type' || card.key === 'purchase_type'))
const amountCard = computed(() => props.chart?.cards.find((card) => card.key === 'amount_band') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'signing_month') ?? null)
const selectedCard = ref<ContractChartCard | null>(null)
const selectedBucket = ref<ContractChartBucket | null>(null)
const dialogOpen = ref(false)
watch(() => props.bucketResetToken, () => { selectedCard.value = null; selectedBucket.value = null; dialogOpen.value = false })
function moneyText(value: number): string {
  if (!Number.isFinite(value)) return '¥ 0'
  if (Math.abs(value) >= 10000) return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(value / 10000)} 万`
  return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)}`
}
function countText(bucket: ContractChartBucket): string { return `${bucket.count} 份 · ${moneyText(bucket.amount)}` }
function muted(bucket: ContractChartBucket): boolean { return bucket.key === 'blank' || bucket.key === 'earlier' || bucket.key === 'unsigned' || bucket.key === 'future' }
function sliceColor(index: number, bucket: ContractChartBucket): string { return muted(bucket) ? 'hsl(var(--muted-foreground))' : CHART_COLORS[index % CHART_COLORS.length] ?? 'hsl(var(--chart-1))' }
function chartTriggers(selector: string, config: ChartConfig): Record<string, (datum: unknown, x: number | Date) => string> { const rendered = componentToString(config, ChartTooltipContent, { hideLabel: true }); return rendered ? { [selector]: rendered } : {} }
function pieData(card: ContractChartCard): PieDatum[] { return card.buckets.filter((bucket) => bucket.count > 0).map((bucket) => ({ key: bucket.key, label: bucket.label, amount: bucket.amount, [bucket.key]: countText(bucket), fill: `var(--color-${bucket.key})` })) }
function pieConfig(card: ContractChartCard): ChartConfig { return Object.fromEntries(card.buckets.map((bucket, index) => [bucket.key, { label: bucket.label, color: sliceColor(index, bucket) }])) }
function maxCount(card: ContractChartCard): number { return Math.max(...card.buckets.map((bucket) => bucket.count), 1) }
function barWidth(card: ContractChartCard, bucket: ContractChartBucket): string { return `${Math.round((bucket.count / maxCount(card)) * 100)}%` }
function monthData(card: ContractChartCard): MonthDatum[] { return card.buckets.map((bucket, index) => ({ index, key: bucket.key, label: bucket.label, count: bucket.count, amount: bucket.amount, [bucket.key]: countText(bucket) })) }
function monthConfig(card: ContractChartCard): ChartConfig { return Object.fromEntries(card.buckets.map((bucket) => [bucket.key, { label: bucket.label, color: bucket.key === 'earlier' || bucket.key === 'unsigned' || bucket.key === 'future' ? 'hsl(var(--muted-foreground))' : MONTH_COLOR }])) }
function bucketActions(card: ContractChartCard): ContractBucketAction[] { return card.buckets.map((bucket) => ({ key: bucket.key, label: bucket.label, ariaLabel: `${bucket.label}，${countText(bucket)}`, value: countText(bucket), disabled: bucket.count === 0, card, bucket })) }
function openBucket(card: ContractChartCard, bucket: ContractChartBucket): void {
  if (bucket.count === 0) return
  selectedCard.value = card
  selectedBucket.value = bucket
  dialogOpen.value = true
  emit('view-bucket', card, bucket)
}
function activate(action: ContractBucketAction): void { openBucket(action.card, action.bucket) }
function openMonth(card: ContractChartCard, datum: MonthDatum): void { const bucket = card.buckets.find((item) => item.key === datum.key); if (bucket) openBucket(card, bucket) }
function openMonthFromDatum(datum: MonthDatum): void {
  const card = monthCard.value
  if (card) openMonth(card, datum)
}
</script>

<template>
  <ChartPageShell :state="loading && !chart ? 'loading' : error && !chart ? 'error' : chart ? 'ready' : 'empty'" aria-label="合同图表">
    <template #loading>正在整理合同图表…</template>
    <template #error><div class="contract-chart-page__state" role="alert"><span>{{ error }}</span><Button type="button" variant="outline" size="sm" @click="emit('retry')">重试</Button></div></template>
    <template #empty><div class="contract-chart-page__state">暂无合同图表</div></template>
    <template #summary><header class="contract-chart-page__heading"><h2>{{ population }} 份 · {{ moneyText(totalAmount) }}</h2><p>当前筛选范围内的合同。状态仍在看板看。金额是合同金额。</p></header></template>
    <template #inline-error><p v-if="error" class="contract-chart-page__refresh-error" role="alert">{{ error }}</p></template>
    <div v-if="chart" class="contract-chart-page__grid">
      <ChartCardFrame v-for="card in donutCards" :key="card.key" :card-key="card.key" :title="card.title" :description="card.description" content-class="contract-chart-page__donut-content">
        <template #content><ChartContainer :config="pieConfig(card)" class="mx-auto aspect-square h-[220px] w-[220px]"><VisSingleContainer :data="pieData(card)" :margin="{ top: 8, bottom: 8 }"><VisDonut :value="(datum: PieDatum) => datum.amount" :color="(datum: PieDatum) => datum.fill" :arc-width="30" :central-label="String(population)" central-sub-label="份" :events="{ [Donut.selectors.segment]: { click: (datum: PieDatum) => { const bucket = card.buckets.find((item) => item.key === datum.key); if (bucket) openBucket(card, bucket) } } }" /><ChartTooltip :triggers="chartTriggers(Donut.selectors.segment, pieConfig(card))" /></VisSingleContainer></ChartContainer><ChartBucketActionList :actions="bucketActions(card).map((action, index) => ({ ...action, color: sliceColor(index, action.bucket) }))" :aria-label="card.title" :test-id-prefix="`contract-${card.key}-bucket`" @activate="activate" /></template>
      </ChartCardFrame>
      <ChartCardFrame v-if="amountCard" :card-key="amountCard.key" :title="amountCard.title" :description="amountCard.description" wide>
        <template #content><ChartBucketActionList :actions="bucketActions(amountCard)" :aria-label="amountCard.title" test-id-prefix="contract-amount-bucket" @activate="activate"><template #default="{ action }"><span class="grid w-full grid-cols-[minmax(0,88px)_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm"><span class="truncate">{{ action.label }}</span><span class="h-2 overflow-hidden rounded-full bg-muted"><span class="block h-full rounded-full bg-primary" :style="{ width: barWidth(amountCard, action.bucket) }" /></span><span class="whitespace-nowrap text-muted-foreground tabular-nums">{{ countText(action.bucket) }}</span></span></template></ChartBucketActionList></template>
      </ChartCardFrame>
      <ChartCardFrame v-if="monthCard" :card-key="monthCard.key" :title="monthCard.title" :description="monthCard.description" wide>
        <template #content><ChartContainer :config="monthConfig(monthCard)" class="aspect-auto h-[240px] w-full"><VisXYContainer :data="monthData(monthCard)" :height="220"><VisGroupedBar :x="(datum: MonthDatum) => datum.index" :y="(datum: MonthDatum) => datum.count" :color="(datum: MonthDatum) => datum.key === 'earlier' || datum.key === 'unsigned' || datum.key === 'future' ? 'hsl(var(--muted-foreground))' : MONTH_COLOR" :rounded-corners="4" :bar-padding="0.35" :events="{ [GroupedBar.selectors.bar]: { click: (datum: MonthDatum) => openMonthFromDatum(datum) } }" /><VisAxis type="x" :tick-line="false" :domain-line="false" :grid-line="false" :tick-values="monthData(monthCard).map((datum) => datum.index)" :tick-format="() => ''" /><VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" /><ChartTooltip :triggers="chartTriggers(GroupedBar.selectors.bar, monthConfig(monthCard))" /></VisXYContainer></ChartContainer><ChartBucketActionList :actions="bucketActions(monthCard)" :aria-label="monthCard.title" test-id-prefix="contract-month-bucket" @activate="activate" /></template>
      </ChartCardFrame>
    </div>
    <template #overlays><ChartBucketDialog class="contract-chart-dialog" :open="dialogOpen" :title="selectedBucket?.label ?? '合同'" :description="bucketLoading && !bucketContracts ? '正在读取这一段合同…' : bucketError && !bucketContracts ? bucketError : `${selectedCard?.title ?? ''} · 共 ${bucketContracts?.total ?? selectedBucket?.count ?? 0} 份`" :loading="bucketLoading" :error="bucketError || null" :has-items="Boolean(bucketContracts)" :has-more="Boolean(bucketContracts && bucketContracts.contracts.length < bucketContracts.total)" :reset-key="bucketResetToken" test-id-prefix="contract-chart" @update:open="(open) => { if (!open) { dialogOpen = false; selectedCard = null; selectedBucket = null; emit('close-bucket') } }" @retry="emit('retry-bucket')" @load-more="emit('load-more')"><template #load-more-label>{{ bucketLoading ? '正在读取…' : bucketError || '查看更多' }}</template><template #items><div class="contract-chart-dialog-list"><button v-for="contract in bucketContracts?.contracts ?? []" :key="contract.id" type="button" @click="emit('open-contract', contract.id)"><span>{{ contract.name }}</span><small>{{ contract.customer_name || '无客户' }} · {{ moneyText(contract.amount) }}</small></button></div></template></ChartBucketDialog></template>
  </ChartPageShell>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
.contract-chart-page__state,.contract-chart-page__refresh-error { display: flex; align-items: center; gap: $wolf-space-sm-v2; color: $wolf-text-secondary-v2; }
.contract-chart-page__heading h2 { margin: 0; font-size: $wolf-font-size-title-v2; line-height: 1.25; }
.contract-chart-page__heading p,.contract-chart-page__refresh-error { margin: $wolf-space-xs-v2 0 0; color: $wolf-text-tertiary-v2; font-size: $wolf-font-size-body-v2; }
.contract-chart-page__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: $wolf-space-md-v2; }
.contract-chart-dialog-list { display: flex; max-height: 24rem; flex-direction: column; overflow: auto; }
.contract-chart-dialog-list button { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; border: 0; border-bottom: 1px solid $wolf-border-default-v2; background: transparent; padding: $wolf-space-sm-v2 0; text-align: left; }
.contract-chart-dialog-list small { color: $wolf-text-tertiary-v2; }
.contract-chart-page__grid :deep(.chart-bucket-actions__action) { min-width: 0; }
.contract-chart-page__grid :deep(.chart-bucket-actions__value) { white-space: normal; overflow-wrap: anywhere; }
:deep(.contract-chart-page__donut-content) { display: grid; grid-template-columns: 220px minmax(0, 1fr); align-items: center; gap: 1.5rem; padding-bottom: 1.5rem; }
.contract-chart-dialog { max-width: 32rem; }
@media (max-width: 720px) { .contract-chart-page__grid { grid-template-columns: minmax(0, 1fr); } :deep(.contract-chart-page__donut-content) { grid-template-columns: minmax(0, 1fr); } }
</style>
