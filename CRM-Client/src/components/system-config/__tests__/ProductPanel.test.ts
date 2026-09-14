import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
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
  ListCard: { props: ['title', 'items', 'loading', 'emptyText'], template: '<div><h3>{{ title }}</h3><div v-for="item in items" :key="item.id"><slot name="itemMain" :item="item" /><slot name="itemMeta" :item="item" /><slot name="itemBadges" :item="item" /><slot name="itemActions" :item="item" /></div><p v-if="items.length === 0">{{ emptyText }}</p></div>' },
  ErrorState: { props: ['title', 'description'], template: '<div role="alert"><strong>{{ title }}</strong><span>{{ description }}</span><slot name="action" /></div>' },
  Button: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  Input: { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  Textarea: { props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
  Badge: { template: '<span><slot /></span>' },
  Select: { template: '<div><slot /></div>' }, SelectContent: { template: '<div><slot /></div>' }, SelectItem: { template: '<div><slot /></div>' }, SelectTrigger: { template: '<button><slot /></button>' }, SelectValue: { template: '<span><slot /></span>' },
  DialogContent: { template: '<div><slot /></div>' }, DialogHeader: { template: '<div><slot /></div>' }, DialogTitle: { template: '<h2><slot /></h2>' }, DialogDescription: { template: '<div><slot /></div>' }, DialogFooter: { template: '<div><slot /></div>' },
  FormField: { template: '<div><slot :componentField="{}" /></div>' }, FormControl: { template: '<div><slot /></div>' }, FormItem: { template: '<div><slot /></div>' }, FormLabel: { template: '<label><slot /></label>' }, FormMessage: { template: '<span><slot /></span>' },
}

const formSubmitStubs = Object.fromEntries(
  Object.entries(stubs).filter(([key]) => ![
    'FormField',
    'FormControl',
    'FormItem',
    'FormLabel',
    'FormMessage',
    'Input',
    'Textarea',
  ].includes(key)),
)


const mountPanel = (props: Record<string, unknown> = {}): VueWrapper => mount(ProductPanel, { props, global: { stubs } })

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
    expect(wrapper.find('input[aria-label="搜索产品名称或编码"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="产品状态"]').exists()).toBe(true)
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
  it('does not open an edit dialog for a read-only edit deep link', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view'])
    const wrapper = mountPanel({ action: 'edit', recordId: 'prd_1' })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.find('h2').exists()).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === '保存')).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === '编辑')).toBe(false)
  })

  it('opens a create dialog when the action prop transitions on an active panel', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view', 'product:create'])
    const wrapper = mountPanel()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.find('h2').exists()).toBe(false)
    await wrapper.setProps({ action: 'create' })
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('新建产品')
    expect(wrapper.findAll('button').some(button => button.text() === '保存')).toBe(true)
  })
  it('opens a pending create deep link when permissions become ready', async () => {
    setActivePinia(createPinia())
    const store = usePermissionStore()
    store.loadState = 'loading'
    store.permissions = []
    const wrapper = mountPanel({ action: 'create' })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.find('h2').exists()).toBe(false)

    setPermissions(['product:view', 'product:create'])
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('新建产品')
  })


  it('renders a retryable error instead of an empty state and recovers after retry', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view'])
    vi.mocked(productApi.list).mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce([mocks.product])
    const wrapper = mountPanel()
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('产品加载失败')
    expect(wrapper.find('button[data-testid="product-list-retry"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('暂无产品')
    await wrapper.get('button[data-testid="product-list-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('CRM 产品')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('creates a product from the product form instead of the module form', async () => {
    setActivePinia(createPinia()); setPermissions(['product:view', 'product:create'])
    vi.mocked(productApi.create).mockResolvedValueOnce(mocks.product)
    const wrapper = mount(ProductPanel, {
      props: { action: 'create' },
      global: { stubs: formSubmitStubs },
      attachTo: document.body,
    })
    await vi.waitFor(() => expect(productApi.list).toHaveBeenCalled())
    await flushPromises()

    const form = wrapper.get('form')
    await form.get('input[name="code"]').setValue('CRM_WOLF')
    await form.get('input[name="name"]').setValue('CRMWolf')
    await form.get('textarea[name="description"]').setValue('客户关系管理平台')
    await form.get('button[type="submit"]').trigger('click')
    await vi.waitFor(() => {
      expect(productApi.create).toHaveBeenCalledWith({
        code: 'CRM_WOLF',
        name: 'CRMWolf',
        description: '客户关系管理平台',
      })
    })
    expect(productApi.createModule).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
