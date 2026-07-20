import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import PaymentRecordDialog from '@/components/dialogs/PaymentRecordDialog.vue'

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
      setup: (props, { slots }) => () => props.open ? h('section', { role: 'dialog' }, slots.default?.()) : null,
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
      slots.default?.()
    ),
  }),
}))

vi.mock('@/components/ui/input', () => ({
  Input: defineComponent({
    name: 'Input',
    props: {
      modelValue: [String, Number],
      placeholder: String,
      type: String,
      disabled: Boolean,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('input', {
      ...attrs,
      type: props.type ?? 'text',
      value: props.modelValue ?? '',
      disabled: props.disabled,
      placeholder: props.placeholder,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    }),
  }),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: defineComponent({
    name: 'Textarea',
    props: {
      modelValue: [String, Number],
      disabled: Boolean,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('textarea', {
      ...attrs,
      value: props.modelValue ?? '',
      disabled: props.disabled,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
    }),
  }),
}))

const sourceText = (): string => readFileSync(
  `${process.cwd()}/src/components/dialogs/PaymentRecordDialog.vue`,
  'utf8'
)

describe('PaymentRecordDialog', () => {
  it('prefills the default amount and emits a typed create payload with the entered local date string', async () => {
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: 1234.56,
      },
    })

    const amountInput = wrapper.get('input[name="actual_amount"]').element as HTMLInputElement
    expect(amountInput.value).toBe('1234.56')

    await wrapper.get('input[name="payment_date"]').setValue('2026-07-16')
    await wrapper.get('input[name="proof_attachment"]').setValue('https://example.com/proof.pdf')
    await wrapper.get('textarea[name="notes"]').setValue('首笔回款')
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.emitted('submit')?.[0]).toEqual([{
      actual_amount: 1234.56,
      payment_date: '2026-07-16',
      proof_attachment: 'https://example.com/proof.pdf',
      notes: '首笔回款',
    }])
  })

  it('validates required amount and payment date with accessible errors', async () => {
    const wrapper = mount(PaymentRecordDialog, {
      props: {
        open: true,
        defaultAmount: null,
      },
    })

    await wrapper.get('input[name="actual_amount"]').setValue('0')
    await wrapper.get('input[name="payment_date"]').setValue('')
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('请输入大于 0 的回款金额')
    expect(wrapper.text()).toContain('请选择回款日期')
    expect(wrapper.get('input[name="actual_amount"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('input[name="payment_date"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(2)
  })

  it('uses shadcn-vue V2 primitives without unsafe TypeScript escapes', () => {
    const source = sourceText()

    expect(source).toContain('@/components/ui/dialog')
    expect(source).toContain('@/components/ui/button')
    expect(source).toContain('@/components/ui/input')
    expect(source).toContain('@/components/ui/textarea')
    expect(source).toContain('DialogDescription')
    expect(source).toContain('variables-v2.scss')
    expect(source).not.toContain('as any')
    expect(source).not.toContain('@ts-ignore')
    expect(source).not.toContain('toISOString')
  })
})
