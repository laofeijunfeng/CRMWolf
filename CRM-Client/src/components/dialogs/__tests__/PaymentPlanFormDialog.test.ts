import { defineComponent, h, nextTick, ref, type VNode } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PaymentPlanFormDialog from '../PaymentPlanFormDialog.vue'
import paymentApi, { type PaymentPlanResponse } from '@/api/payment'

const passthrough = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }): () => VNode {
    return () => h('div', slots['default']?.())
  },
})

const DialogStub = defineComponent({
  props: { open: Boolean },
  emits: ['update:open'],
  setup(_, { slots }): () => VNode {
    return () => h('div', slots['default']?.())
  },
})

const InputStub = defineComponent({
  inheritAttrs: false,
  props: { modelValue: { type: [String, Number], default: '' } },
  emits: ['update:modelValue'],
  setup(props, { emit, attrs }): () => VNode {
    return () => h('input', {
      ...attrs,
      value: props.modelValue,
      onInput: (event: Event) => emit(
        'update:modelValue',
        (event.target as HTMLInputElement).value,
      ),
    })
  },
})

const DateFieldStub = defineComponent({
  inheritAttrs: false,
  props: { modelValue: { type: [String, Date], default: null } },
  emits: ['update:modelValue'],
  setup(_, { emit, attrs }): () => VNode {
    return () => h('input', {
      ...attrs,
      onInput: () => emit('update:modelValue', new Date(2026, 8, 4)),
    })
  },
})

const ButtonStub = defineComponent({
  inheritAttrs: false,
  setup(_, { slots, attrs }): () => VNode {
    return () => h('button', attrs, slots['default']?.())
  },
})

const formStubs = {
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
  InputField: InputStub,
  DateField: DateFieldStub,
  TextareaField: InputStub,
  AlertDialog: DialogStub,
  AlertDialogContent: passthrough,
  AlertDialogHeader: passthrough,
  AlertDialogTitle: passthrough,
  AlertDialogDescription: passthrough,
  AlertDialogFooter: passthrough,
  AlertDialogCancel: ButtonStub,
  AlertDialogAction: ButtonStub,
  Button: ButtonStub,
}

async function fillAndSubmit(wrapper: ReturnType<typeof mount<typeof PaymentPlanFormDialog>>): Promise<void> {
  await wrapper.find('#payment-plan-stage').setValue('首付款')
  await wrapper.find('#payment-plan-amount').setValue('100')
  await wrapper.find('#payment-plan-due-date').setValue('2026-09-04')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('PaymentPlanFormDialog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not reopen after a successful create when the parent controls open state', async () => {
    vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 1 } as PaymentPlanResponse])

    const open = ref(true)
    const Parent = defineComponent({
      components: { PaymentPlanFormDialog },
      setup: () => ({ open }),
      template: '<PaymentPlanFormDialog v-model:open="open" mode="create" :fixed-contract="{ id: 1, contract_name: \'合同\', total_amount: 100 }" />',
    })
    const wrapper = mount(Parent, { global: { stubs: formStubs } })
    const dialog = wrapper.findComponent(PaymentPlanFormDialog)

    await fillAndSubmit(dialog)
    await nextTick()

    expect(open.value).toBe(false)
    expect(dialog.props('open')).toBe(false)
    wrapper.unmount()
  })

  it('emits an object-level success outcome after create', async () => {
    vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 1 } as PaymentPlanResponse])

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedContract: { id: 1, contract_name: '合同', total_amount: 100 },
      },
      global: { stubs: formStubs },
    })

    await fillAndSubmit(wrapper)

    expect(wrapper.emitted('success')).toEqual([[{
      entityType: 'payment-plan',
      entityId: 1,
      operation: 'create',
      outcome: 'success',
      stateSyncRequested: true,
    }]])
    wrapper.unmount()
  })

  it('ignores a stale open event while the successful save close is pending', async () => {
    vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 1 } as PaymentPlanResponse])

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedContract: { id: 1, contract_name: '合同', total_amount: 100 },
      },
      global: { stubs: formStubs },
    })

    await fillAndSubmit(wrapper)
    const vm = wrapper.vm as unknown as { handleOpenChange: (open: boolean) => void }
    vm.handleOpenChange(true)

    expect(wrapper.emitted('update:open')).toEqual([[false]])
    wrapper.unmount()
  })

  it('ignores a stale open event after the parent has applied the successful close', async () => {
    vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 1 } as PaymentPlanResponse])

    const open = ref(true)
    const Parent = defineComponent({
      components: { PaymentPlanFormDialog },
      setup: (): { open: typeof open } => ({ open }),
      template: '<PaymentPlanFormDialog v-model:open="open" mode="create" :fixed-contract="{ id: 1, contract_name: \'合同\', total_amount: 100 }" />',
    })
    const wrapper = mount(Parent, { global: { stubs: formStubs } })
    const dialog = wrapper.findComponent(PaymentPlanFormDialog)

    await fillAndSubmit(dialog)
    await nextTick()
    expect(open.value).toBe(false)

    const vm = dialog.vm as unknown as { handleOpenChange: (open: boolean) => void }
    vm.handleOpenChange(true)
    await nextTick()

    expect(open.value).toBe(false)
    expect(dialog.props('open')).toBe(false)

    open.value = true
    await nextTick()
    expect(dialog.props('open')).toBe(true)
    wrapper.unmount()
  })
})
