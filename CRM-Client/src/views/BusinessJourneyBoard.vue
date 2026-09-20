<script setup lang="ts">
import { computed, onMounted, ref, watchEffect } from 'vue'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import {
  ListFilterPopover,
  TableToolbarButton
} from '@/components/crmwolf'
import type { ListFilterCondition, ListFilterField } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceConfig } from '@/api/viewPreference'
import businessJourneyBoardApi, {
  type BusinessJourneyBoardResponse
} from '@/api/businessJourneyBoard'
import BusinessJourneyBoardView from '@/components/business-journey/BusinessJourneyBoardView.vue'
import CustomerDetailSheet from './CustomerDetailSheet.vue'
import { useHeaderStore } from '@/stores/header'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { useCustomFilterViews } from '@/composables/useCustomFilterViews'
import {
  BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS,
  buildBusinessJourneyBoardParams
} from '@/utils/businessJourneyBoardFilters'
import { logger } from '@/utils/logger'

usePageTitle()

const headerStore = useHeaderStore()
const loading = ref(false)
const errorMessage = ref('')
const board = ref<BusinessJourneyBoardResponse | null>(null)
const boardRequestSequence = ref(0)
const activeFilters = ref<ListFilterCondition[]>([])
const activeSorts = ref<ListSortCondition[]>([])
const activeColumns = ref<ViewPreferenceConfig['columns']>([])
const activeTab = ref('all')
const ownerFilterOptions = ref<{ value: string; label: string }[]>([])
const ownerFilterLoading = ref(false)
const ownerFilterError = ref('')
const ownerFilterRequestSequence = ref(0)
const selectedCustomerId = ref<string | null>(null)
const sheetVisible = computed({
  get: () => selectedCustomerId.value !== null,
  set: (visible: boolean) => {
    if (!visible) selectedCustomerId.value = null
  }
})

const tabs = [{ key: 'all', label: '所有业务' }]
const filterFields = computed<ListFilterField[]>(() => [
  { key: 'last_event_at', label: '最近动态时间', type: 'date' },
  { key: 'owner_id', label: '负责人', type: 'enum', options: ownerFilterOptions.value },
  ...BUSINESS_JOURNEY_BOARD_OPPORTUNITY_DATE_FILTER_FIELDS
])

async function loadBoard(): Promise<void> {
  const requestId = ++boardRequestSequence.value
  loading.value = true
  errorMessage.value = ''
  try {
    const nextBoard = await businessJourneyBoardApi.getBoard(buildBusinessJourneyBoardParams(activeFilters.value))
    if (requestId !== boardRequestSequence.value) return
    board.value = nextBoard
  } catch (error) {
    if (requestId !== boardRequestSequence.value) return
    logger.error('[BusinessJourneyBoard]', '加载业务看板失败', { error })
    errorMessage.value = board.value !== null
      ? '业务看板刷新失败，当前显示上次成功加载的数据'
      : '业务看板加载失败，请重试'
    toast.warning('业务看板加载失败', {
      description: board.value !== null
        ? '当前仍显示上次成功加载的数据，你可以重试。'
        : '请检查网络连接后重试。'
    })
  } finally {
    if (requestId === boardRequestSequence.value) loading.value = false
  }
}

async function fetchOwnerFilterOptions(): Promise<void> {
  const requestId = ++ownerFilterRequestSequence.value
  ownerFilterLoading.value = true
  ownerFilterError.value = ''
  try {
    const response = await businessJourneyBoardApi.getOwnerFilterOptions()
    if (requestId !== ownerFilterRequestSequence.value) return
    ownerFilterOptions.value = response.data.map(owner => ({ value: owner.id, label: owner.name }))
  } catch (error) {
    if (requestId !== ownerFilterRequestSequence.value) return
    logger.error('[BusinessJourneyBoard]', '获取负责人筛选项失败', { error })
    ownerFilterError.value = ownerFilterOptions.value.length > 0
      ? '负责人筛选项加载失败，当前仍保留已有选项'
      : '负责人筛选项加载失败，请重试'
  } finally {
    if (requestId === ownerFilterRequestSequence.value) ownerFilterLoading.value = false
  }
}

const customFilterViews = useCustomFilterViews({
  viewKey: 'business-journey-board.board',
  activeTab,
  activeFilters,
  activeSorts,
  activeColumns,
  refresh: loadBoard
})
const allTabs = computed(() => customFilterViews.mergeTabs(tabs))

async function handleFilterApply(filters: ListFilterCondition[]): Promise<void> {
  activeFilters.value = filters
  await customFilterViews.updateActiveCustomViewConfig()
  void loadBoard()
}

function handleFilterReset(): void {
  activeFilters.value = []
  void customFilterViews.updateActiveCustomViewConfig()
  void loadBoard()
}

async function handleSaveFilterView(filters: ListFilterCondition[]): Promise<void> {
  activeFilters.value = filters
  await customFilterViews.saveAsCustomView(filters)
}

onMounted(() => {
  void fetchOwnerFilterOptions()
  void customFilterViews.loadCustomViews()
  void loadBoard()
})

useTopBarRegistration({ tabs: allTabs, activeTab, actions: () => [] })

watchEffect(() => {
  if (headerStore.activeTab && headerStore.activeTab !== activeTab.value) {
    if (customFilterViews.applyCustomViewTab(headerStore.activeTab)) return
    customFilterViews.applyBuiltInTab(headerStore.activeTab)
    void loadBoard()
  }
})
</script>

<template>
  <div class="business-board-page">
    <div class="business-board-toolbar" aria-label="业务看板工具栏">
      <ListFilterPopover
        v-model="activeFilters"
        :fields="filterFields"
        save-view-enabled
        :save-view-loading="customFilterViews.saving.value"
        @apply="handleFilterApply"
        @reset="handleFilterReset"
        @save-view="handleSaveFilterView"
      />
      <TableToolbarButton
        class="refresh-button"
        :disabled="loading"
        aria-label="刷新业务看板"
        @click="loadBoard"
      >
        <RefreshCw class="refresh-icon" :class="{ spinning: loading }" aria-hidden="true" />
        刷新
      </TableToolbarButton>
    </div>

    <div
      v-if="ownerFilterError"
      class="business-board-inline-error"
      role="alert"
      aria-live="polite"
    >
      <AlertCircle class="error-icon" aria-hidden="true" />
      <span>{{ ownerFilterError }}</span>
      <TableToolbarButton
        class="business-board-inline-retry"
        :disabled="ownerFilterLoading"
        @click="fetchOwnerFilterOptions"
      >
        {{ ownerFilterLoading ? '重试中…' : '重试' }}
      </TableToolbarButton>
    </div>

    <BusinessJourneyBoardView
      :board="board"
      :loading="loading"
      :error-message="errorMessage"
      @retry="loadBoard"
      @legacy-customer-click="selectedCustomerId = $event"
    />

    <CustomerDetailSheet
      v-model:visible="sheetVisible"
      :customer-id="selectedCustomerId"
      @refresh="loadBoard"
      @view-customer="selectedCustomerId = $event"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.business-board-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: $wolf-page-padding-v2;
  gap: 16px;
  background: $wolf-bg-page-v2;
}

.business-board-toolbar,
.business-board-inline-error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.business-board-inline-error {
  min-height: 40px;
  padding: 0 $wolf-space-md-v2;
  border: 1px solid rgba($wolf-danger-v2, 0.18);
  border-radius: $wolf-radius-v2;
  color: $wolf-danger-text-v2;
  background: $wolf-danger-bg-v2;
  font-size: $wolf-font-size-caption-v2;
}

.business-board-inline-retry { margin-left: auto; }
.refresh-icon, .error-icon { width: 14px; height: 14px; }
.spinning { animation: business-board-spin 0.8s linear infinite; }

@keyframes business-board-spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .business-board-page {
    padding: $wolf-page-padding-mobile-v2;
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }
}
</style>
