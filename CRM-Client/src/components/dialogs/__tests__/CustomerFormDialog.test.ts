import { defineComponent, h, nextTick, type VNode } from 'vue'
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CustomerFormDialog from '../CustomerFormDialog.vue'
import FormErrorSummary from '@/components/crmwolf/FormErrorSummary.vue'
import customerApi, { type CustomerDetailResponse } from '@/api/customer'
import procurementApi from '@/api/procurement'
import { acquisitionSourceApi } from '@/api/acquisition-source'
import { customerCreateSchema, customerEditSchema, customerFormSchema } from '@/schemas/customer-form'

vi.mock('@/api/product', () => ({
  default: {
    list: vi.fn().mockResolvedValue([
      {
        id: 'prd_crm',
        public_id: 'prd_crm',
        name: 'CRM',
        description: null,
        is_active: true,
        created_by: 'u',
        updated_by: null,
        created_time: '2026-01-01T00:00:00',
        updated_time: '2026-01-01T00:00:00',
        modules: [],
      },
    ]),
  },
}))
Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
})

const DialogSlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }): () => VNode {
    return () => h('div', slots['default']?.())
  },
})
const DialogPartStub = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }): () => VNode {
    return () => h('div', attrs, slots['default']?.())
  },
})
const IndustryHierarchySelectFieldStub = defineComponent({
  name: 'IndustryHierarchySelectField',
  inheritAttrs: false,
  props: {
    id: { type: String, required: true },
    modelValue: { type: String, default: '' },
    label: { type: String, default: '' },
    error: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    retainedIndustryInfo: { type: Object, default: null },
  },
  emits: ['update:modelValue'],
  setup(props): () => VNode {
    return () => {
      const retained = props.retainedIndustryInfo
      const retainedName = retained !== null && typeof retained === 'object' && 'name' in retained && typeof retained['name'] === 'string' ? retained['name'] : ''
      return h('div', [
        props.label === '' ? null : h('span', props.label),
        h('button', {
          id: props.id,
          type: 'button',
          role: 'combobox',
          disabled: props.disabled,
          'aria-invalid': props.error !== '' ? 'true' : 'false',
          'aria-describedby': props.error !== '' ? `${props.id}-error` : undefined,
        }, `${props.modelValue}${retainedName === '' ? '' : ` ${retainedName}`}`),
      ])
    }
  },
})

const InputFieldStub = defineComponent({
  name: 'InputField',
  inheritAttrs: false,
  props: {
    id: { type: String, required: true },
    modelValue: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }): () => VNode {
    return () => h('input', {
      id: props.id,
      value: props.modelValue,
      disabled: props.disabled,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    })
  },
})

const SelectFieldStub = defineComponent({
  name: 'SelectField',
  inheritAttrs: false,
  props: {
    id: { type: String, required: true },
    modelValue: { type: [String, Number], default: '' },
    label: { type: String, default: '' },
    options: { type: Array, default: () => [] },
    disabled: { type: Boolean, default: false },
    ariaLabel: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }): () => VNode {
    return () => h('div', [
      props.label === '' ? null : h('span', props.label),
      h('button', {
        id: props.id,
        type: 'button',
        disabled: props.disabled,
        'aria-label': props.ariaLabel || undefined,
        onClick: () => {
          const options = props.options as { value?: string | number }[]
          emit('update:modelValue', options[1]?.value ?? options[0]?.value ?? '')
        },
      }, String(props.modelValue ?? '')),
    ])
  },
})

const DateFieldStub = defineComponent({
  name: 'DateField',
  inheritAttrs: false,
  props: {
    id: { type: String, required: true },
    label: { type: String, default: '' },
    modelValue: { type: Date, default: null },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }): () => VNode {
    return () => h('div', [
      props.label === '' ? null : h('span', props.label),
      h('button', {
        id: props.id,
        type: 'button',
        disabled: props.disabled,
        onClick: () => emit('update:modelValue', new Date('2026-12-31T00:00:00')),
      }, props.modelValue === null ? '' : props.modelValue.toISOString()),
    ])
  },
})

const MoreInfoCollapsibleStub = defineComponent({
  name: 'MoreInfoCollapsible',
  inheritAttrs: false,
  props: { open: { type: Boolean, default: false } },
  emits: ['update:open'],
  setup(props, { emit, slots }): () => VNode {
    return () => h('div', {
      onClick: (event: MouseEvent) => {
        const target = event.target instanceof HTMLElement ? event.target : null
        if (target?.closest('#customer-more-info-trigger') !== null) emit('update:open', !props.open)
      },
    }, slots['default']?.())
  },
})
const customerDetail: CustomerDetailResponse = {
  id: 'customer-1',
  public_id: 'CUS-001',
  account_name: '测试客户',
  industry: null,
  city: '上海',
  address: '测试地址',
  company_scale: 'small',
  source: null,
  status: 1,
  owner_id: '1',
  source_lead_id: null,
  default_procurement_method_id: 1,
  loss_reason: null,
  return_reason: null,
  returned_time: null,
  creator_id: '1',
  created_time: '2026-09-04T00:00:00Z',
  last_modified_time: '2026-09-04T00:00:00Z',
  version: 3,
  license_expiry_date: null,
  license_type: null,
  contacts: [],
  product_public_id: 'prd_crm',
  product_name: 'CRM',
  products: [{ public_id: 'prd_crm', name: 'CRM' }],
}

describe('CustomerFormDialog edit initialization', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses the prefetched customer and avoids a second detail-loading transition', async () => {
    const getCustomerDetail = vi.spyOn(customerApi, 'getCustomerDetail')
      .mockRejectedValue(new Error('detail should not be requested when prefetched'))
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const wrapper = shallowMount(CustomerFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: {
        open: true,
        mode: 'edit',
        customerId: customerDetail.id,
        customer: customerDetail,
      },
    })
    await nextTick()

    expect(getCustomerDetail).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('retries loading customer details after the initial request fails', async () => {
    const getCustomerDetail = vi.spyOn(customerApi, 'getCustomerDetail')
      .mockRejectedValueOnce(new Error('initial load failed'))
      .mockResolvedValueOnce(customerDetail)
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const wrapper = shallowMount(CustomerFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: {
        open: true,
        mode: 'edit',
        customerId: customerDetail.id,
      },
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as { retryCustomerDetail: () => void }
    vm.retryCustomerDetail()
    await flushPromises()

    expect(getCustomerDetail).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
  it('forwards detail industry_info to the retained industry selector', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const customer = { ...customerDetail, industry: 'legacy.industry', industry_info: { code: 'legacy.industry', name: '传统 / 已停用' } }
    const wrapper = shallowMount(CustomerFormDialog, {
      global: { stubs: { Dialog: DialogSlotStub, DialogContent: DialogSlotStub, Collapsible: MoreInfoCollapsibleStub, CollapsibleTrigger: defineComponent({ template: '<slot />' }), CollapsibleContent: defineComponent({ template: '<div><slot /></div>' }), IndustryHierarchySelectField: IndustryHierarchySelectFieldStub } },
      props: { open: true, mode: 'edit', customerId: customer.id, customer },
    })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await nextTick()
    expect(wrapper.get('#customer-industry').text()).toContain('传统 / 已停用')
    wrapper.unmount()
  })



describe('CustomerFormDialog product schema', () => {
  it('requires product_public_id on create, form, and edit schemas', () => {
    const missing = {
      account_name: '新客户',
      city: '上海',
      company_scale: '1-50人' as const,
      source_public_id: 'source-1',
      default_procurement_method_id: 1,
      contact_name: '张三',
      contact_mobile: '13800138000',
      contact_position: '经理',
      contact_gender: '男' as const,
    }
    expect(customerCreateSchema.safeParse(missing).success).toBe(false)
    expect(customerFormSchema.safeParse({
      account_name: '新客户',
      city: '上海',
      company_scale: '1-50人',
      source_public_id: 'source-1',
      default_procurement_method_id: 1,
    }).success).toBe(false)
    expect(customerEditSchema.safeParse({
      account_name: '新客户',
      city: '上海',
    }).success).toBe(false)
    expect(customerCreateSchema.safeParse({ ...missing, product_public_id: 'prd_crm' }).success).toBe(true)
  })
})
describe('CustomerFormDialog mode transitions', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not show stale contact validation errors after switching from create to edit', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const wrapper = shallowMount(CustomerFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: {
        open: true,
        mode: 'create',
      },
    })

    await nextTick()
    await (wrapper.vm as unknown as { setFieldError: (field: string, message: string) => void }).setFieldError('contact_gender', '请选择性别')
    await nextTick()
    const errorSummary = wrapper.findComponent(FormErrorSummary)
    expect(errorSummary.props('items')).toEqual(expect.arrayContaining([
      expect.objectContaining({ field: 'contact_gender', label: '性别', message: '请选择性别' }),
    ]))

    await wrapper.setProps({ open: false })
    await wrapper.setProps({
      open: true,
      mode: 'edit',
      customerId: customerDetail.id,
      customer: customerDetail,
    })
    await flushPromises()

    expect(errorSummary.props('items')).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ field: 'contact_gender', label: '性别' }),
    ]))

    wrapper.unmount()
  })
  it('clears ordinary field errors when switching customers', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const customerA = { ...customerDetail, id: 'customer-a' }
    const customerB = { ...customerDetail, id: 'customer-b', city: '北京' }
    const wrapper = shallowMount(CustomerFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: { open: true, mode: 'edit', customerId: customerA.id, customer: customerA },
    })
    await flushPromises()

    interface FormState {
      setFieldError: (field: string, message: string) => void
      errors: Record<string, string | undefined>
      submitError: unknown
    }
    const formState = wrapper.vm as unknown as FormState
    formState.setFieldError('city', '请输入所在城市')
    formState.setFieldError('industry', '行业代码无效')
    formState.submitError = { kind: 'conflict', description: '旧客户冲突' }
    await nextTick()
    expect(formState.errors['city']).toBe('请输入所在城市')
    expect(formState.errors['industry']).toBe('行业代码无效')

    await wrapper.setProps({ customerId: customerB.id, customer: customerB })
    await flushPromises()

    expect(formState.errors['city']).toBeUndefined()
    expect(formState.errors['industry']).toBeUndefined()
    expect(formState.submitError).toBeNull()
    wrapper.unmount()
  })
  it('clears optional profile fields when switching to a customer without them', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const customerA = {
      ...customerDetail,
      id: 'customer-a',
      company_scale: '1-50人',
      source_info: { public_id: 'source-a', name: '来源 A', is_active: true },
      default_procurement_method_id: 8,
    }
    const customerB = {
      ...customerDetail,
      id: 'customer-b',
      company_scale: null,
      source_info: null,
      default_procurement_method_id: null,
      product_public_id: null,
      product_name: null,
      products: [],
    }
    const wrapper = shallowMount(CustomerFormDialog, {
      global: { stubs: { Dialog: DialogSlotStub, DialogContent: DialogSlotStub } },
      props: { open: true, mode: 'edit', customerId: customerA.id, customer: customerA },
    })
    await flushPromises()
    const initialValues = (wrapper.vm as unknown as { values: Record<string, unknown> }).values
    expect(initialValues['product_public_id']).toBe('prd_crm')
    expect(initialValues['company_scale']).toBe('1-50人')
    expect(initialValues['source_public_id']).toBe('source-a')
    expect(initialValues['default_procurement_method_id']).toBe(8)
    await wrapper.setProps({ customerId: customerB.id, customer: customerB })
    await flushPromises()
    const switchedValues = (wrapper.vm as unknown as { values: Record<string, unknown> }).values
    expect(switchedValues['company_scale']).toBeUndefined()
    expect(switchedValues['source_public_id']).toBeUndefined()
    expect(switchedValues['product_public_id']).toBe('')
    expect(switchedValues['default_procurement_method_id']).toBeUndefined()
    wrapper.unmount()
  })
  it('allows editing another field when legacy profile fields are unset', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({ ...customerDetail, city: '北京', version: 4 })
    const legacyCustomer = { ...customerDetail, company_scale: null, source_info: null, default_procurement_method_id: null }
    const wrapper = shallowMount(CustomerFormDialog, {
      global: { stubs: { Dialog: DialogSlotStub, DialogContent: DialogSlotStub } },
      props: { open: true, mode: 'edit', customerId: legacyCustomer.id, customer: legacyCustomer },
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      setValues: (values: Record<string, unknown>) => void
      onSubmit: (event: Event) => Promise<void>
    }
    vm.setValues({ city: '北京' })
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateCustomer).toHaveBeenCalledWith('customer-1', {
      expected_version: 3,
      city: '北京',
    })
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })
  it('preserves an unknown legacy company scale while saving another field', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({ ...customerDetail, city: '北京', version: 4 })
    const legacyCustomer = { ...customerDetail, company_scale: 'small' }
    const wrapper = shallowMount(CustomerFormDialog, {
      global: { stubs: { Dialog: DialogSlotStub, DialogContent: DialogSlotStub } },
      props: { open: true, mode: 'edit', customerId: legacyCustomer.id, customer: legacyCustomer },
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      values: Record<string, unknown>
      setValues: (values: Record<string, unknown>) => void
      onSubmit: (event: Event) => Promise<void>
    }
    expect(vm.values['company_scale']).toBe('small')
    vm.setValues({ city: '北京' })
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateCustomer).toHaveBeenCalledWith('customer-1', {
      expected_version: 3,
      city: '北京',
    })
    wrapper.unmount()
  })
})
 
describe('CustomerFormDialog progressive edit sections', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  const dialogStubs = {
    Dialog: DialogSlotStub,
    DialogContent: DialogSlotStub,
    DialogFooter: DialogSlotStub,
    DialogHeader: DialogPartStub,
    DialogTitle: DialogPartStub,
    DialogDescription: DialogPartStub,
    Collapsible: MoreInfoCollapsibleStub,
    CollapsibleTrigger: defineComponent({ template: '<slot />' }),
    CollapsibleContent: defineComponent({ template: '<div><slot /></div>' }),
    IndustryHierarchySelectField: IndustryHierarchySelectFieldStub,
    SelectField: SelectFieldStub,
    DateField: DateFieldStub,
    InputField: InputFieldStub,
    Button: defineComponent({ inheritAttrs: false, template: '<button v-bind="$attrs"><slot /></button>' }),
    FormField: defineComponent({ setup(_, { slots }): () => VNode { return () => h('div', slots['default']?.({ value: undefined, handleChange: () => undefined })) } }),
    Field: defineComponent({ setup(_, { slots }): () => VNode { return () => h('div', slots['default']?.({ value: undefined, handleChange: () => undefined })) } }),
    FormItem: defineComponent({ template: '<div><slot /></div>' }),
    FormMessage: defineComponent({ template: '<div><slot /></div>' }),
  }
  const mountEdit = (customer: CustomerDetailResponse = { ...customerDetail, company_scale: '1-50人', source_info: { public_id: 'source-1', name: '来源', is_active: true } }): VueWrapper<InstanceType<typeof CustomerFormDialog>> => shallowMount(CustomerFormDialog, {
    global: { stubs: dialogStubs },
    props: {
      open: true,
      mode: 'edit',
      customerId: customer.id,
      customer,
    },
    attachTo: document.body,
  })
  const mountCreate = (): VueWrapper<InstanceType<typeof CustomerFormDialog>> => shallowMount(CustomerFormDialog, {
    global: { stubs: dialogStubs },
    props: { open: true, mode: 'create' },
    attachTo: document.body,
  })
  const mountCreateAndFillRequiredFields = (): VueWrapper<InstanceType<typeof CustomerFormDialog>> => {
    const wrapper = mountCreate()
    const vm = wrapper.vm as unknown as { setValues: (values: Record<string, unknown>) => void }
    vm.setValues({
      account_name: '新客户',
      city: '上海',
      company_scale: '1-50人',
      source_public_id: 'source-1',
      default_procurement_method_id: 1,
      contact_name: '张三',
      contact_mobile: '13800138000',
      contact_position: '经理',
      contact_gender: '男',
      product_public_id: 'prd_crm',
    })
    return wrapper
  }
  it('renders the more-information trigger collapsed in create and edit modes', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const createWrapper = mountCreate()
    const editWrapper = mountEdit()
    await flushPromises()
    expect(createWrapper.get('#customer-more-info-trigger').attributes('aria-expanded')).toBe('false')
    expect(createWrapper.get('#customer-more-info-trigger').attributes('aria-controls')).toBe('customer-more-info-content')
    expect(editWrapper.get('#customer-more-info-trigger').attributes('aria-expanded')).toBe('false')
    expect(editWrapper.get('#customer-more-info-trigger').attributes('aria-controls')).toBe('customer-more-info-content')
    createWrapper.unmount()
    editWrapper.unmount()
  })
  it('places create contact fields above the more-information trigger', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountCreate()
    await flushPromises()
    const contact = wrapper.get('#customer-contact-name').element
    const trigger = wrapper.get('#customer-more-info-trigger').element
    expect(Boolean(contact.compareDocumentPosition(trigger) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    wrapper.unmount()
  })

  it('does not render contact fields in edit mode', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit()
    await flushPromises()
    expect(wrapper.find('#customer-contact-name').exists()).toBe(false)
    expect(wrapper.find('#customer-more-info-trigger').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps more-information layout classes on an inner wrapper', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountCreate()
    await flushPromises()
    const content = wrapper.get('#customer-more-info-content')
    expect(content.classes()).not.toContain('grid')
    expect(content.find('.grid').exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders one flat more-information group without independent save actions', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit({ ...customerDetail, status: 0 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    expect(wrapper.get('#customer-more-info-trigger').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('#customer-more-info-trigger').attributes('aria-controls')).toBe('customer-more-info-content')
    expect(wrapper.text()).toContain('行业')
    expect(wrapper.text()).toContain('客户状态')
    expect(wrapper.text()).toContain('授权类型')
    expect(wrapper.text()).toContain('授权到期日')
    expect(wrapper.text()).toContain('此处只更新客户授权汇总信息，不创建 License 申请、不发起审批，也不修改正式 License 记录。')
    expect(wrapper.findAll('button').some((button) => button.text() === '应用状态变更')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === '保存授权信息')).toBe(false)
    expect(wrapper.findAll('button').some((button) => button.text() === '清除日期')).toBe(false)
    expect(wrapper.findAll('button').filter((button) => button.text() === '保存客户资料')).toHaveLength(1)
    wrapper.unmount()
  })
  it('counts an existing status 0 in the collapsed more-information summary', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit({ ...customerDetail, status: 0, industry: null, license_type: null, license_expiry_date: null })
    await flushPromises()
    await nextTick()

    expect(wrapper.get('#customer-more-info-trigger').text()).toContain('1 项')
    wrapper.unmount()
  })

  it.each([2, 3])('counts read-only existing status %s in the collapsed summary and preserves the read-only message', async (status) => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit({ ...customerDetail, status: status as 2 | 3, industry: null, license_type: null, license_expiry_date: null })
    await flushPromises()
    await nextTick()

    expect(wrapper.get('#customer-more-info-trigger').text()).toContain('1 项')
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('该客户状态由其他流程管理，暂不支持在此修改。')
    wrapper.unmount()
  })

  it('saves an industry-only edit through the ordinary dirty-diff update', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    vi.spyOn(customerApi, 'getIndustryHierarchy').mockResolvedValue({})
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({ ...customerDetail, industry: 'finance.securities', version: 4 })
    const wrapper = mountEdit()
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      industryValue: string
      onSubmit: (event: Event) => Promise<void>
    }
    vm.industryValue = 'finance.securities'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateCustomer).toHaveBeenCalledWith('customer-1', expect.objectContaining({
      expected_version: 3,
      industry: 'finance.securities',
    }))
    expect(updateCustomer.mock.calls[0]?.[1]).not.toHaveProperty('license_type')
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    expect(wrapper.emitted('success')).toHaveLength(1)
    expect(wrapper.emitted('refresh')).toBeUndefined()
  })

  it('saves profile, industry, status, and license in one ordinary PUT', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({
      ...customerDetail,
      industry: 'finance_securities',
      city: '上海',
      status: 1,
      version: 4,
      license_expiry_date: '2027-01-01',
      license_type: 'OFFICIAL',
    })
    const wrapper = mountEdit({ ...customerDetail, status: 0, version: 3, city: '北京' })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      setValues: (values: Record<string, unknown>) => void
      industryValue: string
      lifecycleStatusValue: 0 | 1 | null
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
    }
    vm.setValues({ city: '上海' })
    vm.industryValue = 'finance_securities'
    vm.lifecycleStatusValue = 1
    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2027-01-01'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateCustomer).toHaveBeenCalledTimes(1)
    expect(updateCustomer).toHaveBeenCalledWith('customer-1', {
      expected_version: 3,
      city: '上海',
      industry: 'finance_securities',
      status: 1,
      license_type: 'OFFICIAL',
      license_expiry_date: '2027-01-01',
    })
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    expect(wrapper.emitted('success')).toHaveLength(1)
    wrapper.unmount()
  })

  it('sends optional more-information values through the create POST', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const createCustomer = vi.spyOn(customerApi, 'createCustomer').mockResolvedValue({
      ...customerDetail,
      id: 'customer-created',
      public_id: 'CUS-CREATED',
      account_name: '新客户',
      industry: 'internet_saas',
      city: '上海',
      address: null,
      company_scale: '1-50人',
      status: 1,
      version: 1,
      license_expiry_date: '2026-12-31',
      license_type: 'TRIAL',
    })
    const wrapper = mountCreateAndFillRequiredFields()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      industryValue: string
      lifecycleStatusValue: 0 | 1 | null
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
    }
    vm.industryValue = 'internet_saas'
    vm.lifecycleStatusValue = 1
    vm.licenseTypeValue = 'TRIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(createCustomer).toHaveBeenCalledWith(expect.objectContaining({
      product_public_id: 'prd_crm',
      industry: 'internet_saas',
      status: 1,
      license_type: 'TRIAL',
      license_expiry_date: '2026-12-31',
    }))
    wrapper.unmount()
  })

  it('saves a status change through the ordinary PUT and closes', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const customer = { ...customerDetail, status: 0 as const, version: 8 }
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({ ...customer, status: 1, version: 9 })
    const updateLifecycle = vi.spyOn(customerApi, 'updateCustomerLifecycleStatus')
    const wrapper = mountEdit(customer)
    await flushPromises()

    const vm = wrapper.vm as unknown as { lifecycleStatusValue: 0 | 1 | null; onSubmit: (event: Event) => Promise<void> }
    vm.lifecycleStatusValue = 1
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateLifecycle).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenCalledWith('customer-1', { expected_version: 8, status: 1 })
    expect(wrapper.emitted('refresh')).toBeUndefined()
    expect(wrapper.emitted('success')).toHaveLength(1)
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })
  it.each([2, 3])('does not treat read-only lifecycle status %s as dirty', async (status) => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit({ ...customerDetail, status: status as 2 | 3 })
    await flushPromises()
    const vm = wrapper.vm as unknown as { handleCancel: () => void; showConfirmDialog: boolean; lifecycleStatusValue: unknown }
    expect(vm.lifecycleStatusValue).toBeNull()
    vm.handleCancel()
    expect(vm.showConfirmDialog).toBe(false)
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })

  it('treats null industry and empty industry baseline as unchanged', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit({ ...customerDetail, industry: null })
    await flushPromises()
    const vm = wrapper.vm as unknown as { industryValue: string; industryBaseline: string | null; handleCancel: () => void; showConfirmDialog: boolean }
    expect(vm.industryValue).toBe('')
    expect(vm.industryBaseline).toBe('')
    vm.handleCancel()
    expect(vm.showConfirmDialog).toBe(false)
    wrapper.unmount()
  })

  it('closes and emits success for a clean ordinary save', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
    const wrapper = mountEdit()
    await flushPromises()
    await (wrapper.vm as unknown as { onSubmit: (event: Event) => Promise<void> }).onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateCustomer).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    expect(wrapper.emitted('success')).toHaveLength(1)
    wrapper.unmount()
  })

  it('saves dirty license values through the ordinary PUT and closes', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({ ...customerDetail, account_name: '更新客户', license_type: 'TRIAL', license_expiry_date: '2026-12-31', version: 4 })
    const updateLicense = vi.spyOn(customerApi, 'updateCustomerLicenseSnapshot')
    const wrapper = mountEdit()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      setValues: (values: Record<string, unknown>) => void
      onSubmit: (event: Event) => Promise<void>
    }
    vm.licenseTypeValue = 'TRIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    vm.setValues({ account_name: '更新客户' })
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateLicense).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenCalledWith('customer-1', {
      expected_version: 3,
      account_name: '更新客户',
      license_type: 'TRIAL',
      license_expiry_date: '2026-12-31',
    })
    expect(wrapper.emitted('refresh')).toBeUndefined()
    expect(wrapper.emitted('success')).toHaveLength(1)
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })

  it('expands more information before focusing the rendered industry control on error', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit()
    await flushPromises()
    const vm = wrapper.vm as unknown as { setFieldError: (field: string, message: string) => void; focusFirstError: () => Promise<void>; moreInfoOpen: boolean }
    vm.setFieldError('industry', '请选择行业')
    await nextTick()
    const industryControl = document.querySelector('#customer-industry')
    expect(industryControl).toBeInstanceOf(HTMLElement)
    if (!(industryControl instanceof HTMLElement)) throw new Error('industry control was not rendered')
    const focus = vi.spyOn(HTMLElement.prototype, 'focus')
    await vm.focusFirstError()
    expect(vm.moreInfoOpen).toBe(true)
    expect(focus).toHaveBeenCalledWith({ preventScroll: true })
    expect(focus.mock.instances).toContain(industryControl)
    expect(wrapper.get('#customer-industry').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#customer-industry').attributes('aria-describedby')).toBe('customer-industry-error')
    wrapper.unmount()
  })

  it('tracks ordinary submit as the only writeSubmitting state', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit()
    const vm = wrapper.vm as unknown as { writeSubmitting: boolean; submitting: boolean }
    await flushPromises()
    expect(vm.writeSubmitting).toBe(false)
    vm.submitting = true
    await nextTick()
    expect(vm.writeSubmitting).toBe(true)
    wrapper.unmount()
  })

  it('blocks save when license expiry is set without a type', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
    const wrapper = mountEdit()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
      errors: Record<string, string | undefined>
    }
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateCustomer).not.toHaveBeenCalled()
    expect(vm.errors['license_expiry_date']).toBe('授权到期日期不为空时必须选择授权类型')
    expect(wrapper.emitted('update:open')).toBeUndefined()
    wrapper.unmount()
  })

})
describe('CustomerFormDialog recovery and close guards', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  const mountRecoveryEdit = (customer: CustomerDetailResponse = { ...customerDetail, company_scale: '1-50人', source_info: { public_id: 'source-1', name: '来源', is_active: true } }): VueWrapper<InstanceType<typeof CustomerFormDialog>> => shallowMount(CustomerFormDialog, {
    global: {
      stubs: {
        Dialog: DialogSlotStub,
        DialogContent: DialogSlotStub,
        DialogFooter: DialogSlotStub,
        Collapsible: MoreInfoCollapsibleStub,
        CollapsibleTrigger: defineComponent({ template: '<slot />' }),
        CollapsibleContent: defineComponent({ template: '<div><slot /></div>' }),
        FormField: defineComponent({ setup(_, { slots }): () => VNode { return () => h('div', slots['default']?.({ value: undefined, handleChange: () => undefined })) } }),
        Field: defineComponent({ setup(_, { slots }): () => VNode { return () => h('div', slots['default']?.({ value: undefined, handleChange: () => undefined })) } }),
        FormItem: defineComponent({ template: '<div><slot /></div>' }),
        FormMessage: defineComponent({ template: '<div><slot /></div>' }),
        IndustryHierarchySelectField: IndustryHierarchySelectFieldStub,
        SelectField: SelectFieldStub,
        DateField: DateFieldStub,
        InputField: InputFieldStub,
        Button: defineComponent({ inheritAttrs: false, template: '<button v-bind="$attrs"><slot /></button>' }),
      },
    },
    props: { open: true, mode: 'edit', customerId: customer.id, customer },
  })
  it('labels the status control as 客户状态', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountRecoveryEdit({ ...customerDetail, status: 0 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('客户状态')
    wrapper.unmount()
  })
  it('disables only industry after hierarchy loading failure and retries successfully', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const getHierarchy = vi.spyOn(customerApi, 'getIndustryHierarchy')
      .mockRejectedValueOnce(new Error('hierarchy failed'))
      .mockResolvedValueOnce({ manufacturing: { name: '制造业', children: [] } })
    const wrapper = mountRecoveryEdit()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()
    expect(wrapper.get('#customer-industry').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#customer-industry').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#customer-account-name').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-city').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-company-scale').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-source').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-procurement-method').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-address').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-more-info-trigger').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-lifecycle-status').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-license-type').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-license-expiry-date').attributes('disabled')).toBeUndefined()
    await wrapper.findAll('button').find((button) => button.text() === '重试')?.trigger('click')
    await flushPromises()
    expect(getHierarchy).toHaveBeenCalledTimes(2)
    expect(wrapper.get('#customer-industry').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('#customer-industry').attributes('aria-invalid')).toBe('false')
    wrapper.unmount()
  })

  it('keeps entered values and the dialog open after ordinary PUT failure', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    vi.spyOn(customerApi, 'updateCustomer').mockRejectedValue(new Error('update failed'))
    const wrapper = mountRecoveryEdit()
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      setValues: (values: Record<string, unknown>) => void
      values: Record<string, unknown>
      onSubmit: (event: Event) => Promise<void>
    }
    vm.setValues({ account_name: '当前输入' })
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(vm.values['account_name']).toBe('当前输入')
    expect(wrapper.props('open')).toBe(true)
    wrapper.unmount()
  })
  it('keeps entered license values, dialog open, and error after ordinary PUT failure', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockRejectedValue(new Error('update failed'))
    const updateLicense = vi.spyOn(customerApi, 'updateCustomerLicenseSnapshot')
    const wrapper = mountRecoveryEdit()
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
    }
    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateLicense).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenCalledWith('customer-1', {
      expected_version: 3,
      license_type: 'OFFICIAL',
      license_expiry_date: '2026-12-31',
    })
    expect(wrapper.props('open')).toBe(true)
    expect(wrapper.get('#customer-license-type').text()).toBe('OFFICIAL')
    expect(vm.licenseExpiryDateValue).toBe('2026-12-31')
    expect(wrapper.find('[role="alert"]').text()).toContain('请重试')
    expect(wrapper.emitted('update:open')).toBeUndefined()
    wrapper.unmount()
  })
  it('offers recovery, applies latest values, and retries with refreshed version while preserving input', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const latest = { ...customerDetail, license_type: 'TRIAL' as const, license_expiry_date: '2027-01-01', version: 11 }
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValueOnce({ ...latest, license_type: 'OFFICIAL' as const, license_expiry_date: '2026-12-31', version: 12 })
    const updateLicense = vi.spyOn(customerApi, 'updateCustomerLicenseSnapshot')
    const getDetail = vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue(latest)
    const wrapper = mountRecoveryEdit({ ...customerDetail, version: 10 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
      loadedVersion: number | null
    }
    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(wrapper.text()).toContain('其他人可能已经修改了该对象')
    expect(wrapper.findAll('button').find((button) => button.text() === '使用最新数据')).toBeDefined()

    await wrapper.findAll('button').find((button) => button.text() === '使用最新数据')?.trigger('click')
    await flushPromises()
    expect(getDetail).toHaveBeenCalled()
    expect(vm.licenseTypeValue).toBe('TRIAL')
    expect(vm.licenseExpiryDateValue).toBe('2027-01-01')
    expect(vm.loadedVersion).toBe(11)

    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')?.trigger('click')
    await flushPromises()
    expect(vm.licenseTypeValue).toBe('OFFICIAL')
    expect(vm.licenseExpiryDateValue).toBe('2026-12-31')
    expect(vm.loadedVersion).toBe(11)
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateLicense).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenLastCalledWith('customer-1', {
      expected_version: 11,
      license_type: 'OFFICIAL',
      license_expiry_date: '2026-12-31',
    })
    wrapper.unmount()
  })
  it('refreshes retained industry details when preserving input after a conflict', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const initial = {
      ...customerDetail,
      industry: 'legacy.industry',
      industry_info: { code: 'legacy.industry', name: '旧行业 / 已停用' },
      version: 10,
    }
    const latest = {
      ...initial,
      industry_info: { code: 'legacy.industry', name: '新行业 / 已停用' },
      version: 11,
    }
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
      .mockRejectedValueOnce({ response: { status: 409 } })
    const updateLicense = vi.spyOn(customerApi, 'updateCustomerLicenseSnapshot')
    const getDetail = vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue(latest)
    const wrapper = mountRecoveryEdit(initial)
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
    }
    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')?.trigger('click')
    await flushPromises()

    expect(updateLicense).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenCalledTimes(1)
    expect(getDetail).toHaveBeenCalledTimes(1)
    expect(wrapper.get('#customer-industry').text()).toContain('新行业 / 已停用')
    wrapper.unmount()
  })

  it('gives the more-information trigger the mobile minimum touch height', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountRecoveryEdit()
    await flushPromises()
    expect(wrapper.get('#customer-more-info-trigger').classes()).toContain('h-input-mobile')
    expect(wrapper.get('#customer-more-info-trigger').classes()).toContain('min-h-input-mobile')
    wrapper.unmount()
  })
  it('preserves dirty more-information values across a 409 recovery', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    vi.spyOn(customerApi, 'updateCustomer').mockRejectedValue({ response: { status: 409 } })
    vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue({
      ...customerDetail,
      version: 11,
      city: '深圳',
      status: 0,
      industry: 'finance_securities',
      license_type: 'TRIAL',
      license_expiry_date: '2027-01-01',
    })
    const wrapper = mountRecoveryEdit({ ...customerDetail, version: 10, status: 0 })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      setValues: (values: Record<string, unknown>) => void
      industryValue: string
      lifecycleStatusValue: 0 | 1 | null
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      onSubmit: (event: Event) => Promise<void>
    }
    vm.setValues({ account_name: '当前输入' })
    vm.industryValue = 'internet_saas'
    vm.lifecycleStatusValue = 1
    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')?.trigger('click')
    await flushPromises()
    expect(vm.industryValue).toBe('internet_saas')
    expect(vm.lifecycleStatusValue).toBe(1)
    expect(vm.licenseTypeValue).toBe('OFFICIAL')
    expect(vm.licenseExpiryDateValue).toBe('2026-12-31')
    wrapper.unmount()
  })

  it.each([2, 3])('renders status %s as read-only and clean', async (status) => {
    const wrapper = mountRecoveryEdit({ ...customerDetail, status: status as 2 | 3 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    expect(wrapper.text()).toContain('该客户状态由其他流程管理，暂不支持在此修改。')
    const vm = wrapper.vm as unknown as { handleCancel: () => void; showConfirmDialog: boolean }
    vm.handleCancel()
    expect(vm.showConfirmDialog).toBe(false)
    wrapper.unmount()
  })

  it('keeps ordinary profile dirty state after preserving input through a conflict', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockRejectedValueOnce({ response: { status: 409 } })
    const latest = { ...customerDetail, account_name: '其他人修改', version: 11 }
    const getDetail = vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue(latest)
    const wrapper = mountRecoveryEdit({ ...customerDetail, company_scale: '1-50人', source_info: { public_id: 'source-1', name: '来源', is_active: true }, version: 10 })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      setValues: (values: Record<string, unknown>) => void
      onSubmit: (event: Event) => Promise<void>
      handleCancel: () => void
      showConfirmDialog: boolean
    }
    vm.setValues({ account_name: '当前输入' })
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateCustomer).toHaveBeenCalled()
    await wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')?.trigger('click')
    await flushPromises()
    expect(getDetail).toHaveBeenCalledTimes(1)

    vm.handleCancel()
    expect(vm.showConfirmDialog).toBe(true)
    expect(wrapper.emitted('update:open')).toBeUndefined()
    wrapper.unmount()
  })
  it('merges an untouched industry from latest data when preserving ordinary input', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValueOnce({ ...customerDetail, account_name: '当前输入', industry: 'finance.securities', version: 12 })
    const latest = { ...customerDetail, account_name: '其他人修改', city: '深圳', industry: 'finance.securities', version: 11 }
    const getDetail = vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue(latest)
    const wrapper = mountRecoveryEdit({ ...customerDetail, industry: 'internet.enterprise', version: 10 })
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      values: Record<string, unknown>
      industryValue: string
      setValues: (values: Record<string, unknown>) => void
      onSubmit: (event: Event) => Promise<void>
      refreshConflict: (preserveInput: boolean) => Promise<void>
    }
    vm.setValues({ account_name: '当前输入' })
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateCustomer).toHaveBeenCalledTimes(1)
    expect(updateCustomer).toHaveBeenLastCalledWith('customer-1', {
      expected_version: 10,
      account_name: '当前输入',
    })
    await vm.refreshConflict(true)
    await flushPromises()
    expect(vm.values['city']).toBe('深圳')
    expect(vm.industryValue).toBe('finance.securities')
    expect(vm.values['account_name']).toBe('当前输入')
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateCustomer).toHaveBeenCalledTimes(2)
    expect(updateCustomer.mock.calls[1]?.[1]).toEqual({
      expected_version: 11,
      account_name: '当前输入',
    })

    expect(getDetail).toHaveBeenCalledTimes(1)
    expect(updateCustomer).toHaveBeenLastCalledWith('customer-1', {
      expected_version: 11,
      account_name: '当前输入',
    })
    wrapper.unmount()
  })
  it('keeps status target, dialog open, and error after ordinary PUT failure', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer').mockRejectedValue(new Error('update failed'))
    const updateLifecycle = vi.spyOn(customerApi, 'updateCustomerLifecycleStatus')
    const wrapper = mountRecoveryEdit({ ...customerDetail, status: 0 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()
    const vm = wrapper.vm as unknown as { lifecycleStatusValue: 0 | 1 | null; onSubmit: (event: Event) => Promise<void> }
    vm.lifecycleStatusValue = 1
    await vm.onSubmit(new Event('submit'))
    await flushPromises()

    expect(updateLifecycle).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenCalledWith('customer-1', { expected_version: 3, status: 1 })
    expect(wrapper.props('open')).toBe(true)
    expect(wrapper.get('#customer-lifecycle-status').text()).toBe('1')
    expect(wrapper.find('[role="alert"]').text()).toContain('请重试')
    expect(wrapper.emitted('update:open')).toBeUndefined()
    wrapper.unmount()
  })
  it('offers status recovery after a conflict and retries with refreshed version and preserved target', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const latest = { ...customerDetail, status: 0 as const, version: 11 }
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValueOnce({ ...latest, status: 1, version: 12 })
    const updateLifecycle = vi.spyOn(customerApi, 'updateCustomerLifecycleStatus')
    const getDetail = vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue(latest)
    const wrapper = mountRecoveryEdit({ ...customerDetail, status: 0, version: 10 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()
    const vm = wrapper.vm as unknown as { lifecycleStatusValue: 0 | 1 | null; onSubmit: (event: Event) => Promise<void> }
    vm.lifecycleStatusValue = 1
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('其他人可能已经修改了该对象')
    const preserve = wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')
    expect(preserve).toBeDefined()
    await preserve?.trigger('click')
    await flushPromises()
    expect(getDetail).toHaveBeenCalled()
    expect(vm.lifecycleStatusValue).toBe(1)
    await vm.onSubmit(new Event('submit'))
    await flushPromises()
    expect(updateLifecycle).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenLastCalledWith('customer-1', { status: 1, expected_version: 11 })
    wrapper.unmount()
  })
  it('shows the explicit authorization side-effect warning', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountRecoveryEdit()
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('此处只更新客户授权汇总信息，不创建 License 申请、不发起审批，也不修改正式 License 记录。')
    wrapper.unmount()
  })

  it('drops a stale lifecycle target when the latest server state is read-only', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const latest = { ...customerDetail, status: 2 as const, version: 11 }
    const updateCustomer = vi.spyOn(customerApi, 'updateCustomer')
      .mockRejectedValueOnce({ response: { status: 409 } })
    const updateLifecycle = vi.spyOn(customerApi, 'updateCustomerLifecycleStatus')
    const getDetail = vi.spyOn(customerApi, 'getCustomerDetail').mockResolvedValue(latest)
    const wrapper = mountRecoveryEdit({ ...customerDetail, status: 0, version: 10 })
    await flushPromises()
    await wrapper.get('#customer-more-info-trigger').trigger('click')
    await flushPromises()
    const submitVm = wrapper.vm as unknown as { lifecycleStatusValue: 0 | 1 | null; onSubmit: (event: Event) => Promise<void> }
    submitVm.lifecycleStatusValue = 1
    await submitVm.onSubmit(new Event('submit'))

    await wrapper.findAll('button').find((button) => button.text() === '保留当前输入并继续编辑')?.trigger('click')
    await flushPromises()

    const vm = wrapper.vm as unknown as {
      lifecycleStatusValue: 0 | 1 | null
      lifecycleStatusBaseline: 0 | 1 | null
      showConfirmDialog: boolean
      handleCancel: () => void
    }
    expect(getDetail).toHaveBeenCalledTimes(1)
    expect(updateLifecycle).not.toHaveBeenCalled()
    expect(updateCustomer).toHaveBeenCalledTimes(1)
    expect(vm.lifecycleStatusValue).toBeNull()
    expect(vm.lifecycleStatusBaseline).toBeNull()
    expect(wrapper.text()).toContain('该客户状态由其他流程管理，暂不支持在此修改。')

    vm.handleCancel()
    expect(vm.showConfirmDialog).toBe(false)
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })

  it.each([
    ['ordinary profile', (vm: { setValues: (values: Record<string, unknown>) => void; licenseTypeValue: string | null }): void => { vm.setValues({ account_name: '已修改' }) }],
    ['inline license', (vm: { setValues: (values: Record<string, unknown>) => void; licenseTypeValue: string | null }): void => { vm.licenseTypeValue = 'TRIAL' }],
  ])('invokes discard guard for %s dirty close attempts', async (_label, dirty) => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountRecoveryEdit()
    await flushPromises()
    const vm = wrapper.vm as unknown as { setValues: (values: Record<string, unknown>) => void; licenseTypeValue: string | null; handleCancel: () => void; showConfirmDialog: boolean; confirmCancel: () => void }
    dirty(vm)
    vm.handleCancel()
    expect(vm.showConfirmDialog).toBe(true)
    expect(wrapper.emitted('update:open')).toBeUndefined()
    vm.confirmCancel()
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    wrapper.unmount()
  })
})
