import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import OpportunityWinDialog from '@/components/dialogs/OpportunityWinDialog.vue'
import OpportunityLoseDialog from '@/components/dialogs/OpportunityLoseDialog.vue'
import { handleApiError } from '@/utils/errorHandler'
import type { Opportunity } from '@/api/opportunity'

const mocks = vi.hoisted(() => ({
  confirmDialog: vi.fn(),
  getOpportunity: vi.fn(),
  markAsWon: vi.fn(),
  markAsLost: vi.fn(),
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: mocks.confirmDialog,
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('@/api/opportunity', () => ({
  opportunityApi: {
    getOpportunity: mocks.getOpportunity,
    markAsWon: mocks.markAsWon,
    markAsLost: mocks.markAsLost,
  },
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
      size: String,
      disabled: Boolean,
      loading: Boolean,
    },
    setup: (props, { slots, attrs }) => () => h(
      'button',
      {
        ...attrs,
        type: props.type ?? 'button',
        disabled: props.disabled || props.loading,
      },
      slots.default?.(),
    ),
  }),
}))

vi.mock('@/components/crmwolf', () => {
  const InputField = defineComponent({
    name: 'InputField',
    inheritAttrs: false,
    props: {
      id: String,
      modelValue: [String, Number],
      label: String,
      disabled: Boolean,
    },
    setup: (props, { attrs }) => () => h('div', [
      h('label', { for: props.id }, props.label),
      h('input', {
        ...attrs,
        id: props.id,
        value: props.modelValue ?? '',
        disabled: props.disabled,
      }),
    ]),
  })

  const DateField = defineComponent({
    name: 'DateField',
    inheritAttrs: false,
    props: {
      id: String,
      modelValue: Date,
      label: String,
      disabled: Boolean,
    },
    setup: (props, { attrs }) => () => h('div', [
      h('label', { for: props.id }, props.label),
      h('input', {
        ...attrs,
        id: props.id,
        type: 'date',
        value: props.modelValue instanceof Date
          ? `${props.modelValue.getFullYear()}-${String(props.modelValue.getMonth() + 1).padStart(2, '0')}-${String(props.modelValue.getDate()).padStart(2, '0')}`
          : '',
        disabled: props.disabled,
      }),
    ]),
  })

  const TextareaField = defineComponent({
    name: 'TextareaField',
    inheritAttrs: false,
    props: {
      id: String,
      modelValue: String,
      label: String,
      disabled: Boolean,
    },
    setup: (props, { attrs }) => () => h('div', [
      h('label', { for: props.id }, props.label),
      h('textarea', {
        ...attrs,
        id: props.id,
        value: props.modelValue ?? '',
        disabled: props.disabled,
      }),
    ]),
  })

  return { DateField, InputField, TextareaField }
})

function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

function opportunityFixture(): Opportunity {
  const now = '2026-09-07T10:00:00+08:00'
  return {
    id: 'opp-1',
    public_id: 'OP-1',
    opportunity_number: 'OPP-2026-001',
    opportunity_name: 'CRM 续约商机',
    customer_id: 'customer-1',
    customer_name: '飞驰科技',
    procurement_method_id: null,
    procurement_method_info: null,
    total_amount: 120000,
    user_count: 20,
    unit_price: 6000,
    license_type: 'SUBSCRIPTION',
    subscription_years: 1,
    purchase_type: 'RENEWAL',
    decision_maker_count: null,
    expected_closing_date: '2026-09-30',
    procurement_stage_id: null,
    stage_name: '商务谈判',
    win_probability: 70,
    current_stage_snapshot: null,
    owner_id: 'user-1',
    creator_id: 'user-1',
    status: 0,
    approval_phase: 'approved',
    created_time: now,
    updated_time: now,
    version: 3,
  }
}

describe('Opportunity outcome dialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.confirmDialog.mockResolvedValue(false)
  })

  it('uses a stable context skeleton while loading the win dialog', async () => {
    const deferred = createDeferred<Opportunity>()
    mocks.getOpportunity.mockReturnValue(deferred.promise)

    const wrapper = mount(OpportunityWinDialog, {
      props: { open: true, opportunityId: 'opp-1' },
      attachTo: document.body,
    })

    const summary = wrapper.get('.selection-summary[role="status"]')
    expect(summary.attributes('aria-busy')).toBe('true')
    expect(summary.attributes('aria-label')).toBe('正在加载商机上下文')
    expect(wrapper.findAll('.selection-summary__skeleton-value')).toHaveLength(4)
    expect((wrapper.get('#opportunity-win-amount').element as HTMLInputElement).disabled).toBe(true)
    expect(wrapper.text()).not.toContain('加载商机信息中...')

    deferred.resolve(opportunityFixture())
    await flushPromises()

    expect(wrapper.get('.selection-summary').classes()).toContain('selection-summary--compact')
    expect(wrapper.text()).toContain('CRM 续约商机')
    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.text()).toContain('跟进中')
    expect(wrapper.text()).toContain('提交后状态')
    expect(wrapper.text()).toContain('已赢单')
    expect((wrapper.get('#opportunity-win-amount').element as HTMLInputElement).value).toBe('120000')

    wrapper.unmount()
  })

  it('uses a compact context summary for the lose dialog', async () => {
    mocks.getOpportunity.mockResolvedValue(opportunityFixture())

    const wrapper = mount(OpportunityLoseDialog, {
      props: { open: true, opportunityId: 'opp-1' },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.get('.selection-summary').classes()).toContain('selection-summary--compact')
    expect(wrapper.text()).toContain('CRM 续约商机')
    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.text()).toContain('提交后状态')
    expect(wrapper.text()).toContain('已输单')
    expect((wrapper.get('#opportunity-lose-reason').element as HTMLTextAreaElement).disabled).toBe(false)

    wrapper.unmount()
  })

  it('renders load failures through the shared feedback component without duplicate toast feedback', async () => {
    mocks.getOpportunity.mockRejectedValue(Object.assign(new Error('server error'), {
      response: { status: 500 },
    }))

    const wrapper = mount(OpportunityWinDialog, {
      props: { open: true, opportunityId: 'opp-1' },
      attachTo: document.body,
    })
    await flushPromises()

    const alert = wrapper.get('[role="alert"].feedback-alert')
    expect(alert.text()).toContain('商机详情加载失败')
    expect(alert.text()).toContain('服务器暂时无法处理请求')
    expect(handleApiError).not.toHaveBeenCalled()

    await wrapper.get('.feedback-alert button').trigger('click')
    await flushPromises()

    expect(mocks.getOpportunity).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })
})
