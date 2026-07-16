import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import OpportunityFormDialog from '@/components/dialogs/OpportunityFormDialog.vue'
import type { CustomerDetailResponse, CustomerResponse } from '@/api/customer'
import { UserStatus, type UserResponse } from '@/api/user'

const customerApi = vi.hoisted(() => ({
  getCustomers: vi.fn(),
  getCustomerDetail: vi.fn(),
}))

const procurementApi = vi.hoisted(() => ({
  getProcurementMethodOptions: vi.fn(),
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
vi.mock('@/api/user', () => ({
  default: userApi,
  UserStatus: { ACTIVE: 'active', INACTIVE: 'inactive' },
}))
vi.mock('@/api/opportunity', () => ({
  opportunityApi,
  LicenseType: { SUBSCRIPTION: 'SUBSCRIPTION', PERPETUAL: 'PERPETUAL' },
  PurchaseType: { NEW: 'NEW', RENEWAL: 'RENEWAL', EXPANSION: 'EXPANSION' },
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

vi.mock('@/components/ui/form', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    FormControl: passthrough('FormControl'),
    FormItem: passthrough('FormItem'),
    FormLabel: passthrough('FormLabel'),
    FormMessage: passthrough('FormMessage'),
    FormField: defineComponent({
      name: 'FormField',
      props: { name: { type: String, required: true } },
      setup: (props, { slots }) => () => h('div', { 'data-field': props.name }, slots.default?.({
        componentField: {
          name: props.name,
          modelValue: '',
          'onUpdate:modelValue': vi.fn(),
        },
        value: '',
        handleChange: vi.fn(),
      })),
    }),
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

    expect(wrapper.text()).toContain('上海测试客户')
    expect(customerApi.getCustomerDetail).toHaveBeenCalledWith(42)
    expect(wrapper.findAll('[data-testid="select"]')[0]?.attributes('data-disabled')).toBe('true')

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
    expect(wrapper.text()).toContain('可选择客户')
    expect(wrapper.findAll('[data-testid="select"]')[0]?.attributes('data-disabled')).toBe('false')
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

    const searchInput = wrapper.find('input[placeholder="搜索客户名称"]')
    expect(searchInput.exists()).toBe(true)

    await searchInput.setValue('搜索')
    await flushPromises()
    await nextTick()

    expect(customerApi.getCustomers).toHaveBeenLastCalledWith({ limit: 50, keyword: '搜索' })
    expect(wrapper.text()).toContain('搜索客户')
  })
})
