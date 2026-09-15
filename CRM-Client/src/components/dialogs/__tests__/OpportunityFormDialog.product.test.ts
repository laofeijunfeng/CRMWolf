import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, type Component, type VNode } from 'vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import type { CustomerDetailResponse } from '@/api/customer'
import { LicenseType, OpportunityStatus, PurchaseType, type Opportunity } from '@/api/opportunity'

const customerApi = vi.hoisted(() => ({
  getCustomers: vi.fn(),
  getCustomerDetail: vi.fn(),
}))

const procurementApi = vi.hoisted(() => ({
  getProcurementMethodOptions: vi.fn(),
}))

const productApi = vi.hoisted(() => ({
  list: vi.fn(),
}))

const opportunityApi = vi.hoisted(() => ({
  createOpportunity: vi.fn(),
}))

vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/procurement', () => ({ default: procurementApi }))
vi.mock('@/api/product', () => ({ default: productApi }))
vi.mock('@/api/opportunity', () => ({
  opportunityApi,
  LicenseType: { SUBSCRIPTION: 'SUBSCRIPTION', PERPETUAL: 'PERPETUAL' },
  PurchaseType: { NEW: 'NEW', RENEWAL: 'RENEWAL', EXPANSION: 'EXPANSION' },
  OpportunityStatus: { FOLLOW_UP: 0, WON: 1, LOST: 2 },
}))
vi.mock('@/stores/user', () => ({ useUserStore: (): { userInfo: { id: number; name: string } } => ({ userInfo: { id: 9, name: '当前销售' } }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

function passthrough(name: string): Component {
  return defineComponent({
    name,
    setup(_, { slots }): () => VNode {
      return () => h('div', slots.default?.())
    },
  })
}

vi.mock('@/components/ui/dialog', () => ({
  Dialog: defineComponent({
    name: 'UiDialog',
    props: { open: Boolean },
    emits: ['update:open'],
    setup(props, { slots }): () => VNode | null {
      return () => props.open ? h('section', { role: 'dialog' }, slots.default?.()) : null
    },
  }),
  DialogContent: passthrough('UiDialogContent'),
  DialogHeader: passthrough('UiDialogHeader'),
  DialogTitle: passthrough('UiDialogTitle'),
  DialogDescription: passthrough('UiDialogDescription'),
  DialogFooter: passthrough('UiDialogFooter'),
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: passthrough('UiAlertDialog'),
  AlertDialogAction: passthrough('UiAlertDialogAction'),
  AlertDialogCancel: passthrough('UiAlertDialogCancel'),
  AlertDialogContent: passthrough('UiAlertDialogContent'),
  AlertDialogDescription: passthrough('UiAlertDialogDescription'),
  AlertDialogFooter: passthrough('UiAlertDialogFooter'),
  AlertDialogHeader: passthrough('UiAlertDialogHeader'),
  AlertDialogTitle: passthrough('UiAlertDialogTitle'),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'UiButton',
    props: {
      type: { type: String, default: 'button' },
    },
    setup(props, { slots }): () => VNode {
      return () => h('button', { type: props.type ?? 'button' }, slots.default?.())
    },
  }),
}))

vi.mock('@/components/crmwolf', () => {
  const field = (name: string): Component => defineComponent({
    name,
    inheritAttrs: false,
    props: {
      modelValue: { type: [String, Number, Object], default: '' },
      options: { type: Array, default: () => [] },
      id: { type: String, default: '' },
      placeholder: { type: String, default: '' },
      disabled: { type: Boolean, default: false },
    },
    emits: ['update:modelValue'],
    setup(props, { emit, attrs }): () => VNode {
      return () => h('input', {
        ...attrs,
        id: props.id,
        value: props.modelValue ?? '',
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      })
    },
  })

  return {
    DateField: field('DateField'),
    InputField: field('InputField'),
    SearchableSelectField: field('SearchableSelectField'),
    SelectField: field('SelectField'),
    SegmentedChoiceControl: defineComponent({
      name: 'SegmentedChoiceControl',
      props: {
        modelValue: { type: String, default: '' },
        options: { type: Array, default: () => [] },
      },
      emits: ['update:modelValue'],
      setup(props, { emit }): () => VNode {
        return () => h('div', (props.options as { value: string, label: string }[]).map(option => h('label', {
          onClick: () => emit('update:modelValue', option.value),
        }, option.label)))
      },
    }),
    MultiSelect: defineComponent({
      name: 'MultiSelect',
      props: {
        modelValue: { type: Array, default: () => [] },
        options: { type: Array, default: () => [] },
      },
      emits: ['update:modelValue'],
      setup(props): () => VNode {
        return () => h('div', { 'data-testid': 'product-module-select' }, [
          h('span', { 'data-testid': 'selected-modules' }, (props.modelValue as string[]).join(',')),
        ])
      },
    }),
  }
})

interface ProductModuleFixture {
  id: string
  public_id: string
  name: string
  description: null
  module_role: 'BASE' | 'ADD_ON'
  is_active: true
  sort_order: number
  created_by: string
  updated_by: null
  created_time: string
  updated_time: string
}

interface ProductFixture {
  id: string
  public_id: string
  name: string
  description: null
  is_active: boolean
  created_by: string
  updated_by: null
  created_time: string
  updated_time: string
  modules: ProductModuleFixture[]
}

const productModule = (
  publicId: string,
  name: string,
  role: 'BASE' | 'ADD_ON' = 'BASE',
): ProductModuleFixture => ({
  id: publicId,
  public_id: publicId,
  name,
  description: null,
  module_role: role,
  is_active: true,
  sort_order: 0,
  created_by: 'u',
  updated_by: null,
  created_time: '2026-01-01T00:00:00',
  updated_time: '2026-01-01T00:00:00',
})

const productResponse = (
  publicId: string,
  name: string,
  modules: ProductModuleFixture[],
  isActive = true,
): ProductFixture => ({
  id: publicId,
  public_id: publicId,
  name,
  description: null,
  is_active: isActive,
  created_by: 'u',
  updated_by: null,
  created_time: '2026-01-01T00:00:00',
  updated_time: '2026-01-01T00:00:00',
  modules,
})

const customerDetail = (overrides: Partial<CustomerDetailResponse> = {}): CustomerDetailResponse => ({
  id: '42',
  public_id: 'CUS-42',
  account_name: '上海测试客户',
  industry: null,
  city: '上海',
  address: null,
  company_scale: null,
  source: null,
  status: 0,
  owner_id: '9',
  source_lead_id: null,
  default_procurement_method_id: null,
  loss_reason: null,
  return_reason: null,
  returned_time: null,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  version: 1,
  license_expiry_date: null,
  license_type: null,
  contacts: [],
  product_public_id: 'prd_crm',
  product_name: 'CRM',
  products: [{ public_id: 'prd_crm', name: 'CRM' }],
  ...overrides,
})

const opportunityFixture = (): Opportunity => ({
  id: 'opp_1',
  public_id: 'opp_1',
  opportunity_number: 'OPP-1',
  opportunity_name: 'OA 升级',
  customer_id: '42',
  customer_name: '上海测试客户',
  procurement_method_id: null,
  product_public_id: 'prd_oa',
  product_name: 'OA',
  product_module_public_ids: ['prm_oa_base'],
  product_modules: [{ public_id: 'prm_oa_base', name: '基础版', module_role: 'BASE' }],
  total_amount: 100000,
  user_count: 10,
  unit_price: 10000,
  license_type: LicenseType.SUBSCRIPTION,
  subscription_years: 1,
  purchase_type: PurchaseType.NEW,
  decision_maker_count: null,
  expected_closing_date: '2026-09-30',
  procurement_stage_id: null,
  win_probability: 20,
  owner_id: '9',
  creator_id: '9',
  status: OpportunityStatus.FOLLOW_UP,
  approval_phase: 'draft',
  created_time: '2026-01-01T00:00:00.000Z',
  updated_time: '2026-01-01T00:00:00.000Z',
  version: 1,
})

describe('OpportunityFormDialog product defaults', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    procurementApi.getProcurementMethodOptions.mockResolvedValue([])
    productApi.list.mockResolvedValue([
      productResponse('prd_crm', 'CRM', [productModule('prm_crm_base', '基础版'), productModule('prm_crm_pro', '专业版', 'ADD_ON')]),
      productResponse('prd_oa', 'OA', [productModule('prm_oa_base', '基础版')]),
    ])
    opportunityApi.createOpportunity.mockResolvedValue({ id: 1 })
  })

  it('defaults create mode to the customer active product and its BASE module, not OA', async () => {
    customerApi.getCustomerDetail.mockResolvedValue(customerDetail({ product_public_id: 'prd_crm' }))

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: false,
        customerId: '42',
        customerName: '上海测试客户',
        customerLocked: true,
      },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    expect(wrapper.findComponent({ name: 'SegmentedChoiceControl' }).props('modelValue')).toBe('prd_crm')
    expect(wrapper.get('[data-testid="selected-modules"]').text()).toBe('prm_crm_base')
    expect(wrapper.text()).not.toContain('请选择产品')
    wrapper.unmount()
  })

  it('keeps the saved opportunity product in edit mode even if the customer is CRM', async () => {
    customerApi.getCustomerDetail.mockResolvedValue(customerDetail({ product_public_id: 'prd_crm' }))

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: false,
        opportunity: opportunityFixture(),
      },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    expect(wrapper.findComponent({ name: 'SegmentedChoiceControl' }).props('modelValue')).toBe('prd_oa')
    expect(wrapper.get('[data-testid="selected-modules"]').text()).toBe('prm_oa_base')
    wrapper.unmount()
  })

  it('replaces 暂无可用产品 with the admin empty-catalog sentence', async () => {
    customerApi.getCustomerDetail.mockResolvedValue(customerDetail({ product_public_id: null }))
    productApi.list.mockResolvedValue([])

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: false,
        customerId: '42',
        customerLocked: true,
      },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建')
    expect(wrapper.text()).not.toContain('暂无可用产品')
    wrapper.unmount()
  })
})
