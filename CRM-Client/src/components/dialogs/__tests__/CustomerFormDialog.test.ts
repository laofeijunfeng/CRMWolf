import { defineComponent, h, nextTick, type VNode } from 'vue'
import { shallowMount, flushPromises } from '@vue/test-utils'
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
