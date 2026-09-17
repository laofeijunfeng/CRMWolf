import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import CustomerDealJourneyHoverCard from '@/components/customer/CustomerDealJourneyHoverCard.vue'
import type { DealJourney } from '@/api/dealJourney'

const dealJourneyApi = vi.hoisted(() => ({
  listByCustomer: vi.fn(),
}))

const opportunityApi = vi.hoisted(() => ({
  getOpportunities: vi.fn(),
}))

vi.mock('@/api/dealJourney', () => ({ dealJourneyApi, default: dealJourneyApi }))
vi.mock('@/api/opportunity', () => ({ opportunityApi }))

vi.mock('@/components/crmwolf', () => ({
  AmountText: defineComponent({
    name: 'AmountText',
    props: { value: [Number, String], size: String },
    setup: (props) => () => h('span', `金额 ${String(props.value)}`),
  }),
  Badge: defineComponent({
    name: 'Badge',
    setup: (_, { attrs, slots }) => () => h('span', attrs, slots.default?.()),
  }),
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String, disabled: Boolean },
    setup: (props, { attrs, slots }) => () => h('button', {
      ...attrs,
      type: props.type ?? 'button',
      disabled: props.disabled,
    }, slots.default?.()),
  }),
  HoverInfo: defineComponent({
    name: 'HoverInfo',
    props: { open: Boolean },
    emits: ['update:open'],
    setup: (props, { emit, slots }) => () => h('div', {
      'data-testid': 'hover-info',
      'data-open': String(props.open),
    }, [
      h('button', {
        type: 'button',
        'data-testid': 'open-hover-card',
        onClick: () => emit('update:open', true),
      }, '打开浮窗'),
      slots.trigger?.(),
      slots.default?.(),
    ]),
  }),
  Progress: defineComponent({
    name: 'Progress',
    props: { modelValue: Number },
    setup: (props, { attrs }) => () => h('div', { ...attrs, 'data-progress': String(props.modelValue) }),
  }),
  DataViewStatePanel: defineComponent({
    name: 'DataViewStatePanel',
    inheritAttrs: false,
    props: {
      state: { type: String, required: true },
      errorTitle: { type: String, default: '' },
      errorDescription: { type: String, default: '' },
      emptyTitle: { type: String, default: '' },
      emptyDescription: { type: String, default: '' },
    },
    setup: (props, { attrs, slots }) => () => {
      if (props.state === 'loading') return h('div', attrs, slots.loading?.())
      if (props.state === 'error') return h('div', attrs, [h('span', props.errorTitle), h('span', props.errorDescription), slots['error-action']?.()])
      if (props.state === 'empty') return h('div', attrs, [h('span', props.emptyTitle), h('span', props.emptyDescription)])
      return h('div', attrs, slots.default?.())
    },
  }),
  Skeleton: defineComponent({ name: 'Skeleton', setup: () => () => h('div') }),
}))

vi.mock('@/components/ui/empty', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  })

  return {
    Empty: passthrough('Empty'),
    EmptyDescription: passthrough('EmptyDescription'),
    EmptyHeader: passthrough('EmptyHeader'),
    EmptyTitle: passthrough('EmptyTitle'),
  }
})
vi.mock('@/components/ui/separator', () => ({
  Separator: defineComponent({ name: 'Separator', setup: () => () => h('hr') }),
}))
vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: defineComponent({
    name: 'ScrollArea',
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  }),
}))

const JOURNEY_IDS = {
  first: 'djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  second: 'djy_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
  lost: 'djy_cccccccccccccccccccccccccccccccc',
  third: 'djy_dddddddddddddddddddddddddddddddd',
  fourth: 'djy_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
  archived: 'djy_ffffffffffffffffffffffffffffffff',
  completed: 'djy_11111111111111111111111111111111',
} as const

const journeyFixture = (overrides: Partial<DealJourney> = {}): DealJourney => ({
  id: JOURNEY_IDS.first,
  public_id: JOURNEY_IDS.first,
  name: '企业 CRM 升级项目',
  status: 'ACTIVE',
  current_board_stage: 'closing_soon',
  current_board_stage_label: '即将签约',
  amount: 320000,
  purchase_type: 'NEW',
  started_at: '2026-07-15T00:00:00',
  closed_at: null,
  last_event_at: '2026-07-15T00:00:00',
  primary_opportunity: {
    public_id: 'opp_test_88',
    opportunity_name: '企业 CRM 升级项目',
    status: 0,
    approval_phase: 'approved',
    win_probability: 65,
    expected_closing_date: '2026-08-30',
    product_name: 'CRM',
  },
  ...overrides,
})

const mountHoverCard = () => mount(CustomerDealJourneyHoverCard, {
  props: {
    customerId: 'cus_test_19',
    customerName: '上海测试客户',
  },
  slots: {
    trigger: '<span class="link-text" data-testid="customer-deal-journey-trigger">上海测试客户</span>',
  },
})

const openHoverCard = async (wrapper: VueWrapper): Promise<void> => {
  await wrapper.get('[data-testid="open-hover-card"]').trigger('click')
  await flushPromises()
}

describe('CustomerDealJourneyHoverCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the customer-list trigger supplied by the parent without altering its styles', () => {
    const wrapper = mountHoverCard()

    const trigger = wrapper.get('[data-testid="customer-deal-journey-trigger"]')
    expect(trigger.classes()).toContain('link-text')
    expect(trigger.text()).toBe('上海测试客户')
    expect(wrapper.find('button[data-testid="customer-deal-journey-trigger"]').exists()).toBe(false)
  })

  it('loads deal journeys on first open and previews name, amount, progress, and stage badge', async () => {
    dealJourneyApi.listByCustomer.mockResolvedValue([
      journeyFixture(),
      journeyFixture({
        id: JOURNEY_IDS.second,
        public_id: JOURNEY_IDS.second,
        name: '续约扩容',
        current_board_stage: 'active_progress',
        current_board_stage_label: '持续推进',
        amount: 180000,
      }),
      journeyFixture({
        id: JOURNEY_IDS.lost,
        public_id: JOURNEY_IDS.lost,
        name: '已输单项目',
        status: 'LOST',
        current_board_stage: 'lost',
        current_board_stage_label: '已输单',
      }),
      journeyFixture({
        id: JOURNEY_IDS.archived,
        public_id: JOURNEY_IDS.archived,
        name: '已归档项目',
        status: 'ARCHIVED',
      }),
      journeyFixture({
        id: JOURNEY_IDS.third,
        public_id: JOURNEY_IDS.third,
        name: '增购席位',
        current_board_stage: 'contract_processing',
        current_board_stage_label: '签约中',
        amount: 90000,
      }),
      journeyFixture({
        id: JOURNEY_IDS.fourth,
        public_id: JOURNEY_IDS.fourth,
        name: '第四条不应预览',
        current_board_stage: 'early_communication',
        current_board_stage_label: '初期交流',
        amount: 10000,
      }),
    ])

    const wrapper = mountHoverCard()
    await openHoverCard(wrapper)

    expect(dealJourneyApi.listByCustomer).toHaveBeenCalledWith('cus_test_19')
    expect(opportunityApi.getOpportunities).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="customer-deal-journey-total"]').text()).toBe('共 4 个')
    expect(wrapper.text()).toContain('企业 CRM 升级项目')
    expect(wrapper.text()).toContain('CRM')
    expect(wrapper.text()).toContain('查看全部业务旅程')
    expect(wrapper.text()).not.toContain('赢率')
    expect(wrapper.text()).not.toContain('已输单项目')
    expect(wrapper.text()).not.toContain('已归档项目')
    expect(wrapper.text()).not.toContain('第四条不应预览')
    expect(wrapper.find(`[data-testid="customer-deal-journey-${JOURNEY_IDS.lost}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="customer-deal-journey-${JOURNEY_IDS.archived}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="customer-deal-journey-${JOURNEY_IDS.fourth}"]`).exists()).toBe(false)
    expect(wrapper.findAll('button[data-testid^="customer-deal-journey-djy_"]')).toHaveLength(3)

    const item = wrapper.get(`[data-testid="customer-deal-journey-${JOURNEY_IDS.first}"]`)
    const html = item.html()
    expect(html.indexOf('企业 CRM 升级项目')).toBeLessThan(html.indexOf('金额 320000'))
    expect(html.indexOf('金额 320000')).toBeLessThan(html.indexOf('data-progress'))
    expect(html.indexOf('data-progress')).toBeLessThan(html.indexOf('即将签约'))
    expect(item.get('[data-progress="43"]').exists()).toBe(true)
    expect(wrapper.get(`[data-testid="customer-deal-journey-stage-${JOURNEY_IDS.first}"]`).text()).toBe('即将签约')

    await item.trigger('click')
    expect(wrapper.emitted('select-journey')).toEqual([[JOURNEY_IDS.first]])
    expect(wrapper.get('[data-testid="hover-info"]').attributes('data-open')).toBe('false')
  })

  it('emits view-all from the footer without selecting a journey', async () => {
    dealJourneyApi.listByCustomer.mockResolvedValue([journeyFixture()])

    const wrapper = mountHoverCard()
    await openHoverCard(wrapper)

    const footerButtons = wrapper.findAll('button').filter((button) => button.text().includes('查看全部业务旅程'))
    expect(footerButtons).toHaveLength(1)
    await footerButtons[0].trigger('click')
    expect(wrapper.emitted('view-all')).toEqual([[]])
    expect(wrapper.emitted('select-journey')).toBeUndefined()
  })

  it('shows an empty state when the customer has no previewable journeys', async () => {
    dealJourneyApi.listByCustomer.mockResolvedValue([
      journeyFixture({
        id: JOURNEY_IDS.lost,
        public_id: JOURNEY_IDS.lost,
        status: 'LOST',
        current_board_stage: 'lost',
      }),
    ])

    const wrapper = mountHoverCard()
    await openHoverCard(wrapper)

    expect(opportunityApi.getOpportunities).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无业务旅程')
    expect(wrapper.find(`[data-testid="customer-deal-journey-${JOURNEY_IDS.lost}"]`).exists()).toBe(false)
  })

  it('sets completed journey progress aria-label to 100%', async () => {
    dealJourneyApi.listByCustomer.mockResolvedValue([
      journeyFixture({
        id: JOURNEY_IDS.completed,
        public_id: JOURNEY_IDS.completed,
        name: '已完成项目',
        status: 'COMPLETED',
        current_board_stage: 'completed',
        current_board_stage_label: '已完成',
        amount: 50000,
      }),
    ])

    const wrapper = mountHoverCard()
    await openHoverCard(wrapper)

    const progress = wrapper.get('[data-progress="100"]')
    expect(progress.attributes('aria-label')).toBe('已完成项目 旅程进度 100%')
    expect(wrapper.text()).not.toContain('赢率')
  })

  it('does not repeat the request after the journeys have loaded', async () => {
    dealJourneyApi.listByCustomer.mockResolvedValue([])

    const wrapper = mountHoverCard()
    await openHoverCard(wrapper)
    await openHoverCard(wrapper)

    expect(dealJourneyApi.listByCustomer).toHaveBeenCalledTimes(1)
    expect(opportunityApi.getOpportunities).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无业务旅程')
  })
})
