import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, type Component, type VNode } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import LeadConvertDialog from '@/components/LeadConvertDialog.vue'
import customerApi from '@/api/customer'
import { usePermissionStore } from '@/stores/permissions'
import type { ProductResponse } from '@/schemas/product'

const mocks = vi.hoisted(() => ({
  getLeadDetail: vi.fn(),
  getProcurementMethodOptions: vi.fn(),
  convertLeadToCustomer: vi.fn(),
  listProducts: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

vi.mock('@/api/lead', () => ({
  leadApi: { getLeadDetail: mocks.getLeadDetail },
}))

vi.mock('@/api/procurement', () => ({
  default: { getProcurementMethodOptions: mocks.getProcurementMethodOptions },
}))

vi.mock('@/api/customer', () => ({
  default: { convertLeadToCustomer: mocks.convertLeadToCustomer },
}))

vi.mock('@/api/product', () => ({
  default: { list: mocks.listProducts },
}))

vi.mock('vue-sonner', () => ({ toast: mocks.toast }))

vi.mock('@/utils/confirmDialog', () => ({
  confirmDialog: vi.fn().mockResolvedValue(false),
}))

function passthrough(name: string): Component {
  return defineComponent({
    name,
    setup(_, { slots }): () => VNode {
      return () => h('div', slots['default']?.())
    },
  })
}

vi.mock('@/components/ui/dialog', () => ({
  Dialog: defineComponent({
    name: 'UiDialog',
    props: { open: Boolean },
    emits: ['update:open'],
    setup(props, { slots }): () => VNode | null {
      return () => props.open ? h('section', { role: 'dialog' }, slots['default']?.()) : null
    },
  }),
  DialogContent: passthrough('UiDialogContent'),
  DialogHeader: passthrough('UiDialogHeader'),
  DialogTitle: passthrough('UiDialogTitle'),
  DialogDescription: passthrough('UiDialogDescription'),
  DialogFooter: passthrough('UiDialogFooter'),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'UiButton',
    props: {
      type: { type: String, default: 'button' },
      disabled: { type: Boolean, default: false },
    },
    setup(props, { slots }): () => VNode {
      return () => h('button', { type: props.type ?? 'button', disabled: props.disabled }, slots['default']?.())
    },
  }),
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: defineComponent({
    name: 'UiSkeleton',
    setup(): () => VNode {
      return () => h('div')
    },
  }),
}))

vi.mock('@/components/crmwolf/FeedbackAlert.vue', () => ({
  default: defineComponent({
    name: 'FeedbackAlert',
    setup(): () => null {
      return () => null
    },
  }),
}))

vi.mock('@/components/crmwolf', () => {
  const field = (tag: 'input' | 'select'): Component => defineComponent({
    inheritAttrs: false,
    props: {
      id: { type: String, default: '' },
      disabled: { type: Boolean, default: false },
      modelValue: { type: [String, Number], default: '' },
      label: { type: String, default: '' },
      options: { type: Array, default: () => [] },
    },
    emits: ['update:modelValue'],
    setup(props, { emit, attrs }): () => VNode {
      return () => h('div', [
        h(tag, {
          ...attrs,
          id: props.id,
          disabled: props.disabled,
          value: props.modelValue ?? '',
          onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
        }),
      ])
    },
  })
  return {
    InputField: field('input'),
    SelectField: field('select'),
    ProductIntentPicker: defineComponent({
      name: 'ProductIntentPicker',
      props: {
        modelValue: { type: String, default: '' },
        disabled: { type: Boolean, default: false },
      },
      emits: ['update:modelValue'],
      setup(props): () => VNode {
        return () => h('div', { 'data-testid': 'product-intent-picker' }, props.modelValue)
      },
    }),
  }
})

const product = (publicId: string, name: string): ProductResponse => ({
  id: publicId,
  public_id: publicId,
  name,
  description: null,
  is_active: true,
  created_by: 'u',
  updated_by: null,
  created_time: '2026-01-01T00:00:00',
  updated_time: '2026-01-01T00:00:00',
  modules: [],
})

const leadFixture = {
  id: 'lead-1',
  lead_name: '飞驰科技',
  city: '上海',
  contact_name: '张三',
  contact_phone: '13800000000',
  company_scale: '100-499人',
  owner_info: { name: '李四' },
  acquisition_source: 'referral',
  product_public_id: 'prd_crm',
  product_name: 'CRM',
}

const setPermissions = (codes: string[]): void => {
  const store = usePermissionStore()
  store.loadState = 'ready'
  store.permissions = codes.map((code, index) => ({
    id: index + 1,
    code,
    name: code,
    resource: code.split(':')[0] ?? code,
    action: code.split(':')[1] ?? '',
    is_active: true,
  }))
}

describe('LeadConvertDialog product field', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    setPermissions(['product:view'])
    mocks.getProcurementMethodOptions.mockResolvedValue([{ id: 1, name: '订阅' }])
    mocks.listProducts.mockResolvedValue([product('prd_crm', 'CRM'), product('prd_oa', 'OA')])
    mocks.convertLeadToCustomer.mockResolvedValue({ status: 'SUCCEEDED', customer_id: 'cus-1' })
  })

  it('defaults product_public_id from the lead detail and includes it on submit', async () => {
    mocks.getLeadDetail.mockResolvedValue(leadFixture)

    const wrapper = mount(LeadConvertDialog, {
      props: { open: true, leadId: 'lead-1' },
    })
    await flushPromises()
    await nextTick()

    const vm = wrapper.vm as unknown as {
      formValues: { product_public_id: string; default_procurement_method_id: string | number }
    }
    expect(vm.formValues.product_public_id).toBe('prd_crm')
    vm.formValues.default_procurement_method_id = '1'
    await wrapper.get('form#lead-convert-form').trigger('submit')
    await flushPromises()

    expect(customerApi.convertLeadToCustomer).toHaveBeenCalledWith(
      expect.objectContaining({
        lead_id: 'lead-1',
        product_public_id: 'prd_crm',
      }),
      expect.anything(),
    )
    wrapper.unmount()
  })

  it('blocks submit with 请选择产品 when the lead has no product', async () => {
    mocks.getLeadDetail.mockResolvedValue({ ...leadFixture, product_public_id: null })

    const wrapper = mount(LeadConvertDialog, {
      props: { open: true, leadId: 'lead-1' },
    })
    await flushPromises()
    await nextTick()

    const vm = wrapper.vm as unknown as {
      formValues: { product_public_id: string; default_procurement_method_id: string | number }
    }
    expect(vm.formValues.product_public_id).toBe('')
    vm.formValues.default_procurement_method_id = '1'
    await wrapper.get('form#lead-convert-form').trigger('submit')
    await flushPromises()

    expect(mocks.toast.error).toHaveBeenCalledWith('请选择产品')
    expect(customerApi.convertLeadToCustomer).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
