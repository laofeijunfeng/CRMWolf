import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, type Component, type VNode } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LeadDetailSheet from '@/components/panels/LeadDetailSheet.vue'
import { leadApi, type LeadDetail, type LeadFollowUp } from '@/api/lead'

const makeFollowUp = (id: number, content: string, createdTime: string): LeadFollowUp => ({
  id,
  lead_id: 'lead-1',
  content,
  method: '电话',
  creator_id: '1',
  created_time: createdTime,
})

const leadDetail: LeadDetail = {
  id: 'lead-1',
  public_id: 'LEAD-001',
  lead_name: '测试线索',
  source: '官网',
  city: '上海',
  contact_name: '张三',
  contact_phone: '13800138000',
  company_scale: '1-50人',
  owner_id: '1',
  owner_info: { id: '1', name: '负责人', avatar_url: '' },
  status: 1,
  creator_id: '1',
  creator_info: { id: '1', name: '创建人', avatar_url: '' },
  created_time: '2026-09-04T00:00:00Z',
  last_modified_time: '2026-09-04T00:00:00Z',
  version: 1,
  follow_ups: [
    makeFollowUp(1, '最早跟进', '2026-09-01T09:00:00Z'),
    makeFollowUp(2, '中间跟进', '2026-09-02T09:00:00Z'),
    makeFollowUp(3, '最新跟进', '2026-09-03T09:00:00Z'),
  ],
}

const passthroughStub = (name: string): Component =>
  defineComponent({
    name,
    inheritAttrs: true,
    setup(_, { slots, attrs }) {
      return (): VNode => h('div', attrs, slots['default']?.())
    },
  })

const FollowUpListStub = defineComponent({
  name: 'FollowUpList',
  props: {
    followUps: { type: Array, required: true },
  },
  emits: ['delete'],
  setup(props, { emit }) {
    return (): VNode =>
      h(
        'div',
        { 'data-testid': 'follow-up-list' },
        (props.followUps as LeadFollowUp[]).map((item) =>
          h('div', { key: item.id, class: 'stub-item', 'data-id': String(item.id) }, [
            item.content,
            h(
              'button',
              {
                type: 'button',
                'data-testid': `delete-${item.id}`,
                onClick: () => emit('delete', item),
              },
              'delete',
            ),
          ]),
        ),
      )
  },
})

describe('LeadDetailSheet component resolution & follow-up ordering/scroll', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the lead detail without unresolved component warnings', async () => {
    vi.spyOn(leadApi, 'getLeadDetail').mockResolvedValue(leadDetail)
    const warnings: string[] = []

    const wrapper = shallowMount(LeadDetailSheet, {
      props: {
        leadId: leadDetail.id,
        visible: true,
      },
      global: {
        plugins: [createPinia()],
        config: {
          warnHandler: (message: string): void => {
            warnings.push(message)
          },
        },
      },
    })
    await flushPromises()

    expect(warnings.filter(message => message.includes('Failed to resolve component'))).toEqual([])
    wrapper.unmount()
  })

  it('preserves ascending follow-up order and auto-scrolls on open/switch/add without resetting on delete', async () => {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(960)
    const getLeadDetailSpy = vi.spyOn(leadApi, 'getLeadDetail').mockResolvedValue(leadDetail)
    vi.spyOn(leadApi, 'deleteFollowUp').mockResolvedValue({ message: 'ok' })
    const wrapper = mount(LeadDetailSheet, {
      props: {
        leadId: 'lead-1',
        visible: true,
      },
      global: {
        plugins: [createPinia()],
        stubs: {
          DetailSheet: passthroughStub('DetailSheet'),
          DetailSheetContent: passthroughStub('DetailSheetContent'),
          DetailSheetHeader: passthroughStub('DetailSheetHeader'),
          DetailSheetTitle: passthroughStub('DetailSheetTitle'),
          DetailSheetDescription: passthroughStub('DetailSheetDescription'),
          DetailSheetFooter: passthroughStub('DetailSheetFooter'),
          ScrollArea: passthroughStub('ScrollArea'),
          Card: passthroughStub('Card'),
          CardHeader: passthroughStub('CardHeader'),
          CardContent: passthroughStub('CardContent'),
          Dialog: passthroughStub('Dialog'),
          DialogContent: passthroughStub('DialogContent'),
          DialogHeader: passthroughStub('DialogHeader'),
          DialogTitle: passthroughStub('DialogTitle'),
          DialogDescription: passthroughStub('DialogDescription'),
          DialogFooter: passthroughStub('DialogFooter'),
          LeadFormDialog: true,
          LeadConvertDialog: true,
          StatusBadge: true,
          FollowUpList: FollowUpListStub,
        },
      },
    })
    await flushPromises()

    // Order preserved as ascending (oldest -> newest)
    const items = wrapper.findAll('.stub-item').map(node => node.attributes('data-id'))
    expect(items).toEqual(['1', '2', '3'])

    // Initial open auto-scrolls to bottom
    const initialContainer = wrapper.find('.max-h-\\[400px\\]').element as HTMLElement
    expect(initialContainer.scrollTop).toBe(960)

    // Simulate user scrolling up to read history
    initialContainer.scrollTop = 120

    // Switching lead reloads and scrolls to bottom
    getLeadDetailSpy.mockResolvedValueOnce({
      ...leadDetail,
      id: 'lead-2',
      public_id: 'LEAD-002',
      follow_ups: [
        makeFollowUp(10, '新线索最早', '2026-09-05T09:00:00Z'),
        makeFollowUp(11, '新线索最新', '2026-09-06T09:00:00Z'),
      ],
    })
    await wrapper.setProps({ leadId: 'lead-2' })
    await flushPromises()
    const switchedContainer = wrapper.find('.max-h-\\[400px\\]').element as HTMLElement
    expect(switchedContainer.scrollTop).toBe(960)
    expect(wrapper.findAll('.stub-item').map(node => node.attributes('data-id'))).toEqual(['10', '11'])

    // Deleting a historical follow-up must NOT force-scroll back to bottom
    switchedContainer.scrollTop = 80
    getLeadDetailSpy.mockResolvedValueOnce({
      ...leadDetail,
      id: 'lead-2',
      follow_ups: [makeFollowUp(11, '新线索最新', '2026-09-06T09:00:00Z')],
    })
    await wrapper.find('[data-testid="delete-10"]').trigger('click')
    await flushPromises()
    expect((wrapper.find('.max-h-\\[400px\\]').element as HTMLElement).scrollTop).toBe(80)
    wrapper.unmount()
  })
})
