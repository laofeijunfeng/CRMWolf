import { defineComponent, h, nextTick, type VNode } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LeadFormDialog from '@/components/LeadFormDialog.vue'
import { leadApi, type LeadDetail } from '@/api/lead'
import { acquisitionSourceApi } from '@/api/acquisition-source'

const DialogSlotStub = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }): () => VNode {
    return () => h('div', slots['default']?.())
  },
})

const leadDetail: LeadDetail = {
  id: 'lead-1',
  public_id: 'LEAD-001',
  lead_name: '测试线索',
  source: '官网',
  source_info: {
    public_id: 'source-1',
    name: '官网',
    is_active: true,
  },
  city: '上海',
  contact_name: '测试联系人',
  contact_phone: '13800138000',
  company_scale: '51-200人',
  owner_id: 'user-1',
  status: 1,
  creator_id: 'user-1',
  created_time: '2026-09-04T00:00:00Z',
  last_modified_time: '2026-09-04T00:00:00Z',
  version: 1,
  follow_ups: [],
}

describe('LeadFormDialog edit initialization', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not paint the empty edit form while required data is still loading', async () => {
    let resolveSourceOptions: (() => void) | undefined
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockImplementation(() => new Promise((resolve) => {
      resolveSourceOptions = () => resolve([])
    }))
    vi.spyOn(leadApi, 'getLeadDetail').mockResolvedValue(leadDetail)

    const wrapper = shallowMount(LeadFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: {
        open: true,
        mode: 'edit',
        leadId: leadDetail.id,
      },
    })
    await nextTick()

    const initiallyShowedLoading = wrapper.find('.animate-spin').exists()
    const initiallyShowedForm = wrapper.find('form-stub').exists()

    resolveSourceOptions?.()
    await flushPromises()
    wrapper.unmount()

    expect(initiallyShowedLoading).toBe(true)
    expect(initiallyShowedForm).toBe(false)
  })

  it('opens directly into the prefetched form when the mounted dialog receives its edit props', async () => {
    vi.spyOn(leadApi, 'getLeadDetail').mockRejectedValue(new Error('detail should not be requested when prefetched'))
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const wrapper = shallowMount(LeadFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: {
        open: false,
        mode: 'edit',
        leadId: undefined,
        lead: null,
      },
    })

    await wrapper.setProps({
      open: true,
      leadId: leadDetail.id,
      lead: leadDetail,
    })
    await nextTick()

    expect(wrapper.find('.animate-spin').exists()).toBe(false)
    expect(wrapper.find('form-stub').exists()).toBe(true)
    expect(leadApi.getLeadDetail).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('uses prefetched detail and avoids a second detail request', async () => {
    const getLeadDetail = vi.spyOn(leadApi, 'getLeadDetail')
      .mockRejectedValue(new Error('detail should not be requested when prefetched'))
    vi.spyOn(acquisitionSourceApi, 'listOptions').mockResolvedValue([])

    const wrapper = shallowMount(LeadFormDialog, {
      global: {
        stubs: {
          Dialog: DialogSlotStub,
          DialogContent: DialogSlotStub,
        },
      },
      props: {
        open: true,
        mode: 'edit',
        leadId: leadDetail.id,
        lead: leadDetail,
      },
    })
    await nextTick()
    await flushPromises()

    expect(getLeadDetail).not.toHaveBeenCalled()
    expect(wrapper.find('.animate-spin').exists()).toBe(false)
    wrapper.unmount()
  })
})
