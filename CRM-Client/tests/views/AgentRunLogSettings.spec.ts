import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const listTurns = vi.hoisted(() => vi.fn())
const getTurn = vi.hoisted(() => vi.fn())
const handleApiError = vi.hoisted(() => vi.fn())
const accessState = vi.hoisted(() => ({
  allowed: true,
  unavailable: { value: false },
  pending: { value: false },
}))

vi.mock('@/api/agentRunLog', () => ({
  agentRunLogApi: { listTurns, getTurn },
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('@/composables/usePageTitle', () => ({ usePageTitle: () => undefined }))
vi.mock('@/composables/useSettingsAccess', async () => {
  const { ref } = await import('vue')
  const unavailable = ref(false)
  const pending = ref(false)
  accessState.unavailable = unavailable
  accessState.pending = pending
  return {
    useSettingsAccess: () => ({
      canAccess: () => accessState.allowed,
      permissionsUnavailable: unavailable,
      permissionsPending: pending,
    }),
  }
})
vi.mock('@/components/crmwolf', () => ({
  DataViewStatePanel: defineComponent({
    name: 'DataViewStatePanel',
    props: { state: { type: String, required: true } },
    setup: (props, { slots }) => () => h(
      'div',
      { 'data-state': props.state },
      props.state === 'ready' ? slots.default?.() : null,
    ),
  }),
}))
vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'Sheet',
    setup: (_, { slots }) => () => h('div', { role: 'dialog' }, slots.default?.()),
  }),
  SheetHeader: defineComponent({ name: 'SheetHeader', setup: (_, { slots }) => () => h('div', slots.default?.()) }),
  SheetTitle: defineComponent({ name: 'SheetTitle', setup: (_, { slots }) => () => h('h2', slots.default?.()) }),
  SheetDescription: defineComponent({ name: 'SheetDescription', setup: (_, { slots }) => () => h('p', slots.default?.()) }),
}))
vi.mock('@/components/ui/detail-sheet', () => ({
  DetailSheetContent: defineComponent({
    name: 'DetailSheetContent',
    setup: (_, { slots }) => () => h('div', slots.default?.()),
  }),
}))

import AgentRunLogSettings from '@/views/AgentRunLogSettings.vue'

const listItem = {
  turn_id: 'turn_blocked',
  user_id: 2,
  user_name: '销售李',
  user_text: '记双汇跟进',
  outcome: 'blocked_unwritten' as const,
  summary: '质量 52 分，拦住写入。',
  quality_score: 52,
  customer_name: '双汇',
  model: 'test-model',
  created_time: '2026-09-17T10:00:00',
}

const detail = {
  ...listItem,
  steps: [
    { kind: 'model' as const, title: '判成「记跟进」', detail: 'route = WORKFLOW', tone: 'done' as const },
    { kind: 'code' as const, title: '匹配到客户「双汇」', detail: 'checkpoint 已有客户绑定', tone: 'done' as const },
    { kind: 'code' as const, title: '质量 52 分，拦住', detail: '阈值 60。', tone: 'blocked' as const },
    { kind: 'interaction' as const, title: '只问了一个补充问题', detail: '下一步由谁做什么', tone: 'blocked' as const },
    { kind: 'api' as const, title: '没有调创建', detail: 'create_customer_activity 未调用', tone: 'skipped' as const },
    { kind: 'background' as const, title: '没有整理 / 评分任务', detail: 'Agent 路径不创建 AIJob', tone: 'skipped' as const },
  ],
}

describe('AgentRunLogSettings', () => {
  beforeEach(() => {
    listTurns.mockReset()
    getTurn.mockReset()
    handleApiError.mockReset()
    accessState.allowed = true
    accessState.unavailable.value = false
    accessState.pending.value = false
    listTurns.mockResolvedValue({
      items: [listItem],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    getTurn.mockResolvedValue(detail)
  })

  it('lists turns and opens the six-step process sheet', async () => {
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()

    expect(listTurns).toHaveBeenCalled()
    expect(wrapper.text()).toContain('记双汇跟进')
    expect(wrapper.text()).toContain('拦住未写')
    expect(wrapper.text()).toContain('52')

    await wrapper.find('tbody tr').trigger('click')
    await flushPromises()

    expect(getTurn).toHaveBeenCalledWith('turn_blocked')
    expect(wrapper.text()).toContain('判成「记跟进」')
    expect(wrapper.text()).toContain('质量 52 分，拦住')
    expect(wrapper.text()).toContain('没有调创建')
  })

  it('hides the log when the viewer lacks AI settings access', async () => {
    accessState.allowed = false
    const wrapper = mount(AgentRunLogSettings)
    await flushPromises()

    expect(wrapper.text()).toContain('暂无访问权限')
    expect(listTurns).not.toHaveBeenCalled()
  })
})
