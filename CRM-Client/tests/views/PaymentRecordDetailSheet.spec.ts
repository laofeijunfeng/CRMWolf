import { readFileSync } from 'node:fs'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import type {
  ApprovalInfo,
  ApprovalInfoLite,
  ApprovalNodeInfo,
  PaymentRecordInfo
} from '@/api/payment'

// Type for component's local PaymentRecordDetailInfo
type PaymentRecordDetailInfo = PaymentRecordInfo & {
  record_number?: string
}

const windowOpenMock = vi.fn()
vi.stubGlobal('window', {
  ...globalThis.window,
  open: windowOpenMock
})

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
    props: {
      variant: String,
      role: String,
    },
    setup: (props, { slots, attrs }) => () => h('span', { ...attrs, role: props.role ?? 'status' }, slots.default?.()),
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

vi.mock('@/components/ui/alert', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  })

  return {
    Alert: passthrough('Alert'),
    AlertTitle: passthrough('AlertTitle'),
    AlertDescription: passthrough('AlertDescription'),
  }
})

vi.mock('@/components/ApprovalProcessStepper.vue', () => ({
  default: defineComponent({
    name: 'ApprovalProcessStepper',
    props: {
      records: {
        type: Array as PropType<Array<{
          node_name: string | null
          action: string | null
          approver_name: string | null
        }>>,
        default: () => [],
      },
      isPending: Boolean,
    },
    setup: (props) => () => h(
      'div',
      {
        'data-testid': 'approval-process-stepper',
        'data-pending': String(props.isPending),
      },
      [
        ...props.records.map((record) => h(
          'span',
          [record.node_name, record.action, record.approver_name].filter(Boolean).join(' ')
        )),
        props.isPending ? h('span', '审批中') : null,
      ]
    ),
  }),
}))

import PaymentRecordDetailSheet from '@/views/PaymentRecordDetailSheet.vue'

const paymentRecordFixture = (overrides: Partial<PaymentRecordDetailInfo> = {}): PaymentRecordDetailInfo => ({
  id: 501,
  actual_amount: 60000,
  payment_date: '2026-07-10',
  creator_name: '张三',
  confirmation_status: 'PENDING',
  created_time: '2026-07-10T09:30:00.000Z',
  ...overrides,
})

const approvalNodeFixture = (overrides: Partial<ApprovalNodeInfo> = {}): ApprovalNodeInfo => ({
  id: 1,
  node_order: 1,
  node_name: '财务复核',
  approve_role: 'FINANCE_MANAGER',
  status: 'PENDING',
  ...overrides,
})

const approvalInfoFixture = (overrides: Partial<ApprovalInfo> = {}): ApprovalInfo => ({
  id: 7001,
  status: 'PENDING',
  submitter_id: 'u-1',
  submitter_name: '张三',
  created_time: '2026-07-10T09:30:00.000Z',
  nodes: [approvalNodeFixture()],
  ...overrides,
})

const approvalInfoLiteFixture = (overrides: Partial<ApprovalInfoLite> = {}): ApprovalInfoLite => ({
  id: 7001,
  status: 'PENDING',
  nodes: [approvalNodeFixture()],
  ...overrides,
})

const sourceText = (): string => readFileSync(
  `${process.cwd()}/src/views/PaymentRecordDetailSheet.vue`,
  'utf8'
)

describe('PaymentRecordDetailSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    windowOpenMock.mockReset()
  })

  describe('Empty state rendering', () => {
    it('renders empty state when no record is provided', () => {
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: null,
          record: null,
        },
      })

      expect(wrapper.get('[data-testid="sheet-root"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('暂无回款记录信息')
      expect(wrapper.text()).toContain('请选择一个回款记录查看详情')
    })

    it('does not render empty state when record is provided', () => {
      const record = paymentRecordFixture()
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).not.toContain('暂无回款记录信息')
    })
  })

  describe('Record display', () => {
    it('renders record number in header when provided', () => {
      const record = paymentRecordFixture({ record_number: 'REC-2026-001' })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('REC-2026-001')
    })

    it('renders fallback title when record_number is not provided', () => {
      const record = paymentRecordFixture()
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('回款记录详情')
    })

    it('renders stage name when provided', () => {
      const record = paymentRecordFixture()
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          stageName: '二期尾款',
        },
      })

      expect(wrapper.text()).toContain('二期尾款')
    })

    it('renders payment date', () => {
      const record = paymentRecordFixture({ payment_date: '2026-07-10' })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('2026-07-10')
    })

    it('renders amount with currency format', () => {
      const record = paymentRecordFixture({ actual_amount: 60000 })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('¥60,000.00')
    })

    it('renders creator name', () => {
      const record = paymentRecordFixture({ creator_name: '李四' })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('李四')
    })

    it('renders fallback text for missing creator name', () => {
      const record = paymentRecordFixture({ creator_name: '' })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('未知登记人')
    })

    it('renders notes when provided', () => {
      const record = paymentRecordFixture({ notes: '这是备注内容' })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).toContain('这是备注内容')
    })

    it('does not render notes section when notes is empty', () => {
      const record = paymentRecordFixture({ notes: undefined })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      expect(wrapper.text()).not.toContain('备注')
    })
  })

  describe('Approval display with full ApprovalInfo', () => {
    it('renders approval progress section when approval is provided', () => {
      const record = paymentRecordFixture()
      const approval = approvalInfoFixture()
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          approval,
        },
      })

      expect(wrapper.text()).toContain('审批进度')
      expect(wrapper.text()).toContain('审批中')
    })

    it('renders approval records through ApprovalProcessStepper', () => {
      const record = paymentRecordFixture()
      const approval = approvalInfoFixture({
        nodes: [
          approvalNodeFixture({ node_name: '财务复核', status: 'APPROVED' }),
          approvalNodeFixture({ id: 2, node_order: 2, node_name: '总经理审批', status: 'PENDING' }),
        ],
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          approval,
        },
      })

      expect(wrapper.find('[data-testid="approval-process-stepper"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('提交申请')
      expect(wrapper.text()).toContain('财务复核')
      expect(wrapper.text()).toContain('APPROVE')
    })

    it('renders rejection reason when approval is rejected', () => {
      const record = paymentRecordFixture()
      const approval = approvalInfoFixture({
        status: 'REJECTED',
        reject_reason: '金额凭证不一致',
        nodes: [
          approvalNodeFixture({
            status: 'REJECT',
            comment: '金额凭证不一致',
          }),
        ],
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          approval,
        },
      })

      expect(wrapper.text()).toContain('审批被驳回')
      expect(wrapper.text()).toContain('金额凭证不一致')
    })

    it('renders submission time from full ApprovalInfo', () => {
      const record = paymentRecordFixture()
      const approval = approvalInfoFixture({
        created_time: '2026-07-10T09:30:00.000Z',
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          approval,
        },
      })

      expect(wrapper.text()).toContain('2026-07-10')
    })
  })

  describe('Approval display with ApprovalInfoLite', () => {
    it('renders approval progress with lite approval info', () => {
      const record = paymentRecordFixture()
      const approvalLite = approvalInfoLiteFixture({
        status: 'PENDING',
        nodes: [approvalNodeFixture({ node_name: '财务复核' })],
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          approval: approvalLite,
        },
      })

      expect(wrapper.text()).toContain('审批进度')
      expect(wrapper.find('[data-testid="approval-process-stepper"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('提交申请')
    })

    it('does not crash when ApprovalInfoLite lacks created_time', () => {
      const record = paymentRecordFixture()
      const approvalLite: ApprovalInfoLite = {
        id: 7001,
        status: 'PENDING',
        nodes: [approvalNodeFixture()],
      }
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
          approval: approvalLite,
        },
      })

      // Should render without crashing
      expect(wrapper.get('[data-testid="sheet-root"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('审批进度')
    })
  })

  describe('Voucher link behavior', () => {
    it('renders voucher button for PDF attachments', () => {
      const record = paymentRecordFixture({
        proof_attachment: 'https://example.com/voucher.pdf',
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      const button = wrapper.find('button[aria-label="查看凭证附件，将在新标签页打开"]')
      expect(button.exists()).toBe(true)
      expect(button.text()).toContain('查看凭证')
    })

    it('does not render voucher section when proof_attachment is empty', () => {
      const record = paymentRecordFixture({ proof_attachment: '' })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      // Should not have voucher section
      expect(wrapper.find('[aria-label*="查看凭证"]').exists()).toBe(false)
    })

    it('renders inline image preview for image URLs', () => {
      const record = paymentRecordFixture({
        proof_attachment: 'https://example.com/voucher.jpg',
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      const img = wrapper.find('img.voucher-image')
      expect(img.exists()).toBe(true)
      expect(img.attributes('src')).toBe('https://example.com/voucher.jpg')
      expect(img.attributes('loading')).toBe('lazy')
      expect(img.attributes('alt')).toBe('凭证附件预览')
    })

    it('renders view original button for image attachments', () => {
      const record = paymentRecordFixture({
        proof_attachment: 'https://example.com/voucher.png',
      })
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      const img = wrapper.find('img.voucher-image')
      expect(img.exists()).toBe(true)

      // Verify there's a button to view original
      const buttons = wrapper.findAll('button')
      const viewOriginalButton = buttons.find((b) => b.text().includes('查看原图'))
      expect(viewOriginalButton).toBeDefined()
    })

    it('detects various image extensions correctly', () => {
      const testCases = [
        { url: 'https://example.com/image.jpg', expectImage: true },
        { url: 'https://example.com/image.jpeg', expectImage: true },
        { url: 'https://example.com/image.png', expectImage: true },
        { url: 'https://example.com/image.gif', expectImage: true },
        { url: 'https://example.com/image.webp', expectImage: true },
        { url: 'https://example.com/image.svg', expectImage: true },
        { url: 'https://example.com/document.pdf', expectImage: false },
        { url: 'https://example.com/document.docx', expectImage: false },
      ]

      for (const { url, expectImage } of testCases) {
        const record = paymentRecordFixture({ proof_attachment: url })
        const wrapper = mount(PaymentRecordDetailSheet, {
          props: {
            visible: true,
            recordId: record.id,
            record,
          },
        })

        const img = wrapper.find('img.voucher-image')
        expect(img.exists()).toBe(expectImage)
      }
    })
  })

  describe('Close behavior', () => {
    it('renders close button', () => {
      const record = paymentRecordFixture()
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      const closeButtons = wrapper.findAll('button').filter((b) => b.text().includes('关闭'))
      expect(closeButtons.length).toBeGreaterThan(0)
    })

    it('has correct button structure for close action', () => {
      const record = paymentRecordFixture()
      const wrapper = mount(PaymentRecordDetailSheet, {
        props: {
          visible: true,
          recordId: record.id,
          record,
        },
      })

      // Find close button by text
      const closeButtons = wrapper.findAll('button').filter((b) => b.text().includes('关闭'))
      expect(closeButtons.length).toBeGreaterThan(0)

      // Verify the button has the expected attributes
      const closeButton = closeButtons[0]
      expect(closeButton.attributes('type')).toBe('button')
    })
  })

  describe('Source code compliance', () => {
    it('uses V2 design tokens without Element Plus imports', () => {
      const source = sourceText()

      expect(source).toContain('variables-v2.scss')
      expect(source).not.toMatch(/<el-/)
      expect(source).not.toContain('element-plus')
      expect(source).not.toContain('@element-plus')
      expect(source).not.toContain('variables.scss')
    })

    it('does not use non-null assertions', () => {
      const source = sourceText()

      // Check for non-null assertions in template (formatCreator(props.record!) pattern)
      expect(source).not.toMatch(/formatCreator\(props\.record!\)/)
    })

    it('does not use any type', () => {
      const source = sourceText()

      expect(source).not.toMatch(/: any\b/)
      expect(source).not.toMatch(/as any/)
      expect(source).not.toContain('@ts-ignore')
    })
  })
})
