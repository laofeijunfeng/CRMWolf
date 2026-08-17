import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import CustomerOpportunityHoverCard from '@/components/customer/CustomerOpportunityHoverCard.vue'
import { OpportunityStatus, type OpportunityListResponse } from '@/api/opportunity'

const opportunityApi = vi.hoisted(() => ({
  getOpportunities: vi.fn(),
}))

vi.mock('@/api/opportunity', () => ({ opportunityApi, OpportunityStatus: { LOST: 2 } }))

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

const opportunityFixture = (id: string, overrides: Partial<OpportunityListResponse> = {}): OpportunityListResponse => ({
  id,
  public_id: `public_${id}`,
  opportunity_number: `NO-${id}`,
  opportunity_name: '企业 CRM 升级项目',
  customer_id: 'cus_test_19',
  procurement_method_id: null,
  procurement_method_info: null,
  total_amount: 320000,
  user_count: 20,
  unit_price: 16000,
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  purchase_type: 'NEW',
  decision_maker_count: 1,
  expected_closing_date: '2026-08-30',
  stage_id: 1,
  win_probability: 65,
  owner_id: '9',
  creator_id: '9',
  stage: null,
  stage_info: { id: 1, stage_name: '方案沟通', win_probability: 65, is_default: 0 },
  status: 0,
  approval_phase: 'approved',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  ...overrides,
})

describe('CustomerOpportunityHoverCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the customer-list trigger supplied by the parent without altering its styles', () => {
    const wrapper = mount(CustomerOpportunityHoverCard, {
      props: {
        customerId: 'cus_test_19',
        customerName: '上海测试客户',
      },
      slots: {
        trigger: '<span class="link-text" data-testid="customer-opportunity-trigger">上海测试客户</span>',
      },
    })

    const trigger = wrapper.get('[data-testid="customer-opportunity-trigger"]')
    expect(trigger.classes()).toContain('link-text')
    expect(trigger.text()).toBe('上海测试客户')
    expect(wrapper.find('button[data-testid="customer-opportunity-trigger"]').exists()).toBe(false)
  })

  it('loads the customer opportunities on first hover-card open and emits the selected opportunity', async () => {
    opportunityApi.getOpportunities.mockResolvedValue({
      items: [
        opportunityFixture('opp_test_88'),
        opportunityFixture('opp_test_87'),
        opportunityFixture('opp_test_86', { status: OpportunityStatus.LOST }),
        opportunityFixture('opp_test_85'),
      ],
      total: 4,
      page: 1,
      page_size: 3,
      total_pages: 2,
    })

    const wrapper = mount(CustomerOpportunityHoverCard, {
      props: {
        customerId: 'cus_test_19',
        customerName: '上海测试客户',
      },
    })

    await wrapper.get('[data-testid="open-hover-card"]').trigger('click')
    await flushPromises()

    expect(opportunityApi.getOpportunities).toHaveBeenCalledWith({
      customer_id: 'cus_test_19',
      limit: 3,
      status_exclude: OpportunityStatus.LOST,
      order_by: 'created_time',
      order_dir: 'desc',
    })
    expect(wrapper.text()).toContain('企业 CRM 升级项目')
    expect(wrapper.get('[data-testid="customer-opportunity-total"]').text()).toBe('共 4 个')
    expect(wrapper.text()).toContain('赢率 65%')
    expect(wrapper.get('[data-testid="customer-opportunity-stage-opp_test_88"]').text()).toBe('方案沟通')
    expect(wrapper.get('[data-progress="65"]').exists()).toBe(true)
    expect(wrapper.findAll('button[data-testid^="customer-opportunity-"]')).toHaveLength(3)
    expect(wrapper.find('[data-testid="customer-opportunity-opp_test_86"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="customer-opportunity-opp_test_85"]').exists()).toBe(true)

    const opportunityItem = wrapper.get('[data-testid="customer-opportunity-opp_test_88"]')
    expect(opportunityItem.classes()).not.toContain('min-h-[152px]')
    expect(opportunityItem.classes()).toContain('hover:bg-sidebar-accent')
    expect(wrapper.findComponent({ name: 'AmountText' }).props('size')).toBe('lg')

    await opportunityItem.trigger('click')
    expect(wrapper.emitted('select-opportunity')).toEqual([['opp_test_88']])
    expect(wrapper.get('[data-testid="hover-info"]').attributes('data-open')).toBe('false')
  })

  it('does not repeat the request after the opportunities have loaded', async () => {
    opportunityApi.getOpportunities.mockResolvedValue([])

    const wrapper = mount(CustomerOpportunityHoverCard, {
      props: {
        customerId: 'cus_test_19',
        customerName: '上海测试客户',
      },
    })

    await wrapper.get('[data-testid="open-hover-card"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="open-hover-card"]').trigger('click')
    await flushPromises()

    expect(opportunityApi.getOpportunities).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('暂无商机')
  })
})
