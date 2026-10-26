import { defineComponent, h, type VNode } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { opportunityApi } from '@/api/opportunity'
import ContractFormDialog from '../ContractFormDialog.vue'

vi.mock('@/api/customer', () => ({
  default: {
    getCustomers: vi.fn().mockResolvedValue([]),
    getContacts: vi.fn().mockResolvedValue([]),
    getCustomerDetail: vi.fn(),
  },
}))

vi.mock('@/api/opportunity', () => ({
  opportunityApi: {
    getAvailableForContract: vi.fn(),
  },
}))

vi.mock('@/api/contract', () => ({
  default: {
    createContract: vi.fn(),
    updateContract: vi.fn(),
  },
}))

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

const SelectFieldStub = defineComponent({
  name: 'SelectField',
  inheritAttrs: false,
  props: {
    id: { type: String, required: true },
    modelValue: { type: [String, Number], default: '' },
    options: { type: Array, default: () => [] },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }): () => VNode {
    return () => h('div', { id: props.id }, [
      ...(props.options as { value: string, label: string, disabled?: boolean, disabledReason?: string }[]).map((option) => h('button', {
        type: 'button',
        disabled: option.disabled === true,
        title: option.disabledReason,
        onClick: () => emit('update:modelValue', option.value),
      }, option.label)),
    ])
  },
})

function opportunity(id: string, name: string, reason: string | null = null): ReturnType<typeof Object> {
  return {
    id,
    opportunity_name: name,
    customer_id: 'cus_1',
    customer_name: '武汉微派网络科技有限公司',
    total_amount: 120000,
    user_count: 20,
    license_type: 'SUBSCRIPTION',
    subscription_years: 1,
    contract_unavailable_reason: reason,
  }
}

async function openDialog(): Promise<ReturnType<typeof mount>> {
  const wrapper = mount(ContractFormDialog, {
    props: { open: true },
    global: {
      stubs: {
        Dialog: defineComponent({ template: '<div><slot /></div>' }),
        DialogContent: defineComponent({ template: '<div><slot /></div>' }),
        DialogHeader: defineComponent({ template: '<div><slot /></div>' }),
        DialogTitle: defineComponent({ template: '<div><slot /></div>' }),
        DialogDescription: defineComponent({ template: '<div><slot /></div>' }),
        DialogFooter: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialog: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialogContent: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialogHeader: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialogTitle: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialogDescription: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialogFooter: defineComponent({ template: '<div><slot /></div>' }),
        AlertDialogAction: defineComponent({ template: '<button><slot /></button>' }),
        AlertDialogCancel: defineComponent({ template: '<button><slot /></button>' }),
        FormField: defineComponent({
          props: { name: { type: String, required: true } },
          setup(_props, { slots }): () => VNode {
            return () => h('div', slots['default']?.({ value: '', handleChange: () => undefined }))
          },
        }),
        FormItem: defineComponent({ template: '<div><slot /></div>' }),
        FormMessage: defineComponent({ template: '<div />' }),
        SearchableSelectField: defineComponent({
          props: { id: { type: String, default: '' }, options: { type: Array, default: () => [] } },
          emits: ['update:modelValue'],
          setup(props, { emit }): () => VNode {
            return () => h('button', {
              id: props.id,
              type: 'button',
              onClick: () => emit('update:modelValue', 'cus_1'),
            }, '选择客户')
          },
        }),
        SelectField: SelectFieldStub,
        InputField: defineComponent({
          props: { id: { type: String, default: '' }, modelValue: { type: [String, Number], default: '' } },
          setup(props): () => VNode { return () => h('input', { id: props.id, value: String(props.modelValue ?? '') }) },
        }),
        DateField: defineComponent({ template: '<input />' }),
        FileAttachment: defineComponent({ template: '<div />' }),
        Button: defineComponent({ template: '<button><slot /></button>' }),
      },
    },
  })
  await flushPromises()
  await wrapper.get('#contract-customer').trigger('click')
  await flushPromises()
  return wrapper
}

describe('ContractFormDialog opportunity availability', () => {
  beforeEach(() => {
    vi.mocked(opportunityApi.getAvailableForContract).mockReset()
  })

  it('shows a disabled no-opportunity row when the customer has none', async () => {
    vi.mocked(opportunityApi.getAvailableForContract).mockResolvedValue([])
    const wrapper = await openDialog()
    const option = wrapper.get('#contract-opportunity button')
    expect(option.text()).toBe('没有商机')
    expect(option.attributes('disabled')).toBeDefined()
  })

  it('keeps a below-100 opportunity visible but does not select it', async () => {
    vi.mocked(opportunityApi.getAvailableForContract).mockResolvedValue([
      opportunity('opp_ready', '可创建'),
      opportunity('opp_early', '未到100', '需要先推进到 100%'),
    ])
    const wrapper = await openDialog()
    const options = wrapper.findAll('#contract-opportunity button')
    expect(options.map((item) => item.text())).toEqual(['可创建', '未到100'])
    expect(options[1]?.attributes('disabled')).toBeDefined()
    expect(options[1]?.attributes('title')).toBe('需要先推进到 100%')

    await options[1]?.trigger('click')
    await flushPromises()
    expect(wrapper.get('#contract-name').element).toHaveProperty('value', '')

    await options[0]?.trigger('click')
    await flushPromises()
    expect(wrapper.get('#contract-name').element).toHaveProperty('value', '武汉微派网络科技有限公司-20人-订阅1年')
  })
})
