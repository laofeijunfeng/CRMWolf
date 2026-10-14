<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import AmountText from './AmountText.vue'
import AreaTrendChart from './AreaTrendChart.vue'
import type { AreaTrendDatum, AreaTrendSeries } from './AreaTrendChart.vue'
import type {
  BoardCardActivation,
  BoardCardPresentation,
  BoardColumnPresentation,
  BoardProjection,
  BoardTrendPointPresentation,
  BoardValueType,
} from './boardTypes'

interface Props {
  projection: BoardProjection | null
  loading?: boolean
  refreshing?: boolean
  stale?: boolean
  error?: Error | null
  canDrillThrough?: boolean
  empty?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  refreshing: false,
  stale: false,
  error: null,
  canDrillThrough: false,
  empty: false,
})

const emit = defineEmits<{
  'activate-card': [payload: BoardCardActivation]
  'view-all': [columnKey: string]
  retry: []
}>()

const narrowQuery = typeof window.matchMedia === 'function'
  ? window.matchMedia('(max-width: 767px)')
  : null
const narrow = ref(narrowQuery?.matches ?? false)
const selectedColumnKey = ref('')

function syncNarrowViewport(): void {
  narrow.value = narrowQuery?.matches ?? false
}

onMounted(() => {
  narrowQuery?.addEventListener('change', syncNarrowViewport)
})

onUnmounted(() => {
  narrowQuery?.removeEventListener('change', syncNarrowViewport)
})

const columns = computed(() => props.projection?.columns ?? [])
const metrics = computed(() => props.projection?.metrics ?? [])
const trend = computed(() => props.projection?.trend ?? null)
const visibleColumns = computed(() => {
  if (!narrow.value) return columns.value
  const selected = columns.value.find((column) => column.key === selectedColumnKey.value)
  return selected === undefined ? columns.value.slice(0, 1) : [selected]
})
const showSkeleton = computed(() => props.loading && props.projection === null)
const showBlockingError = computed(() => props.error !== null && props.projection === null && !props.loading)
const showEmpty = computed(() => props.empty && props.projection !== null && !props.loading)

watch(columns, (nextColumns) => {
  if (!nextColumns.some((column) => column.key === selectedColumnKey.value)) {
    selectedColumnKey.value = nextColumns[0]?.key ?? ''
  }
}, { immediate: true })

const toneLabel: Record<BoardColumnPresentation['tone'], string> = {
  neutral: '中性',
  info: '信息',
  success: '成功',
  warning: '警告',
  danger: '危险',
  muted: '静音',
}

function activation(column: BoardColumnPresentation, card: BoardCardPresentation): BoardCardActivation {
  return { id: card.id, columnKey: column.key }
}

function activateCard(column: BoardColumnPresentation, card: BoardCardPresentation): void {
  emit('activate-card', activation(column, card))
}

function viewAll(columnKey: string): void {
  if (!props.canDrillThrough) return
  emit('view-all', columnKey)
}

function chartPoints(points: readonly BoardTrendPointPresentation[]): AreaTrendDatum[] {
  return points.map((point) => {
    const datum: AreaTrendDatum = { month: point.month }
    for (const [key, value] of Object.entries(point.values)) datum[key] = value
    return datum
  })
}

function chartSeries(series: BoardProjection['trend']): AreaTrendSeries[] {
  return series === null
    ? []
    : series.series.map((item) => ({
      key: item.key,
      label: item.label,
      color: item.color,
      ...(item.fillColor === undefined ? {} : { fillColor: item.fillColor }),
    }))
}

function metricValueType(valueType: BoardValueType): string {
  if (valueType === 'amount') return '金额'
  if (valueType === 'percentage') return '百分比'
  return '数量'
}
</script>

<template>
  <section class="board-view" :aria-busy="loading || refreshing ? 'true' : undefined">
    <div
      v-if="error && projection"
      class="board-inline-error"
      role="alert"
    >
      <AlertCircle class="board-inline-error__icon" aria-hidden="true" />
      <span>{{ stale ? '数据已过期' : '刷新失败' }}：{{ error.message }}</span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        data-testid="board-inline-retry"
        :disabled="loading || refreshing"
        @click="emit('retry')"
      >
        重试
      </Button>
    </div>

    <div v-if="refreshing && projection" class="board-refreshing" role="status">
      <RefreshCw class="board-refreshing__icon" aria-hidden="true" />
      <span>正在刷新，当前显示上次成功加载的数据</span>
    </div>

    <div v-if="showSkeleton" class="board-skeleton" data-testid="board-skeleton" aria-label="看板加载中">
      <div class="board-metrics">
        <Skeleton v-for="index in 3" :key="`metric-${index}`" class="h-20 w-full" />
      </div>
      <div class="board-columns">
        <section v-for="index in 4" :key="`column-${index}`" class="board-column">
          <Skeleton class="h-8 w-24" />
          <Skeleton class="h-28 w-full" />
          <Skeleton class="h-28 w-full" />
        </section>
      </div>
    </div>

    <div v-else-if="showBlockingError" class="board-blocking-error" role="alert">
      <AlertCircle class="board-blocking-error__icon" aria-hidden="true" />
      <strong>{{ error?.message || '看板暂时无法加载' }}</strong>
      <span>请检查网络连接后重试。</span>
      <Button type="button" data-testid="board-blocking-retry" @click="emit('retry')">
        重新加载
      </Button>
    </div>

    <template v-else-if="projection">
      <p v-if="showEmpty" class="board-empty" role="status">暂无看板数据</p>

      <div v-if="metrics.length > 0" class="board-metrics" aria-label="看板指标">
        <Card v-for="metric in metrics" :key="metric.key" class="board-metric">
          <CardContent class="board-metric__content">
            <span class="board-metric__label">{{ metric.label }}</span>
            <strong>
              <AmountText v-if="metric.valueType === 'amount'" :value="metric.value" size="lg" />
              <template v-else>{{ metric.value }}</template>
            </strong>
            <span class="board-metric__type">{{ metricValueType(metric.valueType) }}</span>
            <span v-if="metric.secondaryLabel" class="board-metric__secondary">
              {{ metric.secondaryLabel }} {{ metric.secondaryValue }}
            </span>
          </CardContent>
        </Card>
      </div>

      <label v-if="narrow" class="board-state-select">
        <span>选择状态</span>
        <select v-model="selectedColumnKey">
          <option v-for="column in columns" :key="column.key" :value="column.key">
            {{ column.label }}
          </option>
        </select>
      </label>

      <div class="board-columns" :class="{ 'board-columns--narrow': narrow }">
        <section
          v-for="column in visibleColumns"
          :key="column.key"
          class="board-column"
          :data-column-key="column.key"
          :data-tone="column.tone"
        >
          <header class="board-column__header">
            <h2>{{ column.label }}</h2>
            <Badge variant="outline">{{ column.countLabel }}</Badge>
            <span class="board-column__tone">{{ toneLabel[column.tone] }} · {{ column.label }}</span>
          </header>
          <p v-if="column.amountLabel" class="board-column__amount">
            <AmountText :value="column.amountLabel" size="sm" />
          </p>
          <div class="board-column__cards">
            <article
              v-for="card in column.cards"
              :key="String(card.id)"
              class="board-card"
              tabindex="0"
              role="button"
              :aria-label="`查看${card.statusLabel}：${card.title}`"
              @click="activateCard(column, card)"
              @keydown.enter.prevent="activateCard(column, card)"
              @keydown.space.prevent="activateCard(column, card)"
            >
              <div class="board-card__topline">
                <span>{{ card.subtitle ?? '-' }}</span>
                <Badge variant="outline">{{ card.statusLabel }}</Badge>
              </div>
              <h3>{{ card.title }}</h3>
              <AmountText v-if="card.primaryValue" :value="card.primaryValue" size="lg" />
              <p v-if="card.dateLabel">{{ card.dateLabel }}</p>
              <p v-if="card.ownerLabel">{{ card.ownerLabel }}</p>
              <dl v-if="card.metadata.length > 0">
                <div v-for="row in card.metadata" :key="row.key">
                  <dt>{{ row.label }}</dt>
                  <dd>{{ row.value }}</dd>
                </div>
              </dl>
            </article>
            <p v-if="column.cards.length === 0" class="board-column__empty">暂无记录</p>
          </div>
          <footer class="board-column__footer">
            <span v-if="column.hasMore">还有 {{ column.remainingCount }} 条</span>
            <button
              type="button"
              :disabled="!canDrillThrough"
              @click.stop="viewAll(column.key)"
            >
              查看全部
            </button>
          </footer>
        </section>
      </div>

      <AreaTrendChart
        v-if="trend"
        :title="trend.title"
        :description="trend.description"
        :data="chartPoints(trend.points)"
        :series="chartSeries(trend)"
        x-key="month"
      />
    </template>
  </section>
</template>

<style scoped lang="scss">
.board-view {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.board-inline-error,
.board-refreshing,
.board-blocking-error,
.board-empty {
  display: flex;
  align-items: center;
  gap: 8px;
}

.board-inline-error,
.board-blocking-error {
  color: hsl(var(--destructive));
}

.board-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.board-state-select {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.board-state-select select {
  min-height: 40px;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  background: hsl(var(--background));
  color: hsl(var(--foreground));
}

.board-columns {
  display: grid;
  min-width: 0;
  grid-auto-flow: column;
  grid-auto-columns: minmax(280px, 320px);
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  overscroll-behavior: contain;
}

.board-columns--narrow {
  grid-auto-flow: row;
  grid-auto-columns: auto;
  grid-template-columns: minmax(0, 1fr);
  overflow-x: hidden;
}

.board-column {
  display: flex;
  min-width: 0;
  min-height: 180px;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  border-radius: 8px;
  background: hsl(var(--muted));
  padding: 12px;
}

.board-column__header,
.board-card__topline,
.board-column__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.board-column__header h2,
.board-card h3 {
  margin: 0;
  color: hsl(var(--foreground));
}

.board-column__tone,
.board-metric__type,
.board-metric__secondary,
.board-column__empty {
  color: hsl(var(--muted-foreground));
}

.board-column__cards {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.board-card {
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  padding: 12px;
  cursor: pointer;
}

.board-card:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
}

.board-column__empty {
  display: flex;
  min-height: 96px;
  align-items: center;
  justify-content: center;
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
}

.board-column__footer button:disabled {
  cursor: not-allowed;
  opacity: 0.38;
}

.board-inline-error__icon,
.board-blocking-error__icon,
.board-refreshing__icon {
  width: 16px;
  height: 16px;
  flex: none;
}

@media (min-width: 768px) {
  .board-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
