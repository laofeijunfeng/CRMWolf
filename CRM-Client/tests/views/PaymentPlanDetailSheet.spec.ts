import { readFileSync } from 'node:fs'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import type { PaymentPlanResponse, PaymentRecordInfo } from '@/api/payment'

const paymentApi = vi.hoisted(() => ({
  getPaymentPlanDetail: vi.fn(),
}))
const handleApiError = vi.hoisted(() => vi.fn())

vi.mock('@/api/payment', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/payment')>()
  return {
    ...actual,
    default: paymentApi,
  }
})

vi.mock('@/utils/errorHandler', () => ({ handleApiError }))

vi.mock('@/components/ui/sheet', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  })

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
  DetailSheetContent: defineComponent({
    name: 'DetailSheetContent',
    setup: (_, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/card', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  })

  return {
    Card: passthrough('Card'),
    CardHeader: passthrough('CardHeader'),
    CardTitle: passthrough('CardTitle'),
    CardDescription: passthrough('CardDescription'),
    CardContent: passthrough('CardContent'),
  }
})

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: {
      type: String,
      variant: String,
      size: String,
      disabled: Boolean,
    },
    setup: (props, { slots, attrs }) => () => h(
      'button',
      { ...attrs, type: props.type ?? 'button', disabled: props.disabled },
      slots.default?.()
    ),
  }),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: defineComponent({
    name: 'Badge',
    setup: (_, { slots, attrs }) => () => h('span', attrs, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: defineComponent({
    name: 'ScrollArea',
    setup: (_, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/empty', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  })

  return {
    Empty: passthrough('Empty'),
    EmptyHeader: passthrough('EmptyHeader'),
    EmptyMedia: passthrough('EmptyMedia'),
    EmptyTitle: passthrough('EmptyTitle'),
    EmptyDescription: passthrough('EmptyDescription'),
  }
})

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: defineComponent({
    name: 'Skeleton',
    setup: (_, { attrs }) => () => h('div', attrs),
  }),
}))

vi.mock('@/components/StatusBadge.vue', () => ({
  default: defineComponent({
    name: 'StatusBadge',
    props: {
      status: { type: String, required: true },
      type: String,
    },
    setup: (props) => () => h('span', { 'data-testid': 'status-badge', 'data-status': props.status }, props.status),
  }),
}))

interface MockRecord {
  id: number
}

vi.mock('@/components/PaymentRecordList.vue', () => ({
  default: defineComponent({
    name: 'PaymentRecordList',
    props: {
      records: { type: Array as PropType<MockRecord[]>, required: true },
      canRegister: Boolean,
    },
    emits: ['register', 'record-click', 'edit-record', 'view-approval'],
    setup: (props, { emit }) => () => {
      const children = []
      if (props.canRegister) {
        children.push(h('button', { 'data-testid': 'record-register', onClick: () => emit('register') }, '登记回款'))
      }
      const firstRecord = props.records[0]
      if (firstRecord !== undefined) {
        children.push(h('button', { 'data-testid': 'record-click', onClick: () => emit('record-click', firstRecord) }, '记录点击'))
      }
      return h('div', {
        'data-testid': 'payment-record-list',
        'data-record-count': String(props.records.length),
        'data-can-register': String(props.canRegister),
      }, children)
    },
  }),
}))

import PaymentPlanDetailSheet from '@/views/PaymentPlanDetailSheet.vue'

const paymentRecordFixture = (): PaymentRecordInfo => ({
  id: 501,
  actual_amount: 60000,
  payment_date: '2026-07-10',
  creator_name: '张三',
  confirmation_status: 'PENDING',
  created_time: '2026-07-10T09:30:00.000Z',
})

const paymentPlanFixture = (overrides: Partial<PaymentPlanResponse> = {}): PaymentPlanResponse => ({
  id: 101,
  contract_id: 202,
  customer_id: 303,
  plan_number: 'PAY-2026-001',
  stage_name: '二期尾款',
  planned_amount: 120000,
  due_date: '2026-08-01',
  status: 'PARTIAL',
  paid_amount: 60000,
  remaining_amount: 60000,
  payment_records: [paymentRecordFixture()],
  contract_name: '年度服务合同',
  customer_name: '上海测试客户',
  invoice_count: 2,
  invoiced_amount: 50000,
  created_time: '2026-07-01T00:00:00.000Z',
  last_modified_time: '2026-07-10T00:00:00.000Z',
  ...overrides,
})

const getButtonByText = (wrapper: VueWrapper, text: string): DOMWrapper<Element> => {
  const button = wrapper.findAll('button').find((candidate) => candidate.text().includes(text))
  if (button === undefined) {
    throw new Error(`Button not found: ${text}`)
  }
  return button
}

const sourceText = (): string => readFileSync(
  `${process.cwd()}/src/views/PaymentPlanDetailSheet.vue`,
  'utf8'
)

describe('PaymentPlanDetailSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    paymentApi.getPaymentPlanDetail.mockResolvedValue(paymentPlanFixture())
  })

  it('loads and renders the payment plan single-panel sheet foundation', async () => {
    const wrapper = mount(PaymentPlanDetailSheet, {
      props: {
        visible: true,
        planId: 101,
      },
    })

    await flushPromises()

    expect(paymentApi.getPaymentPlanDetail).toHaveBeenCalledWith(101)
    expect(wrapper.get('[data-testid="sheet-root"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('二期尾款')
    expect(wrapper.get('[data-testid="status-badge"]').attributes('data-status')).toBe('partial')
    expect(wrapper.text()).toContain('¥120,000.00')
    expect(wrapper.text()).toContain('¥60,000.00')
    expect(wrapper.text()).toContain('上海测试客户')
    expect(wrapper.text()).toContain('年度服务合同')
    expect(wrapper.text()).toContain('2026-08-01')
    expect(wrapper.text()).toContain('¥50,000.00')
    expect(wrapper.text()).toContain('2 张')
    expect(wrapper.get('[data-testid="payment-record-list"]').attributes('data-record-count')).toBe('1')
  })

  it('emits navigation, register, record click, and submit approval seams without routing', async () => {
    const plan = paymentPlanFixture()
    paymentApi.getPaymentPlanDetail.mockResolvedValue(plan)
    const wrapper = mount(PaymentPlanDetailSheet, {
      props: {
        visible: true,
        planId: 101,
      },
    })

    await flushPromises()

    await wrapper.get('[aria-label="查看客户 上海测试客户"]').trigger('click')
    await wrapper.get('[aria-label="查看合同 年度服务合同"]').trigger('click')
    await wrapper.get('[data-testid="record-register"]').trigger('click')
    await wrapper.get('[data-testid="record-click"]').trigger('click')
    await getButtonByText(wrapper, '提交审批').trigger('click')

    expect(wrapper.emitted('view-customer')?.[0]).toEqual([303, plan])
    expect(wrapper.emitted('view-contract')?.[0]).toEqual([202, plan])
    expect(wrapper.emitted('register-payment')?.[0]).toEqual([plan])
    expect(wrapper.emitted('record-click')?.[0]).toEqual([plan.payment_records[0]])
    expect(wrapper.emitted('submit-approval')?.[0]).toEqual([plan, 501])
  })

  it('renders rejected approval progress and emits the resubmit approval seam', async () => {
    const rejectedPlan = paymentPlanFixture({
      latest_approval: {
        id: 7001,
        status: 'REJECTED',
        submitter_id: 'u-1',
        submitter_name: '张三',
        created_time: '2026-07-10T09:30:00.000Z',
        reject_reason: '金额凭证不一致',
        nodes: [
          {
            id: 1,
            node_order: 1,
            node_name: '财务复核',
            approve_role: 'FINANCE_MANAGER',
            status: 'REJECT',
            approver_name: '财务经理',
            approved_time: '2026-07-10T10:00:00.000Z',
            comment: '金额凭证不一致',
          },
        ],
      },
    })
    paymentApi.getPaymentPlanDetail.mockResolvedValue(rejectedPlan)
    const wrapper = mount(PaymentPlanDetailSheet, {
      props: {
        visible: true,
        planId: 101,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('审批进度')
    expect(wrapper.text()).toContain('审批被驳回')
    expect(wrapper.text()).toContain('金额凭证不一致')
    expect(wrapper.text()).toContain('财务复核')

    await getButtonByText(wrapper, '重新提交审批').trigger('click')

    expect(wrapper.emitted('resubmit-approval')?.[0]).toEqual([rejectedPlan, 501])
  })

  it('keeps the sheet source on V2 primitives without Element Plus imports', () => {
    const source = sourceText()

    expect(source).toContain('variables-v2.scss')
    expect(source).not.toMatch(/<el-/)
    expect(source).not.toContain('element-plus')
    expect(source).not.toContain('@element-plus')
    expect(source).not.toContain('variables.scss')
  })
})
