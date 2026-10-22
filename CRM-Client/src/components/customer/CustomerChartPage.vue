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
  CustomerChartBucket,
  CustomerChartBucketCustomers,
  CustomerChartCard,
  CustomerChartResponse,
} from '@/schemas/customer'
const CHART_COLOR = 'hsl(var(--chart-1))'
const CHART_COLORS = ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(var(--chart-3))', 'hsl(var(--chart-4))', 'hsl(var(--chart-5))']


const props = defineProps<{
  chart: CustomerChartResponse | null
  loading: boolean
  error: string
  bucketCustomers: CustomerChartBucketCustomers | null
  bucketLoading: boolean
  bucketError: string
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

const population = computed(() => props.chart?.population ?? 0)
const pieCards = computed(() => (props.chart?.cards ?? []).filter((card) => card.key === 'status' || card.key === 'license' || card.key === 'scale'))
const industryCard = computed(() => props.chart?.cards.find((card) => card.key === 'industry') ?? null)
const cityCard = computed(() => props.chart?.cards.find((card) => card.key === 'city') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'created_month') ?? null)
const selectedCard = ref<CustomerChartCard | null>(null)
const selectedBucket = ref<CustomerChartBucket | null>(null)
const dialogOpen = computed({
  get: () => selectedBucket.value !== null,
  set: (open: boolean) => {
    if (!open) {
      selectedCard.value = null
      selectedBucket.value = null
      emit('close-bucket')
    }
  },
})
const cardTitle = computed(() => props.chart?.cards.find((card) => card.key === selectedCard.value?.key)?.title ?? '')
const subtitle = computed(() => {
  const total = props.bucketCustomers?.total ?? selectedBucket.value?.count ?? 0
  return `${cardTitle.value} · 共 ${total} 家`
})

function rememberBucket(card: CustomerChartCard, bucket: CustomerChartBucket): void {
  selectedCard.value = card
  selectedBucket.value = bucket
}

function countText(bucket: CustomerChartBucket): string {
  return `${bucket.count} 家 · ${bucket.ratio}%`
}

function sliceColor(index: number, key: string): string {
  if (key === 'blank' || key === 'other') return 'hsl(var(--muted-foreground))'
  return CHART_COLORS[index % CHART_COLORS.length] ?? CHART_COLOR
}

function pieData(card: CustomerChartCard): PieDatum[] {
  return card.buckets
    .filter((bucket) => bucket.count > 0)
    .map((bucket) => ({
      key: bucket.key,
      label: bucket.label,
      count: bucket.count,
      ratio: bucket.ratio,
      fill: `var(--color-${bucket.key})`,
      [bucket.key]: bucket.count,
    }))
}

function pieConfig(card: CustomerChartCard): ChartConfig {
  return Object.fromEntries(card.buckets.map((bucket, index) => [
    bucket.key,
    { label: bucket.label, color: sliceColor(index, bucket.key) },
  ]))
}



function namedBuckets(card: CustomerChartCard): CustomerChartBucket[] {
  return card.buckets.filter((bucket) => bucket.key !== 'other' && bucket.key !== 'blank')
}

function chartRows(card: CustomerChartCard): CustomerChartBucket[] {
  return card.key === 'created_month' ? card.buckets : namedBuckets(card)
}

function rankData(card: CustomerChartCard): RankDatum[] {
  return chartRows(card).map((bucket, index) => ({
    index,
    label: bucket.label,
    count: bucket.count,
    ratio: bucket.ratio,
  }))
}




const monthConfig = {
  count: { label: '客户', color: CHART_COLOR },
} satisfies ChartConfig

function openRank(card: CustomerChartCard | null, datum: RankDatum): void {
  const bucket = card?.buckets[datum.index]
  if (!bucket || bucket.count === 0 || card === null) return
  rememberBucket(card, bucket)
  emit('view-bucket', card, bucket)
}

function openNamed(card: CustomerChartCard, bucket: CustomerChartBucket): void {
  if (bucket.count === 0) return
  rememberBucket(card, bucket)
  emit('view-bucket', card, bucket)
}
</script>

<template>
  <section class="customer-chart-page" aria-label="客户图表">
    <div v-if="loading && !chart" class="customer-chart-page__state">正在整理客户图表…</div>
    <div v-else-if="error && !chart" class="customer-chart-page__state" role="alert">
      <span>{{ error }}</span>
      <Button type="button" variant="outline" size="sm" @click="emit('retry')">重试</Button>
    </div>
    <template v-else-if="chart">
      <header class="customer-chart-page__heading">
        <h2>{{ population }} 家</h2>
        <p>当前筛选范围内的客户。一页同时看，没有负责人。行业、城市只留数量最多的 8 个，其余并进其他。</p>
      </header>
      <p v-if="error" class="customer-chart-page__refresh-error" role="alert">{{ error }}</p>
      <div class="customer-chart-page__grid">
        <Card v-for="card in pieCards" :key="card.key" class="flex flex-col">
          <CardHeader class="items-start pb-0">
            <CardTitle>{{ card.title }}</CardTitle>
            <CardDescription>{{ card.description }}</CardDescription>
          </CardHeader>
          <CardContent class="grid grid-cols-[220px_minmax(0,1fr)] items-center gap-6 pb-6">
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
                  :events="{
                    [Donut.selectors.segment]: {
                      click: (datum: PieDatum) => {
                        const bucket = card.buckets.find((item) => item.key === datum.key)
                        if (bucket) openNamed(card, bucket)
                      },
                    },
                  }"
                />
                <ChartTooltip
                  :triggers="{
                    [Donut.selectors.segment]: componentToString(pieConfig(card), ChartTooltipContent, { hideLabel: true })!,
                  }"
                />
              </VisSingleContainer>
            </ChartContainer>
            <div class="grid gap-2 text-sm">
              <div v-for="bucket in card.buckets" :key="bucket.key" class="grid grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-2">
                <span class="h-2 w-2 rounded-full" :style="{ backgroundColor: sliceColor(card.buckets.indexOf(bucket), bucket.key) }" />
                <span>{{ bucket.label }}</span>
                <span class="text-muted-foreground tabular-nums">{{ countText(bucket) }}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card v-if="industryCard">
          <CardHeader>
            <CardTitle>{{ industryCard.title }}</CardTitle>
            <CardDescription>{{ industryCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="grid gap-2">
              <button
                v-for="bucket in namedBuckets(industryCard)"
                :key="bucket.key"
                type="button"
                class="grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm disabled:cursor-default"
                :disabled="bucket.count === 0"
                @click="industryCard && openNamed(industryCard, bucket)"
              >
                <span class="truncate">{{ bucket.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-muted">
                  <span class="block h-full rounded-full bg-primary" :style="{ width: `${Math.round((bucket.count / Math.max(...namedBuckets(industryCard).map((item) => item.count), 1)) * 100)}%` }" />
                </span>
                <span class="text-muted-foreground tabular-nums">{{ countText(bucket) }}</span>
              </button>
            </div>
          </CardContent>
        </Card>

        <Card v-if="cityCard" class="customer-chart-page__wide">
          <CardHeader>
            <CardTitle>{{ cityCard.title }}</CardTitle>
            <CardDescription>{{ cityCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="grid gap-2">
              <button
                v-for="bucket in namedBuckets(cityCard)"
                :key="bucket.key"
                type="button"
                class="grid grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-3 text-left text-sm disabled:cursor-default"
                :disabled="bucket.count === 0"
                @click="cityCard && openNamed(cityCard, bucket)"
              >
                <span class="truncate">{{ bucket.label }}</span>
                <span class="h-2 overflow-hidden rounded-full bg-muted">
                  <span class="block h-full rounded-full bg-primary" :style="{ width: `${Math.round((bucket.count / Math.max(...namedBuckets(cityCard).map((item) => item.count), 1)) * 100)}%` }" />
                </span>
                <span class="text-muted-foreground tabular-nums">{{ countText(bucket) }}</span>
              </button>
            </div>
          </CardContent>
        </Card>



        <Card v-if="monthCard" class="customer-chart-page__wide">
          <CardHeader>
            <CardTitle>{{ monthCard.title }}</CardTitle>
            <CardDescription>{{ monthCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer :config="monthConfig" class="aspect-auto h-[240px]">
              <VisXYContainer :data="rankData(monthCard)" :height="220">
                <VisArea
                  :x="(datum: RankDatum) => datum.index"
                  :y="(datum: RankDatum) => datum.count"
                  :color="monthConfig.count.color"
                  :opacity="0.4"
                  :events="{
                    [Area.selectors.area]: {
                      click: (datum: RankDatum) => openRank(monthCard, datum),
                    },
                  }"
                />
                <VisLine
                  :x="(datum: RankDatum) => datum.index"
                  :y="(datum: RankDatum) => datum.count"
                  :color="monthConfig.count.color"
                  :line-width="1"
                />
                <VisAxis
                  type="x"
                  :tick-line="false"
                  :domain-line="false"
                  :grid-line="false"
                  :num-ticks="monthCard.buckets.length"
                  :tick-values="rankData(monthCard).map((datum) => datum.index)"
                  :tick-format="(value: number) => monthCard?.buckets[Math.round(value)]?.label ?? ''"
                />
                <VisAxis type="y" :num-ticks="3" :tick-line="false" :domain-line="false" />
                <ChartTooltip />
                <ChartCrosshair
                  :template="componentToString(monthConfig, ChartTooltipContent, { labelKey: 'label' })"
                  :color="monthConfig.count.color"
                />
              </VisXYContainer>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <Dialog :open="dialogOpen" @update:open="dialogOpen = $event">
        <DialogContent class="w-[calc(100%-2rem)] max-w-lg">
          <DialogHeader>
            <DialogTitle>{{ selectedBucket?.label ?? '客户' }}</DialogTitle>
            <DialogDescription>
              {{ bucketLoading && !bucketCustomers ? '正在读取这一组客户…' : bucketError && !bucketCustomers ? bucketError : subtitle }}
            </DialogDescription>
          </DialogHeader>
          <div v-if="bucketError && !bucketCustomers" class="customer-chart-dialog-state">
            <Button v-if="selectedCard && selectedBucket" type="button" variant="outline" size="sm" @click="emit('view-bucket', selectedCard, selectedBucket)">重试</Button>
          </div>
          <div v-else-if="bucketCustomers" class="customer-chart-dialog-list">
            <button
              v-for="customer in bucketCustomers.customers"
              :key="customer.id"
              type="button"
              @click="emit('open-customer', customer.id)"
            >
              <span>{{ customer.name }}</span>
              <small>{{ customer.owner_name || '无负责人' }}</small>
            </button>
            <button
              v-if="bucketCustomers.customers.length < bucketCustomers.total"
              type="button"
              class="customer-chart-dialog-more"
              :disabled="bucketLoading"
              @click="emit('load-more')"
            >
              {{ bucketLoading ? '正在读取…' : bucketError || '查看更多' }}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </template>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.customer-chart-page {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  min-width: 0;
  padding: $wolf-space-md-v2;
}

.customer-chart-page__state,
.customer-chart-page__refresh-error {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-secondary-v2;
}

.customer-chart-page__heading h2 {
  margin: 0;
  font-size: $wolf-font-size-title-v2;
  line-height: 1.25;
}

.customer-chart-page__heading p,
.customer-chart-page__refresh-error {
  margin: $wolf-space-xs-v2 0 0;
  color: $wolf-text-tertiary-v2;
}

.customer-chart-page__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-space-md-v2;
}

.customer-chart-page__wide {
  grid-column: 1 / -1;
}

.customer-chart-dialog-list {
  display: flex;
  flex-direction: column;
  max-height: 24rem;
  overflow: auto;
}

.customer-chart-dialog-list button {
  display: flex;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
  border: 0;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: transparent;
  padding: $wolf-space-sm-v2 0;
  text-align: left;
}

@media (max-width: 900px) {
  .customer-chart-page__grid {
    grid-template-columns: 1fr;
  }
}
</style>
