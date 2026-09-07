import { describe, expect, it, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import PaymentRecordDialog from '@/components/dialogs/PaymentRecordDialog.vue'
import { handleApiError } from '@/utils/errorHandler'

const mocks = vi.hoisted(() => ({
  confirmDialog: vi.fn(),
  getPaymentPlanDetail: vi.fn(),
  getCustomerMemberCandidates: vi.fn(),
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: mocks.confirmDialog,
}))

vi.mock('@/api/payment', () => ({
  default: {
    getPaymentPlanDetail: mocks.getPaymentPlanDetail,
  },
}))

vi.mock('@/api/customer', () => ({
  default: {
    getCustomerMemberCandidates: mocks.getCustomerMemberCandidates,
    addCustomerMember: vi.fn(),
  },
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({
    userInfo: { id: 'user-1', name: '测试用户' },
  }),
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
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
      emits: ['update:open'],
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
    props: {
      type: String,
      variant: String,
      disabled: Boolean,
    },
    setup: (props, { slots, attrs }) => () => h(
      'button',
      { ...attrs, type: props.type ?? 'button', disabled: props.disabled },
      slots.default?.(),
    ),
  }),
}))

vi.mock('@/components/ui/label', () => ({
  Label: defineComponent({
    name: 'Label',
    setup: (_props, { slots, attrs }) => () => h('label', attrs, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/select', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_props, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  })

  return {
    Select: passthrough('Select'),
    SelectContent: passthrough('SelectContent'),
    SelectItem: passthrough('SelectItem'),
    SelectTrigger: passthrough('SelectTrigger'),
    SelectValue: passthrough('SelectValue'),
  }
})

vi.mock('@/components/crmwolf', () => {
  const InputField = defineComponent({
    name: 'InputField',
    inheritAttrs: false,
    props: {
      id: String,
      name: String,
      modelValue: [String, Number],
      label: String,
      type: String,
      disabled: Boolean,
      error: String,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('div', [
      h('label', { for: props.id }, props.label),
      h('input', {
        ...attrs,
        id: props.id,
        name: props.name,
        type: props.type ?? 'text',
        value: props.modelValue ?? '',
        disabled: props.disabled,
        'aria-invalid': props.error ? 'true' : undefined,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      }),
      props.error ? h('p', { role: 'alert' }, props.error) : null,
    ]),
  })

  const TextareaField = defineComponent({
    name: 'TextareaField',
    inheritAttrs: false,
    props: {
      id: String,
      name: String,
      modelValue: String,
      label: String,
      disabled: Boolean,
      error: String,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('div', [
      h('label', { for: props.id }, props.label),
      h('textarea', {
        ...attrs,
        id: props.id,
        name: props.name,
        value: props.modelValue ?? '',
        disabled: props.disabled,
        'aria-invalid': props.error ? 'true' : undefined,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
      }),
      props.error ? h('p', { role: 'alert' }, props.error) : null,
    ]),
  })

  const DateField = defineComponent({
    name: 'DateField',
    props: {
      id: String,
      modelValue: Date,
      label: String,
      disabled: Boolean,
      error: String,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => {
      const value = props.modelValue instanceof Date
        ? `${props.modelValue.getFullYear()}-${String(props.modelValue.getMonth() + 1).padStart(2, '0')}-${String(props.modelValue.getDate()).padStart(2, '0')}`
        : ''
      return h('div', [
        h('label', { for: props.id }, props.label),
        h('input', {
          id: props.id,
          name: 'payment_date',
          type: 'date',
          value,
          disabled: props.disabled,
          'aria-invalid': props.error ? 'true' : undefined,
          onInput: (event: Event) => {
            const nextValue = (event.target as HTMLInputElement).value
            emit('update:modelValue', nextValue === '' ? null : new Date(`${nextValue}T00:00:00`))
          },
        }),
        props.error ? h('p', { role: 'alert' }, props.error) : null,
      ])
    },
  })

  return { DateField, InputField, TextareaField }
})

function findButton(wrapper: ReturnType<typeof mount>, label: string) {
  const button = wrapper.findAll('button').find(item => item.text().trim() === label)
  if (button === undefined) throw new Error(`未找到按钮：${label}`)
  return button
}

async function openSupplementArea(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('button.payment-record-dialog__supplement-trigger').trigger('click')
}


function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

describe('PaymentRecordDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.confirmDialog.mockResolvedValue(false)
    mocks.getCustomerMemberCandidates.mockResolvedValue([])
  })

  it('预填默认信息并提交类型正确的回款登记参数', async () => {
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: 1234.56,
        defaultPayerName: '测试客户',
      },
    })

    expect((wrapper.get('input[name="actual_amount"]').element as HTMLInputElement).value).toBe('1234.56')

    await wrapper.get('input[name="payment_date"]').setValue('2026-07-16')
    await openSupplementArea(wrapper)
    await wrapper.get('input[name="proof_attachment"]').setValue('https://example.com/proof.pdf')
    await wrapper.get('textarea[name="notes"]').setValue('首笔回款')
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.emitted('submit')?.[0]).toEqual([{
      actual_amount: 1234.56,
      actual_payer_name: '测试客户',
      payment_date: '2026-07-16',
      proof_attachment: 'https://example.com/proof.pdf',
      commission_member_id: 'user-1',
      notes: '首笔回款',
    }])
  })

  it('用可访问的字段错误校验金额和回款日期', async () => {
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: null,
        defaultPayerName: '测试客户',
      },
    })

    await wrapper.get('input[name="actual_amount"]').setValue('0')
    await wrapper.get('input[name="payment_date"]').setValue('')
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('请输入大于 0 的回款金额')
    expect(wrapper.text()).toContain('请选择回款日期')
    expect(wrapper.text()).toContain('请先修正以下字段：')
    expect(wrapper.get('input[name="actual_amount"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('input[name="payment_date"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(3)
  })

  it('用紧凑摘要展示回款计划上下文并折叠低频信息', async () => {
    mocks.getPaymentPlanDetail.mockResolvedValue({
      id: 18,
      customer_id: 'customer-1',
      customer_name: '飞驰科技',
      contract_name: '年度服务合同',
      stage_name: '首付款',
      plan_number: 'PP-2026-0018',
      planned_amount: 100000,
      paid_amount: 30000,
      remaining_amount: 70000,
      status: 'PARTIAL',
    })

    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        paymentPlanId: 18,
        defaultAmount: 70000,
        defaultPayerName: '飞驰科技',
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('客户')
    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.text()).toContain('年度服务合同')
    expect(wrapper.text()).toContain('首付款')
    expect(wrapper.text()).toContain('部分回款')
    expect(wrapper.text()).toContain('待回款')
    expect(wrapper.text()).toContain('¥70,000.00')

    const detailsTrigger = wrapper.get('button.selection-summary__details-trigger')
    expect(detailsTrigger.attributes('aria-expanded')).toBe('false')
    await detailsTrigger.trigger('click')

    expect(detailsTrigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.text()).toContain('计划编号')
    expect(wrapper.text()).toContain('PP-2026-0018')
    expect(wrapper.text()).toContain('计划金额')
    expect(wrapper.text()).toContain('¥100,000.00')
    expect(mocks.getCustomerMemberCandidates).toHaveBeenCalledWith('customer-1')
  })

  it('上下文加载时保持弹窗结构稳定并允许表单先呈现', async () => {
    const plan = {
      id: 18,
      customer_id: 'customer-1',
      customer_name: '飞驰科技',
      contract_name: '年度服务合同',
      stage_name: '首付款',
      plan_number: 'PP-2026-0018',
      planned_amount: 100000,
      paid_amount: 30000,
      remaining_amount: 70000,
      status: 'PARTIAL',
    }
    const planDeferred = createDeferred<typeof plan>()
    const membersDeferred = createDeferred<[]>()
    mocks.getPaymentPlanDetail.mockReturnValue(planDeferred.promise)
    mocks.getCustomerMemberCandidates.mockReturnValue(membersDeferred.promise)

    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        paymentPlanId: 18,
        defaultAmount: 70000,
        defaultPayerName: '飞驰科技',
      },
    })
    await nextTick()

    const loadingSummary = wrapper.get('.selection-summary[role="status"]')
    expect(loadingSummary.attributes('aria-busy')).toBe('true')
    expect(loadingSummary.attributes('aria-label')).toBe('正在加载回款计划上下文')
    expect(wrapper.findAll('.selection-summary__skeleton-value')).toHaveLength(5)
    expect(wrapper.get('input[name="actual_amount"]').exists()).toBe(true)
    expect(wrapper.find('.selection-summary__details-trigger').exists()).toBe(false)

    planDeferred.resolve(plan)
    await flushPromises()

    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.text()).toContain('¥70,000.00')
    expect(wrapper.find('.selection-summary__skeleton-value').exists()).toBe(false)
    expect(wrapper.get('button.selection-summary__details-trigger').exists()).toBe(true)

    membersDeferred.resolve([])
    await flushPromises()
  })

  it('上下文加载失败时使用统一反馈且不重复 toast', async () => {
    mocks.getPaymentPlanDetail.mockRejectedValue(Object.assign(new Error('server error'), {
      response: { status: 500 },
    }))

    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        paymentPlanId: 18,
        defaultAmount: 70000,
        defaultPayerName: '飞驰科技',
      },
    })
    await flushPromises()

    const alert = wrapper.get('[role="alert"].feedback-alert')
    expect(alert.text()).toContain('回款计划和团队成员加载失败')
    expect(alert.text()).toContain('服务器暂时无法处理请求')
    expect(handleApiError).not.toHaveBeenCalled()

    await wrapper.get('.feedback-alert button').trigger('click')
    await flushPromises()

    expect(mocks.getPaymentPlanDetail).toHaveBeenCalledTimes(2)
  })

  it('将可选回款信息放入补充信息折叠区', async () => {
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: 5000,
        defaultPayerName: '测试客户',
      },
    })

    const supplementTrigger = wrapper.get('button.payment-record-dialog__supplement-trigger')
    expect(supplementTrigger.attributes('aria-expanded')).toBe('false')

    await supplementTrigger.trigger('click')

    expect(supplementTrigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('input[name="proof_attachment"]').exists()).toBe(true)
    expect(wrapper.find('textarea[name="notes"]').exists()).toBe(true)
  })

  it('默认值未修改时直接关闭，不弹放弃确认', async () => {
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: 5000,
        defaultPayerName: '测试客户',
      },
    })

    await findButton(wrapper, '取消').trigger('click')
    await flushPromises()

    expect(mocks.confirmDialog).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  })

  it('修改内容后关闭时保护未保存输入', async () => {
    mocks.confirmDialog.mockResolvedValue(true)
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: 5000,
        defaultPayerName: '测试客户',
      },
    })

    await openSupplementArea(wrapper)
    await wrapper.get('textarea[name="notes"]').setValue('需要核对银行流水')
    await findButton(wrapper, '取消').trigger('click')
    await flushPromises()

    expect(mocks.confirmDialog).toHaveBeenCalledWith(
      '已填写回款信息，关闭后这些内容不会保存。确定关闭吗？',
      '放弃本次回款登记？',
      { variant: 'destructive', confirmText: '放弃并关闭' },
    )
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  })

  it('使用设计系统字段组件且没有不安全的 TypeScript 逃逸', async () => {
    const source = await import('node:fs').then(({ readFileSync }) => readFileSync(
      `${process.cwd()}/src/components/dialogs/PaymentRecordDialog.vue`,
      'utf8',
    ))

    expect(source).toContain('@/components/ui/dialog')
    expect(source).toContain('@/components/ui/button')
    expect(source).toContain('@/components/crmwolf')
    expect(source).toContain('DialogDescription')
    expect(source).toContain('InputField')
    expect(source).toContain('TextareaField')
    expect(source).toContain('variables-v2.scss')
    expect(source).not.toContain('as any')
    expect(source).not.toContain('@ts-ignore')
    expect(source).not.toContain('toISOString')
  })
})
