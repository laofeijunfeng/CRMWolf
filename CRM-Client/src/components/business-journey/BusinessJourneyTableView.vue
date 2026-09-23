<script setup lang="ts">
import { computed } from 'vue'
import { AmountText, Badge, DataTable, StatusBadge } from '@/components/crmwolf'
import type { ViewDisplayMode, ViewPreferenceConfig } from '@/api/viewPreference'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { BusinessJourneyListItem } from '@/schemas/dealJourney'
import type { FeedbackError } from '@/types/feedback'
import { businessJourneyStagePresentation } from './businessJourneyStagePresentation'

interface Props {
  fields: ListFieldDefinition[]
  data: BusinessJourneyListItem[]
  total: number
  page: number
  pageSize: number
  loading?: boolean
  loadError?: FeedbackError | null
  filters: ListFilterCondition[]
  sorts: ListSortCondition[]
  columns: ViewPreferenceConfig['columns']
  search: string
  displayMode: ViewDisplayMode
  viewApplying?: boolean
  viewApplyError?: FeedbackError | null
  filterViewSaveLoading?: boolean
  viewSaveLoading?: boolean
  ownerOptions?: { value: string; label: string }[]
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  loadError: null,
  viewApplying: false,
  viewApplyError: null,
  filterViewSaveLoading: false,
  viewSaveLoading: false,
  ownerOptions: () => []
})

const emit = defineEmits<{
  'update:page': [value: number]
  'update:page-size': [value: number]
  retry: []
  'row-click': [payload: { customerId: string; journeyPublicId: string }]
  'update:filters': [value: ListFilterCondition[]]
  'filter-apply': [value: ListFilterCondition[]]
  'filter-reset': []
  'filter-save-view': [value: ListFilterCondition[]]
  'update:sorts': [value: ListSortCondition[]]
  'sort-apply': [value: ListSortCondition[]]
  'sort-reset': []
  'column-config-current-change': [value: ViewPreferenceConfig]
  'column-config-save': [value: ViewPreferenceConfig]
  'column-config-reset': []
  'update:view-display-mode': [value: ViewDisplayMode]
  'save-current-view': []
  'retry-view-apply': []
  'update:search': [value: string]
  'search-apply': [value: string]
  'search-clear': []
}>()

const activeColumnPreferenceConfig = computed<ViewPreferenceConfig>(() => ({
  version: 1,
  columns: props.columns
}))

const stageLabels = new Map([
  ['early_communication', '早期沟通'],
  ['active_progress', '积极推进'],
  ['closing_soon', '即将成交'],
  ['contract_processing', '合同处理中'],
  ['payment_processing', '回款处理中'],
  ['invoice_processing', '开票处理中'],
  ['completed', '已完成'],
  ['lost', '已流失']
])

const formatDate = (value: string | null | undefined): string => value?.slice(0, 10) ?? '-'
const handleRowClick = (row: BusinessJourneyListItem): void => {
  emit('row-click', { customerId: row.customer_id, journeyPublicId: row.public_id })
}
</script>

<template>
  <DataTable
    :fields="fields"
    :data="data"
    row-key="public_id"
    :total="total"
    :page="page"
    :page-size="pageSize"
    :loading="loading ?? false"
    :load-error="loadError ?? null"
    height="calc(100vh - 121px)"
    height-strategy="fill"
    scroll-mode="contained"
    row-interactive
    detail-column-key="name"
    :get-row-label="(row: BusinessJourneyListItem) => row.name"
    view-key="business-journeys.list"
    column-config-enabled
    :column-preference-config="activeColumnPreferenceConfig"
    column-preference-mode="custom"
    filter-view-save-enabled
    search-enabled
    :search="search"
    search-placeholder="搜索旅程、客户或商机"
    :search-loading="loading ?? false"
    :filter-view-save-loading="filterViewSaveLoading ?? false"
    :filters="filters"
    :sorts="sorts"
    :view-display-mode="displayMode"
    view-display-mode-enabled
    view-config-trigger-label="视图配置"
    view-config-panel-title="视图配置"
    can-save-current-view
    :view-save-loading="viewSaveLoading ?? false"
    :view-applying="viewApplying ?? false"
    :view-apply-error="viewApplyError ?? null"
    @update:page="emit('update:page', $event)"
    @update:page-size="emit('update:page-size', $event)"
    @retry="emit('retry')"
    @row-click="handleRowClick"
    @update:filters="emit('update:filters', $event)"
    @filter-apply="emit('filter-apply', $event)"
    @filter-reset="emit('filter-reset')"
    @filter-save-view="emit('filter-save-view', $event)"
    @update:sorts="emit('update:sorts', $event)"
    @sort-apply="emit('sort-apply', $event)"
    @sort-reset="emit('sort-reset')"
    @column-config-current-change="emit('column-config-current-change', $event)"
    @column-config-save="emit('column-config-save', $event)"
    @column-config-reset="emit('column-config-reset')"
    @update:view-display-mode="emit('update:view-display-mode', $event)"
    @save-current-view="emit('save-current-view')"
    @retry-view-apply="emit('retry-view-apply')"
    @update:search="emit('update:search', $event)"
    @search-apply="emit('search-apply', $event)"
    @search-clear="emit('search-clear')"
  >
    <template #cell-name="{ row }">
      <span
        class="business-journey-name-link"
        data-testid="business-journey-name-link"
        @click.stop="handleRowClick(row)"
      >
        {{ row.name }}
      </span>
    </template>
    <template #cell-current_board_stage="{ row }">
      <Badge
        variant="outline"
        data-testid="business-journey-stage-badge"
        :class="businessJourneyStagePresentation[row.current_board_stage].badgeClass"
      >
        {{ row.current_board_stage_label || stageLabels.get(row.current_board_stage) || '-' }}
      </Badge>
    </template>
    <template #cell-primary_opportunity_name="{ row }">
      {{ row.primary_opportunity_name || '-' }}
    </template>
    <template #cell-product_name="{ row }">
      {{ row.product_name || '-' }}
    </template>
    <template #cell-amount="{ row }">
      <AmountText :value="row.amount" />
    </template>
    <template #cell-purchase_type="{ row }">
      <StatusBadge v-if="row.purchase_type" :status="row.purchase_type" type="procurementType" />
      <span v-else class="text-muted-foreground">-</span>
    </template>
    <template #cell-owner_id="{ row }">
      {{ row.owner?.name || '-' }}
    </template>
    <template #cell-last_event_at="{ row }">
      {{ formatDate(row.last_event_at) }}
    </template>
    <template #cell-expected_closing_date="{ row }">
      {{ formatDate(row.expected_closing_date) }}
    </template>
  </DataTable>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.business-journey-name-link {
  color: $wolf-text-link-v2;
  font-weight: $wolf-font-weight-medium-v2;
  cursor: pointer;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}
</style>
