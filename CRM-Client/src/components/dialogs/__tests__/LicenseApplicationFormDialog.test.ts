import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, type Component, type VNode } from 'vue'
import LicenseApplicationFormDialog from '../LicenseApplicationFormDialog.vue'
import ProductIntentPicker from '@/components/crmwolf/ProductIntentPicker.vue'
import productApi from '@/api/product'
import licenseApplicationApi from '@/api/licenseApplication'
import type { ContractListResponse } from '@/api/contract'
import type { DeploymentInfoResponse } from '@/api/deployment'
import type { ProductResponse } from '@/schemas/product'
import { usePermissionStore } from '@/stores/permissions'

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }))

vi.mock('vue-sonner', () => ({ toast }))
vi.mock('@/api/product', () => ({ default: { list: vi.fn() } }))
vi.mock('@/api/licenseApplication', () => ({
  default: { create: vi.fn(), submitApplication: vi.fn() },
}))

const LOCKED_HINT = '产品跟随关联合同对应的商机，不可修改'
const EMPTY_CATALOG_COPY = '团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建'

const product = (publicId: string, name: string, isActive = true): ProductResponse => ({
  id: publicId,
  public_id: publicId,
  name,
  description: null,
  is_active: isActive,
  created_by: 'u',
  updated_by: null,
  created_time: '2026-01-01T00:00:00',
  updated_time: '2026-01-01T00:00:00',
  modules: [],
})

const deployment: DeploymentInfoResponse = {
  id: 42,
  customer_id: 'cus_1',
  team_id: 1,
  deployment_name: '生产环境',
  server_address: 'https://crm.example.com',
  authorized_users: null,
  is_default: true,
  created_time: '2026-08-20T10:00:00Z',
  last_modified_time: '2026-08-20T10:00:00Z',
}

const contract: ContractListResponse = {
  id: 9,
  contract_number: 'HT-001',
  contract_name: '年度合同',
  customer_id: 'cus_1',
  opportunity_id: 'opp_1',
  signing_contact_id: 1,
  user_count: 20,
  total_amount: '1000.00',
  license_type: 'SUBSCRIPTION',
  subscription_years: 1,
  standard_unit_price: '50.00',
  status: 'SIGNED',
  signing_date: null,
  effective_date: null,
  expiry_date: null,
  owner_id: 'u',
  creator_id: 'u',
  created_time: '2026-08-20T10:00:00Z',
  last_modified_time: '2026-08-20T10:00:00Z',
}

const slotStub = (name: string, tag = 'div'): Component => defineComponent({
  name,
  setup(_, { slots }): () => VNode {
    return () => h(tag, slots['default']?.())
  },
})

const DateFieldStub = defineComponent({
  name: 'DateField',
  emits: ['update:modelValue'],
  setup(): () => VNode {
    return () => h('div')
  },
})

const ButtonStub = defineComponent({
  inheritAttrs: true,
  setup(_, { attrs, slots }): () => VNode {
    return () => h('button', attrs, slots['default']?.())
  },
})

interface MountOptions {
  licenseType: 'TRIAL' | 'OFFICIAL'
  productPublicId?: string | null
  productName?: string | null
}

const mounted: VueWrapper[] = []

const mountDialog = async (options: MountOptions): Promise<VueWrapper> => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = usePermissionStore()
  store.loadState = 'ready'
  store.permissions = []
  const wrapper = mount(LicenseApplicationFormDialog, {
    props: {
      open: true,
      customerId: 'cus_1',
      deployments: [deployment],
      contracts: [contract],
      defaultLicenseType: options.licenseType,
      defaultContractId: options.licenseType === 'OFFICIAL' ? contract.id : null,
      opportunityProductPublicId: options.productPublicId ?? null,
      opportunityProductName: options.productName ?? null,
    },
    global: {
      plugins: [pinia],
      stubs: {
        Dialog: slotStub('Dialog'),
        DialogContent: slotStub('DialogContent'),
        DialogHeader: slotStub('DialogHeader'),
        DialogTitle: slotStub('DialogTitle'),
        DialogDescription: slotStub('DialogDescription'),
        DialogFooter: slotStub('DialogFooter'),
        SelectField: true,
        InputField: true,
        TextareaField: true,
        SelectionSummary: true,
        DeploymentInfoFormDialog: true,
        DateField: DateFieldStub,
        Button: ButtonStub,
        RouterLink: true,
      },
    },
  })
  mounted.push(wrapper)
  await flushPromises()
  await nextTick()
  return wrapper
}

const submit = async (wrapper: VueWrapper): Promise<void> => {
  const future = new Date()
  future.setDate(future.getDate() + 14)
  wrapper.findComponent(DateFieldStub).vm.$emit('update:modelValue', future)
  await nextTick()
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

const submitButton = (wrapper: VueWrapper): HTMLButtonElement =>
  wrapper.get<HTMLButtonElement>('button[type="submit"]').element

describe('LicenseApplicationFormDialog product', () => {
  afterEach(() => {
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.clearAllMocks()
  })

  it('locks OFFICIAL with a contract to the opportunity product and submits it', async () => {
    vi.mocked(productApi.list).mockResolvedValue([product('prd_apifox', 'Apifox'), product('prd_echo', 'EchoAPI')])
    vi.mocked(licenseApplicationApi.create).mockResolvedValue({ id: 1 } as never)

    const wrapper = await mountDialog({ licenseType: 'OFFICIAL', productPublicId: 'prd_apifox', productName: 'Apifox' })

    expect(wrapper.findComponent(ProductIntentPicker).props('locked')).toBe(true)
    expect(wrapper.findComponent(ProductIntentPicker).props('modelValue')).toBe('prd_apifox')
    expect(wrapper.text()).toContain(LOCKED_HINT)

    await submit(wrapper)
    expect(licenseApplicationApi.create).toHaveBeenCalledWith(expect.objectContaining({
      license_type: 'OFFICIAL',
      contract_id: contract.id,
      product_public_id: 'prd_apifox',
    }))
  })

  it('requires a product for OFFICIAL when the opportunity has none', async () => {
    vi.mocked(productApi.list).mockResolvedValue([product('prd_apifox', 'Apifox')])

    const wrapper = await mountDialog({ licenseType: 'OFFICIAL' })

    expect(wrapper.findComponent(ProductIntentPicker).props('locked')).toBe(false)
    expect(wrapper.findComponent(ProductIntentPicker).props('modelValue')).toBe('')
    expect(wrapper.text()).not.toContain(LOCKED_HINT)

    await submit(wrapper)
    expect(wrapper.get('#license-product-error').text()).toBe('请选择产品')
    expect(licenseApplicationApi.create).not.toHaveBeenCalled()
  })

  it('preselects the opportunity product for TRIAL and lets the user change it', async () => {
    vi.mocked(productApi.list).mockResolvedValue([product('prd_apifox', 'Apifox'), product('prd_echo', 'EchoAPI')])
    vi.mocked(licenseApplicationApi.create).mockResolvedValue({ id: 1 } as never)

    const wrapper = await mountDialog({ licenseType: 'TRIAL', productPublicId: 'prd_apifox', productName: 'Apifox' })

    expect(wrapper.findComponent(ProductIntentPicker).props('locked')).toBe(false)
    expect(wrapper.findComponent(ProductIntentPicker).props('modelValue')).toBe('prd_apifox')

    const echo = wrapper.findComponent(ProductIntentPicker).findAll('[role="radio"]')
      .find((option) => option.text().includes('EchoAPI'))
    await echo?.trigger('click')
    await submit(wrapper)
    expect(licenseApplicationApi.create).toHaveBeenCalledWith(expect.objectContaining({
      license_type: 'TRIAL',
      contract_id: null,
      product_public_id: 'prd_echo',
    }))
  })

  it('clears an inactive opportunity product for TRIAL', async () => {
    vi.mocked(productApi.list).mockResolvedValue([product('prd_apifox', 'Apifox', false), product('prd_echo', 'EchoAPI')])

    const wrapper = await mountDialog({ licenseType: 'TRIAL', productPublicId: 'prd_apifox', productName: 'Apifox' })

    expect(wrapper.findComponent(ProductIntentPicker).props('modelValue')).toBe('')
  })

  it('selects nothing without opportunity product context', async () => {
    vi.mocked(productApi.list).mockResolvedValue([product('prd_apifox', 'Apifox')])

    const wrapper = await mountDialog({ licenseType: 'TRIAL' })

    expect(wrapper.findComponent(ProductIntentPicker).props('modelValue')).toBe('')
  })

  it('shows the opportunity product read-only and allows submit without product view permission', async () => {
    vi.mocked(productApi.list).mockRejectedValue(Object.assign(new Error('Forbidden'), { response: { status: 403 } }))
    vi.mocked(licenseApplicationApi.create).mockResolvedValue({ id: 1 } as never)

    const wrapper = await mountDialog({ licenseType: 'OFFICIAL', productPublicId: 'prd_apifox', productName: 'Apifox' })

    expect(wrapper.get('[data-testid="product-intent-readonly"]').text()).toBe('Apifox')
    expect(submitButton(wrapper).disabled).toBe(false)

    await submit(wrapper)
    expect(licenseApplicationApi.create).toHaveBeenCalledWith(expect.objectContaining({ product_public_id: 'prd_apifox' }))
  })

  it('blocks submit without product view permission and no opportunity product', async () => {
    vi.mocked(productApi.list).mockRejectedValue(Object.assign(new Error('Forbidden'), { response: { status: 403 } }))

    const wrapper = await mountDialog({ licenseType: 'TRIAL' })

    expect(wrapper.get('[role="alert"]').text()).toBe('没有产品查看权限')
    expect(submitButton(wrapper).disabled).toBe(true)

    await submit(wrapper)
    expect(licenseApplicationApi.create).not.toHaveBeenCalled()
  })

  it('shows the empty-catalog copy and blocks submit when no product is active', async () => {
    vi.mocked(productApi.list).mockResolvedValue([])

    const wrapper = await mountDialog({ licenseType: 'TRIAL' })

    expect(wrapper.text()).toContain(EMPTY_CATALOG_COPY)
    expect(submitButton(wrapper).disabled).toBe(true)
  })
})
