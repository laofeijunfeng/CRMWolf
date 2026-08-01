import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useCustomFilterViews } from '../useCustomFilterViews'
import { viewPreferenceApi } from '@/api/viewPreference'
import type { ListFilterCondition } from '@/components/crmwolf/listFilterTypes'
import type { ListSortCondition } from '@/components/crmwolf/listSortTypes'
import type { ViewPreferenceItem } from '@/api/viewPreference'

vi.mock('vue-sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDelete: vi.fn(),
}))

vi.mock('@/utils/renameDialog', () => ({
  renameDialog: vi.fn(),
}))

vi.mock('@/api/viewPreference', () => ({
  viewPreferenceApi: {
    listCustomViews: vi.fn(),
    createCustomView: vi.fn(),
    updateCustomView: vi.fn(),
    deleteCustomView: vi.fn(),
  },
}))

const customView = {
  id: 1,
  team_id: 1,
  user_id: 1,
  view_key: 'customers.list',
  scope: 'personal',
  preference_key: 'custom:1',
  name: '视图 1',
  is_default: false,
  sort_order: null,
  config: {
    version: 1,
    columns: [],
    filters: [{ field: 'account_name', operator: 'contains', value: '测试客户' }],
    sorts: [{ field: 'created_time', order: 'desc' }],
  },
  created_by: 1,
  updated_by: 1,
  created_time: '2026-08-01T00:00:00Z',
  updated_time: '2026-08-01T00:00:00Z',
} satisfies ViewPreferenceItem

describe('useCustomFilterViews', () => {
  it('applies the first moved custom view after loading custom views', async () => {
    const activeTab = ref('all')
    const activeFilters = ref<ListFilterCondition[]>([])
    const activeSorts = ref<ListSortCondition[]>([])
    const refresh = vi.fn()
    const customFilterViews = useCustomFilterViews({
      viewKey: 'customers.list',
      activeTab,
      activeFilters,
      activeSorts,
      refresh,
    })
    vi.mocked(viewPreferenceApi.listCustomViews).mockResolvedValue({
      view_key: 'customers.list',
      items: [
        { ...customView, id: 2, name: '视图 2', sort_order: -1 },
        customView,
      ],
    })

    await customFilterViews.loadCustomViews()

    expect(activeTab.value).toBe('custom-view:2')
    expect(activeFilters.value).toEqual(customView.config.filters)
    expect(activeSorts.value).toEqual(customView.config.sorts)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('restores built-in tab filters and sorts when switching back from a custom view tab', () => {
    const activeTab = ref('all')
    const builtInFilters: ListFilterCondition[] = [{ field: 'owner_id', op: 'eq', value: 1 }]
    const builtInSorts: ListSortCondition[] = [{ field: 'updated_time', direction: 'desc' }]
    const activeFilters = ref<ListFilterCondition[]>(builtInFilters)
    const activeSorts = ref<ListSortCondition[]>(builtInSorts)
    const refresh = vi.fn()

    const customFilterViews = useCustomFilterViews({
      viewKey: 'customers.list',
      activeTab,
      activeFilters,
      activeSorts,
      refresh,
    })
    customFilterViews.customViews.value = [customView]

    expect(customFilterViews.applyCustomViewTab('custom-view:1')).toBe(true)
    expect(activeTab.value).toBe('custom-view:1')
    expect(activeFilters.value).toHaveLength(1)
    expect(activeSorts.value).toHaveLength(1)

    expect(customFilterViews.applyBuiltInTab('public')).toBe(true)
    expect(activeTab.value).toBe('public')
    expect(activeFilters.value).toEqual(builtInFilters)
    expect(activeSorts.value).toEqual(builtInSorts)
  })

  it('moves a custom view before built-in tabs', async () => {
    const activeTab = ref('all')
    const activeFilters = ref<ListFilterCondition[]>([])
    const activeSorts = ref<ListSortCondition[]>([])
    const refresh = vi.fn()
    const customFilterViews = useCustomFilterViews({
      viewKey: 'customers.list',
      activeTab,
      activeFilters,
      activeSorts,
      refresh,
    })
    const secondView = { ...customView, id: 2, name: '视图 2' }
    customFilterViews.customViews.value = [customView, secondView]
    vi.mocked(viewPreferenceApi.updateCustomView).mockResolvedValue({
      ...secondView,
      sort_order: -1,
    })

    customFilterViews.customViewTabs.value[1]?.onMoveToFirst?.()
    await Promise.resolve()

    expect(viewPreferenceApi.updateCustomView).toHaveBeenCalledWith('customers.list', 2, { sort_order: -1 })
    expect(customFilterViews.mergeTabs([
      { key: 'all', label: '所有客户' },
      { key: 'public', label: '公海客户' },
    ]).map((tab) => tab.label)).toEqual(['视图 2', '所有客户', '公海客户', '视图 1'])
  })
})
