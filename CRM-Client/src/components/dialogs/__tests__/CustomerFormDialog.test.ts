import { defineComponent, h, nextTick, type VNode } from 'vue'
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CustomerFormDialog from '../CustomerFormDialog.vue'
import FormErrorSummary from '@/components/crmwolf/FormErrorSummary.vue'
import customerApi, { type CustomerDetailResponse } from '@/api/customer'
import procurementApi from '@/api/procurement'
import { acquisitionSourceApi } from '@/api/acquisition-source'

const DialogSlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }): () => VNode {
    return () => h('div', slots['default']?.())
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
  creator_id: '1',
  created_time: '2026-09-04T00:00:00Z',
  last_modified_time: '2026-09-04T00:00:00Z',
  version: 3,
  license_expiry_date: null,
  license_type: null,
  contacts: [],
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
})
 
describe('CustomerFormDialog progressive edit sections', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  const mountEdit = (customer: CustomerDetailResponse = { ...customerDetail, company_scale: '1-50人', source_info: { public_id: 'source-1', name: '来源', is_active: 1 } }): VueWrapper => shallowMount(CustomerFormDialog, {
    global: {
      stubs: {
        Dialog: DialogSlotStub,
        DialogContent: DialogSlotStub,
        DialogFooter: DialogSlotStub,
        Collapsible: defineComponent({ props: { open: Boolean }, emits: ['update:open'], template: '<div><slot /></div>' }),
        CollapsibleTrigger: defineComponent({ template: '<slot />' }),
        CollapsibleContent: defineComponent({ template: '<div><slot /></div>' }),
        Button: defineComponent({ inheritAttrs: false, template: '<button v-bind="$attrs"><slot /></button>' }),
      },
    },
    props: {
      open: true,
      mode: 'edit',
      customerId: customer.id,
      customer,
    },
  })

  it('starts with the more customer information section collapsed', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit()
    await flushPromises()

    const vm = wrapper.vm as unknown as { moreInfoOpen: boolean }
    expect(vm.moreInfoOpen).toBe(false)
    expect(wrapper.text()).toContain('更多客户信息')
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

  it('keeps the dialog and entered license values when snapshot save fails', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    vi.spyOn(customerApi, 'updateCustomerLicenseSnapshot').mockRejectedValue(new Error('snapshot failed'))
    const wrapper = mountEdit()
    const vm = wrapper.vm as unknown as {
      licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null
      licenseExpiryDateValue: string | null
      saveLicenseSnapshot: () => Promise<void>
    }
    vm.licenseTypeValue = 'TRIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.saveLicenseSnapshot()

    expect(wrapper.props('open')).toBe(true)
    expect(vm.licenseTypeValue).toBe('TRIAL')
    expect(vm.licenseExpiryDateValue).toBe('2026-12-31')
    wrapper.unmount()
  })

  it('uses the current version for a lifecycle 0 to 1 save and emits only refresh', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const customer = { ...customerDetail, status: 0 as const, version: 8 }
    const updateLifecycle = vi.spyOn(customerApi, 'updateCustomerLifecycleStatus').mockResolvedValue({ ...customer, status: 1, version: 9 })
    const wrapper = mountEdit(customer)
    await flushPromises()

    const vm = wrapper.vm as unknown as { lifecycleStatusValue: 0 | 1; saveLifecycleStatus: () => Promise<void> }
    vm.lifecycleStatusValue = 1
    await vm.saveLifecycleStatus()

    expect(updateLifecycle).toHaveBeenCalledWith('customer-1', { status: 1, expected_version: 8 })
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('success')).toBeUndefined()
    expect(wrapper.props('open')).toBe(true)
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

  it('preserves dirty license values and keeps open after profile save', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    vi.spyOn(customerApi, 'updateCustomer').mockResolvedValue({ ...customerDetail, account_name: '更新客户', version: 4 })
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
    expect(vm.licenseTypeValue).toBe('TRIAL')
    expect(vm.licenseExpiryDateValue).toBe('2026-12-31')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('success')).toBeUndefined()
    expect(wrapper.emitted('update:open')).toBeUndefined()
    wrapper.unmount()
  })

  it('expands more information before focusing an industry error', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit()
    await flushPromises()
    const field = document.createElement('input')
    field.scrollIntoView = vi.fn()
    field.focus = vi.fn()
    vi.spyOn(document, 'querySelector').mockReturnValue(field)
    const vm = wrapper.vm as unknown as { setErrors: (errors: Record<string, string>) => void; focusFirstError: () => Promise<void>; moreInfoOpen: boolean }
    vm.setErrors({ industry: '请选择行业' })
    await vm.focusFirstError()
    expect(vm.moreInfoOpen).toBe(true)
    expect(field.focus).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('disables footer save and cancel while an inline write is submitting', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const wrapper = mountEdit()
    const vm = wrapper.vm as unknown as { lifecycleSubmitting: boolean; licenseSubmitting: boolean; writeSubmitting: boolean }
    await flushPromises()
    vm.lifecycleSubmitting = true
    await nextTick()
    expect(vm.writeSubmitting).toBe(true)
    vm.lifecycleSubmitting = false
    vm.licenseSubmitting = true
    await nextTick()
    expect(vm.writeSubmitting).toBe(true)
    wrapper.unmount()
  })
  it('syncs normalized license snapshot values returned by the API', async () => {
    vi.spyOn(procurementApi, 'getProcurementMethodOptions').mockResolvedValue([])
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])
    const updateLicense = vi.spyOn(customerApi, 'updateCustomerLicenseSnapshot').mockResolvedValue({ ...customerDetail, license_type: null, license_expiry_date: null, version: 4 })
    const wrapper = mountEdit()
    await flushPromises()
    const vm = wrapper.vm as unknown as { licenseTypeValue: 'TRIAL' | 'OFFICIAL' | null; licenseExpiryDateValue: string | null; saveLicenseSnapshot: () => Promise<void> }
    vm.licenseTypeValue = 'OFFICIAL'
    vm.licenseExpiryDateValue = '2026-12-31'
    await vm.saveLicenseSnapshot()
    expect(updateLicense).toHaveBeenCalled()
    expect(vm.licenseTypeValue).toBeNull()
    expect(vm.licenseExpiryDateValue).toBeNull()
    wrapper.unmount()
  })
})
