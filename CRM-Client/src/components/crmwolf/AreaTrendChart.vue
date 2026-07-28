<script setup lang="ts">
import { computed, ref } from 'vue'
import { CurveType } from '@unovis/ts'
import { VisArea, VisAxis, VisXYContainer } from '@unovis/vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '@/components/ui/card'

export interface AreaTrendSeries {
  key: string
  label: string
  color: string
  fillColor?: string
}

export interface AreaTrendSummary {
  key: string
  label: string
  value: string
  color: string
}

export type AreaTrendDatum = Record<string, unknown>

interface Props {
  title: string
  description?: string
  data: AreaTrendDatum[]
  series: AreaTrendSeries[]
  summaries?: AreaTrendSummary[]
  xKey?: string
  loading?: boolean
  emptyText?: string
  height?: number
  tooltipFormatter?: ((datum: AreaTrendDatum, series: AreaTrendSeries[]) => string) | undefined
  xTickFormatter?: ((datum: AreaTrendDatum, index: number) => string) | undefined
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
  summaries: () => [],
  xKey: 'label',
  loading: false,
  emptyText: '暂无数据',
  height: 260,
  tooltipFormatter: undefined,
  xTickFormatter: undefined
})

const hasData = computed(() => props.data.length > 0)
const normalizedSummaries = computed(() => props.summaries ?? [])
const chartMargin = { top: 12, right: 18, bottom: 28, left: 36 }
const chartWrapRef = ref<HTMLElement | null>(null)
const tooltipVisible = ref(false)
const tooltipContent = ref('')
const tooltipStyle = ref<Record<string, string>>({})
const tooltipGuideStyle = ref<Record<string, string>>({})

const xAccessor = (_datum: AreaTrendDatum, index: number): number => index

const getSeriesValue = (datum: AreaTrendDatum, key: string): number => {
  const value = datum[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value)
  return 0
}

const makeYAccessor = (key: string) => (datum: AreaTrendDatum): number => getSeriesValue(datum, key)

const formatXAxisTick = (value: number): string => {
  const index = Math.round(value)
  const datum = props.data[index]
  if (!datum) return ''
  if (props.xTickFormatter !== undefined) return props.xTickFormatter(datum, index)
  const label = datum[props.xKey]
  return typeof label === 'string' || typeof label === 'number' ? String(label) : ''
}

const formatYAxisTick = (value: number): string => {
  if (!Number.isFinite(value)) return ''
  return Math.round(value).toLocaleString('zh-CN')
}

const defaultTooltipFormatter = (datum: AreaTrendDatum): string => {
  const label = datum[props.xKey]
  const title = typeof label === 'string' || typeof label === 'number' ? String(label) : ''
  const rows = props.series.map((item) => {
    const value = getSeriesValue(datum, item.key).toLocaleString('zh-CN')
    return `<div class="area-trend-tooltip__row"><span><i style="background:${item.color}"></i>${item.label}</span><strong>${value}</strong></div>`
  }).join('')
  return `<div class="area-trend-tooltip"><div class="area-trend-tooltip__title">${title}</div>${rows}</div>`
}

const getTooltipContent = (
  datum: AreaTrendDatum | undefined,
  _x?: number | Date,
  data?: AreaTrendDatum[],
  leftNearestDatumIndex?: number
): string => {
  const resolvedDatum = datum ?? (leftNearestDatumIndex !== undefined ? data?.[leftNearestDatumIndex] : undefined)
  if (!resolvedDatum) return ''
  return props.tooltipFormatter?.(resolvedDatum, props.series) ?? defaultTooltipFormatter(resolvedDatum)
}

const hideTooltip = (): void => {
  tooltipVisible.value = false
}

const handleChartMouseMove = (event: MouseEvent): void => {
  if (!hasData.value || chartWrapRef.value === null) return

  const rect = chartWrapRef.value.getBoundingClientRect()
  const plotLeft = chartMargin.left
  const plotRight = rect.width - chartMargin.right
  const plotWidth = Math.max(plotRight - plotLeft, 1)
  const pointerX = Math.min(Math.max(event.clientX - rect.left, plotLeft), plotRight)
  const ratio = props.data.length <= 1 ? 0 : (pointerX - plotLeft) / plotWidth
  const datumIndex = Math.min(Math.max(Math.round(ratio * (props.data.length - 1)), 0), props.data.length - 1)
  const content = getTooltipContent(props.data[datumIndex], datumIndex, props.data, datumIndex)
  const datumRatio = props.data.length <= 1 ? 0 : datumIndex / (props.data.length - 1)
  const guideX = plotLeft + datumRatio * plotWidth

  if (content === '') {
    hideTooltip()
    return
  }

  const tooltipWidth = 220
  const tooltipGap = 12
  const leftOffset = guideX + tooltipGap
  const topOffset = event.clientY - rect.top + 12
  const shouldFlipX = leftOffset + tooltipWidth > rect.width

  tooltipContent.value = content
  tooltipStyle.value = {
    left: shouldFlipX ? 'auto' : `${leftOffset}px`,
    right: shouldFlipX ? `${Math.max(rect.width - guideX + tooltipGap, 8)}px` : 'auto',
    top: `${Math.min(topOffset, Math.max(rect.height - 32, 0))}px`
  }
  tooltipGuideStyle.value = {
    left: `${guideX}px`,
    top: `${chartMargin.top}px`,
    bottom: `${chartMargin.bottom}px`
  }
  tooltipVisible.value = true
}
</script>

<template>
  <Card class="area-trend-card" :aria-busy="loading ? 'true' : undefined">
    <CardHeader class="area-trend-card__header">
      <div class="area-trend-card__title-group">
        <CardTitle class="area-trend-card__title">{{ title }}</CardTitle>
        <CardDescription v-if="description" class="area-trend-card__description">
          {{ description }}
        </CardDescription>
      </div>
      <div v-if="$slots['actions']" class="area-trend-card__actions">
        <slot name="actions"></slot>
      </div>
      <div v-else class="area-trend-card__legend" aria-hidden="true">
        <span v-for="item in series" :key="item.key" class="area-trend-card__legend-item">
          <i :style="{ backgroundColor: item.color }"></i>
          {{ item.label }}
        </span>
      </div>
    </CardHeader>

    <CardContent class="area-trend-card__content">
      <div v-if="loading" class="area-trend-card__skeleton" :style="{ height: `${height}px` }">
        <span></span>
      </div>
      <div v-else-if="!hasData" class="area-trend-card__empty" :style="{ height: `${height}px` }">
        {{ emptyText }}
      </div>
      <div
        v-else
        ref="chartWrapRef"
        class="area-trend-chart-wrap"
        @mousemove="handleChartMouseMove"
        @mouseleave="hideTooltip"
      >
        <VisXYContainer
          class="area-trend-chart"
          :data="data"
          :height="height"
          :margin="chartMargin"
        >
          <VisArea
            v-for="item in series"
            :key="item.key"
            :x="xAccessor"
            :y="makeYAccessor(item.key)"
            :color="item.fillColor ?? item.color"
            :line-color="item.color"
            :curve-type="CurveType.MonotoneX"
            :line="true"
            :line-width="2"
            :opacity="1"
          />
          <VisAxis type="x" :tick-format="formatXAxisTick" :grid-line="false" />
          <VisAxis type="y" :tick-format="formatYAxisTick" />
        </VisXYContainer>
        <div
          v-if="tooltipVisible"
          class="area-trend-tooltip-guide"
          :style="tooltipGuideStyle"
          aria-hidden="true"
        ></div>
        <div
          v-if="tooltipVisible"
          class="area-trend-tooltip-host"
          :style="tooltipStyle"
          v-html="tooltipContent"
        ></div>
      </div>
      <div v-if="normalizedSummaries.length > 0" class="area-trend-card__summaries" aria-label="趋势汇总">
        <div v-for="item in normalizedSummaries" :key="item.key" class="area-trend-card__summary">
          <i :style="{ backgroundColor: item.color }" aria-hidden="true"></i>
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </CardContent>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.area-trend-card {
  min-width: 0;
  border-color: rgba($wolf-border-default-v2, 0.9);
  border-radius: $wolf-radius-xl-v2;
  background:
    linear-gradient(0deg, rgba($wolf-primary-v2, 0.045) 0%, rgba($wolf-primary-v2, 0.018) 36%, rgba(255, 255, 255, 0) 72%),
    $wolf-bg-card-v2;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}

.area-trend-card__header {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: space-between;
  gap: $wolf-space-lg-v2;
  padding: 16px 18px 8px;
}

.area-trend-card__title-group {
  min-width: 0;
}

.area-trend-card__title {
  margin: 0;
  color: $wolf-text-primary-v2;
  font-size: 16px;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: 1.4;
  letter-spacing: 0;
}

.area-trend-card__description {
  margin-top: 2px;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.4;
}

.area-trend-card__legend {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px 12px;
  max-width: 45%;
  padding-top: 2px;
}

.area-trend-card__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.4;
  white-space: nowrap;
}

.area-trend-card__legend-item i {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: $wolf-radius-full-v2;
}

.area-trend-card__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.area-trend-card__content {
  padding: 4px 10px 12px;
}

.area-trend-card__summaries {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px 18px;
  padding: 0 16px 4px;
}

.area-trend-card__summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: $wolf-text-secondary-v2;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
}

.area-trend-card__summary i {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: $wolf-radius-full-v2;
}

.area-trend-card__summary strong {
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-mono-v2;
  font-size: 12px;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
}

.area-trend-chart-wrap {
  position: relative;
  min-width: 0;
}

.area-trend-chart {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.area-trend-tooltip-host {
  position: absolute;
  z-index: 10;
  width: 220px;
  pointer-events: none;
}

.area-trend-tooltip-guide {
  position: absolute;
  z-index: 1;
  width: 1px;
  background: rgba($wolf-text-tertiary-v2, 0.26);
  pointer-events: none;
}

.area-trend-card__empty,
.area-trend-card__skeleton {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba($wolf-border-default-v2, 0.8);
  border-radius: $wolf-radius-v2;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.area-trend-card__skeleton {
  overflow: hidden;
  background: linear-gradient(90deg, rgba($wolf-bg-muted-v2, 0.55), rgba($wolf-bg-muted-v2, 0.95), rgba($wolf-bg-muted-v2, 0.55));
  background-size: 200% 100%;
  animation: areaTrendLoading 1.2s ease-in-out infinite;
}

@keyframes areaTrendLoading {
  to {
    background-position: -200% 0;
  }
}

:global(.area-trend-tooltip) {
  min-width: 184px;
  padding: 10px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: $wolf-radius-v2;
  color: $wolf-text-secondary-v2;
  background: rgba(255, 255, 255, 0.96);
  box-shadow:
    0 8px 18px rgba(15, 23, 42, 0.1),
    0 1px 2px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(8px);
}

:global(.area-trend-tooltip__title) {
  margin-bottom: 8px;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-caption-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  line-height: 1.4;
}

:global(.area-trend-tooltip__row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.6;
}

:global(.area-trend-tooltip__row span) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

:global(.area-trend-tooltip__row i) {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: $wolf-radius-full-v2;
}

:global(.area-trend-tooltip__row strong) {
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-mono-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .area-trend-card__header {
    flex-direction: column;
    gap: $wolf-space-sm-v2;
    padding: 14px 14px 8px;
  }

  .area-trend-card__legend {
    justify-content: flex-start;
    max-width: none;
  }

  .area-trend-card__actions {
    width: 100%;
    justify-content: flex-start;
  }

  .area-trend-card__content {
    padding: 2px 6px 10px;
  }

  .area-trend-card__summaries {
    padding: 0 8px 4px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .area-trend-card__skeleton {
    animation: none;
  }
}
</style>
