import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import OpportunityDetailContent from '@/components/panels/OpportunityDetailContent.vue'
import { LicenseType, OpportunityStatus, PurchaseType, type Opportunity } from '@/api/opportunity'
import type { LicenseApplicationResponse } from '@/api/licenseApplication'
import { getDateAfterDays } from '@/utils/format'

const opportunityApi = vi.hoisted(() => ({
  getOpportunity: vi.fn(),
  markAsWon: vi.fn(),
  markAsLost: vi.fn(),
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
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }))

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
vi.mock('@/components/ApprovalProcessGeneric.vue', () => ({
  default: defineComponent({
    name: 'ApprovalProcessGeneric',
    emits: ['resubmit'],
    setup: (_, { emit }) => () => h('button', {
      'data-testid': 'approval-resubmit',
      onClick: () => emit('resubmit'),
    }, '修改并重新提交'),
  }),
}))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({
  default: defineComponent({
    name: 'OpportunityFormDialog',
    props: {
      open: Boolean,
      dialogTitle: String,
      submitText: String,
    },
    emits: ['update:open', 'success'],
    setup: (props, { emit }) => () => props.open
      ? h('button', {
        'data-testid': 'opportunity-form-submit',
        onClick: () => {
          emit('update:open', false)
          emit('success')
        },
      }, props.submitText ?? '确定')
      : null,
  }),
}))

const opportunityFixture = (): Opportunity => ({
  id: 88,
  opportunity_name: 'CRM 升级项目',
  customer_id: 'cus_19',
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
    id: 'cus_19',
    account_name: '上海测试客户',
  },
})


function buildLicenseApplication(
  overrides: Partial<LicenseApplicationResponse> = {}
): LicenseApplicationResponse {
  return {
    id: 1,
    team_id: 1,
    application_number: 'LIC202608200001',
    customer_id: 'cus_19',
    deployment_info_id: null,
    contract_id: null,
    authorized_users: 10,
    expiry_date: getDateAfterDays(14),
    license_type: 'TRIAL',
    enterprise_id: null,
    supported_modules: null,
    server_license_code: null,
    client_license_code: null,
    remark: null,
    license_code: null,
    status: 'ISSUED',
    applicant_id: '9',
    approver_id: null,
    approved_time: null,
    created_time: '2026-08-20T09:46:47',
    last_modified_time: '2026-08-20T09:46:47',
    customer_name: '上海测试客户',
    deployment_name: null,
    contract_name: null,
    ...overrides,
  }
}

describe('OpportunityDetailContent experience states', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    opportunityApi.getOpportunity.mockResolvedValue(opportunityFixture())
    contractApi.getContractByOpportunity.mockRejectedValue({ response: { status: 404 } })
    approvalGenericApi.submitApproval.mockResolvedValue({ approval_id: 99 })
    customerApi.getCustomerDetail.mockResolvedValue({
      id: 'cus_19',
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

  it('moves focus to the back button when embedded detail opens', async () => {
    const wrapper = mount(OpportunityDetailContent, {
      attachTo: document.body,
      props: {
        opportunityId: 88,
        embedded: true,
        customerContext: { customerId: 'cus_19', customerName: '上海测试客户' },
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

  it('keeps resubmit intent when the form closes before emitting success', async () => {
    opportunityApi.getOpportunity.mockResolvedValue({
      ...opportunityFixture(),
      approval_phase: 'rejected',
    })

    const wrapper = mount(OpportunityDetailContent, {
      props: {
        opportunityId: 88,
      },
    })

    await flushPromises()

    await wrapper.get('[data-testid="approval-resubmit"]').trigger('click')
    await nextTick()

    await wrapper.get('[data-testid="opportunity-form-submit"]').trigger('click')
    await flushPromises()

    expect(approvalGenericApi.submitApproval).toHaveBeenCalledWith('OPPORTUNITY', 88)
    expect(toast.success).toHaveBeenCalledWith('商机已重新提交审批')
  })

  it('shows expired and valid customer licenses together on opportunity detail', async () => {
    opportunityApi.getOpportunity.mockResolvedValue({
      ...opportunityFixture(),
      approval_phase: 'approved',
    })
    licenseApplicationApi.list.mockResolvedValue([
      buildLicenseApplication({
        id: 11,
        application_number: 'LIC202607210001',
        expiry_date: getDateAfterDays(-16),
      }),
      buildLicenseApplication({
        id: 12,
        application_number: 'LIC202608200001',
        expiry_date: getDateAfterDays(14),
      }),
    ])

    const wrapper = mount(OpportunityDetailContent, {
      props: {
        opportunityId: 88,
        embedded: true,
        customerContext: { customerId: 'cus_19', customerName: '上海测试客户' },
      },
    })

    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('LIC202607210001')
    expect(wrapper.text()).toContain('LIC202608200001')
    expect(wrapper.text()).toContain('已过期')
    expect(wrapper.text()).not.toContain('暂无许可证申请')
  })

  it('does not pretend license applications are empty when the list request fails', async () => {
    opportunityApi.getOpportunity.mockResolvedValue({
      ...opportunityFixture(),
      approval_phase: 'approved',
    })
    licenseApplicationApi.list.mockRejectedValue(new Error('network error'))

    const wrapper = mount(OpportunityDetailContent, {
      props: {
        opportunityId: 88,
        embedded: true,
        customerContext: { customerId: 'cus_19', customerName: '上海测试客户' },
      },
    })

    await flushPromises()
    await nextTick()

    expect(handleApiError).toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('暂无许可证申请')
    expect(wrapper.text()).toContain('许可证申请加载失败')
  })
})
