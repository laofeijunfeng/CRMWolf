import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import LeadFormDialog from '@/components/LeadFormDialog.vue'
import { leadSchema } from '@/schemas/lead-form'
import { leadApi } from '@/api/lead'
import { acquisitionSourceApi } from '@/api/acquisition-source'
import productApi from '@/api/product'
import { usePermissionStore } from '@/stores/permissions'
import type { ProductResponse } from '@/schemas/product'

const toast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}))

vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/api/lead', () => ({
  leadApi: {
    createLead: vi.fn(),
    updateLead: vi.fn(),
    getLeadDetail: vi.fn(),
  },
}))

vi.mock('@/api/acquisition-source', () => ({
  acquisitionSourceApi: {
    listOptions: vi.fn(),
  },
}))

vi.mock('@/api/product', () => ({
  default: {
    list: vi.fn(),
  },
}))

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
  modules: [
    {
      id: `${publicId}-base`,
      public_id: `${publicId}-base`,
      name: '基础模块',
      description: null,
      module_role: 'BASE',
      is_active: true,
      sort_order: 0,
      created_by: 'u',
      updated_by: null,
      created_time: '2026-01-01T00:00:00',
      updated_time: '2026-01-01T00:00:00',
    },
  ],
})

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

describe('LeadFormDialog product field', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('requires product_public_id on the lead form schema', () => {
    const result = leadSchema.safeParse({
      lead_name: '飞驰科技',
      source_public_id: 'source-1',
      city: '上海',
      contact_name: '张三',
      contact_phone: '13800138000',
    })
    expect(result.success).toBe(false)
    if (result.success) return
    expect(result.error.flatten().fieldErrors.product_public_id).toContain('请选择产品')
  })

  it('renders the product picker next to 线索来源 without module checkboxes and submits product_public_id', async () => {
    setActivePinia(createPinia())
    setPermissions(['product:view'])
    vi.mocked(acquisitionSourceApi.listOptions).mockResolvedValue([
      { public_id: 'source-1', name: '官网', code: 'WEB', is_system: true, is_active: true, sort_order: 1 },
    ])
    vi.mocked(productApi.list).mockResolvedValue([product('prd_crm', 'CRM'), product('prd_oa', 'OA')])
    vi.mocked(leadApi.createLead).mockResolvedValue({
      id: 'lead-1',
      public_id: 'LEAD-001',
      lead_name: '飞驰科技',
      source: '官网',
      city: '上海',
      contact_name: '张三',
      contact_phone: '13800138000',
      status: 0,
      creator_id: 'u',
      created_time: '2026-01-01T00:00:00Z',
      last_modified_time: '2026-01-01T00:00:00Z',
      version: 1,
    })

    const wrapper = mount(LeadFormDialog, {
      props: { open: true, mode: 'create' },
      global: {
        stubs: {
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<div><slot /></div>' },
          DialogHeader: { template: '<div><slot /></div>' },
          DialogTitle: { template: '<h2><slot /></h2>' },
          DialogFooter: { template: '<div><slot /></div>' },
          AlertDialog: { template: '<div></div>' },
          RouterLink: true,
        },
      },
    })
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('线索来源')
    expect(wrapper.findComponent({ name: 'ProductIntentPicker' }).exists()).toBe(true)
    expect(wrapper.text()).not.toContain('基础模块')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)

    await wrapper.get('#lead-name').setValue('飞驰科技')
    await wrapper.get('#lead-city').setValue('上海')
    await wrapper.get('#lead-contact-name').setValue('张三')
    await wrapper.get('#lead-contact-phone').setValue('13800138000')
    interface ModelEmitter {
      $emit: (event: 'update:modelValue', value: string) => void
    }
    const sourceSelect = wrapper.findComponent({ name: 'SelectField' })
    ;(sourceSelect.vm as unknown as ModelEmitter).$emit('update:modelValue', 'source-1')
    const picker = wrapper.findComponent({ name: 'ProductIntentPicker' })
    ;(picker.vm as unknown as ModelEmitter).$emit('update:modelValue', 'prd_crm')
    await nextTick()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(leadApi.createLead).toHaveBeenCalledWith(expect.objectContaining({
      lead_name: '飞驰科技',
      source_public_id: 'source-1',
      product_public_id: 'prd_crm',
    }))
    wrapper.unmount()
  })
})
