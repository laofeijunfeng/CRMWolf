import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, type Component, type VNode } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerDetailSheet from '@/components/panels/CustomerDetailSheet.vue'
import customerApi, { type CustomerDetailResponse } from '@/api/customer'
import customerActivityApi, { type CustomerActivityResponse } from '@/api/customerActivity'
import { dealJourneyApi } from '@/api/dealJourney'
import invoiceApi from '@/api/invoice'
import deploymentApi from '@/api/deployment'

const makeCustomer = (id: string, name: string): CustomerDetailResponse => ({
  id,
  public_id: id,
  account_name: name,
  industry: null,
  city: '上海',
  address: null,
  company_size: null,
  owner_id: '1',
  creator_id: '1',
  created_time: '2026-09-01T00:00:00Z',
  last_modified_time: '2026-09-01T00:00:00Z',
  contacts: [],
} as unknown as CustomerDetailResponse)

const makeActivity = (id: number, content: string, occurredAt: string): CustomerActivityResponse => ({
  id,
  customer_id: 'cust-1',
  original_lead_id: null,
  activity_kind: 'PHONE_CALL',
  activity_category: 'FOLLOW_UP',
  activity_label: '电话跟进',
  source_content: content,
  content,
  method: '电话',
  next_follow_time: null,
  next_action: null,
  occurred_at: occurredAt,
  creator_id: '1',
  created_time: occurredAt,
})

const passthroughStub = (name: string): Component =>
  defineComponent({
    name,
    inheritAttrs: true,
    setup(_, { slots, attrs }) {
      return (): VNode => h('div', attrs, slots['default']?.())
    },
  })

const ScrollAreaStub = defineComponent({
  name: 'ScrollArea',
  setup(_, { slots, attrs }) {
    return (): VNode =>
      h('div', attrs, [
        h('div', { 'data-reka-scroll-area-viewport': '', class: 'test-scroll-viewport' }, slots['default']?.()),
      ])
  },
})

const ContextTabsStub = defineComponent({
  name: 'ContextTabs',
  props: {
    tabs: { type: Array, required: true },
    activeTab: { type: String, required: true },
  },
  emits: ['update:activeTab'],
  setup(props, { emit }) {
    return (): VNode =>
      h(
        'div',
        { 'data-testid': 'context-tabs' },
        (props.tabs as { key: string; label: string }[]).map((tab) =>
          h(
            'button',
            {
              key: tab.key,
              type: 'button',
              'data-testid': `tab-${tab.key}`,
              onClick: () => emit('update:activeTab', tab.key),
            },
            tab.label,
          ),
        ),
      )
  },
})

const FollowUpPanelStub = defineComponent({
  name: 'FollowUpPanel',
  props: {
    followUps: { type: Array, required: true },
  },
  emits: ['add', 'delete'],
  setup(props, { emit }) {
    return (): VNode =>
      h(
        'div',
        { 'data-testid': 'follow-up-panel' },
        (props.followUps as CustomerActivityResponse[]).map((item) =>
          h('div', { key: item.id, class: 'activity-item', 'data-id': String(item.id) }, [
            item.content,
            h(
              'button',
              {
                type: 'button',
                'data-testid': `delete-activity-${item.id}`,
                onClick: () => emit('delete', item),
              },
              'delete',
            ),
          ]),
        ),
      )
  },
})

const FollowUpFormDialogStub = defineComponent({
  name: 'FollowUpFormDialog',
  emits: ['success', 'update:visible'],
  setup(_, { emit }) {
    return (): VNode =>
      h(
        'button',
        {
          type: 'button',
          'data-testid': 'trigger-activity-success',
          onClick: () => emit('success'),
        },
        'submit',
      )
  },
})

describe('CustomerDetailSheet follow-up scroll guards', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(customerApi, 'getCustomerDetail').mockImplementation(async (id) => makeCustomer(id, `客户-${id}`))
    vi.spyOn(customerApi, 'getCustomerMembers').mockResolvedValue([])
    vi.spyOn(dealJourneyApi, 'listByCustomer').mockResolvedValue([])
    vi.spyOn(invoiceApi, 'getInvoiceTitles').mockResolvedValue({ invoice_titles: [] })
    vi.spyOn(deploymentApi, 'list').mockResolvedValue([])
    vi.spyOn(customerActivityApi, 'deleteActivity').mockResolvedValue({ message: 'ok' })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  const mountSheet = (props: { customerId: string; visible: boolean; targetPanel?: 'customer-info' | 'followup' | 'journeys' | 'opportunities' | null }): VueWrapper =>
    mount(CustomerDetailSheet, {
      props,
      global: {
        plugins: [createPinia()],
        stubs: {
          DetailSheetSurface: passthroughStub('DetailSheetSurface'),
          DetailSheetHeader: passthroughStub('DetailSheetHeader'),
          DetailSheetFooter: passthroughStub('DetailSheetFooter'),
          ScrollArea: ScrollAreaStub,
          ContextTabs: ContextTabsStub,
          FollowUpPanel: FollowUpPanelStub,
          FollowUpFormDialog: FollowUpFormDialogStub,
          Card: passthroughStub('Card'),
          CardContent: passthroughStub('CardContent'),
          ContactsPanel: true,
          DealJourneysPanel: true,
          InvoicesPanel: true,
          LicensePanel: true,
          CustomerMembersPanel: true,
          DealJourneyDetailHost: true,
          CustomerFormDialog: true,
          ContactFormDialog: true,
          OpportunityFormDialog: true,
          InvoiceTitleFormDialog: true,
          DeploymentInfoFormDialog: true,
          ApprovalSourceHeader: true,
          ApprovalSourceFooter: true,
          ErrorState: true,
          StatusBadge: true,
        },
      },
    })

  it('scrolls to bottom on tab switch, customer switch, and add; does not reset on delete or 3s AI polling', async () => {
    const firstActivity = makeActivity(1, '最早活动', '2026-11-01T09:00:00Z')
    const secondActivity = makeActivity(2, '最新活动', '2026-11-02T09:00:00Z')
    const activities = [firstActivity, secondActivity]
    const getActivitiesSpy = vi.spyOn(customerActivityApi, 'getActivities').mockResolvedValue(activities)

    const wrapper = mountSheet({ customerId: 'cust-1', visible: true })
    await flushPromises()

    const viewport = wrapper.find('[data-reka-scroll-area-viewport]').element as HTMLElement
    Object.defineProperty(viewport, 'scrollHeight', { value: 1200, configurable: true })
    viewport.scrollTop = 0

    // 1. Switching to 客户活动 tab scrolls to bottom
    await wrapper.find('[data-testid="tab-followup"]').trigger('click')
    await flushPromises()
    expect(viewport.scrollTop).toBe(1200)
    expect(wrapper.findAll('.activity-item').map(n => n.attributes('data-id'))).toEqual(['1', '2'])

    // 2. Adding a new activity scrolls to bottom immediately
    viewport.scrollTop = 100
    getActivitiesSpy.mockResolvedValueOnce([
      ...activities,
      makeActivity(3, '刚新增活动', '2026-11-03T09:00:00Z'),
    ])
    await wrapper.find('[data-testid="trigger-activity-success"]').trigger('click')
    await flushPromises()
    expect(viewport.scrollTop).toBe(1200)

    // 3. User scrolls up to read history; 3s AI status polling refresh MUST NOT force-scroll back to bottom
    viewport.scrollTop = 240
    getActivitiesSpy.mockResolvedValueOnce([
      ...activities,
      makeActivity(3, '刚新增活动（AI已完成）', '2026-11-03T09:00:00Z'),
    ])
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(viewport.scrollTop).toBe(240)

    // 4. Deleting a historical activity MUST NOT force-scroll back to bottom
    viewport.scrollTop = 180
    getActivitiesSpy.mockResolvedValueOnce([
      secondActivity,
      makeActivity(3, '刚新增活动（AI已完成）', '2026-11-03T09:00:00Z'),
    ])
    await wrapper.find('[data-testid="delete-activity-1"]').trigger('click')
    await flushPromises()
    expect(viewport.scrollTop).toBe(180)

    // 5. Switching customer with targetPanel='followup' scrolls to bottom
    await wrapper.setProps({ targetPanel: 'followup' })
    viewport.scrollTop = 50
    getActivitiesSpy.mockResolvedValueOnce([
      makeActivity(20, '另一客户最早', '2026-11-01T09:00:00Z'),
      makeActivity(21, '另一客户最新', '2026-11-04T09:00:00Z'),
    ])
    await wrapper.setProps({ customerId: 'cust-2' })
    await flushPromises()
    expect(viewport.scrollTop).toBe(1200)

    wrapper.unmount()
  })
})
