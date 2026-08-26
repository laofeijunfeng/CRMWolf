import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import FollowUpFormDialog from '@/components/dialogs/FollowUpFormDialog.vue'

const customerActivityApi = vi.hoisted(() => ({
  createActivity: vi.fn(),
  createActivityAndCompleteTracking: vi.fn(),
}))
const toast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('@/api/customerActivity', () => ({ default: customerActivityApi }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/ui/dialog', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  })

  return {
    Dialog: passthrough('Dialog'),
    DialogContent: passthrough('DialogContent'),
    DialogDescription: passthrough('DialogDescription'),
    DialogFooter: passthrough('DialogFooter'),
    DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle'),
  }


})

vi.mock('@/components/ui/alert-dialog', () => {
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  })

  return {
    AlertDialog: passthrough('AlertDialog'),
    AlertDialogAction: passthrough('AlertDialogAction'),
    AlertDialogCancel: passthrough('AlertDialogCancel'),
    AlertDialogContent: passthrough('AlertDialogContent'),
    AlertDialogDescription: passthrough('AlertDialogDescription'),
    AlertDialogFooter: passthrough('AlertDialogFooter'),
    AlertDialogHeader: passthrough('AlertDialogHeader'),
    AlertDialogTitle: passthrough('AlertDialogTitle'),
  }
})

vi.mock('@/components/ui/form', async () => {
  const { defineComponent, h } = await import('vue')
  const { Field } = await import('vee-validate')
  const passthrough = (name: string) => defineComponent({
    name,
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  })

  return {
    FormField: Field,
    FormItem: passthrough('FormItem'),
    FormMessage: passthrough('FormMessage'),
  }
})

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String },
    setup: (props, { slots }) => () => h('button', { type: props.type ?? 'button' }, slots.default?.()),
  }),
}))

vi.mock('@/components/crmwolf', () => {
  const SegmentedChoiceControl = defineComponent({
    name: 'SegmentedChoiceControl',
    props: { modelValue: { type: String, default: '' } },
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('button', {
      type: 'button',
      'data-testid': 'follow-up-method',
      'data-value': props.modelValue,
      onClick: () => emit('update:modelValue', 'PHONE_FOLLOW_UP'),
    }),
  })

  const TextareaField = defineComponent({
    name: 'TextareaField',
    props: {
      id: { type: String, default: '' },
      modelValue: { type: String, default: '' },
    },
    emits: ['update:modelValue'],
    setup: (props, { emit }) => () => h('textarea', {
      id: props.id,
      value: props.modelValue,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
    }),
  })

  const DateField = defineComponent({
    name: 'DateField',
    props: { id: { type: String, default: '' }, modelValue: { type: Date, default: null } },
    emits: ['update:modelValue'],
    setup: (props) => () => h('div', {
      'data-testid': props.id,
      'data-value': props.modelValue?.toISOString().slice(0, 10) ?? '',
    }),
  })

  return { DateField, SegmentedChoiceControl, TextareaField }
})

function mountDialog(sourceTaskPublicId?: string) {
  return mount(FollowUpFormDialog, {
    props: {
      customerId: 'cus_1',
      open: true,
      sourceTaskPublicId,
    },
  })
}

function getTextareaField(wrapper: ReturnType<typeof mount>, id: string) {
  const field = wrapper.findAllComponents({ name: 'TextareaField' })
    .find((component) => component.props('id') === id)
  if (field === undefined) throw new Error(`textarea field ${id} not found`)
  return field
}

async function fillRequiredFields(wrapper: ReturnType<typeof mount>, content: string) {
  await wrapper.getComponent({ name: 'SegmentedChoiceControl' }).vm.$emit('update:modelValue', 'PHONE_FOLLOW_UP')
  await getTextareaField(wrapper, 'follow-up-content').vm.$emit('update:modelValue', content)
  await flushPromises()
}

async function submitAndWaitForActivity(wrapper: ReturnType<typeof mount>) {
  const form = wrapper.get('form').element
  const documentWindow = form.ownerDocument.defaultView
  if (documentWindow === null) throw new Error('form document window is unavailable')

  form.dispatchEvent(new documentWindow.Event('submit', { bubbles: true, cancelable: true }))
  await vi.waitFor(() => {
    expect(customerActivityApi.createActivity).toHaveBeenCalledTimes(1)
  })
}

function findButtonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === text)
  if (button === undefined) throw new Error(`button ${text} not found`)
  return button
}

describe('FollowUpFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    customerActivityApi.createActivity.mockResolvedValue({})
    customerActivityApi.createActivityAndCompleteTracking.mockResolvedValue({})
  })

  it('submits an activity without creating a next step when optional fields are blank', async () => {
    const wrapper = mountDialog()

    expect(wrapper.get('[data-testid="follow-up-next-time"]').attributes('data-value')).toBe('')

    await fillRequiredFields(wrapper, '客户明确暂时没有需求')
    await submitAndWaitForActivity(wrapper)

    expect(customerActivityApi.createActivity).toHaveBeenCalledWith('cus_1', {
      activity_kind: 'PHONE_FOLLOW_UP',
      source_content: '客户明确暂时没有需求',
      next_follow_time: null,
      next_follow_time_source: null,
      next_action: null,
    })
  })

  it('keeps an explicitly supplied next step and records it as user-provided', async () => {
    const wrapper = mountDialog()

    await fillRequiredFields(wrapper, '客户希望下周继续沟通')
    await wrapper.getComponent({ name: 'DateField' }).vm.$emit('update:modelValue', new Date(2026, 7, 28))
    await getTextareaField(wrapper, 'follow-up-next-action').vm.$emit('update:modelValue', '下周确认预算')
    await flushPromises()
    await submitAndWaitForActivity(wrapper)

    expect(customerActivityApi.createActivity).toHaveBeenCalledWith('cus_1', {
      activity_kind: 'PHONE_FOLLOW_UP',
      source_content: '客户希望下周继续沟通',
      next_follow_time: '2026-08-28',
      next_follow_time_source: 'USER',
      next_action: '下周确认预算',
    })
  })

  it('only shows “提交并完成追踪” when the dialog is opened from a tracking task', async () => {
    const ordinaryDialog = mountDialog()
    expect(ordinaryDialog.text()).not.toContain('提交并完成追踪')

    const trackingDialog = mountDialog('fut_1')
    expect(trackingDialog.text()).toContain('提交并完成追踪')

    await fillRequiredFields(trackingDialog, '客户确认本轮不再继续')
    await findButtonByText(trackingDialog, '提交并完成追踪').trigger('click')

    await vi.waitFor(() => {
      expect(customerActivityApi.createActivityAndCompleteTracking).toHaveBeenCalledTimes(1)
    })
    expect(customerActivityApi.createActivityAndCompleteTracking).toHaveBeenCalledWith('cus_1', 'fut_1', {
      activity_kind: 'PHONE_FOLLOW_UP',
      source_content: '客户确认本轮不再继续',
      next_follow_time: null,
      next_follow_time_source: null,
      next_action: null,
    })
    expect(customerActivityApi.createActivity).not.toHaveBeenCalled()
  })

})
