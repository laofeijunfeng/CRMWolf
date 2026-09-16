import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, type VNode } from 'vue'
import ProductIntentPicker from '../ProductIntentPicker.vue'
import productApi from '@/api/product'
import { usePermissionStore } from '@/stores/permissions'
import type { ProductResponse } from '@/schemas/product'

const toast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}))

vi.mock('@/api/product', () => ({
  default: {
    list: vi.fn(),
  },
}))

vi.mock('vue-sonner', () => ({ toast }))

const RouterLinkStub = defineComponent({
  name: 'RouterLink',
  props: {
    to: { type: [String, Object], required: true },
  },
  setup(props, { slots }): () => VNode {
    return () => h('a', { href: typeof props.to === 'string' ? props.to : '' }, slots['default']?.())
  },
})

const EMPTY_CATALOG_COPY = '团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建'
const FORBIDDEN_COPY = '没有产品查看权限'

const product = (
  publicId: string,
  name: string,
  isActive = true,
): ProductResponse => ({
  id: publicId,
  public_id: publicId,
  name,
  description: null,
  is_active: isActive,
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

const mountPicker = async (
  modelValue = '',
  permissions: string[] = ['product:view', 'product:create'],
): Promise<VueWrapper> => {
  setActivePinia(createPinia())
  setPermissions(permissions)
  const wrapper = mount(ProductIntentPicker, {
    props: {
      modelValue,
      'onUpdate:modelValue': (value: string) => wrapper.setProps({ modelValue: value }),
    },
    global: {
      stubs: { RouterLink: RouterLinkStub },
    },
  })
  await flushPromises()
  await nextTick()
  return wrapper
}

describe('ProductIntentPicker', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('toasts 没有产品查看权限 on a 403 list response instead of 操作失败', async () => {
    vi.mocked(productApi.list).mockRejectedValueOnce(Object.assign(new Error('Forbidden'), {
      response: { status: 403 },
    }))

    const wrapper = await mountPicker()

    expect(productApi.list).toHaveBeenCalledWith()
    expect(toast.error).toHaveBeenCalledWith(FORBIDDEN_COPY)
    expect(toast.error).not.toHaveBeenCalledWith(expect.stringContaining('操作失败'))
    expect(wrapper.text()).not.toContain('操作失败')
    wrapper.unmount()
  })

  it('shows the admin empty-catalog copy when there is no active product', async () => {
    vi.mocked(productApi.list).mockResolvedValueOnce([product('prd_legacy', '旧产品', false)])

    const wrapper = await mountPicker()

    expect(wrapper.text()).toContain(EMPTY_CATALOG_COPY)
    expect(wrapper.findComponent({ name: 'SegmentedChoiceControl' }).exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows 去创建产品 only when the user can create products', async () => {
    vi.mocked(productApi.list).mockResolvedValue([])

    const creator = await mountPicker('', ['product:view', 'product:create'])
    const createLink = creator.findComponent(RouterLinkStub)
    expect(creator.text()).toContain('去创建产品')
    expect(createLink.exists()).toBe(true)
    expect(createLink.props('to')).toBe('/settings/products?action=create')
    creator.unmount()

    const viewer = await mountPicker('', ['product:view'])
    expect(viewer.text()).not.toContain('去创建产品')
    expect(viewer.findComponent(RouterLinkStub).exists()).toBe(false)
    viewer.unmount()
  })

  it('includes the current inactive product in options without rendering modules', async () => {
    vi.mocked(productApi.list).mockResolvedValueOnce([
      product('prd_crm', 'CRM'),
      product('prd_oa', 'OA', false),
    ])

    const wrapper = await mountPicker('prd_oa')
    const control = wrapper.getComponent({ name: 'SegmentedChoiceControl' })
    expect(control.props('options')).toEqual([
      { value: 'prd_crm', label: 'CRM' },
      { value: 'prd_oa', label: 'OA' },
    ])
    expect(control.props('modelValue')).toBe('prd_oa')
    expect(wrapper.text()).not.toContain('基础模块')
    expect(wrapper.find('[data-testid="product-module-select"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('caps segmented columns at 3 so product names stay readable', async () => {
    vi.mocked(productApi.list).mockResolvedValueOnce([
      product('prd_a', 'Isolated Name'),
      product('prd_b', 'Verify Product'),
      product('prd_c', '第三产品'),
    ])

    const wrapper = await mountPicker()
    const control = wrapper.getComponent({ name: 'SegmentedChoiceControl' })
    expect(control.attributes('style')).toContain('--segmented-choice-columns: 3')
    wrapper.unmount()
  })

  it('uses the same label chrome as InputField', async () => {
    vi.mocked(productApi.list).mockResolvedValueOnce([product('prd_crm', 'CRM')])

    const wrapper = await mountPicker()
    expect(wrapper.get('div').classes()).toEqual(expect.arrayContaining(['grid', 'gap-wolf-xs']))
    const label = wrapper.getComponent({ name: 'Label' })
    expect(label.text()).toContain('产品')
    expect(label.text()).toContain('*')
    wrapper.unmount()
  })
})
