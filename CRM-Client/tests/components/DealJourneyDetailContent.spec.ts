import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import DealJourneyDetailContent from '@/components/panels/DealJourneyDetailContent.vue'
import { LicenseType, OpportunityStatus, PurchaseType, type Opportunity } from '@/api/opportunity'
import type { DealJourney } from '@/api/dealJourney'

const dealJourneyApi = vi.hoisted(() => ({
  getDetail: vi.fn(),
  getByCustomer: vi.fn(),
  listByCustomer: vi.fn(),
}))
const opportunityApi = vi.hoisted(() => ({
  getOpportunity: vi.fn(),
}))
const contractApi = vi.hoisted(() => ({
  getContractByOpportunity: vi.fn(),
}))
const approvalGenericApi = vi.hoisted(() => ({
  submitApproval: vi.fn(),
}))
const customerApi = vi.hoisted(() => ({
  getCustomerDetail: vi.fn(),
  getCustomerMembers: vi.fn(),
}))
const paymentApi = vi.hoisted(() => ({
  getPaymentPlans: vi.fn(),
}))
const invoiceApi = vi.hoisted(() => ({
  getInvoiceApplications: vi.fn(),
}))
const licenseApplicationApi = vi.hoisted(() => ({
  list: vi.fn(),
}))
const deploymentApi = vi.hoisted(() => ({
  list: vi.fn(),
}))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

vi.mock('vue-router', () => ({
  RouterLink: defineComponent({
    name: 'RouterLink',
    props: { to: [String, Object] },
    setup: (_, { slots }) => () => h('a', slots.default?.()),
  }),
}))
vi.mock('@/api/dealJourney', () => ({ dealJourneyApi, default: dealJourneyApi }))
vi.mock('@/api/opportunity', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/opportunity')>()
  return {
    ...actual,
    opportunityApi,
  }
})
vi.mock('@/api/contract', () => ({ default: contractApi }))
vi.mock('@/api/approvalGeneric', () => ({ default: approvalGenericApi }))
vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/payment', () => ({ default: paymentApi }))
vi.mock('@/api/invoice', () => ({ default: invoiceApi }))
vi.mock('@/api/licenseApplication', () => ({ default: licenseApplicationApi }))
vi.mock('@/api/deployment', () => ({ default: deploymentApi }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => ({ hasAnyPermission: () => true, hasPermission: () => true }),
}))
vi.mock('@/stores/user', () => ({
  useUserStore: () => ({ userInfo: { id: '9' } }),
}))

vi.mock('@/components/crmwolf', () => ({
  AmountText: defineComponent({
    name: 'AmountText',
    props: { value: [Number, String] },
    setup: (props) => () => h('span', String(props.value ?? '')),
  }),
  HoverInfo: defineComponent({
    name: 'HoverInfo',
    setup: (_, { slots }) => () => h('div', [slots.trigger?.(), slots.default?.()]),
  }),
}))
vi.mock('@/components/crmwolf/ListCard.vue', () => ({
  default: defineComponent({
    name: 'ListCard',
    props: {
      title: String,
      items: { type: Array, default: () => [] },
      emptyText: String,
      loading: Boolean,
    },
    setup: (props, { slots }) => () => h('div', { 'data-testid': `list-card-${props.title ?? ''}` }, [
      h('h3', props.title),
      (props.items as Array<{ id: string }>).length > 0
        ? (props.items as Array<{ id: string }>).map((item) => h('div', {
          'data-testid': 'list-card-item',
          'data-item-id': item.id,
        }, [
          slots.itemMain?.({ item }),
          slots.itemMeta?.({ item }),
          h('div', { 'data-testid': 'journey-opportunity-actions' }, slots.itemActions?.({ item })),
        ]))
        : h('div', { 'data-testid': 'list-card-empty' }, props.emptyText),
    ]),
  }),
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
    setup: (props, { slots, attrs }) => () => h('button', {
      ...attrs,
      type: props.type ?? 'button',
      disabled: props.disabled,
      class: [attrs.class, props.variant, props.size].filter(Boolean).join(' '),
    }, slots.default?.()),
  }),
}))
vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: defineComponent({ name: 'ScrollArea', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))
vi.mock('@/components/ui/accordion', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Accordion: passthrough('Accordion'),
    AccordionItem: passthrough('AccordionItem'),
    AccordionTrigger: passthrough('AccordionTrigger'),
    AccordionContent: passthrough('AccordionContent'),
  }
})
vi.mock('@/components/ui/breadcrumb', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Breadcrumb: passthrough('Breadcrumb'),
    BreadcrumbList: passthrough('BreadcrumbList'),
    BreadcrumbItem: passthrough('BreadcrumbItem'),
    BreadcrumbLink: passthrough('BreadcrumbLink'),
    BreadcrumbPage: passthrough('BreadcrumbPage'),
    BreadcrumbSeparator: passthrough('BreadcrumbSeparator'),
  }
})
vi.mock('@/components/ui/alert-dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    AlertDialog: passthrough('AlertDialog'),
    AlertDialogCancel: passthrough('AlertDialogCancel'),
    AlertDialogContent: passthrough('AlertDialogContent'),
    AlertDialogDescription: passthrough('AlertDialogDescription'),
    AlertDialogFooter: passthrough('AlertDialogFooter'),
    AlertDialogHeader: passthrough('AlertDialogHeader'),
    AlertDialogTitle: passthrough('AlertDialogTitle'),
  }
})
vi.mock('@/components/OpportunityStageStepper.vue', () => ({
  default: defineComponent({ name: 'OpportunityStageStepper', setup: () => () => h('div', 'stage stepper') }),
}))
vi.mock('@/components/ApprovalProcessGeneric.vue', () => ({
  default: defineComponent({ name: 'ApprovalProcessGeneric', setup: () => () => h('div', 'approval') }),
}))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({
  default: defineComponent({ name: 'OpportunityFormDialog', setup: () => () => null }),
}))
vi.mock('@/components/dialogs/OpportunityWinDialog.vue', () => ({
  default: defineComponent({ name: 'OpportunityWinDialog', setup: () => () => null }),
}))
vi.mock('@/components/dialogs/OpportunityLoseDialog.vue', () => ({
  default: defineComponent({ name: 'OpportunityLoseDialog', setup: () => () => null }),
}))
vi.mock('@/components/dialogs/PaymentPlanFormDialog.vue', () => ({
  default: defineComponent({ name: 'PaymentPlanFormDialog', setup: () => () => null }),
}))
vi.mock('@/components/dialogs/PaymentRecordDialog.vue', () => ({
  default: defineComponent({ name: 'PaymentRecordDialog', setup: () => () => null }),
}))
vi.mock('@/components/dialogs/InvoiceApplicationFormDialog.vue', () => ({
  default: defineComponent({ name: 'InvoiceApplicationFormDialog', setup: () => () => null }),
}))
vi.mock('@/components/dialogs/LicenseApplicationFormDialog.vue', () => ({
  default: defineComponent({ name: 'LicenseApplicationFormDialog', setup: () => () => null }),
}))
const contractViewPayload = vi.hoisted(() => ({
  id: 31,
  contract_number: 'CON-31',
  contract_name: '旅程合同',
  customer_id: 'cus_test_19',
  customer_name: '上海测试客户',
  opportunity_id: 'opp_test_88',
  opportunity_name: 'CRM 升级项目',
  signing_contact_id: 1,
  user_count: 20,
  total_amount: '320000',
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  standard_unit_price: '16000',
  status: 'SIGNED',
  approval_phase: 'approved',
  signing_date: '2026-09-01',
  effective_date: null,
  expiry_date: null,
  owner_id: '9',
  creator_id: '9',
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-01T00:00:00',
}))
vi.mock('@/components/panels/ContractsPanel.vue', () => ({
  default: defineComponent({
    name: 'ContractsPanel',
    props: { contracts: { type: Array, default: () => [] } },
    emits: ['view'],
    setup: (_, { emit }) => () => h('div', { 'data-testid': 'contracts-panel' }, [
      h('button', {
        type: 'button',
        'data-testid': 'contracts-view',
        onClick: () => emit('view', contractViewPayload.id),
      }, 'view contract'),
    ]),
  }),
}))
vi.mock('@/components/panels/PaymentsPanel.vue', () => ({
  default: defineComponent({ name: 'PaymentsPanel', setup: () => () => h('div', 'payments') }),
}))
vi.mock('@/components/panels/InvoicesPanel.vue', () => ({
  default: defineComponent({ name: 'InvoicesPanel', setup: () => () => h('div', 'invoices') }),
}))
vi.mock('@/components/panels/LicensePanel.vue', () => ({
  default: defineComponent({
    name: 'LicensePanel',
    props: { customerId: String },
    setup: (props) => () => h('div', {
      'data-testid': 'journey-license-panel',
      'data-customer-id': props.customerId ?? '',
    }, 'license'),
  }),
}))

const JOURNEY_PUBLIC_ID = 'djy_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
const OPPORTUNITY_PUBLIC_ID = 'opp_test_88'
const CUSTOMER_PUBLIC_ID = 'cus_test_19'

const journeyFixture = (overrides: Partial<DealJourney> = {}): DealJourney => ({
  id: JOURNEY_PUBLIC_ID,
  public_id: JOURNEY_PUBLIC_ID,
  name: 'CRM 升级项目',
  status: 'OPEN',
  current_board_stage: 'closing_soon',
  current_board_stage_label: '即将签约',
  amount: 320000,
  purchase_type: 'NEW',
  started_at: '2026-07-15T00:00:00',
  closed_at: null,
  last_event_at: '2026-07-15T00:00:00',
  primary_opportunity: {
    public_id: OPPORTUNITY_PUBLIC_ID,
    opportunity_name: 'CRM 升级项目',
    status: 0,
    approval_phase: 'approved',
    win_probability: 50,
    expected_closing_date: '2026-08-30',
    product_name: 'CRM',
  },
  ...overrides,
})

const opportunityFixture = (overrides: Partial<Opportunity> = {}): Opportunity => ({
  id: OPPORTUNITY_PUBLIC_ID,
  public_id: OPPORTUNITY_PUBLIC_ID,
  opportunity_number: 'OPP-88',
  opportunity_name: 'CRM 升级项目',
  customer_id: CUSTOMER_PUBLIC_ID,
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
  approval_phase: 'approved',
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  updated_time: '2026-07-15T00:00:00.000Z',
  version: 1,
  customer_info: {
    id: CUSTOMER_PUBLIC_ID,
    account_name: '上海测试客户',
  },
  ...overrides,
})

const detailFixture = (journey: DealJourney = journeyFixture(), primaryOpportunity: Opportunity | null = opportunityFixture()) => ({
  journey,
  primary_opportunity: primaryOpportunity,
})

async function mountDetail(props: Record<string, unknown> = {}) {
  const wrapper = mount(DealJourneyDetailContent, {
    props: {
      journeyId: JOURNEY_PUBLIC_ID,
      customerId: CUSTOMER_PUBLIC_ID,
      embedded: true,
      canEditCustomerContext: true,
      ...props,
    },
  })
  await flushPromises()
  await nextTick()
  return wrapper
}

function namedFooterButtons(wrapper: { findAll: (selector: string) => Array<{ text: () => string }> }) {
  return wrapper.findAll('button').filter((button) => {
    const text = button.text().replace(/\s+/g, '')
    return text === '赢单' || text === '输单' || text === '编辑'
  })
}


describe('DealJourneyDetailContent fulfillment workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    dealJourneyApi.getDetail.mockResolvedValue(detailFixture())
    contractApi.getContractByOpportunity.mockRejectedValue({ response: { status: 404 } })
    customerApi.getCustomerDetail.mockResolvedValue({
      id: CUSTOMER_PUBLIC_ID,
      account_name: '上海测试客户',
      owner_id: '9',
    })
    customerApi.getCustomerMembers.mockResolvedValue([])
    paymentApi.getPaymentPlans.mockResolvedValue([])
    invoiceApi.getInvoiceApplications.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 })
    licenseApplicationApi.list.mockResolvedValue([])
    deploymentApi.list.mockResolvedValue([])
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('loads the unified detail envelope without customer-scoped or opportunity detail reads', async () => {
    const wrapper = await mountDetail()

    expect(dealJourneyApi.getDetail).toHaveBeenCalledWith(JOURNEY_PUBLIC_ID)
    expect(dealJourneyApi.getByCustomer).not.toHaveBeenCalled()
    expect(opportunityApi.getOpportunity).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('CRM 升级项目')
    expect(wrapper.text()).toContain('上海测试客户')
  })

  it('shows board stage and purchase type in the header, not win/lose footer', async () => {
    const wrapper = await mountDetail()

    const root = wrapper.get('[data-testid="deal-journey-detail"]')
    const header = wrapper.get('[data-testid="deal-journey-header"]')
    expect(header.text()).toContain('即将签约')
    expect(header.text()).toContain('新购')
    expect(header.text()).toContain('CRM 升级项目')
    expect(header.text()).not.toContain('跟进中')
    expect(header.text()).not.toContain('赢单')
    expect(header.text()).not.toContain('输单')
    expect(wrapper.find('[data-testid="deal-journey-detail-footer"]').exists()).toBe(false)
    expect(namedFooterButtons(wrapper)).toHaveLength(0)
    expect(root.text()).toContain('审批进度')
    expect(root.text()).toContain('商机进度')
    expect(root.text()).not.toContain('审批流程')
    expect(root.text()).not.toContain('采购阶段')
  })

  it('renders opportunity row action icons when approved and following', async () => {
    const wrapper = await mountDetail()

    const actions = wrapper.get('[data-testid="journey-opportunity-actions"]').findAll('button')
    expect(actions.map((button) => button.attributes('aria-label'))).toEqual([
      '编辑商机 CRM 升级项目',
      '赢单 CRM 升级项目',
      '输单 CRM 升级项目',
    ])
    expect(actions[0]?.attributes('class') ?? '').toContain('ghost')
  })

  it('does not fetch contracts when primary_opportunity is null', async () => {
    dealJourneyApi.getDetail.mockResolvedValue(detailFixture(
      journeyFixture({
        primary_opportunity: null,
        purchase_type: null,
        amount: 0,
      }),
      null
    ))

    const wrapper = await mountDetail()

    expect(opportunityApi.getOpportunity).not.toHaveBeenCalled()
    expect(contractApi.getContractByOpportunity).not.toHaveBeenCalled()
    expect(licenseApplicationApi.list).toHaveBeenCalledWith(CUSTOMER_PUBLIC_ID)
    expect(wrapper.text()).toContain('该旅程暂无主商机')
    expect(wrapper.find('[data-testid="journey-opportunity-actions"]').exists()).toBe(false)
    const licensePanel = wrapper.get('[data-testid="journey-license-panel"]')
    expect(licensePanel.attributes('data-customer-id')).toBe(CUSTOMER_PUBLIC_ID)
  })

  it('emits the full contract row on view-contract instead of only the numeric id', async () => {
    dealJourneyApi.getDetail.mockResolvedValue(detailFixture(
      journeyFixture(),
      opportunityFixture({ win_probability: 100 })
    ))
    contractApi.getContractByOpportunity.mockResolvedValue(contractViewPayload)
    const wrapper = await mountDetail()

    await wrapper.get('[data-testid="contracts-view"]').trigger('click')

    expect(wrapper.emitted('view-contract')).toEqual([[contractViewPayload]])
  })
})
