// @vitest-environment happy-dom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { ConversationMessageSchema, type ConversationView, type ConversationProjection } from '@/schemas/assistant-contracts'
import { makeTask, message, mocks, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'

type Message = ConversationView['messages'][number]
const item = (state: 'current' | 'complete' | 'unknown' = 'complete') => ({
  item_id: 'item_one', task_public_id: 'fut_one', title: '核对采购时间', related: true,
  evidence_quote: '客户确认已核对', state, result_title: state === 'complete' ? '已完成' : null,
  result_message: state === 'complete' ? '按客户确认完成' : null,
})
const disposition = (id: string, text: string, role: 'NONE' | 'CURRENT' | 'FINAL', batch = 'batch_one', version = 2): Message => {
  const task = makeTask({ status: 'COMPLETED', version, follow_up_disposition: {
    batch_id: batch, status: role === 'FINAL' ? 'DONE' : 'ACTIVE', customer_name: '睿狐科技',
    activity_kind_label: '电话跟进', total: 1, current_index: null, items: [item()],
  } })
  return { ...message(id, text, task), outcome: 'follow_up_disposition', projection: {
    visibility: role === 'NONE' ? 'FALLBACK_RECEIPT' : 'VISIBLE', covered_by: null,
    disposition: { task_public_id: task.public_id, batch_id: batch, item_ids: ['item_one'], card_role: role, version },
  } }
}
const activity = (id: string, text: string, publicId = 'activity_one'): Message => ({
  ...message(id, text, makeTask({ status: 'COMPLETED', committed: [{ kind: 'customer_activity', public_id: publicId }] })),
  outcome: 'activity_written', projection: { visibility: 'VISIBLE', activity_public_id: publicId },
})
const load = async (messages: Message[], overrides: Partial<ConversationView> = {}) => {
  show(view({ messages, ...overrides }))
  const wrapper = mount(SalesAssistantChat)
  await flushPromises()
  return wrapper
}
const older = async (wrapper: VueWrapper, messages: Message[]): Promise<void> => {
  mocks.get.mockResolvedValueOnce(view({ messages }))
  const button = wrapper.findAll('button').find((entry) => entry.text() === '查看更早对话')
  expect(button).toBeDefined()
  await button?.trigger('click')
  await flushPromises()
}

describe('loaded-window semantic coverage', () => {
  it('keeps an accepted activity independently from the final historical task card', async () => {
    const accepted = activity('accepted', '活动事实')
    const final = disposition('final', '最终逐条状态', 'FINAL')
    const wrapper = await load([accepted, final])
    expect(wrapper.text()).toContain('活动事实')
    expect(wrapper.text()).toContain('最终逐条状态')
    wrapper.unmount()
  })

  it('deduplicates activity receipts across overlapping pages, not distinct accepted activities', async () => {
    const latest = activity('new', '最新活动事实')
    latest.at = '2026-10-24T14:00:00'
    const wrapper = await load([latest, activity('different', '另一条活动', 'activity_two')], { older_cursor: 20 })
    await older(wrapper, [activity('old', '旧重复活动事实'), latest])
    expect(wrapper.text()).toContain('最新活动事实')
    expect(wrapper.text()).not.toContain('旧重复活动事实')
    expect(wrapper.text()).toContain('另一条活动')
    wrapper.unmount()
  })

  it('releases a server-covered fallback when its covering card is outside the loaded window', async () => {
    const fallback = disposition('receipt', '必要降级回执', 'NONE')
    fallback.projection = { ...fallback.projection as ConversationProjection, visibility: 'COVERED', covered_by: 'not_loaded' }
    const wrapper = await load([fallback])
    expect(wrapper.text()).toContain('必要降级回执')
    wrapper.unmount()
  })

  it('covers same-round fallback after loading a final card and preserves another batch', async () => {
    const wrapper = await load([disposition('receipt', '已完成旧标题', 'NONE'), disposition('other', '另一轮相同标题', 'NONE', 'batch_two')], { older_cursor: 20 })
    expect(wrapper.text()).toContain('已完成旧标题')
    await older(wrapper, [disposition('final', '最终卡改名后的标题', 'FINAL')])
    expect(wrapper.text()).not.toContain('已完成旧标题')
    expect(wrapper.text()).toContain('最终卡改名后的标题')
    expect(wrapper.text()).toContain('另一轮相同标题')
    wrapper.unmount()
  })

  it('does not hide settled explanations or evidence absent from the final card', async () => {
    const fallback = disposition('receipt', '被拒绝的关联解释', 'NONE')
    if (fallback.task?.follow_up_disposition) fallback.task.follow_up_disposition.items = [{ ...item(), result_message: '关联失效，未修改任务' }]
    const wrapper = await load([fallback, disposition('final', '最终卡', 'FINAL')])
    expect(wrapper.text()).toContain('被拒绝的关联解释')
    wrapper.unmount()
  })

  it('never hides an error or unknown result even with success identity metadata', async () => {
    const failure = { ...activity('error', '权限拒绝仍须可见'), outcome: 'failure' as const }
    const unknown = activity('unknown', '结果待核对')
    unknown.ui = {
      schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'unknown', role: 'assistant', state: 'failed',
      suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '结果待核对' },
      blocks: [{ id: 'error', type: 'error', code: 'UNKNOWN_COMMIT_RESULT', title: '结果待核对', message: '不要重复提交', retryable: false }],
    }
    const wrapper = await load([failure, unknown, activity('accepted', '成功活动')])
    expect(wrapper.text()).toContain('权限拒绝仍须可见')
    expect(wrapper.text()).toContain('结果待核对')
    expect(wrapper.text()).toContain('不要重复提交')
    wrapper.unmount()
  })

  it('does not let a stale overlapping page replace a newer exact-ID card', async () => {
    const wrapper = await load([disposition('same', '新版最终状态', 'FINAL', 'batch_one', 5)], { older_cursor: 20 })
    await older(wrapper, [disposition('same', '旧版当前状态', 'CURRENT', 'batch_one', 2)])
    expect(wrapper.text()).toContain('新版最终状态')
    expect(wrapper.text()).not.toContain('旧版当前状态')
    wrapper.unmount()
  })
})


describe('coverage contract safety', () => {
  it('reveals the server UI, not a client-authored card, when the carrier is absent', async () => {
    const fallback = disposition('covered', '服务器只读回执', 'NONE')
    fallback.projection = { ...fallback.projection as ConversationProjection, visibility: 'COVERED', covered_by: 'outside' }
    fallback.ui = {
      schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'covered', role: 'assistant', state: 'final',
      suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '服务器只读证据' },
      blocks: [{ id: 'server-notice', type: 'notice', tone: 'info', title: '历史跟进任务', text: '服务器只读证据' }],
    }
    expect(ConversationMessageSchema.safeParse(fallback).success).toBe(true)
    const wrapper = await load([fallback])
    expect(wrapper.text()).toContain('服务器只读证据')
    expect(wrapper.text()).not.toContain('这条结果暂时无法显示')
    expect(wrapper.text()).not.toContain('这是只读回执')
    wrapper.unmount()
  })

  it('preserves nonfinal evidence absent from a later final card', async () => {
    const fallback = disposition('source', '早期独有证据', 'NONE')
    if (fallback.task?.follow_up_disposition) fallback.task.follow_up_disposition.items = [{
      ...item('current'), evidence_quote: '必须人工核对', evidence_reason: '来源只在这一条中',
    }]
    const wrapper = await load([fallback, disposition('final', '最终状态', 'FINAL')])
    expect(wrapper.text()).toContain('早期独有证据')
    wrapper.unmount()
  })

  it('treats absent and null optional results as the same fact', async () => {
    const source = disposition('receipt', '无需重复回执', 'NONE')
    const final = disposition('final', '最终状态', 'FINAL')
    const sourceItem = source.task?.follow_up_disposition?.items[0]
    const finalItem = final.task?.follow_up_disposition?.items[0]
    if (sourceItem) delete sourceItem.result_message
    if (finalItem) finalItem.result_message = null
    const wrapper = await load([source, final])
    expect(wrapper.text()).not.toContain('无需重复回执')
    wrapper.unmount()
  })

  it.each(['complete', 'hold', 'skip', 'failed', 'unknown'] as const)('retains mismatched %s result details', async (state) => {
    const source = disposition('source', '必须保留的逐条结果', 'NONE')
    if (source.task?.follow_up_disposition) source.task.follow_up_disposition.items = [{ ...item(), state, result_message: '只有早期回执保留的说明' }]
    const wrapper = await load([source, disposition('final', '不同的最终卡', 'FINAL')])
    expect(wrapper.text()).toContain('必须保留的逐条结果')
    wrapper.unmount()
  })

  it('releases stale covered failure metadata instead of hiding its error', async () => {
    const failure = { ...activity('error', '关联失效，任务未改动'), outcome: 'failure' as const,
      projection: { visibility: 'COVERED' as const, covered_by: 'success', activity_public_id: 'activity_one' } }
    const wrapper = await load([failure, activity('success', '活动成功')])
    expect(wrapper.text()).toContain('关联失效，任务未改动')
    wrapper.unmount()
  })

  it('recognizes legacy success UI without collapsing distinct unidentified facts', async () => {
    const old = message('legacy', '旧版独立回执')
    old.ui = { schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'legacy', role: 'assistant', state: 'final',
      suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '旧版独立回执' },
      blocks: [{ id: 'old', type: 'notice', tone: 'success', title: '本次跟进已写入', text: '旧版独立回执' }] }
    const wrapper = await load([old, activity('new', '新活动')])
    expect(wrapper.text()).toContain('旧版独立回执')
    expect(wrapper.text()).toContain('新活动')
    wrapper.unmount()
  })
})


it('makes a retained old CURRENT card read-only when its authority wait has ended', async () => {
  const source = disposition('old-current', '旧等待', 'CURRENT')
  const wait = { type: 'FOLLOW_UP_DISPOSITION' as const, field: 'follow_up_disposition', question_id: 'q_old',
    action_id: 'action_old', expected_version: 2, prompt: '历史跟进任务' }
  if (source.task) { source.task.status = 'ACTIVE'; source.task.waiting = wait }
  source.ui = { schema_version: 'crm.agent.ui.v1', message_id: 1, turn_id: 'old-current', role: 'assistant', state: 'final',
    suggested_actions: [], metadata: { display: 'MESSAGE', route: 'WORKFLOW', accessibility_label: '历史跟进任务' },
    blocks: [{ id: 'old-card', type: 'interaction', interaction_id: 'old-card', interaction_type: 'choice',
      business_action: 'settle_follow_up_disposition', presentation: 'OPEN_FOLLOW_UP_DISPOSITION', state: 'ACTIVE',
      disposition_items: [{ ...item('current') }], prompt: '历史跟进任务', fields: [], facts: [],
      options: [{ value: 'item_one:complete', label: '已完成', disabled: false }],
      selection_mode: 'single', min_selections: 1, max_selections: 1, allow_cancel: false,
      submit_on_select: true, submit_label: '提交', submit_action_id: 'action_old' }] }
  // A newer card lacks the old evidence; preserving it must not revive its command.
  const final = disposition('final', '当前最终状态', 'FINAL')
  if (source.task?.follow_up_disposition) source.task.follow_up_disposition.items = [{ ...item('unknown'), result_message: '旧证据须保留' }]
  const wrapper = await load([source, final], { focused_task: final.task })
  const retained = wrapper.findAllComponents(AgentUIMessage).find((component) => component.props('message').turn_id === 'old-current')
  expect(retained).toBeDefined()
  const block = retained?.props('message').blocks.find((entry) => entry.type === 'interaction')
  expect(block?.type === 'interaction' ? block.state : null).toBe('READ_ONLY')
  expect(block?.type === 'interaction' ? block.submit_action_id : 'missing').toBeNull()
  expect(mocks.command).not.toHaveBeenCalled()
  wrapper.unmount()
})
