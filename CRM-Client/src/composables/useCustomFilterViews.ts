import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { toast } from 'vue-sonner'
import { viewPreferenceApi, type ViewPreferenceConfig, type ViewPreferenceItem } from '@/api/viewPreference'
import type { TabItem } from '@/stores/header'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import { confirmDelete } from '@/utils/confirmDialog'
import { renameDialog } from '@/utils/renameDialog'

const CUSTOM_VIEW_TAB_PREFIX = 'custom-view:'

interface UseCustomFilterViewsOptions {
  viewKey: string
  activeTab: Ref<string>
  activeFilters: Ref<ListFilterCondition[]>
  activeSorts: Ref<ListSortCondition[]>
  refresh: () => void | Promise<void>
}

interface UseCustomFilterViewsReturn {
  customViews: Ref<ViewPreferenceItem[]>
  customViewTabs: ComputedRef<TabItem[]>
  loading: Ref<boolean>
  saving: Ref<boolean>
  loadCustomViews: () => Promise<void>
  saveAsCustomView: (filters: ListFilterCondition[]) => Promise<void>
  mergeTabs: (builtInTabs: TabItem[]) => TabItem[]
  applyCustomViewTab: (tabKey: string) => boolean
  applyBuiltInTab: (tabKey: string) => boolean
  updateActiveCustomViewConfig: () => Promise<void>
}

function buildTabKey(viewId: number): string {
  return `${CUSTOM_VIEW_TAB_PREFIX}${viewId}`
}

function buildViewConfig(filters: ListFilterCondition[], sorts: ListSortCondition[]): ViewPreferenceConfig {
  return {
    version: 1,
    columns: [],
    filters: filters as unknown as Record<string, unknown>[],
    sorts: sorts as unknown as Record<string, unknown>[]
  }
}

export function isCustomFilterViewTab(tabKey: string): boolean {
  return tabKey.startsWith(CUSTOM_VIEW_TAB_PREFIX)
}

export function useCustomFilterViews(options: UseCustomFilterViewsOptions): UseCustomFilterViewsReturn {
  const customViews = ref<ViewPreferenceItem[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const builtInViewSnapshot = ref<{
    filters: ListFilterCondition[]
    sorts: ListSortCondition[]
  } | null>(null)

  function buildCustomViewTab(view: ViewPreferenceItem): TabItem {
    return {
      key: buildTabKey(view.id),
      label: view.name ?? '未命名视图',
      isCustomView: true,
      customViewId: view.id,
      onMoveToFirst: (): void => {
        void moveCustomViewToFirst(view)
      },
      onRename: (): void => {
        void renameCustomView(view)
      },
      onDelete: (): void => {
        void deleteCustomView(view)
      }
    }
  }

  const customViewTabs = computed<TabItem[]>(() =>
    customViews.value.map((view) => buildCustomViewTab(view))
  )

  function findViewByTabKey(tabKey: string): ViewPreferenceItem | undefined {
    if (!isCustomFilterViewTab(tabKey)) return undefined
    const id = Number(tabKey.slice(CUSTOM_VIEW_TAB_PREFIX.length))
    if (!Number.isInteger(id)) return undefined
    return customViews.value.find((view) => view.id === id)
  }

  async function loadCustomViews(): Promise<void> {
    loading.value = true
    try {
      const response = await viewPreferenceApi.listCustomViews(options.viewKey, { skipErrorNotification: true })
      customViews.value = response.items
      const firstMovedView = response.items.find((view) => view.sort_order !== null)
      if (firstMovedView !== undefined && !isCustomFilterViewTab(options.activeTab.value)) {
        applyCustomViewTab(buildTabKey(firstMovedView.id))
      }
    } catch {
      toast.error('自定义视图加载失败')
    } finally {
      loading.value = false
    }
  }

  async function saveAsCustomView(filters: ListFilterCondition[]): Promise<void> {
    if (filters.length === 0) return

    saving.value = true
    try {
      const view = await viewPreferenceApi.createCustomView(options.viewKey, {
        config: buildViewConfig(filters, options.activeSorts.value)
      })
      customViews.value = [...customViews.value, view]
      options.activeFilters.value = (view.config.filters ?? []) as unknown as ListFilterCondition[]
      options.activeSorts.value = (view.config.sorts ?? []) as unknown as ListSortCondition[]
      options.activeTab.value = buildTabKey(view.id)
      await options.refresh()
      toast.success('已另存为视图')
    } catch {
      toast.error('另存为视图失败')
    } finally {
      saving.value = false
    }
  }

  function mergeTabs(builtInTabs: TabItem[]): TabItem[] {
    const pinnedTabs = customViews.value
      .filter((view) => view.sort_order !== null)
      .map((view) => buildCustomViewTab(view))
    const normalTabs = customViews.value
      .filter((view) => view.sort_order === null)
      .map((view) => buildCustomViewTab(view))

    return [...pinnedTabs, ...builtInTabs, ...normalTabs]
  }

  async function updateActiveCustomViewConfig(): Promise<void> {
    const view = findViewByTabKey(options.activeTab.value)
    if (!view) return

    try {
      const updated = await viewPreferenceApi.updateCustomView(options.viewKey, view.id, {
        config: buildViewConfig(options.activeFilters.value, options.activeSorts.value)
      })
      customViews.value = customViews.value.map((item) => item.id === updated.id ? updated : item)
    } catch {
      toast.error('自定义视图更新失败')
    }
  }

  function applyCustomViewTab(tabKey: string): boolean {
    const view = findViewByTabKey(tabKey)
    if (!view) return false

    if (!isCustomFilterViewTab(options.activeTab.value)) {
      builtInViewSnapshot.value = {
        filters: [...options.activeFilters.value],
        sorts: [...options.activeSorts.value],
      }
    }
    options.activeTab.value = tabKey
    options.activeFilters.value = (view.config.filters ?? []) as unknown as ListFilterCondition[]
    options.activeSorts.value = (view.config.sorts ?? []) as unknown as ListSortCondition[]
    void options.refresh()
    return true
  }

  function applyBuiltInTab(tabKey: string): boolean {
    if (isCustomFilterViewTab(tabKey)) return false

    const wasCustomViewTab = isCustomFilterViewTab(options.activeTab.value)
    options.activeTab.value = tabKey
    if (wasCustomViewTab) {
      options.activeFilters.value = builtInViewSnapshot.value?.filters ?? []
      options.activeSorts.value = builtInViewSnapshot.value?.sorts ?? []
      builtInViewSnapshot.value = null
    }
    return wasCustomViewTab
  }

  async function moveCustomViewToFirst(view: ViewPreferenceItem): Promise<void> {
    const sortOrders = customViews.value
      .map((item) => item.sort_order)
      .filter((sortOrder): sortOrder is number => sortOrder !== null)
    const nextSortOrder = Math.min(0, ...sortOrders) - 1

    try {
      const updated = await viewPreferenceApi.updateCustomView(options.viewKey, view.id, {
        sort_order: nextSortOrder,
      })
      customViews.value = customViews.value
        .map((item) => item.id === updated.id ? updated : item)
        .sort((left, right) => {
          const leftPinned = left.sort_order !== null
          const rightPinned = right.sort_order !== null
          if (leftPinned !== rightPinned) return leftPinned ? -1 : 1
          if (left.sort_order !== null && right.sort_order !== null && left.sort_order !== right.sort_order) {
            return left.sort_order - right.sort_order
          }
          return left.id - right.id
        })
      toast.success('已移到最前')
    } catch {
      toast.error('视图排序更新失败')
    }
  }

  async function renameCustomView(view: ViewPreferenceItem): Promise<void> {
    const nextName = await renameDialog({
      title: '重命名视图',
      initialName: view.name ?? '',
      maxLength: 100,
    })
    const normalizedName = nextName?.trim()
    if (normalizedName === undefined || normalizedName === '' || normalizedName === view.name) return

    try {
      const updated = await viewPreferenceApi.updateCustomView(options.viewKey, view.id, { name: normalizedName })
      customViews.value = customViews.value.map((item) => item.id === updated.id ? updated : item)
      toast.success('视图已重命名')
    } catch {
      toast.error('视图重命名失败')
    }
  }

  async function deleteCustomView(view: ViewPreferenceItem): Promise<void> {
    const confirmed = await confirmDelete(view.name ?? '该视图')
    if (!confirmed) return

    try {
      await viewPreferenceApi.deleteCustomView(options.viewKey, view.id)
      customViews.value = customViews.value.filter((item) => item.id !== view.id)
      if (options.activeTab.value === buildTabKey(view.id)) {
        options.activeTab.value = 'all'
        options.activeFilters.value = []
        options.activeSorts.value = []
        await options.refresh()
      }
      toast.success('视图已删除')
    } catch {
      toast.error('视图删除失败')
    }
  }

  return {
    customViews,
    customViewTabs,
    loading,
    saving,
    loadCustomViews,
    saveAsCustomView,
    mergeTabs,
    applyCustomViewTab,
    applyBuiltInTab,
    updateActiveCustomViewConfig,
  }
}
