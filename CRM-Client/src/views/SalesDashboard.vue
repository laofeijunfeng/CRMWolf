<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { AmountText, AreaTrendChart, DataViewStatePanel, ListFilterPopover, MetricCard, TableToolbarButton } from '@/components/crmwolf'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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
const funnelError = ref('')
const trendError = ref('')
const ownerFilterError = ref('')
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
    color: 'hsl(var(--chart-1))',
    fillColor: 'hsl(var(--chart-1) / 0.14)'
  },
  {
    key: 'valid',
    label: '有效跟进',
    color: 'hsl(var(--chart-4))',
    fillColor: 'hsl(var(--chart-4) / 0.16)'
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
      color: followUpTrendSeries[0]?.color ?? 'hsl(var(--chart-1))'
    },
    {
      key: 'valid',
      label: '有效跟进',
      value: formatCount(totals.valid),
      color: followUpTrendSeries[1]?.color ?? 'hsl(var(--chart-4))'
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
    `<div class="grid grid-cols-[minmax(0,1fr)_minmax(44px,max-content)] items-center gap-space-4 text-caption leading-[1.6] text-muted-foreground">
      <span class="min-w-0 truncate">${escapeHtml(member.name)}</span>
      <strong class="justify-self-end font-mono font-semibold tabular-nums text-foreground">${formatCount(member.total)}</strong>
    </div>`
  )).join('')
  const memberSection = memberRows
    ? `<div class="flex min-w-0 flex-col gap-0.5">${memberRows}</div>`
    : '<div class="text-caption text-muted-foreground">无成员明细</div>'

  return `<div class="area-trend-tooltip">
    <div class="area-trend-tooltip__title">${escapeHtml(point.date)}</div>
    <div class="area-trend-tooltip__row"><span><i style="background:hsl(var(--chart-1))"></i>跟进总数</span><strong>${formatCount(point.total)}</strong></div>
    <div class="area-trend-tooltip__row"><span><i style="background:hsl(var(--chart-4))"></i>有效跟进</span><strong>${formatCount(point.valid)}</strong></div>
    <div class="my-space-2 h-px bg-border/80"></div>
    ${memberSection}
  </div>`
}

const hasText = (value: string | null | undefined): value is string => {
  return value !== null && value !== undefined && value.trim() !== ''
}

const getMetricDescription = (metric: SalesDashboardMetric): string => {
  if (!hasText(metric.secondary_label)) return ''
  return `${metric.secondary_label}：`
}

const getMetricFooter = (metric: SalesDashboardMetric): string => {
  if (!hasText(metric.rate_label)) return ''
  return `${metric.rate_label}：${formatPercent(metric.rate)}`
}

const getMetricExtraFooter = (metric: SalesDashboardMetric): string => {
  if (!hasText(metric.extra_secondary_label)) return ''
  const value = metric.extra_secondary_type === 'amount'
    ? ''
    : formatCount(metric.extra_secondary_value)
  return `${metric.extra_secondary_label}：${value}`
}

const getDashboardParams = (): {
  funnel: { start_date: string | null; end_date: string | null; owner_id: string | null }
  trend: { start_date: string; end_date: string; owner_id: string | null }
} => {
  const createdTimeBounds = getDateBounds(activeFilters.value, 'created_time')
  const ownerId = getDelimitedFilterValues(activeFilters.value, 'owner_id')
  return {
    funnel: {
      start_date: createdTimeBounds.start ?? null,
      end_date: createdTimeBounds.end ?? null,
      owner_id: ownerId
    },
    trend: {
      ...getTrendDateBounds(),
      owner_id: ownerId
    }
  }
}

const loadDashboard = async (): Promise<void> => {
  loading.value = true
  errorMessage.value = ''
  funnelError.value = ''
  trendError.value = ''
  const params = getDashboardParams()
  const [funnelResult, trendResult] = await Promise.allSettled([
    salesDashboardApi.getFunnel(params.funnel),
    salesDashboardApi.getFollowUpTrend(params.trend)
  ])

  if (funnelResult.status === 'fulfilled') {
    dashboard.value = funnelResult.value
  } else {
    logger.error('[SalesDashboard]', '加载销售漏斗失败', { error: String(funnelResult.reason) })
    funnelError.value = '销售漏斗暂时无法加载'
  }

  if (trendResult.status === 'fulfilled') {
    followUpTrend.value = trendResult.value
  } else {
    logger.error('[SalesDashboard]', '加载跟进趋势失败', { error: String(trendResult.reason) })
    trendError.value = '跟进趋势暂时无法加载'
  }

  if (funnelResult.status === 'rejected' && trendResult.status === 'rejected') {
    errorMessage.value = '销售看板暂时无法加载，请重试'
  }
  if (funnelResult.status === 'rejected' || trendResult.status === 'rejected') {
    toast.warning('销售看板部分数据加载失败', {
      description: '已保留可用数据，你可以针对失败区域重试。'
    })
  }
  loading.value = false
}

const fetchOwnerFilterOptions = async (): Promise<void> => {
  ownerFilterError.value = ''
  try {
    const response = await salesDashboardApi.getOwnerFilterOptions()
    ownerFilterOptions.value = response.data.map((owner) => ({
      value: owner.id,
      label: owner.name
    }))
  } catch (error) {
    logger.error('[SalesDashboard]', '获取销售成员筛选项失败', { error })
    ownerFilterError.value = '销售成员筛选项加载失败'
  }
}

const handleFilterApply = (filters: ListFilterCondition[]): void => {
  activeFilters.value = filters
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
  <div class="box-border flex h-full min-h-0 flex-col overflow-hidden bg-background p-[var(--page-padding)] max-sm:pb-[calc(var(--page-padding)+var(--safe-bottom))]">
    <div class="mb-space-3 flex min-h-control items-center justify-start gap-space-2" aria-label="销售漏斗工具栏">
      <ListFilterPopover
        :model-value="activeFilters"
        :fields="filterFields"
        @update:model-value="activeFilters = $event"
        @apply="handleFilterApply"
      />
      <TableToolbarButton
        class="shrink-0 grow-0 [&_svg]:size-icon-xs"
        :disabled="loading"
        aria-label="刷新销售看板"
        @click="loadDashboard"
      >
        <RefreshCw :class="{ 'animate-spin motion-reduce:animate-none': loading }" aria-hidden="true" />
        刷新
      </TableToolbarButton>
    </div>

    <div
      v-if="ownerFilterError"
      class="dashboard-banner -mt-space-2 mb-space-3 flex shrink-0 items-center gap-space-2 rounded-md border border-destructive/[0.16] bg-destructive/[0.06] px-space-3 text-caption leading-[var(--line-height-body)] text-destructive"
      role="status"
    >
      <AlertCircle class="size-icon-sm" aria-hidden="true" />
      <span>{{ ownerFilterError }}</span>
      <TableToolbarButton class="ml-auto" @click="fetchOwnerFilterOptions">
        重试
      </TableToolbarButton>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto pb-space-2">
      <section class="flex flex-col gap-space-4" aria-label="销售漏斗概览">
        <div
          v-if="errorMessage"
          class="dashboard-banner flex items-center gap-space-2 rounded-md border border-destructive/[0.18] bg-destructive/10 px-space-3 text-caption leading-[var(--line-height-body)] text-destructive"
          role="alert"
        >
          <AlertCircle class="size-icon-sm" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>

        <div
          v-if="funnelError"
          class="dashboard-banner mb-space-2 flex items-center gap-space-2 rounded-md border border-destructive/[0.16] bg-destructive/[0.06] px-space-3 text-caption leading-[var(--line-height-body)] text-destructive"
          role="status"
        >
          <AlertCircle class="size-icon-sm" aria-hidden="true" />
          <span>{{ funnelError }}</span>
          <TableToolbarButton class="ml-auto" @click="loadDashboard">
            重试
          </TableToolbarButton>
        </div>
        <div class="grid grid-cols-1 gap-space-3 sm:grid-cols-2 md:grid-cols-3 md:gap-space-4">
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
                <strong v-else-if="hasText(metric.secondary_label)" class="font-mono font-semibold tabular-nums text-success">
                  {{ formatCount(metric.secondary_value) }}
                </strong>
              </template>
              <template #footer>
                <strong
                  v-if="hasText(metric.extra_secondary_label)"
                  class="min-w-0 font-semibold text-foreground"
                >
                  {{ getMetricExtraFooter(metric) }}
                </strong>
                <strong
                  v-else-if="hasText(metric.rate_label)"
                  class="min-w-0 font-semibold text-foreground"
                >
                  {{ getMetricFooter(metric) }}
                </strong>
              </template>
            </MetricCard>
          </template>

          <template v-else-if="loading">
            <MetricCard
              v-for="item in 6"
              :key="item"
              title="加载中"
              loading
            />
          </template>
          <DataViewStatePanel v-else state="empty" empty-title="暂无销售漏斗数据" class="col-span-full" />
        </div>
      </section>

      <section class="mt-space-4" aria-label="客户活动趋势">
        <div
          v-if="trendError"
          class="dashboard-banner mb-space-2 flex items-center gap-space-2 rounded-md border border-destructive/[0.16] bg-destructive/[0.06] px-space-3 text-caption leading-[var(--line-height-body)] text-destructive"
          role="status"
        >
          <AlertCircle class="size-icon-sm" aria-hidden="true" />
          <span>{{ trendError }}</span>
          <TableToolbarButton class="ml-auto" @click="loadDashboard">
            重试
          </TableToolbarButton>
        </div>
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
              <SelectTrigger
                class="trend-range-select border-border/95 text-caption leading-[var(--line-height-body)] text-muted-foreground"
                aria-label="选择跟进趋势范围"
              >
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
@use '@/styles/tokens.scss' as *;

// 40px 横幅高度暂无令牌
.dashboard-banner {
  min-height: 40px;
}

// 覆盖 SelectTrigger 移动端 touch-target 高度，保持 32px
.trend-range-select {
  width: 104px;
  height: var(--control-h-md);
}

@media (max-width: $bp-sm) {
  .trend-range-select {
    width: 100%;
  }
}
</style>
