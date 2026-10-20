<script setup lang="ts">
import { computed, ref } from 'vue'
import { Donut, GroupedBar } from '@unovis/ts'
import { VisAxis, VisDonut, VisGroupedBar, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  componentToString,
  type ChartConfig,
} from '@/components/ui/chart'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type {
  ContractChartBucket,
  ContractChartBucketContracts,
  ContractChartCard,
  ContractChartResponse,
} from '@/api/contract'

const props = defineProps<{
  chart: ContractChartResponse | null
  loading: boolean
  error: string
  bucketContracts: ContractChartBucketContracts | null
  bucketLoading: boolean
  bucketError: string
}>()

const emit = defineEmits<{
  retry: []
  'retry-bucket': []
  'open-contract': [contractId: number]
  'view-bucket': [card: ContractChartCard, bucket: ContractChartBucket]
  'view-all': [card: ContractChartCard, bucket: ContractChartBucket]
  'close-bucket': []
}>()

interface PieDatum { key: string, label: string, amount: number, fill: string, [segment: string]: string | number }

const CHART_COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))']
const population = computed(() => props.chart?.population ?? 0)
const totalAmount = computed(() => props.chart?.total_amount ?? 0)
const donutCards = computed(() => (props.chart?.cards ?? []).filter((card) => card.key === 'license_type' || card.key === 'purchase_type'))
const amountCard = computed(() => props.chart?.cards.find((card) => card.key === 'amount_band') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'signing_month') ?? null)
const selectedCard = ref<ContractChartCard | null>(null)
const selectedBucket = ref<ContractChartBucket | null>(null)
const dialogOpen = computed({
  get: () => props.bucketContracts !== null || props.bucketLoading || props.bucketError !== '',
  set: (open: boolean) => {
    if (!open) {
      selectedCard.value = null
      selectedBucket.value = null
      emit('close-bucket')
    }
  },
})

function moneyText(value: number): string {
  if (!Number.isFinite(value)) return '¥ 0'
  if (Math.abs(value) >= 10000) {
    return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(value / 10000)} 万`
  }
  return `¥ ${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)}`
}

function countText(bucket: ContractChartBucket): string {
  return `${bucket.count} 份 · ${moneyText(bucket.amount)}`
}

function muted(bucket: ContractChartBucket): boolean {
  return bucket.key === 'blank' || bucket.key === 'earlier' || bucket.key === 'unsigned' || bucket.key === 'future'
}

function sliceColor(index: number, bucket: ContractChartBucket): string {
  if (muted(bucket)) return 'hsl(var(--muted-foreground))'
  return CHART_COLORS[index % CHART_COLORS.length] ?? 'hsl(var(--chart-1))'
}

function hoverText(bucket: ContractChartBucket): string {
  return countText(bucket)
}

function chartTriggers(selector: string, config: ChartConfig): Record<string, (datum: unknown, x: number | Date) => string> {
  const render = componentToString(config, ChartTooltipContent, { hideLabel: true })
  return render === undefined ? {} : { [selector]: render }
}


function pieData(card: ContractChartCard): PieDatum[] {
  return card.buckets
    .filter((bucket) => bucket.count > 0)
    .map((bucket) => ({
      key: bucket.key,
      label: bucket.label,
      amount: bucket.amount,
      fill: `var(--color-${bucket.key})`,
      [bucket.key]: hoverText(bucket),
    }))
}

function pieConfig(card: ContractChartCard): ChartConfig {
  return Object.fromEntries(card.buckets.map((bucket, index) => [
    bucket.key,
    { label: bucket.label, color: sliceColor(index, bucket) },
  ]))
}

function maxCount(card: ContractChartCard): number {
  return Math.max(...card.buckets.map((bucket) => bucket.count), 1)
}

function barWidth(card: ContractChartCard, bucket: ContractChartBucket): string {
  return `${Math.round((bucket.count / maxCount(card)) * 100)}%`
}

interface MonthDatum {
  index: number
  label: string
  count: number
  amount: number
  key: string
  [segment: string]: string | number
}

function monthData(card: ContractChartCard): MonthDatum[] {
  return card.buckets.map((bucket, index) => ({
    index,
    key: bucket.key,
    label: bucket.label,
    count: bucket.count,
    amount: bucket.amount,
    [bucket.key]: hoverText(bucket),
  }))
}

const MONTH_COLOR = 'hsl(var(--chart-1))'

function monthConfig(card: ContractChartCard): ChartConfig {
  return Object.fromEntries(card.buckets.map((bucket) => [
    bucket.key,
    {
      label: bucket.label,
      color: bucket.key === 'earlier' || bucket.key === 'unsigned' || bucket.key === 'future'
        ? 'hsl(var(--muted-foreground))'
        : MONTH_COLOR,
    },
  ]))
}

function openBucket(card: ContractChartCard, bucket: ContractChartBucket): void {
  if (bucket.count === 0) return
  selectedCard.value = card
  selectedBucket.value = bucket
  emit('view-bucket', card, bucket)
}

function openMonth(card: ContractChartCard, datum: MonthDatum): void {
  const bucket = card.buckets.find((item) => item.key === datum.key)
  if (bucket) openBucket(card, bucket)
}
</script>

<template>
  <section class="contract-chart-page" aria-label="合同图表">
    <div v-if="loading && !chart" class="contract-chart-page__state">正在整理合同图表…</div>
    <div v-else-if="error && !chart" class="contract-chart-page__state" role="alert">
      <span>{{ error }}</span>
      <Button type="button" variant="outline" size="sm" @click="emit('retry')">重试</Button>
    </div>
    <template v-else-if="chart">
      <header class="contract-chart-page__heading">
        <h2>{{ population }} 份 · {{ moneyText(totalAmount) }}</h2>
        <p>当前筛选范围内的合同。状态仍在看板看。金额是合同金额。</p>
      </header>
      <p v-if="error" class="contract-chart-page__refresh-error" role="alert">{{ error }}</p>
      <div class="contract-chart-page__grid">
        <Card v-for="card in donutCards" :key="card.key">
          <CardHeader class="items-start pb-0">
            <CardTitle>{{ card.title }}</CardTitle>
            <CardDescription>{{ card.description }}</CardDescription>
          </CardHeader>
          <CardContent class="grid grid-cols-[220px_minmax(0,1fr)] items-center gap-6 pb-6">
            <ChartContainer :config="pieConfig(card)" class="mx-auto aspect-square h-[220px] w-[220px]">
              <VisSingleContainer :data="pieData(card)" :margin="{ top: 8, bottom: 8 }">
                <VisDonut
                  :value="(datum: PieDatum) => datum.amount"
                  :color="(datum: PieDatum) => datum.fill"
                  :arc-width="30"
                  :central-label="String(population)"
                  central-sub-label="份"
                  :events="{
                    [Donut.selectors.segment]: {
                      click: (datum: PieDatum) => {
                        const bucket = card.buckets.find((item) => item.key === datum.key)
                        if (bucket) openBucket(card, bucket)
                      },
                    },
                  }"
                />
                <ChartTooltip
                  :triggers="{
                    ...chartTriggers(Donut.selectors.segment, pieConfig(card)),
                  }"
                />
              </VisSingleContainer>
            </ChartContainer>
            <div class="grid gap-2 text-sm">
              <button
                v-for="(bucket, index) in card.buckets"
                :key="bucket.key"
                type="button"
                class="grid grid-cols-[8px_max-content_auto] items-center gap-2 text-left text-sm whitespace-nowrap disabled:cursor-default"
                :disabled="bucket.count === 0"
                @click="openBucket(card, bucket)"
              >
                <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: sliceColor(index, bucket) }" />
                <span>{{ bucket.label }}</span>
                <span class="text-muted-foreground tabular-nums">{{ countText(bucket) }}</span>
              </button>
            </div>
          </CardContent>
        </Card>

        <Card v-if="amountCard" class="contract-chart-page__amount">
          <CardHeader>
            <CardTitle>{{ amountCard.title }}</CardTitle>
            <CardDescription>{{ amountCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="grid gap-2">
              <button
                v-for="bucket in amountCard.buckets"
                :key="bucket.key"
                type="button"
                class="grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm disabled:cursor-default"
                :disabled="bucket.count === 0"
                @click="openBucket(amountCard, bucket)"
              >
                <span class="truncate">{{ bucket.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-muted">
                  <span class="block h-full rounded-full bg-primary" :style="{ width: barWidth(amountCard, bucket) }" />
                </span>
                <span class="whitespace-nowrap text-muted-foreground tabular-nums">{{ countText(bucket) }}</span>
              </button>
            </div>
          </CardContent>
        </Card>

        <Card v-if="monthCard" class="contract-chart-page__wide">
          <CardHeader>
            <CardTitle>{{ monthCard.title }}</CardTitle>
            <CardDescription>{{ monthCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer :config="monthConfig(monthCard)" class="aspect-auto h-[240px] w-full">
              <VisXYContainer :data="monthData(monthCard)" :height="220">
                <VisGroupedBar
                  :x="(datum: MonthDatum) => datum.index"
                  :y="(datum: MonthDatum) => datum.count"
                  :color="(datum: MonthDatum) => datum.key === 'earlier' || datum.key === 'unsigned' || datum.key === 'future' ? 'hsl(var(--muted-foreground))' : MONTH_COLOR"
                  :rounded-corners="4"
                  :bar-padding="0.35"
                  :events="{ [GroupedBar.selectors.bar]: { click: (datum: MonthDatum) => { if (monthCard) openMonth(monthCard, datum) } } }"
                />
                <VisAxis
                  type="x"
                  :tick-line="false"
                  :domain-line="false"
                  :grid-line="false"
                  :tick-values="monthData(monthCard).map((datum) => datum.index)"
                  :tick-format="() => ''"
                />
                <VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" />
                <ChartTooltip :triggers="chartTriggers(GroupedBar.selectors.bar, monthConfig(monthCard))" />
              </VisXYContainer>
            </ChartContainer>
            <div class="mt-3 grid gap-2" :style="{ gridTemplateColumns: `repeat(${monthCard.buckets.length}, minmax(0, 1fr))` }">
              <button
                v-for="bucket in monthCard.buckets"
                :key="bucket.key"
                type="button"
                class="text-center text-sm disabled:cursor-default"
                :disabled="bucket.count === 0"
                @click="openBucket(monthCard, bucket)"
              >
                <span class="block text-xs">{{ bucket.label }}</span>
                <span class="block text-xs text-muted-foreground">{{ bucket.count }} 份</span>
              </button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Dialog :open="dialogOpen" @update:open="dialogOpen = $event">
        <DialogContent class="w-[calc(100%-2rem)] max-w-lg">
          <DialogHeader>
            <DialogTitle>{{ bucketContracts ? `${bucketContracts.total} 份` : '合同' }}</DialogTitle>
            <DialogDescription>
              {{ bucketLoading ? '正在读取这一段合同…' : bucketError || '这一段里的合同。' }}
            </DialogDescription>
          </DialogHeader>
          <div v-if="bucketError" class="contract-chart-page__state">
            <Button type="button" variant="outline" size="sm" @click="emit('retry-bucket')">重试</Button>
          </div>
          <div v-else-if="bucketContracts" class="contract-chart-dialog-list">
            <button
              v-for="contract in bucketContracts.contracts"
              :key="contract.id"
              type="button"
              @click="emit('open-contract', contract.id)"
            >
              <span>{{ contract.name }}</span>
              <small>{{ contract.customer_name || '无客户' }} · {{ moneyText(contract.amount) }}</small>
            </button>
          </div>
          <DialogFooter v-if="selectedCard && selectedBucket && bucketContracts && bucketContracts.total > bucketContracts.contracts.length">
            <Button type="button" variant="outline" @click="emit('view-all', selectedCard, selectedBucket)">查看详情</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </template>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.contract-chart-page {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  padding: $wolf-space-md-v2;
}

.contract-chart-page__state,
.contract-chart-page__refresh-error {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-secondary-v2;
}

.contract-chart-page__heading h2 {
  margin: 0;
  font-size: $wolf-font-size-title-v2;
  line-height: 1.25;
}

.contract-chart-page__heading p,
.contract-chart-page__refresh-error {
  margin: $wolf-space-xs-v2 0 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-body-v2;
}

.contract-chart-page__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.contract-chart-page__amount,
.contract-chart-page__wide {
  grid-column: 1 / -1;
}

.contract-chart-dialog-list {
  display: flex;
  max-height: 24rem;
  flex-direction: column;
  overflow: auto;
}

.contract-chart-dialog-list button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  border: 0;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: transparent;
  padding: $wolf-space-sm-v2 0;
  text-align: left;
}

.contract-chart-dialog-list small {
  color: $wolf-text-tertiary-v2;
}

@media (max-width: 720px) {
  .contract-chart-page__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
