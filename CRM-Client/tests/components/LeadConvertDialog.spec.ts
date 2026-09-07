import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import LeadConvertDialog from '@/components/LeadConvertDialog.vue'

const mocks = vi.hoisted(() => ({
  getLeadDetail: vi.fn(),
  getProcurementMethodOptions: vi.fn(),
  confirmDialog: vi.fn(),
}))

vi.mock('@/api/lead', () => ({
  leadApi: { getLeadDetail: mocks.getLeadDetail },
}))

vi.mock('@/api/procurement', () => ({
  default: { getProcurementMethodOptions: mocks.getProcurementMethodOptions },
}))

vi.mock('@/api/customer', () => ({
  default: { convertLeadToCustomer: vi.fn() },
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: mocks.confirmDialog,
}))

vi.mock('@/components/ui/dialog', () => {
  const passthrough = (name: string, tag = 'div') => defineComponent({
    name,
    setup: (_props, { slots, attrs }) => () => h(tag, attrs, slots.default?.()),
  })

  return {
    Dialog: defineComponent({
      name: 'Dialog',
      props: { open: Boolean },
      setup: (props, { slots }) => () => props.open
        ? h('section', { role: 'dialog' }, slots.default?.())
        : null,
    }),
    DialogContent: passthrough('DialogContent'),
    DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle', 'h2'),
    DialogDescription: passthrough('DialogDescription', 'p'),
    DialogFooter: passthrough('DialogFooter'),
  }
})

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, disabled: Boolean },
    setup: (props, { slots, attrs }) => () => h(
      'button',
      { ...attrs, type: props.type ?? 'button', disabled: props.disabled },
      slots.default?.(),
    ),
  }),
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: defineComponent({
    name: 'Skeleton',
    setup: (_props, { attrs }) => () => h('div', { ...attrs, 'data-skeleton': 'true' }),
  }),
}))

vi.mock('@/components/crmwolf/FeedbackAlert.vue', () => ({
  default: defineComponent({
    name: 'FeedbackAlert',
    props: { error: Object, density: String, retryLabel: String },
    emits: ['retry'],
    setup: (props, { emit }) => () => h('button', {
      type: 'button',
      'data-feedback-alert': 'true',
      onClick: () => emit('retry'),
    }, props.retryLabel ?? '重试'),
  }),
}))

vi.mock('@/components/crmwolf', () => {
  const field = (tag: 'input' | 'select') => defineComponent({
    inheritAttrs: false,
    props: { id: String, disabled: Boolean, modelValue: [String, Number], label: String, options: Array },
    setup: (props, { attrs }) => () => h('div', [
      h(tag, {
        ...attrs,
        id: props.id,
        disabled: props.disabled,
        value: props.modelValue ?? '',
      }),
    ]),
  })

  return {
    InputField: field('input'),
    SelectField: field('select'),
  }
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => { resolve = nextResolve })
  return { promise, resolve }
}

const leadFixture = {
  id: 'lead-1',
  lead_name: '飞驰科技',
  city: '上海',
  contact_name: '张三',
  contact_phone: '13800000000',
  company_scale: '100-499人',
  owner_info: { name: '李四' },
  acquisition_source: 'referral',
}

describe('LeadConvertDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getProcurementMethodOptions.mockResolvedValue([{ id: 1, name: '订阅' }])
    mocks.confirmDialog.mockResolvedValue(false)
  })

  it('keeps the dialog open with recovery feedback when lead context loading fails', async () => {
    const serverError = Object.assign(new Error('接口异常'), {
      response: { status: 500 },
    })
    mocks.getLeadDetail
      .mockRejectedValueOnce(serverError)
      .mockResolvedValueOnce(leadFixture)

    const wrapper = mount(LeadConvertDialog, {
      props: { open: true, leadId: 'lead-1' },
    })
    await flushPromises()

    expect(wrapper.emitted('update:open')).toBeUndefined()
    expect(wrapper.get('[data-feedback-alert]').text()).toContain('重新加载线索信息')
    expect(wrapper.get('#lead-convert-account-name').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-feedback-alert]').trigger('click')
    await flushPromises()

    expect(mocks.getLeadDetail).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.find('[data-feedback-alert]').exists()).toBe(false)
  })

  it('keeps the loading placeholder until both context requests finish', async () => {
    const leadRequest = deferred<typeof leadFixture>()
    const procurementRequest = deferred<Array<{ id: number; name: string }>>()
    mocks.getLeadDetail.mockReturnValue(leadRequest.promise)
    mocks.getProcurementMethodOptions.mockReturnValue(procurementRequest.promise)

    const wrapper = mount(LeadConvertDialog, {
      props: { open: true, leadId: 'lead-1' },
    })

    leadRequest.resolve(leadFixture)
    await flushPromises()

    expect(wrapper.findAll('.lead-convert-dialog__loading-card').length).toBeGreaterThan(0)
    expect(wrapper.text()).not.toContain('飞驰科技')

    procurementRequest.resolve([{ id: 1, name: '订阅' }])
    await flushPromises()

    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.findAll('.lead-convert-dialog__loading-card')).toHaveLength(0)
  })

  it('keeps a structured loading placeholder and stable disabled form while lead data is loading', async () => {
    const leadRequest = deferred<typeof leadFixture>()
    mocks.getLeadDetail.mockReturnValue(leadRequest.promise)

    const wrapper = mount(LeadConvertDialog, {
      props: { open: true, leadId: 'lead-1' },
    })

    expect(wrapper.get('.lead-convert-dialog__body')).toBeTruthy()
    expect(wrapper.findAll('.lead-convert-dialog__loading-card').length).toBeGreaterThan(0)
    expect(wrapper.get('#lead-convert-account-name').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#lead-convert-city').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#lead-convert-procurement-method').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('获取线索详情失败')

    leadRequest.resolve(leadFixture)
    await flushPromises()

    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.findAll('.lead-convert-dialog__loading-card')).toHaveLength(0)
  })
})
