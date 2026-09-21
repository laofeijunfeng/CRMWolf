import type { VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, type PropType } from 'vue'
import type { ContractListResponse, ContractResponse } from '@/api/contract'
import type { DealJourney } from '@/api/dealJourney'
import type {
  ApprovalInfoLite,
  PaymentPlanResponse,
  PaymentRecordDetailResponse,
  PaymentRecordInfo,
  PaymentRecordUpdate,
} from '@/api/payment'
import type { DetailContextNode } from '@/types/detailContext'

type BreadcrumbPaymentRecord = PaymentRecordInfo & { record_number?: string }

const contractApi = vi.hoisted(() => ({
  getContract: vi.fn(),
  deleteContract: vi.fn(),
}))
const approvalGenericApi = vi.hoisted(() => ({
  submitApproval: vi.fn(),
  cancelApproval: vi.fn(),
}))
const paymentApi = vi.hoisted(() => ({
  getPaymentRecordDetail: vi.fn(),
  updatePaymentRecord: vi.fn(),
}))
const confirmDelete = vi.hoisted(() => vi.fn())
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn() }))
const journeyRefresh = vi.hoisted(() => vi.fn())
const submitEntity = vi.hoisted(() => vi.fn())

vi.mock('@/api/contract', () => ({ default: contractApi }))
vi.mock('@/api/approvalGeneric', () => ({ default: approvalGenericApi }))
vi.mock('@/api/payment', () => ({ default: paymentApi }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDelete }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/stores/approval', () => ({ useApprovalStore: () => ({ submitEntity }) }))

vi.mock('@/components/panels/DealJourneyDetailContent.vue', () => ({
  default: defineComponent({
    name: 'DealJourneyDetailContent',
    props: {
      customerId: { type: String, required: true },
      journeyId: { type: String, required: true },
      journey: { type: Object as PropType<DealJourney | null>, default: null },
      embedded: Boolean,
      showBreadcrumb: Boolean,
      customerContext: Object,
      canEditCustomerContext: { type: Boolean, default: null },
    },
    emits: [
      'close',
      'refresh',
      'create-contract',
      'edit-contract',
      'delete-contract',
      'submit-contract-approval',
      'withdraw-contract-approval',
      'view-contract',
      'view-payment-plan',
    ],
    setup(_, { expose }) {
      expose({ refresh: journeyRefresh })
      return () => h('div', { 'data-testid': 'journey-content' })
    },
  }),
}))

vi.mock('@/components/crmwolf/DetailContextHost.vue', () => ({
  default: defineComponent({
    name: 'DetailContextHost',
    props: {
      nodes: { type: Array as PropType<readonly DetailContextNode[]>, default: () => [] },
      canGoBack: { type: Boolean, default: false },
      showHeader: { type: Boolean, default: true },
    },
    emits: ['back', 'close', 'navigate'],
    setup: (_, { slots }) => () => h('div', { 'data-testid': 'detail-context-host' }, slots.default?.()),
  }),
}))

vi.mock('@/components/panels/ContractDetailContent.vue', () => ({
  default: defineComponent({
    name: 'ContractDetailContent',
    props: {
      contractId: { type: Number, default: null },
      embedded: { type: Boolean, default: false },
      showBreadcrumb: { type: Boolean, default: true },
    },
    emits: ['back', 'close', 'approve', 'reject', 'view-payment-plan', 'refresh'],
    setup: props => () => h('div', {
      'data-testid': 'contract-detail-content',
      'data-contract-id': String(props.contractId ?? ''),
    }),
  }),
}))

vi.mock('@/components/panels/PaymentPlanDetailContent.vue', () => ({
  default: defineComponent({
    name: 'PaymentPlanDetailContent',
    props: {
      planId: { type: Number, default: null },
      visible: { type: Boolean, default: true },
      embedded: { type: Boolean, default: false },
    },
    emits: ['update:visible', 'close', 'refresh', 'record-click', 'view-approval', 'view-customer', 'view-contract'],
    setup: props => () => h('div', {
      'data-testid': 'payment-plan-detail-content',
      'data-plan-id': String(props.planId ?? ''),
    }),
  }),
}))

vi.mock('@/components/panels/PaymentRecordDetailContent.vue', () => ({
  default: defineComponent({
    name: 'PaymentRecordDetailContent',
    props: {
      recordId: { type: Number, default: null },
      visible: { type: Boolean, default: true },
      embedded: { type: Boolean, default: false },
      record: { type: Object, default: null },
      stageName: { type: String, default: '' },
      approval: { type: Object, default: null },
    },
    emits: ['update:visible', 'close', 'refresh', 'edit', 'resubmit'],
    setup: props => () => h('div', {
      'data-testid': 'payment-record-detail-content',
      'data-record-id': String(props.recordId ?? ''),
    }),
  }),
}))

vi.mock('@/components/dialogs/ContractFormDialog.vue', () => ({
  default: defineComponent({
    name: 'ContractFormDialog',
    props: { open: Boolean, customerId: String, customerName: String, customerLocked: Boolean, contract: Object, fixedOpportunity: Object },
    emits: ['update:open', 'success'],
    setup: props => () => h('div', { 'data-visible': String(props.open) }),
  }),
}))
vi.mock('@/components/dialogs/EditRecordDialog.vue', () => ({
  default: defineComponent({
    name: 'EditRecordDialog',
    props: { open: Boolean, record: Object, submitting: Boolean },
    emits: ['update:open', 'submit'],
    setup: props => () => h('div', { 'data-visible': String(props.open) }),
  }),
}))

import DealJourneyDetailHost from '@/components/business-journey/DealJourneyDetailHost.vue'
import DealJourneyDetailContent from '@/components/panels/DealJourneyDetailContent.vue'
import DetailContextHost from '@/components/crmwolf/DetailContextHost.vue'
import ContractDetailContent from '@/components/panels/ContractDetailContent.vue'
import PaymentPlanDetailContent from '@/components/panels/PaymentPlanDetailContent.vue'
import PaymentRecordDetailContent from '@/components/panels/PaymentRecordDetailContent.vue'
import ContractFormDialog from '@/components/dialogs/ContractFormDialog.vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'

const contractFixture = (overrides: Partial<ContractListResponse> = {}): ContractListResponse => ({
  id: 31,
  contract_number: 'CON-31',
  contract_name: '旅程合同',
  customer_id: 'cus_test',
  customer_name: '测试客户',
  opportunity_id: 'opp_test',
  opportunity_name: '测试商机',
  signing_contact_id: 1,
  user_count: 10,
  total_amount: '100000',
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  standard_unit_price: '10000',
  status: 'DRAFT',
  approval_phase: 'draft',
  signing_date: null,
  effective_date: null,
  expiry_date: null,
  owner_id: '9',
  creator_id: '9',
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-01T00:00:00',
  ...overrides,
})

const paymentRecordFixture = (overrides: Partial<PaymentRecordInfo> = {}): PaymentRecordInfo => ({
  id: 51,
  actual_amount: 50000,
  payment_date: '2026-09-15',
  created_time: '2026-09-15T00:00:00',
  approval_phase: 'rejected',
  ...overrides,
})

const approvalFixture = (overrides: Partial<ApprovalInfoLite> = {}): ApprovalInfoLite => ({
  id: 901,
  status: 'PENDING',
  current_approver_name: '财务经理',
  nodes: [],
  ...overrides,
})

const paymentRecordDetailFixture = (
  overrides: Partial<PaymentRecordDetailResponse> = {},
): PaymentRecordDetailResponse => ({
  id: 51,
  payment_plan_id: 41,
  actual_amount: 50000,
  payment_date: '2026-09-15',
  created_time: '2026-09-15T00:00:00',
  last_modified_time: '2026-09-21T00:00:00',
  approval_phase: 'approved',
  confirmation_status: 'CONFIRMED',
  status: 'APPROVED',
  approval: approvalFixture({ status: 'APPROVED' }),
  payment_plan: {
    id: 41,
    stage_name: '验收款',
    planned_amount: 50000,
    paid_amount: 50000,
    remaining_amount: 0,
    due_date: '2026-09-15',
    status: 'COMPLETED',
    last_modified_time: '2026-09-21T00:00:00',
  },
  ...overrides,
})

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T | PromiseLike<T>) => void
}

function createDeferred<T>(): Deferred<T> {
  let resolvePromise: ((value: T | PromiseLike<T>) => void) | undefined
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve
  })
  if (resolvePromise === undefined) throw new Error('Deferred resolver was not initialized')
  return { promise, resolve: resolvePromise }
}

const paymentPlanFixture = (overrides: Partial<PaymentPlanResponse> = {}): PaymentPlanResponse => ({
  id: 41,
  contract_id: 31,
  stage_name: '首款',
  planned_amount: 50000,
  due_date: '2026-09-15',
  status: 'PARTIAL',
  payment_records: [paymentRecordFixture()],
  customer_id: 'cus_test',
  customer_name: '测试客户',
  created_time: '2026-09-01T00:00:00',
  last_modified_time: '2026-09-01T00:00:00',
  ...overrides,
})

const customerPrefixFixture = (): DetailContextNode => ({
  type: 'customer',
  id: 'cus_test',
  label: '测试客户',
  source: 'customer-detail',
})

const createContractPayload = {
  opportunityId: 'opp_test',
  customerId: 'cus_test',
  customerName: '测试客户',
  opportunityName: '测试商机',
  totalAmount: 100000,
  userCount: 10,
  licenseType: 'SUBSCRIPTION',
  subscriptionYears: 1,
}

function mountHost(props: Record<string, unknown> = {}) {
  return mount(DealJourneyDetailHost, {
    props: {
      customerId: 'cus_test',
      customerName: '测试客户',
      journeyId: 'djy_test',
      journeyName: '华东续约旅程',
      embedded: true,
      ...props,
    },
    global: { plugins: [createPinia()] },
  })
}

async function expectRefresh(wrapper: VueWrapper): Promise<void> {
  await flushPromises()
  expect(journeyRefresh).toHaveBeenCalledOnce()
  expect(wrapper.emitted('refresh')).toHaveLength(1)
}

describe('DealJourneyDetailHost', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    journeyRefresh.mockResolvedValue(true)
    contractApi.deleteContract.mockResolvedValue(undefined)
    approvalGenericApi.submitApproval.mockResolvedValue(undefined)
    approvalGenericApi.cancelApproval.mockResolvedValue(undefined)
    paymentApi.updatePaymentRecord.mockResolvedValue(undefined)
    paymentApi.getPaymentRecordDetail.mockResolvedValue(paymentRecordDetailFixture())
    submitEntity.mockResolvedValue({ approval_id: 77 })
    confirmDelete.mockResolvedValue(true)
  })

  it('renders one DealJourneyDetailContent inside a single context host without nested sheets', () => {
    const wrapper = mountHost()

    expect(wrapper.findAllComponents(DealJourneyDetailContent)).toHaveLength(1)
    expect(wrapper.getComponent(DealJourneyDetailContent).props()).toMatchObject({
      customerId: 'cus_test',
      journeyId: 'djy_test',
      embedded: true,
      showBreadcrumb: false,
    })
    expect(wrapper.getComponent(DetailContextHost).props()).toMatchObject({
      nodes: [{ type: 'journey', id: 'djy_test', label: '华东续约旅程' }],
      canGoBack: false,
      showHeader: false,
    })
    expect(wrapper.findComponent({ name: 'ContractDetailSheet' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'PaymentPlanDetailSheet' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'PaymentRecordDetailSheet' }).exists()).toBe(false)
  })

  it('shows journey and contract in one context path without another Sheet', async () => {
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contractFixture())
    await nextTick()

    expect(wrapper.getComponent(DetailContextHost).props('nodes')).toMatchObject([
      { type: 'journey', id: 'djy_test', label: '华东续约旅程' },
      { type: 'contract', id: '31', label: '旅程合同' },
    ])
    expect(wrapper.getComponent(ContractDetailContent).props()).toMatchObject({
      contractId: 31,
      embedded: true,
      showBreadcrumb: false,
    })
    expect(wrapper.findComponent({ name: 'ContractDetailSheet' }).exists()).toBe(false)
  })

  it('builds journey contract plan record breadcrumbs and supports ancestor navigation', async () => {
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name, plan_number: 'PAY-001' })
    const record: BreadcrumbPaymentRecord = {
      ...paymentRecordFixture({ id: 51 }),
      record_number: 'REC-051',
    }

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contract)
    await nextTick()
    wrapper.getComponent(ContractDetailContent).vm.$emit('view-payment-plan', plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()

    expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => node.label)).toEqual([
      '华东续约旅程',
      '旅程合同',
      'PAY-001',
      'REC-051',
    ])

    wrapper.getComponent(DetailContextHost).vm.$emit('navigate', 1)
    await nextTick()
    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(true)
    expect(wrapper.findComponent(PaymentRecordDetailContent).exists()).toBe(false)
  })

  it('auto-inserts the contract node when opening a payment plan directly from the journey', async () => {
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name, plan_number: 'PAY-001' })

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()

    expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => node.label)).toEqual([
      '华东续约旅程',
      '旅程合同',
      'PAY-001',
    ])
    expect(wrapper.getComponent(PaymentPlanDetailContent).props()).toMatchObject({
      planId: plan.id,
      visible: true,
      embedded: true,
    })
    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(false)
  })

  it('returns to the same mounted journey content element after backing out of a contract', async () => {
    const wrapper = mountHost()
    const journeyElement = wrapper.get('[data-testid="journey-content"]').element

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contractFixture())
    await nextTick()
    expect(wrapper.get('[data-testid="journey-content"]').element).toBe(journeyElement)

    wrapper.getComponent(DetailContextHost).vm.$emit('back')
    await nextTick()

    expect(wrapper.get('[data-testid="journey-content"]').element).toBe(journeyElement)
    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(false)
    expect(wrapper.getComponent(DetailContextHost).props()).toMatchObject({
      nodes: [{ type: 'journey', id: 'djy_test' }],
      canGoBack: false,
      showHeader: false,
    })
  })

  it('delegates customer prefix navigation to view-customer without switching internal nodes', async () => {
    const wrapper = mountHost({ contextPrefix: [customerPrefixFixture()] })

    expect(wrapper.getComponent(DetailContextHost).props()).toMatchObject({
      showHeader: true,
      canGoBack: true,
    })
    expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => node.type)).toEqual(['customer', 'journey'])

    wrapper.getComponent(DetailContextHost).vm.$emit('navigate', 0)
    await nextTick()

    expect(wrapper.emitted('view-customer')).toEqual([['cus_test']])
    expect(wrapper.getComponent(DealJourneyDetailContent).exists()).toBe(true)
    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(false)
    expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => node.type)).toEqual(['customer', 'journey'])

    wrapper.getComponent(DetailContextHost).vm.$emit('back')
    await nextTick()

    expect(wrapper.emitted('view-customer')).toEqual([['cus_test'], ['cus_test']])
    expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => node.type)).toEqual(['customer', 'journey'])
  })

  it('resets the context stack and child state when journeyId changes', async () => {
    const wrapper = mountHost()
    const contract = contractFixture()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contract)
    await nextTick()
    wrapper.getComponent(ContractDetailContent).vm.$emit('view-payment-plan', paymentPlanFixture({ contract_name: contract.contract_name }))
    await nextTick()
    expect(wrapper.findComponent(PaymentPlanDetailContent).exists()).toBe(true)

    await wrapper.setProps({ journeyId: 'djy_next' })

    expect(wrapper.getComponent(DetailContextHost).props('nodes')).toMatchObject([
      { type: 'journey', id: 'djy_next', label: '华东续约旅程' },
    ])
    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(false)
    expect(wrapper.findComponent(PaymentPlanDetailContent).exists()).toBe(false)
    expect(wrapper.findComponent(PaymentRecordDetailContent).exists()).toBe(false)
    expect(wrapper.getComponent(DealJourneyDetailContent).props('journeyId')).toBe('djy_next')
  })

  it('reuses the ancestor contract node when a payment plan navigates back to its contract', async () => {
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name, plan_number: 'PAY-001' })
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contract)
    await nextTick()
    wrapper.getComponent(ContractDetailContent).vm.$emit('view-payment-plan', plan)
    await nextTick()

    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('view-contract', plan.contract_id, plan)
    await nextTick()

    expect(wrapper.getComponent(DetailContextHost).props('nodes').map(node => `${node.type}:${node.id}`)).toEqual([
      'journey:djy_test',
      'contract:31',
    ])
    expect(wrapper.getComponent(ContractDetailContent).props('contractId')).toBe(31)
    expect(wrapper.findComponent(PaymentPlanDetailContent).exists()).toBe(false)
  })

  it('emits close from the context header without altering the context stack', async () => {
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contractFixture())
    await nextTick()

    wrapper.getComponent(DetailContextHost).vm.$emit('close')

    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.getComponent(DetailContextHost).props('nodes')).toMatchObject([
      { type: 'journey' },
      { type: 'contract' },
    ])
  })

  it('opens the existing contract form and refreshes journey after create success', async () => {
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('create-contract', createContractPayload)
    await nextTick()

    expect(wrapper.getComponent(ContractFormDialog).props()).toMatchObject({
      open: true,
      customerId: 'cus_test',
      fixedOpportunity: expect.objectContaining({ id: 'opp_test' }),
    })
    wrapper.getComponent(ContractFormDialog).vm.$emit('success')
    await expectRefresh(wrapper)
  })

  it('loads the existing contract before opening edit and refreshes after success', async () => {
    const detailedContract = { ...contractFixture(), notes: 'detail' } as ContractResponse
    contractApi.getContract.mockResolvedValue(detailedContract)
    const wrapper = mountHost()

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('edit-contract', contractFixture())
    await flushPromises()

    expect(contractApi.getContract).toHaveBeenCalledWith(31)
    expect(wrapper.getComponent(ContractFormDialog).props()).toMatchObject({ open: true, contract: detailedContract })
    wrapper.getComponent(ContractFormDialog).vm.$emit('success')
    await expectRefresh(wrapper)
  })

  it('confirms and deletes through the existing contract API before refreshing', async () => {
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('delete-contract', contractFixture())
    await flushPromises()

    expect(confirmDelete).toHaveBeenCalledWith('合同 "旅程合同"')
    expect(contractApi.deleteContract).toHaveBeenCalledWith(31)
    await expectRefresh(wrapper)
  })

  it('returns to the journey root when the open contract is deleted', async () => {
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-contract', contractFixture())
    await nextTick()
    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(true)

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('delete-contract', contractFixture())
    await flushPromises()

    expect(wrapper.findComponent(ContractDetailContent).exists()).toBe(false)
    expect(wrapper.getComponent(DetailContextHost).props('nodes')).toMatchObject([
      { type: 'journey', id: 'djy_test' },
    ])
    await expectRefresh(wrapper)
  })

  it('submits and withdraws contract approval through the existing APIs', async () => {
    const wrapper = mountHost()
    const content = wrapper.getComponent(DealJourneyDetailContent)

    content.vm.$emit('submit-contract-approval', contractFixture())
    await flushPromises()
    expect(approvalGenericApi.submitApproval).toHaveBeenCalledWith('CONTRACT', 31)
    expect(journeyRefresh).toHaveBeenCalledTimes(1)

    content.vm.$emit('withdraw-contract-approval', contractFixture({ status: 'PENDING_REVIEW' }))
    await flushPromises()
    expect(approvalGenericApi.cancelApproval).toHaveBeenCalledWith('CONTRACT', 31)
    expect(journeyRefresh).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('refresh')).toHaveLength(2)
  })

  it('mounts payment record detail from plan events within the same host', async () => {
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()

    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      recordId: record.id,
      visible: true,
      stageName: '首款',
      record: expect.objectContaining({ id: record.id }),
    })
    expect(wrapper.findComponent(PaymentPlanDetailContent).exists()).toBe(false)

    wrapper.getComponent(DetailContextHost).vm.$emit('back')
    await nextTick()
    expect(wrapper.getComponent(PaymentPlanDetailContent).props('planId')).toBe(plan.id)
    expect(wrapper.findComponent(PaymentRecordDetailContent).exists()).toBe(false)

    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('view-approval', record)
    await nextTick()
    expect(wrapper.getComponent(PaymentRecordDetailContent).props('recordId')).toBe(record.id)
  })

  it('reloads authoritative payment record state before refreshing journey and parent', async () => {
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]
    const updatedApproval = approvalFixture({ id: 902, status: 'APPROVED' })
    const updatedRecord = paymentRecordDetailFixture({
      id: record.id,
      actual_amount: 52000,
      approval_phase: 'approved',
      confirmation_status: 'CONFIRMED',
      approval: updatedApproval,
      payment_plan: {
        ...paymentRecordDetailFixture().payment_plan,
        stage_name: '终验款',
      },
    })
    paymentApi.getPaymentRecordDetail.mockResolvedValueOnce(updatedRecord)

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('refresh')
    await flushPromises()

    expect(paymentApi.getPaymentRecordDetail).toHaveBeenCalledWith(record.id)
    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      visible: true,
      record: updatedRecord,
      approval: updatedApproval,
      stageName: '终验款',
    })
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('keeps the current payment record when detail reload fails and still refreshes journey', async () => {
    const error = new Error('detail refresh failed')
    paymentApi.getPaymentRecordDetail.mockRejectedValueOnce(error)
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('refresh')
    await flushPromises()

    expect(handleApiError).toHaveBeenCalledWith(error, '刷新回款记录详情')
    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      visible: true,
      record,
      stageName: plan.stage_name,
    })
    expect(wrapper.getComponent(DealJourneyDetailContent).exists()).toBe(true)
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('does not restore a payment record left while its detail refresh is pending', async () => {
    const detailRequest = createDeferred<PaymentRecordDetailResponse>()
    paymentApi.getPaymentRecordDetail.mockReturnValueOnce(detailRequest.promise)
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('refresh')
    await nextTick()
    wrapper.getComponent(DetailContextHost).vm.$emit('back')
    await nextTick()

    detailRequest.resolve(paymentRecordDetailFixture({ id: record.id, actual_amount: 99000 }))
    await flushPromises()

    expect(wrapper.findComponent(PaymentRecordDetailContent).exists()).toBe(false)
    expect(wrapper.getComponent(PaymentPlanDetailContent).props('planId')).toBe(plan.id)
    expect(wrapper.getComponent(DealJourneyDetailContent).exists()).toBe(true)
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('does not overwrite a newly selected payment record with a stale detail response', async () => {
    const detailRequest = createDeferred<PaymentRecordDetailResponse>()
    paymentApi.getPaymentRecordDetail.mockReturnValueOnce(detailRequest.promise)
    const wrapper = mountHost()
    const contract = contractFixture()
    const firstPlan = paymentPlanFixture({ contract_name: contract.contract_name })
    const firstRecord = firstPlan.payment_records[0]
    const secondRecord = paymentRecordFixture({ id: 52, actual_amount: 25000 })
    const secondPlan = paymentPlanFixture({
      id: 42,
      stage_name: '尾款',
      payment_records: [secondRecord],
    })

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', firstPlan.id, firstPlan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', firstRecord)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('refresh')
    await nextTick()

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', secondPlan.id, secondPlan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', secondRecord)
    await nextTick()
    detailRequest.resolve(paymentRecordDetailFixture({ id: firstRecord.id, actual_amount: 99000 }))
    await flushPromises()

    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      visible: true,
      recordId: secondRecord.id,
      record: secondRecord,
      stageName: secondPlan.stage_name,
    })
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('reloads authoritative payment record state after a normal edit before refreshing journey and parent', async () => {
    const journeyRequest = createDeferred<boolean>()
    journeyRefresh.mockReturnValueOnce(journeyRequest.promise)
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]
    const updatedApproval = approvalFixture({ id: 902, status: 'APPROVED' })
    const updatedRecord = paymentRecordDetailFixture({
      id: record.id,
      actual_amount: 62000,
      approval_phase: 'approved',
      confirmation_status: 'CONFIRMED',
      status: 'APPROVED',
      approval: updatedApproval,
      payment_plan: {
        ...paymentRecordDetailFixture().payment_plan,
        stage_name: '终验款',
        status: 'COMPLETED',
      },
    })
    paymentApi.getPaymentRecordDetail.mockResolvedValueOnce(updatedRecord)

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('edit')
    await nextTick()

    const update: PaymentRecordUpdate = { actual_amount: 62000, notes: 'updated' }
    wrapper.getComponent(EditRecordDialog).vm.$emit('submit', record.id, update)
    await flushPromises()

    expect(paymentApi.updatePaymentRecord).toHaveBeenCalledWith(record.id, update)
    expect(paymentApi.getPaymentRecordDetail).toHaveBeenCalledWith(record.id)
    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      visible: true,
      record: updatedRecord,
      approval: updatedApproval,
      stageName: '终验款',
    })
    expect(wrapper.getComponent(EditRecordDialog).props('open')).toBe(false)
    expect(toast.success).toHaveBeenCalledWith('回款记录更新成功')
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(paymentApi.getPaymentRecordDetail.mock.invocationCallOrder[0])
      .toBeLessThan(journeyRefresh.mock.invocationCallOrder[0])
    expect(wrapper.emitted('refresh')).toBeUndefined()

    journeyRequest.resolve(true)
    await flushPromises()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('reloads changed approval state after resubmission before refreshing journey and parent', async () => {
    const journeyRequest = createDeferred<boolean>()
    journeyRefresh.mockReturnValueOnce(journeyRequest.promise)
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]
    const resubmittedApproval = approvalFixture({ id: 903, status: 'PENDING', current_approver_name: '总经理' })
    const resubmittedRecord = paymentRecordDetailFixture({
      id: record.id,
      actual_amount: 58000,
      approval_phase: 'pending_review',
      confirmation_status: 'PENDING',
      status: 'PENDING',
      approval: resubmittedApproval,
      payment_plan: {
        ...paymentRecordDetailFixture().payment_plan,
        stage_name: '尾款',
        status: 'PARTIAL',
      },
    })
    paymentApi.getPaymentRecordDetail.mockResolvedValueOnce(resubmittedRecord)

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('resubmit')
    await nextTick()

    const update: PaymentRecordUpdate = { actual_amount: 58000 }
    wrapper.getComponent(EditRecordDialog).vm.$emit('submit', record.id, update)
    await flushPromises()

    expect(paymentApi.updatePaymentRecord).toHaveBeenCalledWith(record.id, update)
    expect(submitEntity).toHaveBeenCalledWith('PAYMENT', record.id)
    expect(paymentApi.getPaymentRecordDetail).toHaveBeenCalledWith(record.id)
    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      visible: true,
      record: resubmittedRecord,
      approval: resubmittedApproval,
      stageName: '尾款',
    })
    expect(wrapper.getComponent(EditRecordDialog).props('open')).toBe(false)
    expect(toast.success).toHaveBeenCalledWith('已重新提交审批')
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(submitEntity.mock.invocationCallOrder[0])
      .toBeLessThan(paymentApi.getPaymentRecordDetail.mock.invocationCallOrder[0])
    expect(paymentApi.getPaymentRecordDetail.mock.invocationCallOrder[0])
      .toBeLessThan(journeyRefresh.mock.invocationCallOrder[0])
    expect(wrapper.emitted('refresh')).toBeUndefined()

    journeyRequest.resolve(true)
    await flushPromises()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('keeps the open payment record when post-edit detail reload fails and still refreshes journey and parent', async () => {
    const error = new Error('detail refresh failed after edit')
    paymentApi.getPaymentRecordDetail.mockRejectedValueOnce(error)
    const journeyRequest = createDeferred<boolean>()
    journeyRefresh.mockReturnValueOnce(journeyRequest.promise)
    const wrapper = mountHost()
    const contract = contractFixture()
    const plan = paymentPlanFixture({ contract_name: contract.contract_name })
    const record = plan.payment_records[0]

    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('view-payment-plan', plan.id, plan)
    await nextTick()
    wrapper.getComponent(PaymentPlanDetailContent).vm.$emit('record-click', record)
    await nextTick()
    wrapper.getComponent(PaymentRecordDetailContent).vm.$emit('edit')
    await nextTick()
    wrapper.getComponent(EditRecordDialog).vm.$emit('submit', record.id, { notes: 'updated' })
    await flushPromises()

    expect(handleApiError).toHaveBeenCalledWith(error, '刷新回款记录详情')
    expect(wrapper.getComponent(PaymentRecordDetailContent).props()).toMatchObject({
      visible: true,
      record,
      stageName: plan.stage_name,
    })
    expect(wrapper.getComponent(DealJourneyDetailContent).exists()).toBe(true)
    expect(wrapper.getComponent(EditRecordDialog).props('open')).toBe(false)
    expect(journeyRefresh).toHaveBeenCalledOnce()
    expect(wrapper.emitted('refresh')).toBeUndefined()

    journeyRequest.resolve(true)
    await flushPromises()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('preserves the host and does not emit refresh when content refresh rejects', async () => {
    journeyRefresh.mockRejectedValueOnce(new Error('refresh failed'))
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('create-contract', createContractPayload)
    await nextTick()
    wrapper.getComponent(ContractFormDialog).vm.$emit('success')
    await flushPromises()

    expect(wrapper.getComponent(DealJourneyDetailContent).exists()).toBe(true)
    expect(wrapper.emitted('close')).toBeUndefined()
    expect(wrapper.emitted('refresh')).toBeUndefined()
    expect(handleApiError).toHaveBeenCalledWith(expect.any(Error), '刷新业务旅程详情')
  })

  it('preserves the host when content reports a failed refresh', async () => {
    journeyRefresh.mockResolvedValueOnce(false)
    const wrapper = mountHost()
    wrapper.getComponent(DealJourneyDetailContent).vm.$emit('create-contract', createContractPayload)
    await nextTick()
    wrapper.getComponent(ContractFormDialog).vm.$emit('success')
    await flushPromises()

    expect(wrapper.getComponent(DealJourneyDetailContent).exists()).toBe(true)
    expect(wrapper.emitted('refresh')).toBeUndefined()
  })
})
