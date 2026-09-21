import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'

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
const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
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
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerMocks.push }),
}))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))
vi.mock('@/utils/logger', () => ({ logger: { error: vi.fn() } }))
vi.mock('vue-sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }))
vi.mock('@/views/DealJourneyDetailSheet.vue', () => ({
  default: defineComponent({
    name: 'DealJourneyDetailSheet',
    props: {
      customerId: String,
      customerName: String,
      journeyId: String,
      journeyName: String,
      visible: Boolean,
    },
    emits: ['update:visible', 'refresh', 'view-customer'],
    setup: props => () => h('div', {
      'data-testid': 'journey-detail-sheet',
      'data-visible': String(props.visible),
    }),
  }),
}))
vi.mock('@/views/CustomerDetailSheet.vue', () => ({
  default: defineComponent({
    name: 'CustomerDetailSheet',
    props: {
      customerId: String,
      visible: Boolean,
    },
    emits: ['update:visible', 'refresh', 'view-customer'],
    setup: props => () => h('div', {
      'data-testid': 'customer-detail-sheet',
      'data-visible': String(props.visible),
      'data-customer-id': props.customerId ?? '',
    }),
  }),
}))

import BusinessJourneys from '@/views/BusinessJourneys.vue'
import BusinessJourneyTableView from '@/components/business-journey/BusinessJourneyTableView.vue'
import BusinessJourneyBoardView from '@/components/business-journey/BusinessJourneyBoardView.vue'
import { useHeaderStore } from '@/stores/header'
import DealJourneyDetailSheet from '@/views/DealJourneyDetailSheet.vue'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'

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
const customLostTableViewResponse = {
  ...customLostBoardViewResponse,
  items: [{
    ...customLostBoardViewResponse.items[0],
    config: {
      ...customLostBoardViewResponse.items[0].config,
      display_mode: 'table' as const,
    },
  }],
}


const listItemFixture = {
  customer_id: 'cus_table',
  customer_name: '表格客户',
  public_id: 'djy_table',
  name: '华东续约旅程',
}

const boardItemFixture = {
  customerId: 'cus_board',
  journeyPublicId: 'djy_board',
}

const boardCardFixture = {
  public_id: 'djy_board',
  journey_name: '华南新签旅程',
  customer_id: 'cus_board',
  customer_name: '看板客户',
  owner: null,
  status: 'ACTIVE',
  current_board_stage: 'active_progress',
  amount: 1000,
  contract_summary: { count: 0, signed_count: 0, amount: 0 },
  payment_summary: { plan_count: 0, record_count: 0, planned_amount: 0, paid_amount: 0, remaining_amount: 0 },
  invoice_summary: { application_count: 0, issued_count: 0, applied_amount: 0, issued_amount: 0 },
}

const TableStub = defineComponent({
  name: 'BusinessJourneyTableView',
  props: {
    viewApplyError: { type: Object, default: null },
  },
  emits: ['update:view-display-mode', 'row-click', 'retry-view-apply'],
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
        DealJourneyDetailSheet: false,
        CustomerDetailSheet: false,
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
  it('starts the board projection while custom-view persistence is pending', async () => {
    viewPreferenceMocks.listCustomViews.mockResolvedValue(customLostTableViewResponse)
    const wrapper = mountPage()
    await flushPromises()
    const headerStore = useHeaderStore()
    headerStore.setActiveTab('custom-view:7')
    await flushPromises()

    let resolvePersistence: (value: typeof customLostBoardViewResponse.items[0]) => void = () => undefined
    const persistence = new Promise<typeof customLostBoardViewResponse.items[0]>((resolve) => {
      resolvePersistence = resolve
    })
    let resolveBoard: (value: typeof emptyBoard) => void = () => undefined
    const boardResponse = new Promise<typeof emptyBoard>((resolve) => {
      resolveBoard = resolve
    })
    viewPreferenceMocks.updateCustomView.mockReturnValueOnce(persistence)
    journeyApiMocks.getBoard.mockReturnValueOnce(boardResponse)

    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('update:view-display-mode', 'board')
    await wrapper.vm.$nextTick()

    expect(viewPreferenceMocks.updateCustomView).toHaveBeenCalledOnce()
    expect(journeyApiMocks.getBoard).toHaveBeenCalledOnce()
    expect(wrapper.getComponent(BusinessJourneyBoardView).props('loading')).toBe(true)

    resolvePersistence({
      ...customLostBoardViewResponse.items[0],
      config: {
        ...customLostBoardViewResponse.items[0].config,
        display_mode: 'board',
      },
    })
    resolveBoard(emptyBoard)
    await flushPromises()

    expect(journeyApiMocks.getBoard).toHaveBeenCalledOnce()
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

  it('keeps a failed custom view apply stable until explicit retry', async () => {
    viewPreferenceMocks.listCustomViews.mockResolvedValue(customLostTableViewResponse)
    const wrapper = mountPage()
    await flushPromises()
    journeyApiMocks.list.mockClear()
    const headerStore = useHeaderStore()
    journeyApiMocks.list.mockRejectedValueOnce(new Error('offline'))

    // Simulate the stale header value being replayed after the composable rolls
    // the page state back. The watcher must consume it instead of applying again.
    headerStore.setActiveTab('custom-view:7')
    await flushPromises()
    headerStore.setActiveTab('custom-view:7')
    await flushPromises()

    expect(journeyApiMocks.list).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(BusinessJourneyTableView).exists()).toBe(true)
    expect(wrapper.getComponent(BusinessJourneyTableView).props('viewApplyError')).toMatchObject({
      title: '视图应用失败',
      retryable: true,
    })
    expect(headerStore.activeTab).toBe('all')

    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('retry-view-apply')
    await flushPromises()

    expect(journeyApiMocks.list).toHaveBeenCalledTimes(2)
    expect(headerStore.activeTab).toBe('custom-view:7')
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

  it('opens from table and restores the originating focus after close', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('row-click', {
      customerId: listItemFixture.customer_id,
      journeyPublicId: listItemFixture.public_id,
    })
    await nextTick()

    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: listItemFixture.customer_id,
      journeyId: listItemFixture.public_id,
      visible: true,
    })

    wrapper.getComponent(DealJourneyDetailSheet).vm.$emit('update:visible', false)
    await nextTick()
    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: null,
      journeyId: null,
      visible: false,
    })
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })

  it('passes the journey name from the table row into the sheet and clears it on close', async () => {
    journeyApiMocks.list.mockResolvedValueOnce({
      ...emptyList,
      items: [listItemFixture],
      total: 1,
      total_pages: 1,
    })
    const wrapper = mountPage()
    await flushPromises()

    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('row-click', {
      customerId: listItemFixture.customer_id,
      journeyPublicId: listItemFixture.public_id,
    })
    await nextTick()

    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: listItemFixture.customer_id,
      customerName: listItemFixture.customer_name,
      journeyId: listItemFixture.public_id,
      journeyName: listItemFixture.name,
      visible: true,
    })
    expect(routerMocks.push).not.toHaveBeenCalled()

    wrapper.getComponent(DealJourneyDetailSheet).vm.$emit('update:visible', false)
    await nextTick()

    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: null,
      customerName: undefined,
      journeyId: null,
      journeyName: undefined,
      visible: false,
    })
  })

  it('drills from journey detail into the customer sheet and restores the originating focus', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()

    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('row-click', {
      customerId: listItemFixture.customer_id,
      journeyPublicId: listItemFixture.public_id,
    })
    await nextTick()
    wrapper.getComponent(DealJourneyDetailSheet).vm.$emit('view-customer', listItemFixture.customer_id)
    await nextTick()

    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: null,
      journeyId: null,
      visible: false,
    })
    expect(wrapper.getComponent(CustomerDetailSheet).props()).toMatchObject({
      customerId: listItemFixture.customer_id,
      visible: true,
    })
    expect(routerMocks.push).not.toHaveBeenCalled()

    wrapper.getComponent(CustomerDetailSheet).vm.$emit('update:visible', false)
    await nextTick()
    await nextTick()

    expect(wrapper.getComponent(CustomerDetailSheet).props()).toMatchObject({
      customerId: null,
      visible: false,
    })
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })

  it('opens the same independent sheet from the board public-id payload', async () => {
    const wrapper = mountPage()
    await flushPromises()
    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('update:view-display-mode', 'board')
    await flushPromises()

    wrapper.getComponent(BusinessJourneyBoardView).vm.$emit('row-click', boardItemFixture)
    await nextTick()

    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: boardItemFixture.customerId,
      journeyId: boardItemFixture.journeyPublicId,
      visible: true,
    })
  })

  it('resolves the journey name from the board card public-id payload', async () => {
    journeyApiMocks.getBoard.mockResolvedValueOnce({
      ...emptyBoard,
      columns: [{
        key: 'active_progress',
        title: '积极推进',
        description: '',
        count: 1,
        amount: 1000,
        cards: [boardCardFixture],
      }],
    })
    const wrapper = mountPage()
    await flushPromises()
    wrapper.getComponent(BusinessJourneyTableView).vm.$emit('update:view-display-mode', 'board')
    await flushPromises()

    wrapper.getComponent(BusinessJourneyBoardView).vm.$emit('row-click', boardItemFixture)
    await nextTick()

    expect(wrapper.getComponent(DealJourneyDetailSheet).props()).toMatchObject({
      customerId: boardItemFixture.customerId,
      customerName: boardCardFixture.customer_name,
      journeyId: boardItemFixture.journeyPublicId,
      journeyName: boardCardFixture.journey_name,
      visible: true,
    })
    expect(routerMocks.push).not.toHaveBeenCalled()
  })
})
