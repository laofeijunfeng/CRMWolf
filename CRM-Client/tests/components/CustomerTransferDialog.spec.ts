import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import CustomerTransferDialog from '@/components/dialogs/CustomerTransferDialog.vue'
import type { CustomerResponse } from '@/api/customer'

const mocks = vi.hoisted(() => ({
  getTeamMembers: vi.fn(),
  assignCustomer: vi.fn(),
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/types/feedback', () => ({
  toFeedbackError: vi.fn((_error: unknown, context: string) => ({
    kind: 'unknown',
    title: `${context}加载失败`,
    description: '请重试',
  })),
}))
vi.mock('@/components/ui/alert-dialog', () => {
  const passthrough = (name: string, tag = 'div') => defineComponent({
    name,
    setup: (_props, { slots, attrs }) => () => h(tag, attrs, slots.default?.()),
  })

  return {
    AlertDialog: defineComponent({
      name: 'AlertDialog',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open
        ? h('section', { role: 'alertdialog' }, slots.default?.())
        : null,
    }),
    AlertDialogAction: passthrough('AlertDialogAction', 'button'),
    AlertDialogCancel: passthrough('AlertDialogCancel', 'button'),
    AlertDialogContent: passthrough('AlertDialogContent'),
    AlertDialogDescription: passthrough('AlertDialogDescription', 'p'),
    AlertDialogFooter: passthrough('AlertDialogFooter'),
    AlertDialogHeader: passthrough('AlertDialogHeader'),
    AlertDialogTitle: passthrough('AlertDialogTitle', 'h2'),
  }
})
vi.mock('@/api/customer', () => ({
  default: { assignCustomer: mocks.assignCustomer },
}))
vi.mock('@/api/team', () => ({
  teamApi: { getTeamMembers: mocks.getTeamMembers },
}))
vi.mock('@/stores/team', () => ({
  useTeamStore: () => ({
    currentTeam: { id: 'team-1' },
    fetchUserTeams: vi.fn(),
  }),
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
    DialogDescription: passthrough('DialogDescription', 'p'),
    DialogFooter: passthrough('DialogFooter'),
    DialogTitle: passthrough('DialogTitle', 'h2'),
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

vi.mock('@/components/ui/label', () => ({
  Label: defineComponent({
    name: 'Label',
    setup: (_props, { slots, attrs }) => () => h('label', attrs, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/radio-group', () => ({
  RadioGroup: defineComponent({
    name: 'RadioGroup',
    props: { modelValue: String, disabled: Boolean },
    setup: (_props, { slots, attrs }) => () => h('div', attrs, slots.default?.()),
  }),
  RadioGroupItem: defineComponent({
    name: 'RadioGroupItem',
    props: { value: String, id: String },
    setup: (props) => () => h('input', { type: 'radio', id: props.id, value: props.value }),
  }),
}))

vi.mock('@/components/crmwolf', () => ({
  SelectField: defineComponent({
    name: 'SelectField',
    props: {
      id: String,
      modelValue: String,
      options: { type: Array, default: () => [] },
      disabled: Boolean,
      label: String,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('label', [
      props.label,
      h('select', {
        id: props.id,
        value: props.modelValue,
        disabled: props.disabled,
        onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value),
      }, (props.options as Array<{ value: string; label: string }>).map(option =>
        h('option', { value: option.value }, option.label),
      )),
    ]),
  }),
  TextareaField: defineComponent({
    name: 'TextareaField',
    props: { id: String, modelValue: String, label: String, disabled: Boolean },
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('label', [
      props.label,
      h('textarea', {
        id: props.id,
        value: props.modelValue,
        disabled: props.disabled,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
      }),
    ]),
  }),
}))

const customerFixture = (): CustomerResponse => ({
  id: 'customer-1',
  account_name: '飞驰科技',
  owner_id: 'owner-1',
  owner_info: { id: 'owner-1', name: '当前负责人' },
} as CustomerResponse)

describe('CustomerTransferDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getTeamMembers.mockResolvedValue([
      { id: 'owner-1', name: '当前负责人' },
      { id: 'owner-2', name: '新负责人' },
    ])
  })

  it('展示客户、当前负责人和移交后影响范围', async () => {
    const wrapper = mount(CustomerTransferDialog, {
      props: { open: true, customer: customerFixture() },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('飞驰科技')
    expect(wrapper.text()).toContain('当前负责人')
    expect(wrapper.text()).toContain('尚未选择')
    expect(wrapper.text()).toContain('客户 + 跟进中商机')
    expect(wrapper.text()).toContain('关联合同')
  })

  it('没有填写移交内容时直接关闭，不触发放弃确认', async () => {
    const wrapper = mount(CustomerTransferDialog, {
      props: { open: true, customer: customerFixture() },
    })

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  })

  it('填写移交内容后关闭时保护未保存输入', async () => {
    const wrapper = mount(CustomerTransferDialog, {
      props: { open: true, customer: customerFixture() },
    })
    await flushPromises()

    await wrapper.get('textarea#customer-transfer-remark').setValue('交接说明')
    await flushPromises()
    const cancelButton = wrapper.findAll('button').find(button => button.text().includes('取消'))
    if (cancelButton === undefined) throw new Error('未找到取消按钮')
    await cancelButton.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('放弃更改？')
    expect(wrapper.text()).toContain('您有未保存的移交信息，确定要关闭吗？')
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})
