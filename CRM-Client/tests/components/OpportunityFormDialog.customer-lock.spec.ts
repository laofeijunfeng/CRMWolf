import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import type { CustomerDetailResponse, CustomerResponse } from '@/api/customer'
import { LicenseType, OpportunityStatus, PurchaseType, type Opportunity } from '@/api/opportunity'
import { UserStatus, type UserResponse } from '@/api/user'

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

const userApi = vi.hoisted(() => ({
  getUsers: vi.fn(),
}))

const opportunityApi = vi.hoisted(() => ({
  createOpportunity: vi.fn(),
}))

const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/procurement', () => ({ default: procurementApi }))
vi.mock('@/api/product', () => ({ default: productApi }))
vi.mock('@/api/user', () => ({
  default: userApi,
  UserStatus: { ACTIVE: 'active', INACTIVE: 'inactive' },
}))
vi.mock('@/api/opportunity', () => ({
  opportunityApi,
  LicenseType: { SUBSCRIPTION: 'SUBSCRIPTION', PERPETUAL: 'PERPETUAL' },
  PurchaseType: { NEW: 'NEW', RENEWAL: 'RENEWAL', EXPANSION: 'EXPANSION' },
  OpportunityStatus: { FOLLOW_UP: 0, WON: 1, LOST: 2 },
}))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ userInfo: { id: 9, name: '当前销售' } }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/ui/dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Dialog: defineComponent({
      name: 'Dialog',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open ? h('section', { role: 'dialog' }, slots.default?.()) : null,
    }),
    DialogContent: passthrough('DialogContent'),
    DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle'),
    DialogDescription: passthrough('DialogDescription'),
    DialogFooter: passthrough('DialogFooter'),
  }
})

vi.mock('@/components/ui/alert-dialog', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    AlertDialog: passthrough('AlertDialog'),
    AlertDialogAction: passthrough('AlertDialogAction'),
    AlertDialogCancel: passthrough('AlertDialogCancel'),
    AlertDialogContent: passthrough('AlertDialogContent'),
    AlertDialogDescription: passthrough('AlertDialogDescription'),
    AlertDialogFooter: passthrough('AlertDialogFooter'),
    AlertDialogHeader: passthrough('AlertDialogHeader'),
    AlertDialogTitle: passthrough('AlertDialogTitle'),
  }
})

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({ name: 'Button', props: { type: String }, setup: (props, { slots }) => () => h('button', { type: props.type ?? 'button' }, slots.default?.()) }),
}))

vi.mock('@/components/ui/input', () => ({
  Input: defineComponent({
    name: 'Input',
    props: {
      modelValue: [String, Number],
      placeholder: String,
      type: String,
    },
    emits: ['update:modelValue'],
    setup: (props, { emit, attrs }) => () => h('input', {
      ...attrs,
      value: props.modelValue,
      placeholder: props.placeholder,
      type: props.type ?? 'text',
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    }),
  }),
}))


vi.mock('@/components/ui/select', () => ({
  Select: defineComponent({
    name: 'Select',
    props: { disabled: Boolean },
    emits: ['update:open'],
    setup: (props, { slots }) => () => h('div', {
      'data-testid': 'select',
      'data-disabled': String(Boolean(props.disabled)),
    }, slots.default?.()),
  }),
  SelectContent: defineComponent({ name: 'SelectContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  SelectItem: defineComponent({
    name: 'SelectItem',
    props: { value: { type: String, required: true } },
    setup: (props, { slots }) => () => h('div', { 'data-testid': 'select-item', 'data-value': props.value }, slots.default?.()),
  }),
  SelectTrigger: defineComponent({ name: 'SelectTrigger', setup: (_, { slots }) => () => h('button', { type: 'button' }, slots.default?.()) }),
  SelectValue: defineComponent({ name: 'SelectValue', props: { placeholder: String }, setup: (props) => () => h('span', props.placeholder) }),
}))

vi.mock('@/components/crmwolf', () => {
  const field = (name: string) => defineComponent({
    name,
    inheritAttrs: false,
    props: {
      modelValue: { type: [String, Number, Object], default: '' },
      options: { type: Array, default: () => [] },
      searchValue: String,
      placeholder: String,
      disabled: Boolean,
      id: String,
      label: String,
    },
    emits: ['update:modelValue', 'update:searchValue'],
    setup: (props, { emit, attrs }) => () => h('div', [
      h('input', {
        ...attrs,
        id: props.id,
        value: props.modelValue ?? '',
        disabled: props.disabled,
        placeholder: props.placeholder,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      }),
    ]),
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
      setup: (props, { emit }) => () => h('div', (props.options as { value: string, label: string }[]).map(option => h('label', {
        onClick: () => emit('update:modelValue', option.value),
      }, option.label))),
    }),
    MultiSelect: defineComponent({
      name: 'MultiSelect',
      props: {
        modelValue: { type: Array, default: () => [] },
        options: { type: Array, default: () => [] },
        placeholder: String,
        disabled: Boolean,
      },
      emits: ['update:modelValue'],
      setup: (props, { emit }) => () => h('div', { 'data-testid': 'product-module-select' }, [
        h('span', { 'data-testid': 'selected-modules' }, (props.modelValue as string[]).join(',')),
        ...(props.options as { value: string, label: string }[]).map(option => h('button', {
          type: 'button',
          'data-testid': `module-option-${option.value}`,
          onClick: () => emit('update:modelValue', [...(props.modelValue as string[]), option.value]),
        }, option.label)),
      ]),
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

const productModule = (publicId: string, name: string): ProductModuleFixture => ({
  id: publicId,
  public_id: publicId,
  name,
  description: null,
  module_role: name === '基础版' ? 'BASE' : 'ADD_ON',
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

const opportunityFixture = (overrides: Partial<Opportunity> = {}): Opportunity => ({
  id: 'opp_1',
  public_id: 'opp_1',
  opportunity_number: 'OPP-1',
  opportunity_name: 'OA 升级',
  customer_id: '7',
  customer_name: '可选择客户',
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
  ...overrides,
})

const customerResponse = (id: number, accountName: string): CustomerResponse => ({
  id,
  account_name: accountName,
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
})

const userResponse = (id: number, name: string): UserResponse => ({
  id,
  name,
  email: `user-${id}@example.com`,
  mobile: null,
  avatar_url: null,
  employee_no: null,
  region: null,
  status: UserStatus.ACTIVE,
  roles: [],
  created_at: '2026-07-15T00:00:00.000Z',
  updated_at: '2026-07-15T00:00:00.000Z',
})

const customerDetail = (id: number, accountName: string): CustomerDetailResponse => ({
  id,
  account_name: accountName,
  industry: null,
  city: '上海',
  address: null,
  company_scale: null,
  source: null,
  status: 0,
  owner_id: '9',
  source_lead_id: null,
  default_procurement_method_id: null,
  creator_id: '9',
  created_time: '2026-07-15T00:00:00.000Z',
  last_modified_time: '2026-07-15T00:00:00.000Z',
  version: 1,
  contacts: [],
  company_background: null,
  company_website: null,
  main_business: null,
  similar_customers: null,
  project_background: null,
  profile_status: null,
  profile_generated_time: null,
  profile_error_message: null,
  default_opportunity: null,
})

describe('OpportunityFormDialog customer lock behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    procurementApi.getProcurementMethodOptions.mockResolvedValue([])
    productApi.list.mockResolvedValue([
      productResponse('prd_crm', 'CRM', [productModule('prm_base', '基础版'), productModule('prm_pro', '专业版')]),
      productResponse('prd_oa', 'OA', [productModule('prm_oa_base', '基础版')]),
    ])
    userApi.getUsers.mockResolvedValue([userResponse(9, '当前销售')])
    opportunityApi.createOpportunity.mockResolvedValue({ id: 1 })
  })

  it('shows the locked customer name from props before customer detail finishes loading', async () => {
    let resolveDetail: (value: CustomerDetailResponse) => void = () => undefined
    customerApi.getCustomerDetail.mockReturnValue(new Promise<CustomerDetailResponse>((resolve) => {
      resolveDetail = resolve
    }))

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: false,
        customerId: 42,
        customerName: '上海测试客户',
        customerLocked: true,
      },
    })

    await wrapper.setProps({ open: true })
    await nextTick()

    const lockedCustomerInput = wrapper.find('input#opportunity-customer-locked')
    expect(lockedCustomerInput.exists()).toBe(true)
    expect(lockedCustomerInput.element.value).toBe('上海测试客户')
    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith(42)

    resolveDetail(customerDetail(42, '上海测试客户'))
    await flushPromises()
  })

  it('keeps the customer Select unlocked and populated for general opportunity creation', async () => {
    customerApi.getCustomers.mockResolvedValue([customerResponse(7, '可选择客户')])
    customerApi.getCustomerDetail.mockResolvedValue(customerDetail(7, '可选择客户'))

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: false,
      },
    })

    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    expect(customerApi.getCustomers).toHaveBeenCalledWith({ limit: 50 })
    const customerSelect = wrapper.findComponent({ name: 'SearchableSelectField' })
    expect(customerSelect.exists()).toBe(true)
    expect(customerSelect.props('options')).toEqual([{ value: 7, label: '可选择客户' }])
  })

  it('searches customers from the unlocked customer dropdown search input', async () => {
    customerApi.getCustomers
      .mockResolvedValueOnce([customerResponse(7, '初始客户')])
      .mockResolvedValueOnce([customerResponse(8, '搜索客户')])

    const wrapper = mount(OpportunityFormDialog, {
      props: {
        open: false,
      },
    })

    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    const customerSelect = wrapper.findComponent({ name: 'SearchableSelectField' })
    expect(customerSelect.exists()).toBe(true)

    await customerSelect.vm.$emit('update:searchValue', '搜索')
    await flushPromises()
    await nextTick()

    expect(customerApi.getCustomers).toHaveBeenLastCalledWith({ limit: 50, keyword: '搜索' })
    expect(customerSelect.props('options')).toEqual([{ value: 8, label: '搜索客户' }])
  })

  it('shows product segmented options and module options for the selected product', async () => {
    customerApi.getCustomers.mockResolvedValue([customerResponse(7, '可选择客户')])

    const wrapper = mount(OpportunityFormDialog, {
      props: { open: false },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    expect(productApi.list).toHaveBeenCalled()
    expect(wrapper.text()).toContain('CRM')
    expect(wrapper.text()).toContain('OA')

    const crmOption = wrapper.findAll('label').find(label => label.text() === 'CRM')
    expect(crmOption).toBeTruthy()
    await crmOption!.trigger('click')
    await nextTick()

    expect(wrapper.find('[data-testid="module-option-prm_base"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="module-option-prm_oa_base"]').exists()).toBe(false)
  })
  it('resets modules to the new product base module when switching products', async () => {
    customerApi.getCustomers.mockResolvedValue([customerResponse(7, '可选择客户')])

    const wrapper = mount(OpportunityFormDialog, {
      props: { open: false },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()
    const crmOption = wrapper.findAll('label').find(label => label.text() === 'CRM')
    expect(crmOption).toBeTruthy()
    await crmOption!.trigger('click')
    await nextTick()

    await wrapper.get('[data-testid="module-option-prm_pro"]').trigger('click')
    await nextTick()
    expect(wrapper.get('[data-testid="selected-modules"]').text()).toContain('prm_pro')

    const oaOption = wrapper.findAll('label').find(label => label.text() === 'OA')
    expect(oaOption).toBeTruthy()
    await oaOption!.trigger('click')
    await nextTick()

    expect(wrapper.get('[data-testid="selected-modules"]').text()).toBe('prm_oa_base')
    expect(wrapper.find('[data-testid="module-option-prm_oa_base"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="module-option-prm_pro"]').exists()).toBe(false)
  })

  it('defaults create form to the first active product and its base module', async () => {
    customerApi.getCustomers.mockResolvedValue([customerResponse(7, '可选择客户')])
    productApi.list.mockResolvedValue([
      productResponse('prd_legacy', '旧产品', [productModule('prm_legacy', '基础版')], false),
      productResponse('prd_crm', 'CRM', [productModule('prm_base', '基础版'), productModule('prm_pro', '专业版')]),
      productResponse('prd_oa', 'OA', [productModule('prm_oa_base', '基础版')]),
    ])

    const wrapper = mount(OpportunityFormDialog, {
      props: { open: false },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await nextTick()

    expect(wrapper.findComponent({ name: 'SegmentedChoiceControl' }).props('modelValue')).toBe('prd_crm')
    expect(wrapper.get('[data-testid="selected-modules"]').text()).toBe('prm_base')
    expect(wrapper.text()).not.toContain('请选择产品')
    expect(wrapper.find('[data-testid="module-option-prm_oa_base"]').exists()).toBe(false)
  })

  it('keeps the existing product and modules when editing an opportunity', async () => {
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
    expect(wrapper.find('[data-testid="module-option-prm_base"]').exists()).toBe(false)
  })
})
