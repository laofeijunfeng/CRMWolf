import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProductPanel from '@/components/system-config/ProductPanel.vue'
import { flushPromises } from '@vue/test-utils'
import productApi from '@/api/product'
import { usePermissionStore } from '@/stores/permissions'

const mocks = vi.hoisted(() => ({
  product: {
    public_id: 'prd_1', team_id: 1, code: 'CRM', name: 'CRM 产品', description: '基础 CRM', is_active: true,
    created_by: 'u', updated_by: null, created_time: '2026-01-01T00:00:00', updated_time: '2026-01-01T00:00:00',
    modules: [
      { public_id: 'prm_1', team_id: 1, product_id: 1, code: 'BASE', name: '基础模块', description: null, module_role: 'BASE' as const, is_active: true, sort_order: 0, created_by: 'u', updated_by: null, created_time: '2026-01-01T00:00:00', updated_time: '2026-01-01T00:00:00' },
      { public_id: 'prm_2', team_id: 1, product_id: 1, code: 'ADD_ON', name: '增强模块', description: null, module_role: 'ADD_ON' as const, is_active: true, sort_order: 1, created_by: 'u', updated_by: null, created_time: '2026-01-01T00:00:00', updated_time: '2026-01-01T00:00:00' },
    ],
  },
}))

vi.mock('@/api/product', () => ({ default: {
  list: vi.fn().mockResolvedValue([mocks.product]), get: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(),
  createModule: vi.fn(), updateModule: vi.fn(), deleteModule: vi.fn(),
} }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDialog: vi.fn().mockResolvedValue(true), confirmDelete: vi.fn().mockResolvedValue(true) }))

const stubs = {
  Dialog: { props: ['open'], template: '<div v-if="open"><slot /></div>' },
  ListCard: { props: ['title', 'items', 'loading', 'emptyText'], template: '<div><h3>{{ title }}</h3><div v-for="item in items" :key="item.id"><slot name="itemMain" :item="item" /><slot name="itemMeta" :item="item" /><slot name="itemBadges" :item="item" /><slot name="itemActions" :item="item" /></div></div>' },
  Button: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  Input: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  Badge: { template: '<span><slot /></span>' },
  Select: { template: '<div><slot /></div>' }, SelectContent: { template: '<div><slot /></div>' }, SelectItem: { template: '<div><slot /></div>' }, SelectTrigger: { template: '<button><slot /></button>' }, SelectValue: { template: '<span><slot /></span>' },
  DialogContent: { template: '<div><slot /></div>' }, DialogHeader: { template: '<div><slot /></div>' }, DialogTitle: { template: '<h2><slot /></h2>' }, DialogDescription: { template: '<div><slot /></div>' }, DialogFooter: { template: '<div><slot /></div>' },
  FormField: { template: '<div><slot :componentField="{}" /></div>' }, FormControl: { template: '<div><slot /></div>' }, FormItem: { template: '<div><slot /></div>' }, FormLabel: { template: '<label><slot /></label>' }, FormMessage: { template: '<span><slot /></span>' }, Textarea: { template: '<textarea />' },
}

const setPermissions = (codes: string[]): void => {
  const store = usePermissionStore()
  store.loadState = 'ready'
  store.permissions = codes.map((code, index) => ({ id: index + 1, code, name: code, resource: code.split(':')[0] ?? code, action: code.split(':')[1] ?? '', is_active: true }))
}

describe('ProductPanel', () => {
  afterEach(() => vi.clearAllMocks())

  it('shows product data to a read-only user without maintenance buttons', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view'])
    const wrapper = mount(ProductPanel, { global: { stubs } })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.text()).toContain('CRM 产品')
    expect(wrapper.text()).toContain('基础模块')
    expect(wrapper.findAll('button').some(button => button.text().includes('新建产品'))).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text().includes('编辑'))).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text().includes('删除'))).toBe(false)
  })

  it('shows add-on module deletion for editors without product deletion permission', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view', 'product:edit'])
    const wrapper = mount(ProductPanel, { global: { stubs } })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.findAll('button').some(button => button.text() === '删除模块')).toBe(true)
    expect(wrapper.findAll('button').some(button => button.text() === '删除')).toBe(false)
  })

  it('shows editor controls while keeping base module protected', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view', 'product:create', 'product:edit', 'product:delete'])
    const wrapper = mount(ProductPanel, { global: { stubs } })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.text()).toContain('CRM 产品')
    expect(wrapper.text()).toContain('新建产品')
    expect(wrapper.text()).toContain('新增模块')
    expect(wrapper.findAll('button').filter(button => button.text() === '删除模块')).toHaveLength(1)
  })
})
