import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import ContactFormDialog from '@/components/dialogs/ContactFormDialog.vue'
import type { ContactResponse } from '@/api/customer'

const customerApi = vi.hoisted(() => ({
  createContact: vi.fn(),
  updateContact: vi.fn(),
}))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn() }))

vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/ui/dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Dialog: defineComponent({
      name: 'Dialog',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open ? h('section', { role: 'dialog' }, slots.default?.()) : null,
    }),
    DialogContent: passthrough('DialogContent'),
    DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle'),
    DialogDescription: passthrough('DialogDescription'),
    DialogFooter: passthrough('DialogFooter'),
  }
})

vi.mock('@/components/ui/alert-dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
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
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    FormField: Field,
    FormControl: passthrough('FormControl'),
    FormItem: passthrough('FormItem'),
    FormLabel: passthrough('FormLabel'),
    FormMessage: passthrough('FormMessage'),
  }
})

vi.mock('@/components/ui/radio-group', async () => {
  const { defineComponent, h, inject, provide } = await import('vue')
  interface RadioContext {
    select: (value: string) => void
  }
  const radioGroupKey = Symbol('RadioGroup')
  return {
    RadioGroup: defineComponent({
      name: 'RadioGroup',
      props: { modelValue: String },
      emits: ['update:modelValue'],
      setup: (props, { emit, slots }) => {
        provide<RadioContext>(radioGroupKey, {
          select: (value: string) => emit('update:modelValue', value),
        })
        return () => h('div', {
          'data-testid': 'gender-radio',
          'data-model-value': props.modelValue ?? '',
        }, slots.default?.())
      },
    }),
    RadioGroupItem: defineComponent({
      name: 'RadioGroupItem',
      props: {
        id: String,
        value: { type: String, required: true },
      },
      setup: (props) => {
        const radioGroup = inject<RadioContext>(radioGroupKey)
        return () => h('button', {
          id: props.id,
          type: 'button',
          'data-testid': `gender-${props.value}`,
          onClick: () => radioGroup?.select(props.value),
        }, props.value)
      },
    }),
  }
})

vi.mock('@/components/ui/label', () => ({
  Label: defineComponent({ name: 'Label', setup: (_, { slots }) => () => h('label', slots.default?.()) }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, loading: Boolean },
    setup: (props, { slots }) => () => h('button', { type: props.type ?? 'button' }, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/input', () => ({
  Input: defineComponent({
    name: 'Input',
    props: { modelValue: [String, Number], type: String, autocomplete: String, placeholder: String },
    emits: ['update:modelValue'],
    setup: (props, { attrs, emit }) => () => h('input', {
      ...attrs,
      type: props.type ?? 'text',
      value: props.modelValue ?? '',
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    }),
  }),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: defineComponent({ name: 'Textarea', setup: (_, { attrs }) => () => h('textarea', attrs) }),
}))

vi.mock('@/components/ui/select', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Select: passthrough('Select'),
    SelectContent: passthrough('SelectContent'),
    SelectTrigger: passthrough('SelectTrigger'),
    SelectValue: passthrough('SelectValue'),
    SelectItem: defineComponent({ name: 'SelectItem', props: { value: String }, setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  }
})

vi.mock('@/components/ui/switch', () => ({
  Switch: defineComponent({
    name: 'Switch',
    props: { checked: Boolean, id: String },
    emits: ['update:checked'],
    setup: (props, { emit }) => () => h('button', {
      id: props.id,
      type: 'button',
      'data-testid': 'decision-maker-switch',
      onClick: () => emit('update:checked', !props.checked),
    }),
  }),
}))

const contactFixture = (gender: number | null): ContactResponse => ({
  id: 12,
  customer_id: 19,
  name: '李四',
  gender,
  position: '研发经理',
  is_decision_maker: false,
  mobile: '18627965322',
  email: null,
  wechat_id: null,
  remark: null,
  reports_to: null,
  is_primary: false,
  created_time: '2026-07-15T00:00:00',
})

describe('ContactFormDialog gender contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    customerApi.createContact.mockResolvedValue(contactFixture(1))
    customerApi.updateContact.mockResolvedValue(contactFixture(1))
  })

  it('maps backend female code 2 to the 女 option when editing a contact', async () => {
    const wrapper = mount(ContactFormDialog, {
      props: {
        customerId: 19,
        open: true,
        contact: contactFixture(2),
      },
    })

    await flushPromises()
    await nextTick()

    expect(wrapper.get('[data-testid="gender-radio"]').attributes('data-model-value')).toBe('女')
  })

  it('submits selected male and female genders as backend enum codes', async () => {
    const wrapper = mount(ContactFormDialog, {
      props: {
        customerId: 19,
        open: true,
      },
    })

    await wrapper.get('input[name="name"]').setValue('李四')
    await wrapper.get('input[name="mobile"]').setValue('18627965322')
    await wrapper.get('[data-testid="gender-男"]').trigger('click')
    await wrapper.get('form').trigger('submit')

    await vi.waitFor(() => {
      expect(customerApi.createContact).toHaveBeenCalledWith(19, expect.objectContaining({ gender: '1' }))
    })

    customerApi.createContact.mockClear()
    await wrapper.get('[data-testid="gender-女"]').trigger('click')
    await wrapper.get('form').trigger('submit')

    await vi.waitFor(() => {
      expect(customerApi.createContact).toHaveBeenCalledWith(19, expect.objectContaining({ gender: '2' }))
    })
  })
})
