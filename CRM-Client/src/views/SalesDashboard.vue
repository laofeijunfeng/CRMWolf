<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, BarChart3, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { AmountText, ListFilterPopover, MetricCard, TableToolbarButton } from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import salesDashboardApi, { type SalesDashboardMetric, type SalesDashboardFunnelResponse } from '@/api/salesDashboard'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { getDateBounds, getDelimitedFilterValues } from '@/utils/listFilters'
import { logger } from '@/utils/logger'

usePageTitle()

const headerStore = useHeaderStore()
const loading = ref(false)
const errorMessage = ref('')
const dashboard = ref<SalesDashboardFunnelResponse | null>(null)
const activeFilters = ref<ListFilterCondition[]>([])
const ownerFilterOptions = ref<{ value: string; label: string }[]>([])

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

const formatCount = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('zh-CN').format(value)
}

const formatPercent = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '-'
  return `${Number(value).toFixed(Number.isInteger(value) ? 0 : 1)}%`
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
    dashboard.value = await salesDashboardApi.getFunnel({
      start_date: createdTimeBounds.start ?? null,
      end_date: createdTimeBounds.end ?? null,
      owner_id: getDelimitedFilterValues(activeFilters.value, 'owner_id')
    })
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

    <section class="dashboard-summary" aria-label="销售漏斗概览">
      <div class="summary-header">
        <div class="summary-title">
          <BarChart3 class="summary-icon" aria-hidden="true" />
          <div>
            <h2>销售漏斗</h2>
          </div>
        </div>
      </div>

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
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.sales-dashboard-page {
  min-height: 100%;
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
}

.dashboard-summary {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
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

.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $wolf-space-lg-v2;
}

.summary-title {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: $wolf-space-md-v2;

  h2 {
    margin: 0;
    color: $wolf-text-primary-v2;
    font-size: 18px;
    font-weight: $wolf-font-weight-semibold-v2;
    line-height: 1.4;
  }
}

.summary-icon {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  padding: 7px;
  color: $wolf-primary-v2;
  background: $wolf-primary-light-v2;
  border-radius: $wolf-radius-v2;
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
    min-height: 100%;
    padding: $wolf-page-padding-mobile-v2;
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .summary-header {
    align-items: flex-start;
  }

  .summary-title {
    align-items: flex-start;
  }

  .summary-icon {
    margin-top: 2px;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .refresh-icon.spinning {
    animation: none;
  }
}
</style>
