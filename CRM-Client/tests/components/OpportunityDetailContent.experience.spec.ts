import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import { LicenseType, OpportunityStatus, PurchaseType, type Opportunity } from '@/api/opportunity'

const opportunityApi = vi.hoisted(() => ({
  getOpportunity: vi.fn(),
  markAsWon: vi.fn(),
  markAsLost: vi.fn(),
}))
const contractApi = vi.hoisted(() => ({
  getContractByOpportunity: vi.fn(),
}))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('vue-router', () => ({
  RouterLink: defineComponent({
    name: 'RouterLink',
    props: { to: [String, Object] },
    setup: (_, { slots }) => () => h('a', slots.default?.()),
  }),
}))
vi.mock('@/api/opportunity', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/opportunity')>()
  return {
    ...actual,
    opportunityApi,
  }
})
vi.mock('@/api/contract', () => ({ default: contractApi }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => ({ hasAnyPermission: () => true }),
}))

vi.mock('@/components/ui/card', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Card: passthrough('Card'),
    CardHeader: passthrough('CardHeader'),
    CardContent: passthrough('CardContent'),
  }
})
vi.mock('@/components/ui/badge', () => ({ Badge: defineComponent({ name: 'Badge', setup: (_, { slots }) => () => h('span', slots.default?.()) }) }))
vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String, disabled: Boolean },
    setup: (props, { slots, attrs }) => () => h('button', { ...attrs, type: props.type ?? 'button', disabled: props.disabled }, slots.default?.()),
  }),
}))
vi.mock('@/components/ui/separator', () => ({ Separator: defineComponent({ name: 'Separator', setup: () => () => h('hr') }) }))
vi.mock('@/components/ui/scroll-area', () => ({ ScrollArea: defineComponent({ name: 'ScrollArea', setup: (_, { slots }) => () => h('div', slots.default?.()) }) }))
vi.mock('@/components/ui/dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Dialog: passthrough('Dialog'),
    DialogContent: passthrough('DialogContent'),
    DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle'),
    DialogDescription: passthrough('DialogDescription'),
    DialogFooter: passthrough('DialogFooter'),
  }
})
vi.mock('@/components/ui/input', () => ({ Input: defineComponent({ name: 'Input', setup: () => () => h('input') }) }))
vi.mock('@/components/ui/label', () => ({ Label: defineComponent({ name: 'Label', setup: (_, { slots }) => () => h('label', slots.default?.()) }) }))
vi.mock('@/components/ui/textarea', () => ({ Textarea: defineComponent({ name: 'Textarea', setup: () => () => h('textarea') }) }))
vi.mock('@/components/ui/date-picker', () => ({ DatePicker: defineComponent({ name: 'DatePicker', setup: () => () => h('input', { type: 'date' }) }) }))
vi.mock('@/components/OpportunityStageStepper.vue', () => ({ default: defineComponent({ name: 'OpportunityStageStepper', setup: () => () => h('div', 'stage stepper') }) }))

const opportunityFixture = (): Opportunity => ({
  id: 88,
  opportunity_name: 'CRM 升级项目',
  customer_id: 19,
  customer_name: '上海测试客户',
  procurement_method_id: null,
  total_amount: 320000,
  user_count: 20,
  unit_price: 16000,
  license_type: LicenseType.SUBSCRIPTION,
  subscription_years: 1,
  purchase_type: PurchaseType.NEW,
  decision_maker_count: 1,
  expected_closing_date: '2026-08-30',
  procurement_stage_id: 1,
  stage_name: '方案沟通',
  win_probability: 50,
  owner_id: '9',
  status: OpportunityStatus.FOLLOW_UP,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  updated_time: '2026-07-15T00:00:00.000Z',
  version: 1,
  customer_info: {
    id: 19,
    account_name: '上海测试客户',
  },
})

describe('OpportunityDetailContent experience states', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    opportunityApi.getOpportunity.mockResolvedValue(opportunityFixture())
    contractApi.getContractByOpportunity.mockRejectedValue({ response: { status: 404 } })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('moves focus to the back button when embedded detail opens', async () => {
    const wrapper = mount(OpportunityDetailContent, {
      attachTo: document.body,
      props: {
        opportunityId: 88,
        embedded: true,
        customerContext: { customerId: 19, customerName: '上海测试客户' },
      },
    })

    await flushPromises()
    await nextTick()

    const backButton = wrapper.get('[data-testid="opportunity-detail-back"]')
    expect(document.activeElement).toBe(backButton.element)
  })

  it('announces loading state while opportunity detail is being fetched', async () => {
    opportunityApi.getOpportunity.mockReturnValue(new Promise(() => undefined))

    const wrapper = mount(OpportunityDetailContent, {
      props: {
        opportunityId: 88,
      },
    })

    await nextTick()

    const loadingState = wrapper.get('[role="status"]')
    expect(loadingState.attributes('aria-live')).toBe('polite')
    expect(loadingState.text()).toContain('加载中')
  })

  it('shows an inline error with a retry action when loading detail fails', async () => {
    opportunityApi.getOpportunity
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(opportunityFixture())

    const wrapper = mount(OpportunityDetailContent, {
      props: {
        opportunityId: 88,
      },
    })

    await flushPromises()

    const errorState = wrapper.get('[role="alert"]')
    expect(errorState.text()).toContain('商机详情加载失败')

    await wrapper.get('[data-testid="retry-opportunity-detail"]').trigger('click')
    await flushPromises()

    expect(opportunityApi.getOpportunity).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})
