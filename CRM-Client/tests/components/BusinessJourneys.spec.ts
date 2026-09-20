import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'

const journeyApiMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getBoard: vi.fn(),
  getOwnerFilterOptions: vi.fn(),
}))
const viewPreferenceMocks = vi.hoisted(() => ({
  listCustomViews: vi.fn(),
  createCustomView: vi.fn(),
  updateCustomView: vi.fn(),
  deleteCustomView: vi.fn(),
}))

vi.mock('@/api/dealJourney', () => ({
  dealJourneyApi: journeyApiMocks,
  default: journeyApiMocks,
}))
vi.mock('@/api/viewPreference', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/viewPreference')>()
  return {
    ...original,
    viewPreferenceApi: viewPreferenceMocks,
  }
})
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))
vi.mock('@/utils/logger', () => ({ logger: { error: vi.fn() } }))
vi.mock('vue-sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }))

import BusinessJourneys from '@/views/BusinessJourneys.vue'
import BusinessJourneyTableView from '@/components/business-journey/BusinessJourneyTableView.vue'
import BusinessJourneyBoardView from '@/components/business-journey/BusinessJourneyBoardView.vue'
import { useHeaderStore } from '@/stores/header'

const emptyList = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  total_pages: 0,
}
const emptyBoard = {
  columns: [],
  summary: {
    total_count: 0,
    total_amount: 0,
    active_count: 0,
    completed_count: 0,
    lost_count: 0,
  },
  truncated: false,
}
const customLostBoardViewResponse = {
  view_key: 'business-journeys.list',
  items: [{
    id: 7,
    team_id: 1,
    user_id: 2,
    view_key: 'business-journeys.list',
    scope: 'personal' as const,
    preference_key: 'custom:7',
    name: '流失看板',
    is_default: false,
    sort_order: null,
    config: {
      version: 1,
      columns: [],
      filters: [{ field: 'status', op: 'eq', value: 'LOST' }],
      sorts: [],
      display_mode: 'board' as const,
    },
    created_by: 2,
    updated_by: 2,
    created_time: '2026-09-20T10:00:00',
    updated_time: '2026-09-20T10:00:00',
  }],
}

const TableStub = defineComponent({
  name: 'BusinessJourneyTableView',
  emits: ['update:view-display-mode', 'row-click'],
  setup(_, { emit }) {
    return () => h('button', {
      'data-testid': 'table-projection',
      onClick: () => emit('update:view-display-mode', 'board'),
    }, 'table')
  },
})
const BoardStub = defineComponent({
  name: 'BusinessJourneyBoardView',
  props: {
    board: { type: Object, default: null },
    loading: { type: Boolean, default: false },
    errorMessage: { type: String, default: '' },
  },
  emits: ['retry', 'row-click'],
  setup() {
    return () => h('div', { 'data-testid': 'board-projection' }, 'board')
  },
})

function mountPage() {
  return mount(BusinessJourneys, {
    global: {
      plugins: [createPinia()],
      stubs: {
        BusinessJourneyTableView: TableStub,
        BusinessJourneyBoardView: BoardStub,
        BusinessJourneyListTools: true,
      },
    },
  })
}

describe('BusinessJourneys', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    journeyApiMocks.list.mockResolvedValue(emptyList)
    journeyApiMocks.getBoard.mockResolvedValue(emptyBoard)
    journeyApiMocks.getOwnerFilterOptions.mockResolvedValue({ data: [] })
    viewPreferenceMocks.listCustomViews.mockResolvedValue({ view_key: 'business-journeys.list', items: [] })
    viewPreferenceMocks.updateCustomView.mockImplementation(async (_key, _id, payload) => ({
      ...customLostBoardViewResponse.items[0],
      config: payload.config ?? customLostBoardViewResponse.items[0].config,
    }))
  })

  it('loads only the table projection initially', async () => {
    mountPage()
    await flushPromises()

    expect(journeyApiMocks.list).toHaveBeenCalledOnce()
    expect(journeyApiMocks.getBoard).not.toHaveBeenCalled()
  })

  it('switches to board through the existing view config event', async () => {
    const wrapper = mountPage()
    await flushPromises()

    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('update:view-display-mode', 'board')
    await flushPromises()

    expect(journeyApiMocks.getBoard).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(BusinessJourneyBoardView).exists()).toBe(true)
  })

  it('uses built-in tab at runtime and explicit filters for a saved board view', async () => {
    viewPreferenceMocks.listCustomViews.mockResolvedValue(customLostBoardViewResponse)
    const wrapper = mountPage()
    await flushPromises()
    const headerStore = useHeaderStore()

    headerStore.setActiveTab('active')
    await flushPromises()
    expect(journeyApiMocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'active' }))

    headerStore.setActiveTab('custom-view:7')
    await flushPromises()
    const params = journeyApiMocks.getBoard.mock.calls.at(-1)?.[0]
    expect(params?.tab).toBe('all')
    expect(JSON.parse(params?.filters ?? '[]')).toEqual([
      { field: 'status', op: 'eq', value: 'LOST' },
    ])
    expect(wrapper.findComponent(BusinessJourneyBoardView).exists()).toBe(true)
  })

  it('keeps table and board last-success state independent across stale failures', async () => {
    const firstList = { ...emptyList, items: [{ public_id: 'djy_table' }], total: 1, total_pages: 1 }
    journeyApiMocks.list.mockResolvedValueOnce(firstList)
    const wrapper = mountPage()
    await flushPromises()

    journeyApiMocks.getBoard.mockResolvedValueOnce({
      ...emptyBoard,
      columns: [{ key: 'active_progress', title: '积极推进', description: '', count: 0, amount: 0, cards: [] }],
    })
    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('update:view-display-mode', 'board')
    await flushPromises()

    journeyApiMocks.getBoard.mockRejectedValueOnce(new Error('offline'))
    const board = wrapper.getComponent(BusinessJourneyBoardView)
    board.vm.$emit('retry')
    await flushPromises()

    expect(wrapper.getComponent(BusinessJourneyBoardView).props('board')).not.toBeNull()
    expect(wrapper.getComponent(BusinessJourneyBoardView).props('errorMessage')).toContain('上次成功加载的数据')
  })
})
