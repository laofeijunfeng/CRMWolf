import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, ref, toValue, type PropType } from 'vue'
import CustomerTracking from '@/views/CustomerTracking.vue'
import type { FollowUpTaskItem } from '@/api/followUpTask'
import type { TabItem } from '@/stores/header'

const followUpTaskApi = vi.hoisted(() => ({
  list: vi.fn(),
  getDetail: vi.fn(),
  transition: vi.fn(),
}))
const followUpConfirmationApi = vi.hoisted(() => ({
  list: vi.fn(),
  getPendingCount: vi.fn(),
  resolve: vi.fn(),
}))
const headerStore = vi.hoisted(() => ({ activeTab: '' }))
const topBarState = vi.hoisted(() => ({ tabs: [] as TabItem[] }))
const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn(() => Promise.resolve()) }),
}))

vi.mock('@/api/followUpTask', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/api/followUpTask')>()
  return {
    ...original,
    followUpTaskApi,
    followUpConfirmationApi,
  }
})
vi.mock('@/stores/header', () => ({ useHeaderStore: () => headerStore }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: vi.fn() }))
vi.mock('@/composables/useTopBarRegistration', () => ({
  useTopBarRegistration: (options: { tabs?: unknown }): void => {
    topBarState.tabs = options.tabs === undefined ? [] : toValue(options.tabs as never)
  },
}))
vi.mock('@/composables/useCustomFilterViews', () => ({
  isCustomFilterViewTab: (key: string) => key.startsWith('custom-view:'),
  useCustomFilterViews: () => ({
    saving: ref(false),
    mergeTabs: (tabs: TabItem[]) => tabs,
    loadCustomViews: vi.fn(() => Promise.resolve()),
    applyCustomViewTab: vi.fn(() => false),
    applyBuiltInTab: vi.fn(() => false),
    saveAsCustomView: vi.fn(),
    updateActiveCustomViewConfig: vi.fn(),
    saveActiveCustomViewColumns: vi.fn(),
  }),
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDialog: vi.fn(() => Promise.resolve(true)) }))
vi.mock('vue-sonner', () => ({ toast }))

vi.mock('@/components/crmwolf', () => ({
  DataTable: defineComponent({
    name: 'DataTable',
    props: {
      data: { type: Array as PropType<Record<string, unknown>[]>, default: () => [] },
    },
    setup: (props, { slots }) => () => h('div', { 'data-testid': 'tracking-table' },
      props.data.map(row => h('article', { 'data-testid': `task-${String(row['public_id'])}` }, [
        slots['cell-tracking_content']?.({ row }),
        slots['cell-status_label']?.({ row }),
        slots['cell-actions']?.({ row }),
      ])),
    ),
  }),
  HoverInfo: defineComponent({
    name: 'HoverInfo',
    setup: (_, { slots }) => () => h('div', slots.trigger?.()),
  }),
  TableRowActions: defineComponent({
    name: 'TableRowActions',
    props: {
      row: { type: Object as PropType<Record<string, unknown>>, required: true },
      primaryActions: { type: Array as PropType<Array<{ label: string; visible?: boolean; handler: (row: Record<string, unknown>) => void }>>, default: () => [] },
      secondaryActions: { type: Array as PropType<Array<{ label: string; visible?: boolean; handler: (row: Record<string, unknown>) => void }>>, default: () => [] },
    },
    setup: (props) => () => h('div', [
      ...props.primaryActions,
      ...props.secondaryActions,
    ].filter(action => action.visible !== false).map(action => h('button', {
      type: 'button',
      'data-action': action.label,
      onClick: () => action.handler(props.row),
    }, action.label))),
  }),
  DateField: defineComponent({ name: 'DateField', setup: () => () => null }),
  TextareaField: defineComponent({ name: 'TextareaField', setup: () => () => null }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: defineComponent({
    name: 'Button',
    setup: (_, { slots, attrs }) => () => h('button', { ...attrs, type: 'button' }, slots.default?.()),
  }),
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: defineComponent({ name: 'Badge', setup: (_, { slots }) => () => h('span', slots.default?.()) }),
}))
vi.mock('@/components/ui/card', () => ({
  Card: defineComponent({ name: 'Card', setup: (_, { slots }) => () => h('section', slots.default?.()) }),
  CardContent: defineComponent({ name: 'CardContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: defineComponent({ name: 'Dialog', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  DialogContent: defineComponent({ name: 'DialogContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  DialogDescription: defineComponent({ name: 'DialogDescription', setup: (_, { slots }) => () => h('p', slots.default?.()) }),
  DialogFooter: defineComponent({ name: 'DialogFooter', setup: (_, { slots }) => () => h('footer', slots.default?.()) }),
  DialogHeader: defineComponent({ name: 'DialogHeader', setup: (_, { slots }) => () => h('header', slots.default?.()) }),
  DialogTitle: defineComponent({ name: 'DialogTitle', setup: (_, { slots }) => () => h('h2', slots.default?.()) }),
}))
vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({ name: 'Sheet', setup: (_, { slots }) => () => h('aside', slots.default?.()) }),
  SheetFooter: defineComponent({ name: 'SheetFooter', setup: (_, { slots }) => () => h('footer', slots.default?.()) }),
  SheetHeader: defineComponent({ name: 'SheetHeader', setup: (_, { slots }) => () => h('header', slots.default?.()) }),
  SheetTitle: defineComponent({ name: 'SheetTitle', setup: (_, { slots }) => () => h('h2', slots.default?.()) }),
}))
vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({ name: 'DetailSheetContent', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))
vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: defineComponent({ name: 'ScrollArea', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
}))
vi.mock('@/components/dialogs/FollowUpFormDialog.vue', () => ({
  default: defineComponent({ name: 'FollowUpFormDialog', setup: () => () => null }),
}))

const taskFixture = (): FollowUpTaskItem => ({
  id: '10',
  public_id: 'fut_10',
  customer: {
    id: 'customer_1',
    public_id: 'cus_1',
    name: '中移互联网',
    account_name: '中移互联网',
  },
  owner_id: '1',
  creator_id: '1',
  title: '本周四反馈新的数据分级分类收集表给张雷雨',
  status: 'OPEN',
  due_at: '2026-08-13T09:00:00+08:00',
  pending_confirmations: [{
    public_id: 'fuc_case_13',
    question_text: '上次安排的「本周四反馈新的数据分级分类收集表给张雷雨」这次是否已经完成?',
    suggested_action: 'COMPLETE',
    created_time: '2026-08-12T04:13:48+08:00',
  }],
})

const unrelatedTaskFixture = (): FollowUpTaskItem => ({
  id: '11',
  public_id: 'fut_11',
  customer: {
    id: 'customer_2',
    public_id: 'cus_2',
    name: '另一客户',
    account_name: '另一客户',
  },
  owner_id: '1',
  creator_id: '1',
  title: '补充部署信息',
  status: 'OPEN',
  due_at: '2026-08-18T09:00:00+08:00',
  pending_confirmations: [],
})

const resolvedResponse = {
  case: null,
  decision: {
    action: 'COMPLETE',
    confidence: 1,
    reason: '用户确认已完成',
    resolved: true,
    proposed_due_at: null,
    proposed_due_at_text: null,
  },
  application: {
    status: 'APPLIED',
    case_public_id: 'fuc_case_13',
    task_public_id: 'fut_10',
    action: 'COMPLETE',
    skip_reason: null,
    execution_results: [],
  },
  assistant_follow_up_prompt: null,
  usage_policy: { rule: 'application service' },
}

describe('CustomerTracking inline follow-up confirmations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    headerStore.activeTab = ''
    topBarState.tabs = []
    followUpTaskApi.list.mockResolvedValue({ items: [taskFixture(), unrelatedTaskFixture()], total: 2 })
    followUpTaskApi.getDetail.mockResolvedValue(taskFixture())
    followUpConfirmationApi.getPendingCount.mockResolvedValue(1)
    followUpConfirmationApi.resolve.mockResolvedValue(resolvedResponse)
  })

  it('does not expose a confirmation tab and renders the case on its matching task', async () => {
    const wrapper = mount(CustomerTracking, { global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(topBarState.tabs.map(tab => tab.label)).not.toContain('待确认')
    const task = wrapper.get('[data-testid="task-fut_10"]')
    expect(task.text()).toContain('需确认')
    expect(task.text()).toContain('上次安排的「本周四反馈新的数据分级分类收集表给张雷雨」这次是否已经完成?')
    expect(task.get('[data-action="确认完成"]').exists()).toBe(true)

    const unrelatedTask = wrapper.get('[data-testid="task-fut_11"]')
    expect(unrelatedTask.text()).not.toContain('需确认')
    expect(unrelatedTask.text()).not.toContain('上次安排的')
    expect(unrelatedTask.find('[data-action="确认完成"]').exists()).toBe(false)
  })

  it('resolves the task-owned case through the confirmation API and refreshes tasks', async () => {
    const wrapper = mount(CustomerTracking, { global: { plugins: [createPinia()] } })
    await flushPromises()

    await wrapper.get('[data-action="确认完成"]').trigger('click')
    await flushPromises()

    expect(followUpConfirmationApi.resolve).toHaveBeenCalledWith('fuc_case_13', { reply_text: '已完成' })
    expect(followUpTaskApi.transition).not.toHaveBeenCalled()
    expect(followUpTaskApi.list).toHaveBeenCalledTimes(2)
  })
})
