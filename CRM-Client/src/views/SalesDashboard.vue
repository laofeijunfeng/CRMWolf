<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, ArrowRight, BarChart3, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { AmountText, ListFilterPopover, TableToolbarButton } from '@/components/crmwolf'
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

      <div class="flow-scroll" :class="{ loading }">
        <template v-if="metrics.length > 0">
          <template
            v-for="(metric, index) in metrics"
            :key="metric.key"
          >
            <article class="flow-card" :aria-label="metric.label">
              <div class="card-topline">
                <span class="card-label">{{ metric.label }}</span>
                <span class="card-count">{{ formatCount(metric.count) }}</span>
              </div>
              <div class="card-secondary">
                <span>{{ metric.secondary_label || '-' }}：</span>
                <AmountText
                  v-if="metric.secondary_type === 'amount'"
                  :value="metric.secondary_value"
                  tone="success"
                  size="sm"
                />
                <strong v-else>{{ formatCount(metric.secondary_value) }}</strong>
              </div>
              <div class="card-rate">
                <span v-if="metric.rate_label">{{ metric.rate_label }}：{{ formatPercent(metric.rate) }}</span>
                <span v-else>-</span>
              </div>
            </article>

            <ArrowRight
              v-if="index < metrics.length - 1"
              class="flow-arrow"
              aria-hidden="true"
            />
          </template>
        </template>

        <template v-else>
          <article
            v-for="item in 6"
            :key="item"
            class="flow-card flow-card--skeleton"
          >
            <div class="skeleton-line skeleton-line--top"></div>
            <div class="skeleton-line"></div>
            <div class="skeleton-line skeleton-line--short"></div>
          </article>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.sales-dashboard-page {
  min-height: calc(100vh - $wolf-topbar-height-v2);
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

.flow-scroll {
  display: grid;
  grid-template-columns: repeat(6, minmax(148px, 1fr));
  align-items: stretch;
  gap: $wolf-space-md-v2;
  overflow-x: auto;
  padding-bottom: $wolf-space-xs-v2;
  scrollbar-width: thin;
}

.flow-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 148px;
  min-height: 112px;
  padding: $wolf-card-padding-v2;
  background: $wolf-bg-card-v2;
  border: 1px solid $wolf-border-default-v2;
  border-radius: $wolf-radius-v2;
  box-shadow: $wolf-shadow-card-v2;
}

.card-topline {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: $wolf-space-md-v2;
}

.card-label {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.card-count {
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-mono-v2;
  font-size: 24px;
  font-weight: $wolf-font-weight-semibold-v2;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.card-secondary,
.card-rate {
  display: flex;
  align-items: center;
  min-height: 20px;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  line-height: 1.35;
  white-space: nowrap;
}

.card-secondary {
  margin-top: $wolf-space-md-v2;

  strong {
    color: $wolf-accent-v2;
    font-family: $wolf-font-mono-v2;
    font-weight: $wolf-font-weight-semibold-v2;
    font-variant-numeric: tabular-nums;
  }
}

.card-rate {
  color: $wolf-text-tertiary-v2;
}

.flow-arrow {
  display: none;
}

.flow-card--skeleton {
  gap: $wolf-space-md-v2;
}

.skeleton-line {
  height: 12px;
  width: 80%;
  background: $wolf-bg-muted-v2;
  border-radius: $wolf-radius-sm-v2;
}

.skeleton-line--top {
  height: 24px;
  width: 100%;
}

.skeleton-line--short {
  width: 52%;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: $wolf-breakpoint-md-v2) {
  .flow-scroll {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm-v2;
    margin-right: calc(-1 * $wolf-page-padding-mobile-v2);
    padding-right: $wolf-page-padding-mobile-v2;
  }

  .flow-card {
    flex: 0 0 156px;
  }

  .flow-arrow {
    display: block;
    width: 16px;
    height: 16px;
    flex: 0 0 16px;
    color: $wolf-text-tertiary-v2;
  }
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .sales-dashboard-page {
    min-height: calc($wolf-viewport-height-mobile-v2 - $wolf-topbar-height-mobile-v2);
    padding: $wolf-page-padding-mobile-v2;
    padding-bottom: calc($wolf-bottom-nav-height-v2 + $wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
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
}

@media (prefers-reduced-motion: reduce) {
  .refresh-icon.spinning {
    animation: none;
  }
}
</style>
