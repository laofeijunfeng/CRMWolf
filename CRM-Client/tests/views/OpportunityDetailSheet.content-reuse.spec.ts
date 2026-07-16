import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import OpportunityDetailSheet from '@/views/OpportunityDetailSheet.vue'
import { LicenseType, OpportunityStatus, PurchaseType, type Opportunity } from '@/api/opportunity'

const routerPush = vi.hoisted(() => vi.fn())
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
  useRouter: () => ({ push: routerPush }),
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

vi.mock('@/components/ui/sheet', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Sheet: defineComponent({
      name: 'Sheet',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open ? h('section', { 'data-testid': 'sheet-root' }, slots.default?.()) : null,
    }),
    SheetHeader: passthrough('SheetHeader'),
    SheetTitle: passthrough('SheetTitle'),
    SheetDescription: passthrough('SheetDescription'),
    SheetFooter: passthrough('SheetFooter'),
  }
})

vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({ name: 'DetailSheetContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

vi.mock('@/components/ui/card', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Card: passthrough('Card'),
    CardHeader: passthrough('CardHeader'),
    CardContent: passthrough('CardContent'),
  }
})

vi.mock('@/components/ui/badge', () => ({
  Badge: defineComponent({ name: 'Badge', setup: (_, { slots }) => () => h('span', slots.default?.()) }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String, disabled: Boolean },
    setup: (props, { slots, attrs }) => () => h('button', { ...attrs, type: props.type ?? 'button', disabled: props.disabled }, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/separator', () => ({
  Separator: defineComponent({ name: 'Separator', setup: () => () => h('hr') }),
}))

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: defineComponent({ name: 'ScrollArea', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

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

vi.mock('@/components/ui/input', () => ({
  Input: defineComponent({ name: 'Input', setup: () => () => h('input') }),
}))

vi.mock('@/components/ui/label', () => ({
  Label: defineComponent({ name: 'Label', setup: (_, { slots }) => () => h('label', slots.default?.()) }),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: defineComponent({ name: 'Textarea', setup: () => () => h('textarea') }),
}))

vi.mock('@/components/ui/date-picker', () => ({
  DatePicker: defineComponent({ name: 'DatePicker', setup: () => () => h('input', { type: 'date' }) }),
}))

vi.mock('@/components/OpportunityStageStepper.vue', () => ({
  default: defineComponent({ name: 'OpportunityStageStepper', setup: () => () => h('div', 'stage stepper') }),
}))

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

describe('OpportunityDetailSheet content reuse', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    opportunityApi.getOpportunity.mockResolvedValue(opportunityFixture())
    contractApi.getContractByOpportunity.mockRejectedValue({ response: { status: 404 } })
  })

  it('renders the reusable opportunity detail content inside a single sheet shell', async () => {
    const wrapper = mount(OpportunityDetailSheet, {
      props: {
        visible: true,
        opportunityId: 88,
      },
    })

    await flushPromises()

    expect(wrapper.findAll('[data-testid="sheet-root"]')).toHaveLength(1)
    const content = wrapper.get('[data-testid="opportunity-detail-content"]')
    expect(content.attributes('data-opportunity-id')).toBe('88')
  })
})
