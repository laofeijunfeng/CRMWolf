import { defineComponent, h, nextTick, ref, type VNode } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PaymentPlanFormDialog from '../PaymentPlanFormDialog.vue'
import contractApi from '@/api/contract'
import paymentApi, { type PaymentPlanResponse } from '@/api/payment'
import { formatCurrency } from '@/utils/format'

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
  props: {
    modelValue: { type: [String, Number], default: '' },
    error: { type: String, default: '' },
    helperText: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  setup(props, { emit, attrs }): () => VNode {
    return () => h('div', [
      h('input', {
        ...attrs,
        value: props.modelValue,
        onInput: (event: Event) => emit(
          'update:modelValue',
          (event.target as HTMLInputElement).value,
        ),
      }),
      props.error !== ''
        ? h('p', { 'data-testid': `${String(attrs.id)}-error` }, props.error)
        : props.helperText !== ''
          ? h('p', { 'data-testid': `${String(attrs.id)}-helper` }, props.helperText)
          : null,
    ])
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
  beforeEach(() => {
    vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([])
  })

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

  function existingPlan(amount: number, id = 9): PaymentPlanResponse {
    return {
      id,
      contract_id: 1,
      stage_name: '一期',
      planned_amount: amount,
      due_date: '2026-08-01',
      status: 'PENDING',
      payment_records: [],
      created_time: '2026-08-01T00:00:00.000Z',
      last_modified_time: '2026-08-01T00:00:00.000Z',
    }
  }

  it('prefills remaining allocatable amount after existing plans load', async () => {
    vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([existingPlan(12000)])
    vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
      },
      global: { stubs: formStubs },
    })
    await flushPromises()

    expect((wrapper.get('#payment-plan-amount').element as HTMLInputElement).value).toBe('28000')
    expect(wrapper.get('[data-testid="payment-plan-amount-helper"]').text()).toBe(
      `还可分配 ${formatCurrency(28000)}`,
    )
    wrapper.unmount()
  })

  it('shows an over-cap field error on input and does not submit', async () => {
    vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([existingPlan(12000)])
    const createSpy = vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
      },
      global: { stubs: formStubs },
    })
    await flushPromises()

    await wrapper.get('#payment-plan-amount').setValue('30000')
    await nextTick()

    expect(wrapper.get('[data-testid="payment-plan-amount-error"]').text()).toBe(
      `回款计划合计不能超过合同金额 ${formatCurrency(40000)}，当前还可分配 ${formatCurrency(28000)}`,
    )

    await wrapper.get('#payment-plan-stage').setValue('二期')
    await wrapper.get('#payment-plan-due-date').setValue('2026-09-04')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(createSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('clears the over-cap error and submits the remaining amount', async () => {
    vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([existingPlan(12000)])
    const createSpy = vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
      },
      global: { stubs: formStubs },
    })
    await flushPromises()

    await wrapper.get('#payment-plan-amount').setValue('30000')
    await nextTick()
    await wrapper.get('#payment-plan-amount').setValue('28000')
    await nextTick()
    expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

    await wrapper.get('#payment-plan-stage').setValue('二期')
    await wrapper.get('#payment-plan-due-date').setValue('2026-09-04')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(createSpy).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not flag an already-over contract when lowering the edited plan', async () => {
    const current = existingPlan(12000, 1)
    vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([
      current,
      existingPlan(30000, 2),
    ])
    const updateSpy = vi.spyOn(paymentApi, 'updatePaymentPlan').mockResolvedValue({
      ...current,
      planned_amount: 11000,
    } as PaymentPlanResponse)

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'edit',
        plan: current,
        fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
      },
      global: { stubs: formStubs },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

    await wrapper.get('#payment-plan-amount').setValue('13000')
    await nextTick()
    expect(wrapper.get('[data-testid="payment-plan-amount-error"]').text()).toContain('不能超过合同金额')

    await wrapper.get('#payment-plan-amount').setValue('11000')
    await nextTick()
    expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

    await wrapper.get('#payment-plan-stage').setValue('一期')
    await wrapper.get('#payment-plan-due-date').setValue('2026-09-04')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(updateSpy).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('skips over-cap errors when existing plans fail to load and still submits', async () => {
    vi.spyOn(paymentApi, 'getPaymentPlans').mockRejectedValue(new Error('network'))
    const createSpy = vi.spyOn(paymentApi, 'createPaymentPlans').mockResolvedValue([{ id: 2 } as PaymentPlanResponse])

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedContract: { id: 1, contract_name: '合同', total_amount: 40000 },
      },
      global: { stubs: formStubs },
    })
    await flushPromises()

    expect((wrapper.get('#payment-plan-amount').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('[data-testid="payment-plan-amount-error"]').exists()).toBe(false)

    await fillAndSubmit(wrapper)
    expect(createSpy).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('loads contract total when editing without a fixed contract', async () => {
    const current = existingPlan(12000, 1)
    vi.spyOn(paymentApi, 'getPaymentPlans').mockResolvedValue([current])
    vi.spyOn(contractApi, 'getContract').mockResolvedValue({
      id: 1,
      total_amount: '40000',
    } as Awaited<ReturnType<typeof contractApi.getContract>>)

    const wrapper = mount(PaymentPlanFormDialog, {
      props: {
        open: true,
        mode: 'edit',
        plan: current,
      },
      global: { stubs: formStubs },
    })
    await flushPromises()

    expect(contractApi.getContract).toHaveBeenCalledWith(1)
    expect(wrapper.get('[data-testid="payment-plan-amount-helper"]').text()).toContain(
      formatCurrency(40000),
    )
    wrapper.unmount()
  })
})
