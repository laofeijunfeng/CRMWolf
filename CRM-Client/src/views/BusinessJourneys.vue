<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch, watchEffect } from 'vue'
import type { ViewDisplayMode, ViewPreferenceConfig } from '@/api/viewPreference'
import { dealJourneyApi, type BusinessJourneyTab } from '@/api/dealJourney'
import BusinessJourneyBoardView from '@/components/business-journey/BusinessJourneyBoardView.vue'
import BusinessJourneyListTools from '@/components/business-journey/BusinessJourneyListTools.vue'
import BusinessJourneyTableView from '@/components/business-journey/BusinessJourneyTableView.vue'
import DealJourneyDetailSheet from '@/views/DealJourneyDetailSheet.vue'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'
import { createBusinessJourneyListFields } from '@/components/business-journey/businessJourneyListFields'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import { isCustomFilterViewTab, useCustomFilterViews } from '@/composables/useCustomFilterViews'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import type {
  BusinessJourneyBoardResponse,
  BusinessJourneyListItem
} from '@/schemas/dealJourney'
import { useHeaderStore } from '@/stores/header'
import type { FeedbackError } from '@/types/feedback'
import { serializeListQuery } from '@/utils/listQuery'
import { logger } from '@/utils/logger'

usePageTitle()

const headerStore = useHeaderStore()
const activeTab = ref<string>('all')
const displayMode = ref<ViewDisplayMode>('table')
const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])
const search = ref('')
const ownerOptions = ref<{ value: string; label: string }[]>([])

const tableLoading = ref(false)
const tableError = ref<FeedbackError | null>(null)
const tableItems = ref<BusinessJourneyListItem[]>([])
const tableRequestSequence = ref(0)
const tableHasSuccess = ref(false)
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const boardLoading = ref(false)
const boardErrorMessage = ref('')
const board = ref<BusinessJourneyBoardResponse | null>(null)
const boardRequestSequence = ref(0)
const boardHasSuccess = ref(false)
const selectedJourneyCustomerId = ref<string | null>(null)
const selectedJourneyCustomerName = ref<string | undefined>(undefined)
const selectedJourneyName = ref<string | undefined>(undefined)
const selectedJourneyId = ref<string | null>(null)
const journeyDetailVisible = ref(false)
let journeyDetailTrigger: HTMLElement | null = null
const selectedCustomerId = ref<string | null>(null)
const customerDetailVisible = ref(false)

const builtInFilters: Record<string, ListFilterCondition[]> = {
  all: [],
  active: [{ field: 'status', op: 'in', value: ['ACTIVE', 'WON'] }],
  completed: [{ field: 'status', op: 'eq', value: 'COMPLETED' }],
  lost: [{ field: 'status', op: 'eq', value: 'LOST' }]
}

const builtInTabs = [
  { key: 'all', label: '全部旅程' },
  { key: 'active', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'lost', label: '已流失' }
]

const fields = computed(() => createBusinessJourneyListFields(ownerOptions.value))
const requestTab = computed<BusinessJourneyTab>(() =>
  isCustomFilterViewTab(activeTab.value)
    ? 'all'
    : (activeTab.value as BusinessJourneyTab)
)

function projectionQuery(): {
  tab: BusinessJourneyTab
  search?: string
  filters: string
  sorts: string
} {
  const keyword = search.value.trim()
  return {
    tab: requestTab.value,
    ...(keyword === '' ? {} : { search: keyword }),
    ...serializeListQuery({ filters: activeFilters.value, sorts: activeSorts.value })
  }
}

function tableFailure(error: unknown): FeedbackError {
  logger.error('[BusinessJourneys]', '加载业务旅程列表失败', { error })
  return tableHasSuccess.value
    ? {
        title: '业务旅程列表刷新失败',
        description: '当前显示上次成功加载的数据，你可以重试。',
        kind: 'unknown',
        retryable: true,
        variant: 'error'
      }
    : {
        title: '业务旅程列表加载失败',
        description: '请检查网络连接后重试。',
        kind: 'unknown',
        retryable: true,
        variant: 'error'
      }
}

async function loadTable(): Promise<boolean> {
  const requestId = ++tableRequestSequence.value
  tableLoading.value = true
  tableError.value = null
  try {
    const response = await dealJourneyApi.list({
      skip: (pagination.current - 1) * pagination.pageSize,
      limit: pagination.pageSize,
      ...projectionQuery()
    })
    if (requestId !== tableRequestSequence.value || displayMode.value !== 'table') return false
    tableItems.value = response.items
    pagination.total = response.total
    tableHasSuccess.value = true
    return true
  } catch (error) {
    if (requestId !== tableRequestSequence.value || displayMode.value !== 'table') return false
    tableError.value = tableFailure(error)
    return false
  } finally {
    if (requestId === tableRequestSequence.value) tableLoading.value = false
  }
}

async function loadBoard(): Promise<boolean> {
  const requestId = ++boardRequestSequence.value
  boardLoading.value = true
  boardErrorMessage.value = ''
  try {
    const response = await dealJourneyApi.getBoard(projectionQuery())
    if (requestId !== boardRequestSequence.value || displayMode.value !== 'board') return false
    board.value = response
    boardHasSuccess.value = true
    return true
  } catch (error) {
    if (requestId !== boardRequestSequence.value || displayMode.value !== 'board') return false
    logger.error('[BusinessJourneys]', '加载业务旅程看板失败', { error })
    boardErrorMessage.value = boardHasSuccess.value
      ? '旅程看板刷新失败，当前显示上次成功加载的数据'
      : '旅程看板加载失败，请重试'
    return false
  } finally {
    if (requestId === boardRequestSequence.value) boardLoading.value = false
  }
}

function invalidateInactiveProjection(nextMode: ViewDisplayMode): void {
  if (nextMode === 'table') {
    boardRequestSequence.value += 1
    boardLoading.value = false
  } else {
    tableRequestSequence.value += 1
    tableLoading.value = false
  }
}

function refreshActiveProjection(): Promise<boolean> {
  return displayMode.value === 'table' ? loadTable() : loadBoard()
}

const customFilterViews = useCustomFilterViews({
  viewKey: 'business-journeys.list',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  activeDisplayMode: displayMode,
  builtInDisplayMode: 'table',
  getBuiltInFilters: tabKey => builtInFilters[tabKey] ?? [],
  refresh: refreshActiveProjection,
  onViewApplySuccess: tabKey => headerStore.setActiveTab(tabKey)
})

watch(displayMode, (nextMode, previousMode) => {
  if (nextMode !== previousMode) invalidateInactiveProjection(nextMode)
}, { flush: 'sync' })
const allTabs = computed(() => customFilterViews.mergeTabs(builtInTabs))

useTopBarRegistration({
  tabs: allTabs,
  activeTab,
  actions: () => []
})

async function fetchOwnerOptions(): Promise<void> {
  try {
    const response = await dealJourneyApi.getOwnerFilterOptions()
    ownerOptions.value = response.data.map(owner => ({ value: owner.id, label: owner.name }))
  } catch (error) {
    logger.error('[BusinessJourneys]', '加载负责人筛选项失败', { error })
  }
}

async function handleDisplayModeChange(mode: ViewDisplayMode): Promise<void> {
  if (mode === displayMode.value) return
  displayMode.value = mode
  const projectionRefresh = refreshActiveProjection()
  await Promise.all([
    customFilterViews.updateActiveCustomViewConfig(),
    projectionRefresh,
  ])
}

async function handleFilterApply(filters: ListFilterCondition[]): Promise<void> {
  activeFilters.value = filters
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
  await refreshActiveProjection()
}
function handleFilterReset(): void {
  activeFilters.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  void refreshActiveProjection()
}

async function handleSortApply(sorts: ListSortCondition[]): Promise<void> {
  activeSorts.value = sorts
  pagination.current = 1
  await customFilterViews.updateActiveCustomViewConfig()
  await refreshActiveProjection()
}

function handleSortReset(): void {
  activeSorts.value = []
  pagination.current = 1
  void customFilterViews.updateActiveCustomViewConfig()
  void refreshActiveProjection()
}

function handleSearchApply(value: string): void {
  search.value = value.trim()
  pagination.current = 1
  void refreshActiveProjection()
}

function handleSearchClear(): void {
  search.value = ''
  pagination.current = 1
  void refreshActiveProjection()
}

function handleColumnConfigSave(config: ViewPreferenceConfig): void {
  activeColumns.value = config.columns
  void customFilterViews.saveActiveCustomViewColumns(config.columns)
}

function handleColumnConfigReset(): void {
  activeColumns.value = []
  void customFilterViews.saveActiveCustomViewColumns([])
}

function handlePageChange(page: number): void {
  pagination.current = page
  void loadTable()
}

function handlePageSizeChange(pageSize: number): void {
  pagination.pageSize = pageSize
  pagination.current = 1
  void loadTable()
}

function findCustomerName(customerId: string, journeyPublicId: string): string | undefined {
  const tableMatch = tableItems.value.find(item => item.customer_id === customerId && item.public_id === journeyPublicId)
  if (tableMatch !== undefined) return tableMatch.customer_name

  const boardMatch = board.value?.columns
    .flatMap(column => column.cards)
    .find(card => 'public_id' in card && card.customer_id === customerId && card.public_id === journeyPublicId)
  return boardMatch?.customer_name
}

function findJourneyName(customerId: string, journeyPublicId: string): string | undefined {
  const tableMatch = tableItems.value.find(item => item.customer_id === customerId && item.public_id === journeyPublicId)
  if (tableMatch !== undefined) return tableMatch.name

  return board.value?.columns
    .flatMap(column => column.cards)
    .find(card => card.customer_id === customerId && card.public_id === journeyPublicId)
    ?.journey_name
}

function handleRowClick(payload: { customerId: string; journeyPublicId: string }): void {
  journeyDetailTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  selectedJourneyCustomerId.value = payload.customerId
  selectedJourneyCustomerName.value = findCustomerName(payload.customerId, payload.journeyPublicId)
  selectedJourneyName.value = findJourneyName(payload.customerId, payload.journeyPublicId)
  selectedJourneyId.value = payload.journeyPublicId
  journeyDetailVisible.value = true
}

function clearJourneyDetailSelection(): void {
  journeyDetailVisible.value = false
  selectedJourneyCustomerId.value = null
  selectedJourneyCustomerName.value = undefined
  selectedJourneyName.value = undefined
  selectedJourneyId.value = null
}

async function restoreJourneyTriggerFocus(): Promise<void> {
  const trigger = journeyDetailTrigger
  journeyDetailTrigger = null
  await nextTick()
  if (trigger?.isConnected === true) trigger.focus()
}

async function handleJourneyDetailVisibleChange(visible: boolean): Promise<void> {
  journeyDetailVisible.value = visible
  if (visible) return

  clearJourneyDetailSelection()
  if (customerDetailVisible.value) return
  await restoreJourneyTriggerFocus()
}

function handleViewCustomer(customerId: string): void {
  clearJourneyDetailSelection()
  selectedCustomerId.value = customerId
  customerDetailVisible.value = true
}

async function handleCustomerDetailVisibleChange(visible: boolean): Promise<void> {
  customerDetailVisible.value = visible
  if (visible) return

  selectedCustomerId.value = null
  await restoreJourneyTriggerFocus()
}

function refreshJourneyProjection(): void {
  void refreshActiveProjection()
}

watchEffect(() => {
  const nextTab = headerStore.activeTab
  if (nextTab === '' || nextTab === activeTab.value) return
  pagination.current = 1
  if (customFilterViews.consumeFailedViewApply(nextTab)) {
    headerStore.activeTab = activeTab.value
    return
  }
  if (customFilterViews.applyCustomViewTab(nextTab)) return
  customFilterViews.applyBuiltInTab(nextTab)
  void refreshActiveProjection()
})

onMounted(() => {
  void fetchOwnerOptions()
  void customFilterViews.loadCustomViews()
  void loadTable()
})
</script>

<template>
  <div class="business-journeys-page">
    <BusinessJourneyListTools
      v-if="displayMode === 'board'"
      :fields="fields"
      :filters="activeFilters"
      :sorts="activeSorts"
      :columns="activeColumns"
      :search="search"
      :display-mode="displayMode"
      :loading="boardLoading"
      :saving="customFilterViews.saving.value"
      @update:search="search = $event"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @update:filters="activeFilters = $event"
      @filter-apply="handleFilterApply"
      @filter-reset="handleFilterReset"
      @filter-save-view="customFilterViews.saveAsCustomView"
      @update:sorts="activeSorts = $event"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="handleColumnConfigReset"
      @update:view-display-mode="handleDisplayModeChange"
      @save-current-view="customFilterViews.saveCurrentAsCustomView"
      @refresh="refreshActiveProjection"
    />

    <BusinessJourneyTableView
      v-if="displayMode === 'table'"
      :fields="fields"
      :data="tableItems"
      :total="pagination.total"
      :page="pagination.current"
      :page-size="pagination.pageSize"
      :loading="tableLoading"
      :load-error="tableError"
      :filters="activeFilters"
      :sorts="activeSorts"
      :columns="activeColumns"
      :search="search"
      :display-mode="displayMode"
      :view-applying="customFilterViews.applying.value"
      :view-apply-error="customFilterViews.applyError.value"
      :filter-view-save-loading="customFilterViews.saving.value"
      :view-save-loading="customFilterViews.saving.value"
      :owner-options="ownerOptions"
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
      @retry="loadTable"
      @row-click="handleRowClick"
      @update:filters="activeFilters = $event"
      @filter-apply="handleFilterApply"
      @filter-reset="handleFilterReset"
      @filter-save-view="customFilterViews.saveAsCustomView"
      @update:sorts="activeSorts = $event"
      @sort-apply="handleSortApply"
      @sort-reset="handleSortReset"
      @column-config-current-change="activeColumns = $event.columns"
      @column-config-save="handleColumnConfigSave"
      @column-config-reset="handleColumnConfigReset"
      @update:view-display-mode="handleDisplayModeChange"
      @save-current-view="customFilterViews.saveCurrentAsCustomView"
      @retry-view-apply="customFilterViews.retryViewApply"
      @update:search="search = $event"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
    />

    <BusinessJourneyBoardView
      v-else
      :board="board"
      :loading="boardLoading"
      :error-message="boardErrorMessage"
      @retry="loadBoard"
      @row-click="handleRowClick"
    />
  </div>

  <DealJourneyDetailSheet
    :customer-id="selectedJourneyCustomerId"
    :customer-name="selectedJourneyCustomerName"
    :journey-id="selectedJourneyId"
    :journey-name="selectedJourneyName"
    :visible="journeyDetailVisible"
    @update:visible="handleJourneyDetailVisibleChange"
    @refresh="refreshJourneyProjection"
    @view-customer="handleViewCustomer"
  />

  <CustomerDetailSheet
    :customer-id="selectedCustomerId"
    :visible="customerDetailVisible"
    @update:visible="handleCustomerDetailVisibleChange"
    @refresh="refreshJourneyProjection"
  />
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.business-journeys-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: $wolf-list-page-padding-top-v2 $wolf-page-padding-v2 $wolf-page-padding-v2;
  gap: 16px;
  background: $wolf-bg-page-v2;
}

@media (max-width: 900px) {
  .business-journeys-page {
    padding: $wolf-page-padding-mobile-v2;
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }
}
</style>
