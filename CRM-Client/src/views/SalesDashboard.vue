<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import {
  AmountText,
  AreaTrendChart,
  ListFilterPopover,
  MetricCard,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  TableToolbarButton
} from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import salesDashboardApi, {
  type SalesDashboardFollowUpTrendPoint,
  type SalesDashboardFollowUpTrendResponse,
  type SalesDashboardMetric,
  type SalesDashboardFunnelResponse
} from '@/api/salesDashboard'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { getDateBounds, getDelimitedFilterValues } from '@/utils/listFilters'
import { logger } from '@/utils/logger'

usePageTitle()

const headerStore = useHeaderStore()
const loading = ref(false)
const errorMessage = ref('')
const dashboard = ref<SalesDashboardFunnelResponse | null>(null)
const followUpTrend = ref<SalesDashboardFollowUpTrendResponse | null>(null)
const activeFilters = ref<ListFilterCondition[]>([])
const ownerFilterOptions = ref<{ value: string; label: string }[]>([])
const trendRange = ref('30')

const trendRangeOptions = [
  { value: '7', label: '近 7 天' },
  { value: '30', label: '近 30 天' },
  { value: '90', label: '近 90 天' }
]

const filterFields = computed<ListFilterField[]>(() => [
  {
    key: 'created_time',
    label: '时间',
    type: 'date'
  },
  {
    key: 'owner_id',
    label: '销售成员',
    type: 'enum',
    options: ownerFilterOptions.value
  }
])

const metrics = computed<SalesDashboardMetric[]>(() => dashboard.value?.metrics ?? [])
const followUpTrendSeries = [
  {
    key: 'total',
    label: '跟进总数',
    color: '#2563eb',
    fillColor: 'rgba(37, 99, 235, 0.14)'
  },
  {
    key: 'valid',
    label: '有效跟进',
    color: '#60a5fa',
    fillColor: 'rgba(96, 165, 250, 0.16)'
  }
]

const followUpTrendData = computed(() => {
  return (followUpTrend.value?.data ?? []).map((item) => ({
    label: formatTrendDate(item.date),
    date: item.date,
    total: item.total,
    valid: item.valid,
    members: item.members
  }))
})

const followUpTrendSummaries = computed(() => {
  const totals = followUpTrendData.value.reduce(
    (acc, item) => {
      acc.total += item.total
      acc.valid += item.valid
      return acc
    },
    { total: 0, valid: 0 }
  )

  return [
    {
      key: 'total',
      label: '跟进总数',
      value: formatCount(totals.total),
      color: followUpTrendSeries[0]?.color ?? '#2563eb'
    },
    {
      key: 'valid',
      label: '有效跟进',
      value: formatCount(totals.valid),
      color: followUpTrendSeries[1]?.color ?? '#60a5fa'
    }
  ]
})

const formatCount = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('zh-CN').format(value)
}

const formatPercent = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(Number.isInteger(value) ? 0 : 1)}%`
}

const formatTrendDate = (value: string): string => {
  const [year, month, day] = value.split('-')
  if (year === undefined || month === undefined || day === undefined) return value
  return `${Number(month)}/${Number(day)}`
}

const formatLocalDate = (date: Date): string => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getTrendDateBounds = (): { start_date: string; end_date: string } => {
  const days = Number(trendRange.value)
  const endDate = new Date()
  const startDate = new Date(endDate)
  startDate.setDate(endDate.getDate() - Math.max(days - 1, 0))

  return {
    start_date: formatLocalDate(startDate),
    end_date: formatLocalDate(endDate)
  }
}

const escapeHtml = (value: string): string => {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const formatFollowUpTooltip = (datum: Record<string, unknown>): string => {
  const point = datum as unknown as SalesDashboardFollowUpTrendPoint & { label: string }
  const members = Array.isArray(point.members) ? point.members.slice(0, 6) : []
  const memberRows = members.map((member) => (
    `<div class="sales-follow-tooltip__member">
      <span>${escapeHtml(member.name)}</span>
      <strong>${formatCount(member.total)}</strong>
    </div>`
  )).join('')
  const memberSection = memberRows
    ? `<div class="sales-follow-tooltip__members">${memberRows}</div>`
    : '<div class="sales-follow-tooltip__empty">无成员明细</div>'

  return `<div class="area-trend-tooltip sales-follow-tooltip">
    <div class="area-trend-tooltip__title">${escapeHtml(point.date)}</div>
    <div class="area-trend-tooltip__row"><span><i style="background:#2563eb"></i>跟进总数</span><strong>${formatCount(point.total)}</strong></div>
    <div class="area-trend-tooltip__row"><span><i style="background:#60a5fa"></i>有效跟进</span><strong>${formatCount(point.valid)}</strong></div>
    <div class="sales-follow-tooltip__divider"></div>
    ${memberSection}
  </div>`
}

const hasText = (value: string | null | undefined): value is string => {
  return value !== null && value !== undefined && value.trim() !== ''
}

const getMetricDescription = (metric: SalesDashboardMetric): string => {
  if (!hasText(metric.secondary_label)) return '-'
  return `${metric.secondary_label}：`
}

const getMetricFooter = (metric: SalesDashboardMetric): string => {
  if (!hasText(metric.rate_label)) return '-'
  return `${metric.rate_label}：${formatPercent(metric.rate)}`
}

const loadDashboard = async (): Promise<void> => {
  loading.value = true
  errorMessage.value = ''
  try {
    const createdTimeBounds = getDateBounds(activeFilters.value, 'created_time')
    const ownerId = getDelimitedFilterValues(activeFilters.value, 'owner_id')
    const funnelParams = {
      start_date: createdTimeBounds.start ?? null,
      end_date: createdTimeBounds.end ?? null,
      owner_id: ownerId
    }
    const trendParams = {
      ...getTrendDateBounds(),
      owner_id: ownerId
    }
    const [funnelResponse, followUpTrendResponse] = await Promise.all([
      salesDashboardApi.getFunnel(funnelParams),
      salesDashboardApi.getFollowUpTrend(trendParams)
    ])
    dashboard.value = funnelResponse
    followUpTrend.value = followUpTrendResponse
  } catch (error) {
    logger.error('[SalesDashboard]', '加载销售看板失败', { error })
    errorMessage.value = '销售看板加载失败'
    toast.error('销售看板加载失败')
  } finally {
    loading.value = false
  }
}

const fetchOwnerFilterOptions = async (): Promise<void> => {
  try {
    const response = await salesDashboardApi.getOwnerFilterOptions()
    ownerFilterOptions.value = response.data.map((owner) => ({
      value: owner.id,
      label: owner.name
    }))
  } catch (error) {
    logger.error('[SalesDashboard]', '获取销售成员筛选项失败', { error })
    ownerFilterOptions.value = []
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
  void loadDashboard()
}

const handleFilterReset = (): void => {
  activeFilters.value = []
  void loadDashboard()
}

const handleTrendRangeChange = (): void => {
  void loadDashboard()
}

onMounted(() => {
  headerStore.clear()
  void fetchOwnerFilterOptions()
  void loadDashboard()
})
</script>

<template>
  <div class="sales-dashboard-page">
    <div class="dashboard-toolbar" aria-label="销售漏斗工具栏">
      <ListFilterPopover
        v-model="activeFilters"
        :fields="filterFields"
        @apply="handleFilterApply"
        @reset="handleFilterReset"
      />
      <TableToolbarButton
        class="refresh-button"
        :disabled="loading"
        aria-label="刷新销售看板"
        @click="loadDashboard"
      >
        <RefreshCw class="refresh-icon" :class="{ spinning: loading }" aria-hidden="true" />
        刷新
      </TableToolbarButton>
    </div>

    <div class="dashboard-scroll">
      <section class="dashboard-summary" aria-label="销售漏斗概览">
        <div v-if="errorMessage" class="dashboard-error" role="alert">
          <AlertCircle class="error-icon" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>

        <div class="metric-grid" :class="{ loading }">
          <template v-if="metrics.length > 0">
            <MetricCard
              v-for="metric in metrics"
              :key="metric.key"
              :title="metric.label"
              :value="formatCount(metric.count)"
              :footer="getMetricFooter(metric)"
              :badge="hasText(metric.rate_label) ? formatPercent(metric.rate) : ''"
              tone="positive"
              :aria-label="metric.label"
            >
              <template #description>
                <span>{{ getMetricDescription(metric) }}</span>
                <AmountText
                  v-if="metric.secondary_type === 'amount'"
                  :value="metric.secondary_value"
                  tone="success"
                  size="sm"
                />
                <strong v-else class="metric-secondary-value">{{ formatCount(metric.secondary_value) }}</strong>
              </template>
            </MetricCard>
          </template>

          <template v-else>
            <MetricCard
              v-for="item in 6"
              :key="item"
              title="加载中"
              loading
            />
          </template>
        </div>
      </section>

      <section class="dashboard-trend" aria-label="客户活动趋势">
        <AreaTrendChart
          title="跟进趋势"
          description="每日客户活动与有效跟进"
          :data="followUpTrendData"
          :series="followUpTrendSeries"
          :summaries="followUpTrendSummaries"
          :loading="loading"
          :height="240"
          :tooltip-width="280"
          :tooltip-formatter="formatFollowUpTooltip"
        >
          <template #actions>
            <Select v-model="trendRange" @update:model-value="handleTrendRangeChange">
              <SelectTrigger class="trend-range-select" aria-label="选择跟进趋势范围">
                <SelectValue placeholder="选择范围" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="option in trendRangeOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </SelectItem>
              </SelectContent>
            </Select>
          </template>
        </AreaTrendChart>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.sales-dashboard-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
}

.dashboard-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: $wolf-space-sm-v2;
}

.dashboard-summary {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.dashboard-trend {
  margin-top: $wolf-space-lg-v2;
}

.trend-range-select {
  width: 104px;
  height: 32px;
  border-color: rgba($wolf-border-default-v2, 0.95);
  background: $wolf-bg-card-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.dashboard-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: $wolf-space-sm-v2;
  min-height: 32px;
  margin-bottom: $wolf-space-md-v2;
  background: transparent;
}

.refresh-button {
  flex: 0 0 auto;
}

.refresh-icon {
  width: 14px;
  height: 14px;
}

.refresh-icon.spinning {
  animation: spin 0.8s linear infinite;
}

.dashboard-error {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm-v2;
  min-height: 40px;
  padding: 0 $wolf-space-md-v2;
  color: $wolf-danger-text-v2;
  background: $wolf-danger-bg-v2;
  border: 1px solid rgba($wolf-danger-v2, 0.18);
  border-radius: $wolf-radius-v2;
  font-size: $wolf-font-size-caption-v2;
}

.error-icon {
  width: 16px;
  height: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  gap: $wolf-space-lg-v2;
}

.metric-secondary-value {
  color: $wolf-accent-v2;
  font-family: $wolf-font-mono-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
}

:global(.sales-follow-tooltip__member) {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(44px, max-content);
  align-items: center;
  gap: 16px;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.6;
}

:global(.sales-follow-tooltip__member span) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.sales-follow-tooltip__member strong) {
  justify-self: end;
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-mono-v2;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
}

:global(.sales-follow-tooltip__divider) {
  height: 1px;
  margin: 8px 0;
  background: rgba($wolf-border-default-v2, 0.8);
}

:global(.sales-follow-tooltip__members) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

:global(.sales-follow-tooltip__empty) {
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: $wolf-breakpoint-md-v2) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: $wolf-space-md-v2;
  }
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .sales-dashboard-page {
    height: 100%;
    min-height: 0;
    padding: $wolf-page-padding-mobile-v2;
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .trend-range-select {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .refresh-icon.spinning {
    animation: none;
  }
}
</style>
