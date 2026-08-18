import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import CustomerDetailSheet from '@/views/CustomerDetailSheet.vue'
import HoverInfo from '@/components/crmwolf/HoverInfo.vue'
import type { CustomerDetailResponse } from '@/api/customer'
import { usePermissionStore } from '@/stores/permissions'
import { useUserStore } from '@/stores/user'


if (typeof globalThis.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    pointerType: string
    constructor(type: string, init: MouseEventInit & { pointerType?: string } = {}) {
      super(type, init)
      this.pointerType = init.pointerType ?? 'mouse'
    }
  }
  globalThis.PointerEvent = PointerEventPolyfill as typeof PointerEvent
}

const routeState = vi.hoisted(() => ({
  path: '/customers',
  query: {} as Record<string, string>,
}))
const routerPush = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const routerReplace = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const customerApi = vi.hoisted(() => ({
  getCustomerDetail: vi.fn(),
  getCustomerMembers: vi.fn(),
}))
const customerActivityApi = vi.hoisted(() => ({ getActivities: vi.fn() }))
const opportunityApi = vi.hoisted(() => ({ getOpportunities: vi.fn() }))
const contractApi = vi.hoisted(() => ({ getCustomerContracts: vi.fn() }))
const invoiceApi = vi.hoisted(() => ({ getInvoiceTitles: vi.fn() }))
const deploymentApi = vi.hoisted(() => ({ list: vi.fn() }))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn() }))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
}))
vi.mock('@/api/customer', () => ({ default: customerApi }))
vi.mock('@/api/customerActivity', () => ({ default: customerActivityApi }))
vi.mock('@/api/opportunity', () => ({ opportunityApi }))
vi.mock('@/api/contract', () => ({ default: contractApi }))
vi.mock('@/api/invoice', () => ({ default: invoiceApi }))
vi.mock('@/api/deployment', () => ({ default: deploymentApi }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/crmwolf', async () => {
  const { default: HoverInfo } = await import('@/components/crmwolf/HoverInfo.vue')
  return {
    HoverInfo,
    ContextTabs: defineComponent({
      name: 'ContextTabs',
      props: { tabs: Array, activeTab: String },
      emits: ['update:activeTab'],
      setup: (props, { emit }) => () => h('nav', (props.tabs as { key: string; label: string }[]).map(tab => h('button', {
        type: 'button',
        'data-testid': `tab-${tab.key}`,
        'data-active': String(props.activeTab === tab.key),
        onClick: () => emit('update:activeTab', tab.key),
      }, tab.label))),
    }),
  }
})

vi.mock('@/components/ui/sheet', () => {
  const passthrough = (name: string) => defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    Sheet: defineComponent({
      name: 'Sheet',
      props: { open: Boolean },
      emits: ['update:open'],
      setup: (props, { slots }) => () => props.open ? h('section', { 'data-testid': 'sheet-root' }, slots.default?.()) : null,
    }),
    SheetHeader: passthrough('SheetHeader'),
    SheetFooter: passthrough('SheetFooter'),
  }
})

vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({ name: 'DetailSheetContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    props: { type: String, variant: String, size: String, disabled: Boolean },
    setup: (props, { slots, attrs }) => () => h('button', { ...attrs, type: props.type ?? 'button', disabled: props.disabled }, slots.default?.()),
  }),
}))

vi.mock('@/components/ui/badge', () => ({ Badge: defineComponent({ name: 'Badge', setup: (_, { slots }) => () => h('span', slots.default?.()) }) }))
vi.mock('@/components/ui/card', () => ({
  Card: defineComponent({ name: 'Card', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  CardContent: defineComponent({ name: 'CardContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))
vi.mock('@/components/ui/scroll-area', () => ({ ScrollArea: defineComponent({ name: 'ScrollArea', setup: (_, { slots }) => () => h('div', slots.default?.()) }) }))
vi.mock('@/components/ui/empty', () => ({
  Empty: defineComponent({ name: 'Empty', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  EmptyHeader: defineComponent({ name: 'EmptyHeader', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  EmptyMedia: defineComponent({ name: 'EmptyMedia', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  EmptyTitle: defineComponent({ name: 'EmptyTitle', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  EmptyDescription: defineComponent({ name: 'EmptyDescription', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  EmptyContent: defineComponent({ name: 'EmptyContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))

vi.mock('@/components/panels/FollowUpPanel.vue', () => ({ default: defineComponent({ name: 'FollowUpPanel', setup: () => () => h('div', 'followup') }) }))
vi.mock('@/components/panels/ContactsPanel.vue', () => ({ default: defineComponent({ name: 'ContactsPanel', setup: () => () => h('div', 'contacts') }) }))
vi.mock('@/components/panels/OpportunitiesPanel.vue', () => ({ default: defineComponent({ name: 'OpportunitiesPanel', setup: () => () => h('div', 'opportunities') }) }))
vi.mock('@/components/panels/InvoicesPanel.vue', () => ({ default: defineComponent({ name: 'InvoicesPanel', setup: () => () => h('div', 'invoices') }) }))
vi.mock('@/components/panels/LicensePanel.vue', () => ({ default: defineComponent({ name: 'LicensePanel', setup: () => () => h('div', 'license') }) }))
vi.mock('@/components/panels/CustomerMembersPanel.vue', () => ({ default: defineComponent({ name: 'CustomerMembersPanel', setup: () => () => h('div', 'members') }) }))
vi.mock('@/components/panels/OpportunityDetailContent.vue', () => ({ default: defineComponent({ name: 'OpportunityDetailContent', setup: () => () => h('div') }) }))
vi.mock('@/components/panels/ContractDetailContent.vue', () => ({ default: defineComponent({ name: 'ContractDetailContent', setup: () => () => h('div') }) }))
vi.mock('@/components/dialogs/FollowUpFormDialog.vue', () => ({ default: defineComponent({ name: 'FollowUpFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/ContactFormDialog.vue', () => ({ default: defineComponent({ name: 'ContactFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/OpportunityFormDialog.vue', () => ({ default: defineComponent({ name: 'OpportunityFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/ContractFormDialog.vue', () => ({ default: defineComponent({ name: 'ContractFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/InvoiceTitleFormDialog.vue', () => ({ default: defineComponent({ name: 'InvoiceTitleFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/CustomerFormDialog.vue', () => ({ default: defineComponent({ name: 'CustomerFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/DeploymentInfoFormDialog.vue', () => ({ default: defineComponent({ name: 'DeploymentInfoFormDialog', setup: () => () => null }) }))
vi.mock('@/components/dialogs/EditRecordDialog.vue', () => ({ default: defineComponent({ name: 'EditRecordDialog', setup: () => () => null }) }))
vi.mock('@/views/PaymentPlanDetailSheet.vue', () => ({ default: defineComponent({ name: 'PaymentPlanDetailSheet', setup: () => () => null }) }))
vi.mock('@/views/PaymentRecordDetailSheet.vue', () => ({ default: defineComponent({ name: 'PaymentRecordDetailSheet', setup: () => () => null }) }))

const customerFixture = (overrides: Partial<CustomerDetailResponse> = {}): CustomerDetailResponse => ({
  id: 'cus_test_19',
  public_id: 'cus_test_19',
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
  customer_brief_status: 'COMPLETED',
  customer_brief_markdown: '## 跟进进展\n- 本周四已完成数据分级表回收 [1]',
  customer_brief_citations: JSON.stringify({
    '1': {
      source_type: 'follow_up',
      source_id: 'act_1',
      title: '客户活动：电话沟通',
      excerpt: '确认本周四回收数据分级分类收集表。',
    },
  }),
  ...overrides,
})

const wait = async (ms: number): Promise<void> => {
  await new Promise(resolve => {
    setTimeout(resolve, ms)
  })
}

const dumpCitation = (): Record<string, string | null | boolean> => {
  const citation = document.querySelector('.customer-brief-citation')
  const grace = citation?.closest('[data-grace-area-trigger]') ?? document.querySelector('[data-grace-area-trigger]')
  return {
    hasHoverInfoChip: citation !== null,
    citationText: citation?.textContent ?? null,
    citationHtml: citation?.outerHTML ?? null,
    graceTag: grace?.tagName ?? null,
    graceState: grace?.getAttribute('data-state') ?? null,
    bodyHasTitle: document.body.textContent?.includes('客户活动：电话沟通') ?? false,
    bodyHasExcerpt: document.body.textContent?.includes('确认本周四回收数据分级分类收集表。') ?? false,
    bodySnippet: document.body.textContent?.slice(0, 400) ?? null,
  }
}

describe('CustomerDetailSheet citation hover', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const userStore = useUserStore()
    const permissionStore = usePermissionStore()
    userStore.userInfo = { id: 9, name: '测试用户', email: 'test@example.com' } as typeof userStore.userInfo
    permissionStore.permissions = [
      { code: 'customer:edit:own' },
    ] as typeof permissionStore.permissions
    vi.clearAllMocks()
    routeState.path = '/customers'
    routeState.query = {}
    customerApi.getCustomerDetail.mockResolvedValue(customerFixture())
    customerActivityApi.getActivities.mockResolvedValue([])
    opportunityApi.getOpportunities.mockResolvedValue([])
    contractApi.getCustomerContracts.mockResolvedValue([])
    invoiceApi.getInvoiceTitles.mockResolvedValue({ invoice_titles: [] })
    deploymentApi.list.mockResolvedValue([])
    customerApi.getCustomerMembers.mockResolvedValue([])
  })

  it('parses [1] into a hoverable citation chip, not plain text', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      attachTo: document.body,
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    const dump = dumpCitation()
    expect(dump, JSON.stringify(dump, null, 2)).toMatchObject({
      hasHoverInfoChip: true,
      citationText: '[1]',
    })
    expect(wrapper.findComponent(HoverInfo).exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows citation title and excerpt after hovering the index chip', async () => {
    const wrapper = mount(CustomerDetailSheet, {
      attachTo: document.body,
      props: {
        customerId: 'cus_test_19',
        visible: true,
      },
    })

    await flushPromises()
    await nextTick()

    const citation = wrapper.get('.customer-brief-citation')
    citation.element.dispatchEvent(new PointerEvent('pointerenter', {
      bubbles: true,
      cancelable: true,
      pointerType: 'mouse',
    }))
    citation.element.dispatchEvent(new MouseEvent('mouseenter', {
      bubbles: true,
      cancelable: true,
    }))
    await nextTick()
    await wait(220)

    const dump = dumpCitation()
    expect(dump, JSON.stringify(dump, null, 2)).toMatchObject({
      bodyHasTitle: true,
      bodyHasExcerpt: true,
    })
    wrapper.unmount()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })
})
