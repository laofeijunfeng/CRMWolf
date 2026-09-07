import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import EditRecordDialog from '@/components/dialogs/EditRecordDialog.vue'
import type { PaymentRecordResponse } from '@/api/payment'

const { confirmDialogMock } = vi.hoisted(() => ({
  confirmDialogMock: vi.fn(),
}))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: confirmDialogMock,
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

vi.mock('@/components/crmwolf', () => {
  const inputField = defineComponent({
    name: 'InputField',
    props: { modelValue: [String, Number], disabled: Boolean, error: String },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('div', [
      h('input', {
        ...attrs,
        value: props.modelValue ?? '',
        disabled: props.disabled,
        'aria-invalid': props.error ? 'true' : undefined,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      }),
      props.error ? h('p', { role: 'alert' }, props.error) : null,
    ]),
  })

  const textareaField = defineComponent({
    name: 'TextareaField',
    props: { modelValue: [String, Number], disabled: Boolean, error: String },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('div', [
      h('textarea', {
        ...attrs,
        value: props.modelValue ?? '',
        disabled: props.disabled,
        'aria-invalid': props.error ? 'true' : undefined,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
      }),
      props.error ? h('p', { role: 'alert' }, props.error) : null,
    ]),
  })

  const dateField = defineComponent({
    name: 'DateField',
    props: { modelValue: Date, disabled: Boolean, error: String },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('div', [
      h('input', {
        ...attrs,
        value: props.modelValue instanceof Date && !Number.isNaN(props.modelValue.getTime())
          ? `${props.modelValue.getFullYear()}-${String(props.modelValue.getMonth() + 1).padStart(2, '0')}-${String(props.modelValue.getDate()).padStart(2, '0')}`
          : '',
        disabled: props.disabled,
        'aria-invalid': props.error ? 'true' : undefined,
        onInput: (event: Event) => {
          const value = (event.target as HTMLInputElement).value
          const [year, month, day] = value.split('-').map(Number)
          emit('update:modelValue', value === '' ? null : new Date(year, month - 1, day))
        },
      }),
      props.error ? h('p', { role: 'alert' }, props.error) : null,
    ]),
  })

  return { InputField: inputField, TextareaField: textareaField, DateField: dateField }
})

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

const recordFixture = (): PaymentRecordResponse => ({
  id: 77,
  payment_plan_id: 101,
  record_number: 'REC-2026-001',
  actual_amount: 8800.5,
  payment_date: '2026-07-12',
  actual_payer_name: '原付款方',
  proof_attachment: 'https://example.com/old-proof.pdf',
  notes: '原备注',
  creator_id: 'u-1',
  creator_name: '张三',
  created_time: '2026-07-12T09:30:00.000Z',
  last_modified_time: '2026-07-12T09:30:00.000Z',
})

const sourceText = (): string => readFileSync(
  `${process.cwd()}/src/components/dialogs/EditRecordDialog.vue`,
  'utf8'
)

describe('EditRecordDialog', () => {
  it('initializes from the payment record and emits record id with a typed update payload', async () => {
    const wrapper = mount(EditRecordDialog, {
      props: {
        open: true,
        record: recordFixture(),
      },
    })

    const amountInput = wrapper.get('input[name="actual_amount"]').element as HTMLInputElement
    const dateInput = wrapper.get('#edit-record-date input').element as HTMLInputElement
    await wrapper.get('button.edit-record-dialog__supplement-trigger').trigger('click')
    const proofInput = wrapper.get('input[name="proof_attachment"]').element as HTMLInputElement
    const notesInput = wrapper.get('textarea[name="notes"]').element as HTMLTextAreaElement

    expect(amountInput.value).toBe('8800.5')
    expect(dateInput.value).toBe('2026-07-12')
    expect(proofInput.value).toBe('https://example.com/old-proof.pdf')
    expect(notesInput.value).toBe('原备注')

    await wrapper.get('input[name="actual_amount"]').setValue('9900')
    await wrapper.get('input[name="actual_payer_name"]').setValue('新的付款方')
    await wrapper.get('#edit-record-date input').setValue('2026-07-16')
    await wrapper.get('input[name="proof_attachment"]').setValue('https://example.com/new-proof.pdf')
    await wrapper.get('textarea[name="notes"]').setValue('更新备注')
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.emitted('submit')?.[0]).toEqual([77, {
      actual_amount: 9900,
      payment_date: '2026-07-16',
      actual_payer_name: '新的付款方',
      proof_attachment: 'https://example.com/new-proof.pdf',
      notes: '更新备注',
    }])
  })

  it('validates required amount and payment date with accessible errors', async () => {
    const wrapper = mount(EditRecordDialog, {
      props: {
        open: true,
        record: recordFixture(),
      },
    })

    await wrapper.get('input[name="actual_amount"]').setValue('-1')
    await wrapper.get('#edit-record-date input').setValue('')
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('请输入大于 0 的回款金额')
    expect(wrapper.text()).toContain('请选择回款日期')
    expect(wrapper.get('input[name="actual_amount"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#edit-record-date input').attributes('aria-invalid')).toBe('true')
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(3)
    expect(wrapper.get('.form-error-summary').text()).toContain('请先修正以下字段：')
  })

  it('keeps optional record details collapsed and expands them for note validation', async () => {
    const wrapper = mount(EditRecordDialog, {
      props: {
        open: true,
        record: {
          ...recordFixture(),
          actual_amount: 8800.5,
          proof_attachment: '',
          notes: '',
        },
      },
    })

    const trigger = wrapper.get('button.edit-record-dialog__supplement-trigger')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('input[name="proof_attachment"]').exists()).toBe(false)
    expect(wrapper.find('textarea[name="notes"]').exists()).toBe(false)

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('input[name="proof_attachment"]').element).toBeTruthy()
    expect(wrapper.get('textarea[name="notes"]').element).toBeTruthy()

    await wrapper.get('textarea[name="notes"]').setValue(`${'长'.repeat(201)}`)
    await wrapper.get('form').trigger('submit')
    await nextTick()

    expect(wrapper.text()).toContain('备注不能超过 200 字')
    expect(trigger.attributes('aria-expanded')).toBe('true')
  })

  it('protects modified content before closing and does not add a guard for untouched content', async () => {
    confirmDialogMock.mockResolvedValue(false)
    const wrapper = mount(EditRecordDialog, {
      props: {
        open: true,
        record: recordFixture(),
      },
    })

    await wrapper.get('button.edit-record-dialog__supplement-trigger').trigger('click')
    await wrapper.get('textarea[name="notes"]').setValue('新的备注')
    await wrapper.get('.edit-record-dialog__footer button[type="button"]').trigger('click')
    expect(confirmDialogMock).toHaveBeenCalledWith(
      '已修改回款记录，关闭后这些修改不会保存。确定关闭吗？',
      '放弃本次修改？',
      { variant: 'destructive', confirmText: '放弃并关闭' },
    )
    expect(wrapper.emitted('update:open')).toBeUndefined()

    confirmDialogMock.mockResolvedValue(true)
    await wrapper.get('.edit-record-dialog__footer button[type="button"]').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('uses shadcn-vue V2 primitives without unsafe TypeScript escapes', () => {
    const source = sourceText()

    expect(source).toContain('@/components/ui/dialog')
    expect(source).toContain('@/components/ui/button')
    expect(source).toContain('@/components/crmwolf')
    expect(source).toContain('DialogDescription')
    expect(source).toContain('variables-v2.scss')
    expect(source).not.toContain('as any')
    expect(source).not.toContain('@ts-ignore')
    expect(source).not.toContain('toISOString')
  })
})
