import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InvoiceApplicationFormDialog from '@/components/dialogs/InvoiceApplicationFormDialog.vue'
import contractApi from '@/api/contract'
import customerApi from '@/api/customer'
import invoiceApi from '@/api/invoice'
import paymentApi from '@/api/payment'

vi.mock('@/api/contract', () => ({
  default: {
    getCustomerContracts: vi.fn(),
  },
}))

vi.mock('@/api/customer', () => ({
  default: {
    getCustomers: vi.fn(),
  },
}))

vi.mock('@/api/invoice', () => ({
  default: {
    getInvoiceTitles: vi.fn(),
  },
}))

vi.mock('@/api/payment', () => ({
  default: {
    getPaymentPlans: vi.fn(),
  },
}))

vi.mock('@/api/approvalGeneric', () => ({
  default: {
    submitApproval: vi.fn(),
  },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('vue-sonner', () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

const DialogStub = defineComponent({
  name: 'Dialog',
  props: {
    open: { type: Boolean, default: false },
  },
  template: '<div v-if="open"><slot /></div>',
})

const PassthroughStub = defineComponent({
  name: 'PassthroughStub',
  template: '<div><slot /></div>',
})

const SelectFieldStub = defineComponent({
  name: 'SelectField',
  props: {
    id: { type: String, default: '' },
    modelValue: { type: [String, Number], default: '' },
    options: { type: Array, default: () => [] },
  },
  emits: ['update:modelValue'],
  template: '<div :data-testid="id"><slot /></div>',
})

const InputFieldStub = defineComponent({
  name: 'InputField',
  props: {
    id: { type: String, default: '' },
    modelValue: { type: [String, Number], default: '' },
  },
  emits: ['update:modelValue'],
  methods: {
    handleInput(event: Event) {
      this.$emit('update:modelValue', (event.target as HTMLInputElement).value)
    },
  },
  template: '<input :id="id" :value="modelValue" @input="handleInput" />',
})

function findSelectField(wrapper: ReturnType<typeof mount>, id: string) {
  const field = wrapper.findAllComponents({ name: 'SelectField' })
    .find(component => component.props('id') === id)
  if (field === undefined) throw new Error(`SelectField ${id} not found`)
  return field
}

describe('InvoiceApplicationFormDialog', () => {
  beforeEach(() => {
    vi.mocked(customerApi.getCustomers).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    vi.mocked(contractApi.getCustomerContracts).mockResolvedValue([
      {
        id: 11,
        contract_name: '年度服务合同',
        total_amount: '100000.00',
      },
    ] as never)
    vi.mocked(invoiceApi.getInvoiceTitles).mockResolvedValue({
      invoice_titles: [
        {
          id: 31,
          customer_id: 'customer-1',
          title_type: 'COMPANY',
          title: '测试公司',
          taxpayer_id: '913100000000000000',
          bank_name: null,
          bank_account: null,
          address: null,
          phone: null,
          is_default: true,
          created_time: '2026-01-01T00:00:00',
          last_modified_time: '2026-01-01T00:00:00',
        },
      ],
    })
    vi.mocked(paymentApi.getPaymentPlans).mockResolvedValue([
      {
        id: 101,
        contract_id: 11,
        stage_name: '尾款',
        planned_amount: 100000,
        due_date: '2026-01-31',
        status: 'COMPLETED',
        paid_amount: 100000,
        remaining_amount: 0,
        payment_records: [],
        created_time: '2026-01-01T00:00:00',
        last_modified_time: '2026-01-01T00:00:00',
      },
    ])
  })

  it('uses planned amount for paid payment plans when creating invoices', async () => {
    const wrapper = mount(InvoiceApplicationFormDialog, {
      props: {
        open: true,
        mode: 'create',
        fixedCustomer: {
          id: 'customer-1',
          account_name: '测试客户',
        },
        fixedContractId: 11,
      },
      global: {
        stubs: {
          Dialog: DialogStub,
          DialogContent: PassthroughStub,
          DialogDescription: PassthroughStub,
          DialogFooter: PassthroughStub,
          DialogHeader: PassthroughStub,
          DialogTitle: PassthroughStub,
          Button: PassthroughStub,
          SearchableSelectField: PassthroughStub,
          SelectField: SelectFieldStub,
          InputField: InputFieldStub,
          InvoiceTypeSegmentedControl: PassthroughStub,
          SelectionSummary: PassthroughStub,
        },
      },
    })

    await flushPromises()

    const paymentPlanField = findSelectField(wrapper, 'invoice-application-plan')
    expect(paymentPlanField.props('options')).toEqual([
      {
        value: 101,
        label: '尾款 · 计划 ¥100,000.00',
      },
    ])

    await paymentPlanField.vm.$emit('update:modelValue', '101')
    await nextTick()

    expect(wrapper.find('#invoice-application-amount').element).toHaveProperty('value', '100000')
  })
})
