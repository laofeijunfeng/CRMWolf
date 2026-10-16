<script setup lang="ts">
import { computed, ref } from 'vue'
import { VisArea, VisAxis, VisDonut, VisSingleContainer, VisXYContainer } from '@unovis/vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  'close-bucket': []
}>()

const selected = ref<{ cardKey: string; bucketKey: string } | null>(null)
const population = computed(() => props.chart?.population ?? 0)
const selectedCard = computed(() => props.chart?.cards.find((card) => card.key === selected.value?.cardKey) ?? null)
const selectedBucket = computed(() => selectedCard.value?.buckets.find((bucket) => bucket.key === selected.value?.bucketKey) ?? null)
const pieCards = computed(() => (props.chart?.cards ?? []).filter((card) => card.key === 'status' || card.key === 'license' || card.key === 'scale'))
const industryCard = computed(() => props.chart?.cards.find((card) => card.key === 'industry') ?? null)
const cityCard = computed(() => props.chart?.cards.find((card) => card.key === 'city') ?? null)
const monthCard = computed(() => props.chart?.cards.find((card) => card.key === 'created_month') ?? null)
const monthData = computed(() => (monthCard.value?.buckets ?? []).map((bucket) => ({ label: bucket.label, count: bucket.count })))
const dialogOpen = computed({
  get: () => props.bucketCustomers !== null || props.bucketLoading || props.bucketError !== '',
  set: (open: boolean) => {
    if (!open) emit('close-bucket')
  },
})



function themeColor(alpha: number, muted = false): string {
  if (typeof document === 'undefined') return muted ? 'hsl(215 16% 47% / 0.45)' : `hsl(221 83% 53% / ${alpha})`
  const root = getComputedStyle(document.documentElement)
  const primary = root.getPropertyValue('--primary').trim() || '221 83% 53%'
  const quiet = root.getPropertyValue('--muted-foreground').trim() || '215 16% 47%'
  return muted ? `hsl(${quiet} / 0.45)` : `hsl(${primary} / ${alpha})`
}

const SLICE_ALPHA = [1, 0.82, 0.66, 0.52, 0.4, 0.3, 0.22]

function bucketColor(card: CustomerChartCard, bucket: CustomerChartBucket): string {
  if (bucket.key === 'other' || bucket.key === 'blank') return themeColor(1, true)
  const index = Math.max(card.buckets.findIndex((item) => item.key === bucket.key), 0)
  return themeColor(SLICE_ALPHA[index % SLICE_ALPHA.length] ?? 1)
}

function selectBucket(card: CustomerChartCard, bucket: CustomerChartBucket): void {
  if (bucket.count === 0) return
  selected.value = { cardKey: card.key, bucketKey: bucket.key }
}

function visibleSlices(card: CustomerChartCard): CustomerChartBucket[] {
  return card.buckets.filter((bucket) => bucket.count > 0)
}

function pieValue(bucket: CustomerChartBucket): number {
  return bucket.count
}

function pieColor(card: CustomerChartCard): (bucket: CustomerChartBucket) => string {
  return (bucket) => bucketColor(card, bucket)
}

function barWidth(card: CustomerChartCard, bucket: CustomerChartBucket): string {
  const max = Math.max(...card.buckets.map((item) => item.count), 1)
  return `${Math.round((bucket.count / max) * 100)}%`
}

function countText(bucket: CustomerChartBucket): string {
  return `${bucket.count} 家 · ${bucket.ratio}%`
}

const monthX = (_datum: { label: string }, index: number): number => index
const monthY = (datum: { count: number }): number => datum.count
const monthTick = (value: number): string => monthData.value[Math.round(value)]?.label ?? ''
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
        <Card v-for="card in pieCards" :key="card.key">
          <CardHeader>
            <CardTitle>{{ card.title }}</CardTitle>
            <CardDescription>{{ card.description }}</CardDescription>
          </CardHeader>
          <CardContent class="customer-chart-pie">
            <VisSingleContainer :data="visibleSlices(card)" :height="180">
              <VisDonut :value="pieValue" :color="pieColor(card)" :arc-width="28" />
            </VisSingleContainer>
            <ul>
              <li v-for="bucket in card.buckets" :key="bucket.key">
                <button type="button" :disabled="bucket.count === 0" @click="selectBucket(card, bucket)">
                  <i :style="{ background: bucketColor(card, bucket) }" />
                  <span>{{ bucket.label }}</span>
                  <strong>{{ countText(bucket) }}</strong>
                </button>
              </li>
            </ul>
          </CardContent>
        </Card>
        <Card v-if="industryCard">
          <CardHeader>
            <CardTitle>{{ industryCard.title }}</CardTitle>
            <CardDescription>{{ industryCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul class="customer-chart-bars">
              <li v-for="bucket in industryCard.buckets" :key="bucket.key">
                <button type="button" :disabled="bucket.count === 0" @click="selectBucket(industryCard, bucket)">
                  <span>{{ bucket.label }}</span>
                  <b><i :style="{ width: barWidth(industryCard, bucket), background: bucketColor(industryCard, bucket) }" /></b>
                  <strong>{{ countText(bucket) }}</strong>
                </button>
              </li>
            </ul>
          </CardContent>
        </Card>
        <Card v-if="cityCard" class="customer-chart-page__wide">
          <CardHeader>
            <CardTitle>{{ cityCard.title }}</CardTitle>
            <CardDescription>{{ cityCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul class="customer-chart-bars">
              <li v-for="bucket in cityCard.buckets" :key="bucket.key">
                <button type="button" :disabled="bucket.count === 0" @click="selectBucket(cityCard, bucket)">
                  <span>{{ bucket.label }}</span>
                  <b><i :style="{ width: barWidth(cityCard, bucket), background: bucketColor(cityCard, bucket) }" /></b>
                  <strong>{{ countText(bucket) }}</strong>
                </button>
              </li>
            </ul>
          </CardContent>
        </Card>
        <Card v-if="monthCard" class="customer-chart-page__wide">
          <CardHeader>
            <CardTitle>{{ monthCard.title }}</CardTitle>
            <CardDescription>{{ monthCard.description }}</CardDescription>
          </CardHeader>
          <CardContent>
            <VisXYContainer :data="monthData" :height="220">
              <VisArea :x="monthX" :y="monthY" :color="themeColor(0.22)" :line-color="themeColor(1)" curve-type="monotoneX" :line="true" :opacity="1" />
              <VisAxis type="x" :tick-format="monthTick" :grid-line="false" />
              <VisAxis type="y" />
            </VisXYContainer>
            <ul class="customer-chart-months">
              <li v-for="bucket in monthCard.buckets" :key="bucket.key">
                <button type="button" :disabled="bucket.count === 0" @click="selectBucket(monthCard, bucket)">
                  {{ bucket.label }} {{ countText(bucket) }}
                </button>
              </li>
            </ul>
          </CardContent>
        </Card>
      </div>
      <aside v-if="selectedBucket && selectedCard" class="customer-chart-preview" aria-live="polite">
        <header>
          <strong>{{ selectedBucket.label }}</strong>
          <span>{{ countText(selectedBucket) }}</span>
          <Button type="button" variant="outline" size="sm" @click="emit('view-bucket', selectedCard, selectedBucket)">查看详情</Button>
        </header>
        <button
          v-for="customer in selectedBucket.preview"
          :key="customer.id"
          type="button"
          @click="emit('open-customer', customer.id)"
        >
          <span>{{ customer.name }}</span>
          <small>{{ customer.owner_name || '无负责人' }}</small>
        </button>
      </aside>
      <Dialog :open="dialogOpen" @update:open="dialogOpen = $event">
        <DialogContent class="w-[calc(100%-2rem)] max-w-lg">
          <DialogHeader>
            <DialogTitle>{{ selectedBucket?.label ?? '这一段' }}</DialogTitle>
            <DialogDescription>
              {{ bucketLoading ? '正在读取这一段客户' : bucketError || `共 ${bucketCustomers?.total ?? 0} 家` }}
            </DialogDescription>
          </DialogHeader>
          <div v-if="bucketCustomers" class="customer-chart-dialog-list">
            <button
              v-for="customer in bucketCustomers.customers"
              :key="customer.id"
              type="button"
              @click="emit('open-customer', customer.id)"
            >
              <span>{{ customer.name }}</span>
              <small>{{ customer.owner_name || '无负责人' }}</small>
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
  --customer-chart-1: hsl(var(--primary));
  --customer-chart-2: hsl(var(--primary) / 0.78);
  --customer-chart-3: hsl(var(--primary) / 0.62);
  --customer-chart-4: hsl(var(--primary) / 0.48);
  --customer-chart-5: hsl(var(--primary) / 0.36);
  --customer-chart-6: hsl(var(--primary) / 0.24);
  --customer-chart-7: hsl(var(--muted-foreground));
  --customer-chart-muted: hsl(var(--muted-foreground) / 0.45);
  min-height: 0;
  padding: $wolf-space-lg-v2;
  overflow: auto;
}

.customer-chart-page__heading h2 {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
}

.customer-chart-page__heading p,
.customer-chart-page__state,
.customer-chart-page__refresh-error {
  color: $wolf-text-tertiary-v2;
}

.customer-chart-pie button,
.customer-chart-bars button,
.customer-chart-months button,
.customer-chart-preview button,
.customer-chart-dialog-list button {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  color: $wolf-text-primary-v2;
}

.customer-chart-pie button span,
.customer-chart-bars button span {
  flex: 1;
  min-width: 0;
}

.customer-chart-pie button strong,
.customer-chart-bars button strong,
.customer-chart-preview header strong,
.customer-chart-preview header span {
  white-space: nowrap;
}
.customer-chart-bars,
.customer-chart-months,
.customer-chart-pie ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.customer-chart-bars button,
.customer-chart-pie button,
.customer-chart-months button,
.customer-chart-preview button,
.customer-chart-dialog-list button {
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  color: $wolf-text-primary-v2;
}

.customer-chart-bars b {
  flex: 1;
  height: 8px;
  border-radius: $wolf-radius-full-v2;
  background: $wolf-bg-muted-v2;
}

.customer-chart-bars i,
.customer-chart-pie i {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: inherit;
}

.customer-chart-bars i {
  width: auto;
  height: 100%;
}

.customer-chart-preview {
  margin-top: $wolf-space-md-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  padding: $wolf-space-md-v2;
  background: $wolf-bg-card-v2;
}

@media (max-width: 900px) {
  .customer-chart-page__grid {
    grid-template-columns: 1fr;
  }
}
</style>
