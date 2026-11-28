// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { confirmation, drive, field, makeTask, message, mocks, prepared, reply, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'
import AgentUIMessage from '@/components/agent-ui/AgentUIMessage.vue'
import type { AssistantTurn, StageEvent } from '@/api/assistant'
import type { ConversationView } from '@/schemas/assistant-contracts'

async function send(wrapper: VueWrapper, text = '今天客户沟通'): Promise<void> {
  await wrapper.find('textarea').setValue(text)
  await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
  await flushPromises()
}

const button = (wrapper: VueWrapper, label: string) =>
  wrapper.findAll('button').find((item) => item.text() === label)

const stageRow = (wrapper: VueWrapper, label: string) =>
  wrapper.findAll('span').find((item) => item.text() === label)?.element.closest('li')

const expectContextFailureWhileJudging = (wrapper: VueWrapper): void => {
  const context = stageRow(wrapper, '读取客户记录')
  // Status color is carried by the design-system tone token, never by a raw text class.
  expect(context?.querySelector('.text-tone-danger') !== null).toBe(true)
  expect(context?.textContent).toContain('失败')
  expect(context?.textContent).not.toContain('进行中')
  expect(context?.querySelector('.text-tone-success')).toBeNull()
  expect(context?.textContent).not.toMatch(/91 分|1\.2 秒/)
  expect(stageRow(wrapper, '比对未完成任务')?.textContent).toContain('进行中')
}

describe('durable processing and recovery in a continuous conversation', () => {
  it('uses only signed customer candidates and the current waiting identity', async () => {
    const current = makeTask({ waiting: field({ type: 'OBJECT_SELECTION', field: 'customer', candidates: [{ id: 'cus_a', account_name: '睿狐科技' }, { id: 'cus_b', account_name: '睿狐集团' }] }) })
    show(view({ focused_task: current, messages: [message('one', '请选择客户', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('睿狐集团'))?.trigger('click')
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({ input: expect.objectContaining({ kind: 'submit_field', choice: 'cus_b', action_id: 'action1', expected_version: 1 }) }))
  })

  it('renders stage progress during an accepted text turn and settles on the server result', async () => {
    const running = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: running, version: 1 }), prepared(running)))
    const finished = makeTask({ waiting: field() })
    mocks.get.mockResolvedValue(view({ version: 1, focused_task: finished, messages: [message('one', '请补充客户名称', finished)] }))
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'structure', phase: 'start' })
      await new Promise<void>((resolve) => { finish = resolve })
      handlers.onStage({ stage: 'quality_gate', phase: 'done', score: 85 })
      handlers.onWaiting({ task: finished, message: '请补充客户名称' })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.text()).toContain('整理活动内容')
    expect(wrapper.text()).toContain('原始内容已保存，处理仍在后台继续；关闭或刷新不会取消')
    finish?.()
    await flushPromises()
    expect(wrapper.text()).toContain('请补充客户名称')
    expect(wrapper.text()).not.toContain('原始内容已保存，处理仍在后台继续；关闭或刷新不会取消')
  })

  it('names entity stages by the record they work on and rounds durations to seconds', async () => {
    const running = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: running, version: 1 }), prepared(running)))
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'structure', phase: 'start', subject: '部署信息' })
      handlers.onStage({ stage: 'structure', phase: 'done', ms: 1200 })
      handlers.onStage({ stage: 'write', phase: 'start', subject: '部署信息' })
      await new Promise<void>((resolve) => { finish = resolve })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '给睿狐科技加一条部署信息')
    expect(stageRow(wrapper, '整理部署信息')?.textContent).toContain('1 秒')
    expect(stageRow(wrapper, '保存部署信息')?.textContent).toContain('进行中')
    expect(wrapper.text()).not.toContain('整理活动内容')
    expect(wrapper.text()).not.toContain('写入客户活动')
    finish?.()
    wrapper.unmount()
  })

  it('shows which segment of a long transcript is being organized', async () => {
    const running = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: running, version: 1 }), prepared(running)))
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'structure', phase: 'start', segment: { index: 1, total: 3 } })
      handlers.onStage({ stage: 'structure', phase: 'done', ms: 40_000, segment: { index: 1, total: 3 } })
      handlers.onStage({ stage: 'structure', phase: 'start', segment: { index: 2, total: 3 } })
      await new Promise<void>((resolve) => { finish = resolve })
      handlers.onStage({ stage: 'structure', phase: 'done', ms: 30_000, segment: { index: 2, total: 3 } })
      handlers.onStage({ stage: 'structure', phase: 'start', segment: { index: 3, total: 3 } })
      handlers.onStage({ stage: 'structure', phase: 'done', ms: 2_000, segment: { index: 3, total: 3 } })
      handlers.onWaiting({ task: running, message: '请补充客户名称' })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    const row = (): string | null | undefined => stageRow(wrapper, '整理活动内容')?.textContent
    expect(row()).toContain('第 2/3 段 · 进行中…')
    expect(wrapper.text()).toContain('原始内容已保存，处理仍在后台继续；关闭或刷新不会取消')
    finish?.()
    await flushPromises()
    // Segment durations add up to the stage total.
    expect(row()).toContain('已完成 3/3 段 · 1 分 12 秒')
    wrapper.unmount()
  })

  it('gets a completed result if the accepted stream ended without a waiting frame', async () => {
    const current = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    drive((handlers) => { handlers.onAccepted('atn_one', 1) })
    mocks.turn.mockResolvedValue({ turn_id: 'atn_one', status: 'SUCCEEDED', events: [], task: current })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(mocks.turn).toHaveBeenCalledWith('ast_one', 'atn_one', 1)
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })

  it('shows only the write stage while a frozen confirmation is being committed', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    let finish: (() => void) | undefined
    drive(async () => { await new Promise<void>((resolve) => { finish = resolve }) })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('写入客户活动')
    expect(wrapper.text()).not.toContain('判断活动类型')
    finish?.()
    await flushPromises()
    wrapper.unmount()
  })

  it('shows frozen preview values instead of mutable draft values', async () => {
    const current = makeTask({ waiting: confirmation(), draft: { ...makeTask().draft, content: { status: 'CANDIDATE', value: '可变草稿' } } })
    show(view({ focused_task: current, messages: [message('one', '确认？', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('冻结整理稿')
    expect(wrapper.text()).toContain('冻结客户')
    expect(wrapper.text()).not.toContain('可变草稿')
  })

  it('surfaces a server failure without pretending the activity was written', async () => {
    const current = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    drive((handlers) => handlers.onError({ code: 'AI_UNAVAILABLE', retryable: true, message: '模型暂不可用' }))
    mocks.get.mockResolvedValue(view({ messages: [{ ...message('failure', '模型暂不可用'), outcome: 'failure' }] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.text()).toContain('模型暂不可用')
    expect(wrapper.text()).not.toContain('已写入')
  })

  it('reads an organize failure after the stream is lost without cancelling or retrying', async () => {
    const failure = '内容已保存，但整理未完成，尚未写入客户活动'
    const current = makeTask({ processing_turn_id: 'atn_one', processing_turn_status: 'RUNNING' })
    const finished = makeTask({ reprocess_turn_id: 'atn_one' })
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    mocks.get.mockResolvedValue(view({ focused_task: finished, messages: [message('user', '只收下一次的跟进', null, 'user'), message('result', failure, finished)] }))
    drive((handlers) => { handlers.onAccepted('atn_one', 1); handlers.onNetworkLost() })
    mocks.turn.mockResolvedValue({
      turn_id: 'atn_one', status: 'FAILED', lease_version: 1, reprocess_allowed: true,
      events: [{ seq: 2, event: 'error', data: { code: 'UPSTREAM_TIMEOUT', stage: 'structure', retryable: true, message: failure, task_public_id: 'ast_one' } }],
      task: finished
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '只收下一次的跟进')
    expect(mocks.retry).not.toHaveBeenCalled()
    expect(mocks.command).not.toHaveBeenCalled()
    expect(mocks.choice).not.toHaveBeenCalled()
    expect(mocks.turn).toHaveBeenCalled()
    expect(wrapper.text()).toContain(failure)
    expect(wrapper.text()).toContain('重新处理')
    expect(wrapper.text()).not.toContain('刷新后可继续')
    expect(wrapper.text()).not.toContain('连接中断')
    expect(wrapper.text()).not.toContain('重试同步')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
    expect(mocks.command).not.toHaveBeenCalled()
    expect(mocks.choice).not.toHaveBeenCalled()
  })

  it.each(['event', 'task'] as const)('does not reprocess when its fresh turn GET reports unknown via %s', async (source) => {
    const offered = makeTask({ reprocess_turn_id: 'atn_one' })
    show(view({ focused_task: offered }))
    mocks.turn.mockResolvedValue({
      turn_id: 'atn_one', status: 'FAILED', lease_version: 2, reprocess_allowed: true,
      task: { ...offered, version: 2, ...(source === 'task' ? { reconciliation_required: true } : {}) },
      events: source === 'event'
        ? [{ seq: 1, event: 'error', data: { code: 'UNKNOWN_COMMIT_RESULT', message: '结果待核对' } }]
        : []
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(button(wrapper, '重新处理')).toBeDefined()
    await button(wrapper, '重新处理')?.trigger('click')
    await flushPromises()
    expect(mocks.turn).toHaveBeenCalledWith('ast_one', 'atn_one', 0)
    expect(mocks.retry).not.toHaveBeenCalled()
    expect(mocks.stream).not.toHaveBeenCalled()
    expect(button(wrapper, '重新处理')).toBeUndefined()
    expect(wrapper.get('textarea').element.disabled).toBe(true)
    wrapper.unmount()
  })

  it('hides reprocess when the organize failure is not retryable', async () => {
    const failure = '内容已保存，但整理未完成，尚未写入客户活动'
    const finished = makeTask({ reprocess_turn_id: null })
    show(view({ focused_task: finished, messages: [message('result', failure, finished, 'assistant')] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain(failure)
    expect(wrapper.text()).not.toContain('重新处理')
    wrapper.unmount()
    expect(mocks.command).not.toHaveBeenCalled()
  })

  it('promises only that a saved turn keeps running after one minute', async () => {
    vi.useFakeTimers()
    const current = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    drive(async () => { await new Promise<void>(() => undefined) })
    const wrapper = mount(SalesAssistantChat)
    try {
      await flushPromises()
      await send(wrapper)
      await vi.advanceTimersByTimeAsync(60_000)
      await flushPromises()
      expect(wrapper.text()).toContain('内容已保存，可以离开本页，完成后会通知你。')
      expect(wrapper.text()).not.toContain('刷新后可继续')
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
    expect(mocks.command).not.toHaveBeenCalled()
    expect(mocks.choice).not.toHaveBeenCalled()
  })

  it('keeps polling a live turn with GET and does not restart it', async () => {
    vi.useFakeTimers()
    const current = makeTask({ processing_turn_id: 'atn_one', processing_turn_status: 'PENDING' })
    show(view({ focused_task: current, messages: [message('user', '已收下的原句', null, 'user')] }))
    mocks.turn.mockResolvedValue({ turn_id: 'atn_one', status: 'PENDING', lease_version: 0, reprocess_allowed: false, events: [], task: current })
    const wrapper = mount(SalesAssistantChat)
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('已受理，正在确认处理结果')
      expect(wrapper.text()).not.toContain('重试同步')
      const reads = mocks.turn.mock.calls.length
      await vi.advanceTimersByTimeAsync(1000)
      await flushPromises()
      expect(mocks.turn.mock.calls.length).toBeGreaterThan(reads)
      expect(mocks.retry).not.toHaveBeenCalled()
      expect(mocks.stream).not.toHaveBeenCalled()
      expect(mocks.text).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('recovers the same internal turn on mount with GET and never creates user input', async () => {
    const current = makeTask({ processing_turn_id: 'atn_internal', processing_turn_status: 'RUNNING' })
    show(view({ focused_task: current, messages: [message('old', '已记录这条客户活动。')] }))
    mocks.turn.mockResolvedValue({ turn_id: 'atn_internal', status: 'RUNNING', events: [], task: current })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(mocks.turn).toHaveBeenCalledWith('ast_one', 'atn_internal', 0)
    expect(mocks.text).not.toHaveBeenCalled()
    expect(mocks.command).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已记录这条客户活动')
    wrapper.unmount()
  })

  it.each(['SUCCEEDED', 'RUNNING'] as const)('follows a successor when the original turn GET reports %s', async (status) => {
    const current = makeTask({ processing_turn_id: 'atn_original', processing_turn_status: 'RUNNING' })
    const next = makeTask({ processing_turn_id: 'atn_next', processing_turn_status: 'RUNNING' })
    show(view({ focused_task: current }))
    mocks.get.mockResolvedValue(view({ focused_task: next }))
    mocks.turn.mockResolvedValueOnce({ turn_id: 'atn_original', status, events: [], task: status === 'SUCCEEDED' ? next : current })
      .mockResolvedValue({ turn_id: 'atn_next', status: 'RUNNING', events: [], task: next })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(mocks.turn).toHaveBeenCalledWith('ast_one', 'atn_next', 0)
    expect(mocks.stream).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not silently start a new transcript when opening persisted history fails', async () => {
    mocks.open.mockRejectedValue(new Error('断网'))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('网络已断开，已有内容都还在')
    await send(wrapper, '不要丢原会话')
    expect(mocks.text).not.toHaveBeenCalled()
  })
})

describe('shared conversation recovery', () => {
  it('does not replace the new focus with a lower-version conversation GET', async () => {
    const current = makeTask({ public_id: 'ast_new', version: 5 })
    mocks.text.mockResolvedValue(reply(view({ version: 2, focused_task: current, messages: [message('latest', '新的当前记录', current)] }), prepared(current)))
    mocks.get.mockResolvedValue(view({ version: 1, focused_task: makeTask({ public_id: 'ast_old', waiting: field() }), messages: [message('stale', '迟到的旧提示')] }))
    drive((handlers) => handlers.onWaiting({ task: current, message: '本次处理完成' }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.text()).not.toContain('迟到的旧提示')
    expect(wrapper.text()).toContain('新的当前记录')
  })

  it('replaces repeated plain completion publications with one task boundary and keeps it after history catches up', async () => {
    const current = makeTask()
    const completed = makeTask({ status: 'COMPLETED', version: 2 })
    mocks.text.mockResolvedValue(reply(view({ version: 1, focused_task: current }), prepared(current)))
    let publishAgain: (() => void) | undefined
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onWaiting({ task: completed, message: '服务端普通收尾正文' })
      publishAgain = () => handlers.onWaiting({ task: completed, message: '重复收尾正文' })
      await new Promise<void>((resolve) => { finish = resolve })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('这条结果暂时无法显示')
    publishAgain?.()
    await flushPromises()
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    mocks.get.mockResolvedValue(view({ version: 2, focused_task: completed, messages: [
      { ...message(`completion:${completed.public_id}`, '本次任务已完成', completed), outcome: 'task_completed' }
    ] }))
    finish?.()
    await flushPromises()
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('服务端普通收尾正文')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps a newly committed activity result when the same publication completes the task', async () => {
    const current = makeTask()
    const completed = makeTask({ status: 'COMPLETED', version: 2, committed: [{ kind: 'customer_activity', public_id: 'act_done' }] })
    mocks.text.mockResolvedValue(reply(view({ version: 1, focused_task: current }), prepared(current)))
    mocks.get.mockResolvedValue(view({ version: 2, focused_task: completed, messages: [
      { ...message('result', '活动写入回执', completed), outcome: 'activity_written' },
      { ...message(`completion:${completed.public_id}`, '本次任务已完成', completed), outcome: 'task_completed' }
    ] }))
    drive((handlers) => handlers.onWaiting({ task: completed, message: '活动写入回执' }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.findAll('[role="separator"]')).toHaveLength(1)
    expect(wrapper.findAllComponents({ name: 'AgentUIMessage' }).some((item) => item.text().includes('活动写入回执'))).toBe(true)
    expect(wrapper.text().indexOf('活动写入回执')).toBeLessThan(wrapper.text().indexOf('本次任务已完成'))
    wrapper.unmount()
  })

  it('does not mark a completed-looking snapshot with an outstanding wait as completed', async () => {
    const current = makeTask()
    mocks.text.mockResolvedValue(reply(view({ version: 1, focused_task: current }), prepared(current)))
    const waitingTask = makeTask({ status: 'COMPLETED', version: 2, waiting: field() })
    mocks.get.mockResolvedValue(view({ version: 2, focused_task: waitingTask, messages: [message('wait', '仍需补充', waitingTask)] }))
    drive((handlers) => handlers.onWaiting({ task: waitingTask, message: '仍需补充' }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.find('[role="separator"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not publish completion after a failed stream even when its later snapshot says completed', async () => {
    const current = makeTask()
    const completed = makeTask({ status: 'COMPLETED', version: 2 })
    mocks.text.mockResolvedValue(reply(view({ version: 1, focused_task: current }), prepared(current)))
    mocks.get.mockRejectedValue(new Error('history unavailable'))
    drive((handlers) => {
      handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: '结果待核对' })
      handlers.onWaiting({ task: completed, message: '不可作为成功依据' })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.find('[role="separator"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('stale-window feedback', () => {
  it('restores a rejected ordinary input instead of losing it or replaying an old version forever', async () => {
    const previous = message('old', '先前结果')
    mocks.text.mockRejectedValue(Object.assign(new Error('版本冲突'), { isAxiosError: true, response: { status: 409 } }))
    mocks.get.mockResolvedValue(view({ version: 2, messages: [previous, message('new', '其他窗口已更新')] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '尚未接受的完整原句')
    expect(wrapper.find('textarea').element.value).toBe('尚未接受的完整原句')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('其他窗口已更新')
    expect(mocks.text).toHaveBeenCalledTimes(1)
  })
})

describe('focus changes during recovery', () => {
  it('retires the old recovery UI when the shared conversation moves to a new item', async () => {
    const old = makeTask({ processing_turn_id: 'atn_old', processing_turn_status: 'RUNNING' })
    const next = makeTask({ public_id: 'ast_new', version: 2, waiting: field({ action_id: 'new-action', expected_version: 2 }) })
    show(view({ version: 1, focused_task: old }))
    mocks.turn.mockResolvedValueOnce({ turn_id: 'atn_old', status: 'RUNNING', events: [], task: old })
      .mockResolvedValue({ turn_id: 'atn_old', status: 'SUCCEEDED', events: [], task: { ...old, processing_turn_id: null, processing_turn_status: null } })
    mocks.get.mockResolvedValueOnce(view({ version: 1, focused_task: old }))
      .mockResolvedValue(view({ version: 2, focused_task: next, messages: [message('new', '新沟通等待客户', next)] }))
    const wrapper = mount(SalesAssistantChat)
    try {
      vi.useFakeTimers()
      await flushPromises()
      await vi.advanceTimersByTimeAsync(1000)
      await flushPromises()
      expect(wrapper.text()).toContain('新沟通等待客户')
      expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
      expect(mocks.retry).not.toHaveBeenCalled()
      expect(mocks.stream).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })
})

const resultEnvelope = (blocks: ReadonlyArray<Record<string, unknown>>) => ({
  schema_version: 'crm.agent.ui.v1' as const,
  message_id: 8,
  turn_id: 'turn-result',
  role: 'assistant' as const,
  state: 'final' as const,
  blocks,
  suggested_actions: [],
  metadata: { display: 'MESSAGE' as const, route: 'WORKFLOW' as const, accessibility_label: '结果' }
})

describe('local process card after an authoritative result', () => {
  it('keeps the write stage visible until the server result arrives', async () => {
    const current = makeTask({ waiting: confirmation() })
    show(view({ focused_task: current, messages: [message('one', '确认？', current)] }))
    mocks.command.mockResolvedValue(reply(view({ focused_task: current, messages: [message('one', '确认？', current)] }), prepared(current, 'confirm')))
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'write', phase: 'start', seq: 2 })
      await new Promise<void>((resolve) => { finish = resolve })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('写入客户活动')
    expect(wrapper.text()).toContain('处理中')
    expect(wrapper.text()).not.toContain('已更新')
    expect(wrapper.text()).not.toContain('本次跟进已写入')
    finish?.()
    await flushPromises()
    wrapper.unmount()
  })

  it('hides the process card once the activity write result is on screen', async () => {
    const current = makeTask({ waiting: confirmation() })
    const written = makeTask({ version: 4, committed: [{ kind: 'customer_activity', public_id: 'act_ok' }] })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    const success = {
      ...message('result', '活动已写入', written),
      outcome: 'activity_written' as const
    }
    mocks.get.mockResolvedValue(view({
      version: 4,
      focused_task: written,
      messages: [message('user', '确认', null, 'user'), success]
    }))
    drive((handlers) => {
      handlers.onStage({ stage: 'write', phase: 'done', ms: 20 })
      handlers.onWaiting({ task: written, message: '活动已写入' })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已写入')
    expect(wrapper.text()).not.toContain('执行过程')
    expect(wrapper.text()).not.toContain('原始内容已保存')
    expect(wrapper.text()).not.toContain('已更新')
    wrapper.unmount()
  })

  it('hides the process card for the follow-up success notice without a second success card', async () => {
    const current = makeTask({ waiting: confirmation() })
    const written = makeTask({ version: 4, committed: [{ kind: 'customer_activity', public_id: 'act_ok' }] })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    const success = {
      ...message('result', '睿狐科技 · 普通跟进', written),
      outcome: 'follow_up_disposition' as const,
      ui: resultEnvelope([{
        id: 'b_notice_written', type: 'notice', tone: 'success', title: '本次跟进已写入', text: '睿狐科技 · 普通跟进'
      }])
    }
    mocks.get.mockResolvedValue(view({ version: 4, focused_task: written, messages: [message('user', '确认', null, 'user'), success] }))
    drive((handlers) => { handlers.onWaiting({ task: written, message: '本次跟进已写入' }) })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('本次跟进已写入')
    expect(wrapper.text()).not.toContain('执行过程')
    expect(wrapper.text()).not.toContain('已更新')
    wrapper.unmount()
  })

  it('does not rebuild a process card when replaying a historical success', async () => {
    const written = makeTask({ committed: [{ kind: 'customer_activity', public_id: 'act_ok' }] })
    const success = { ...message('result', '活动已写入', written), outcome: 'activity_written' as const }
    show(view({ focused_task: written, messages: [message('user', '上次的跟进', null, 'user'), success] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('已写入')
    expect(wrapper.text()).not.toContain('执行过程')
    expect(wrapper.text()).not.toContain('原始内容已保存')
    wrapper.unmount()
  })

  it('keeps a new turn\'s process card when an older success is already on screen', async () => {
    const previous = makeTask({ public_id: 'ast_old', committed: [{ kind: 'customer_activity', public_id: 'act_old' }] })
    const old = { ...message('old', '活动已写入', previous), outcome: 'activity_written' as const }
    const current = makeTask()
    show(view({ focused_task: current, messages: [message('user', '上次', null, 'user'), old] }))
    mocks.text.mockResolvedValue(reply(view({
      version: 2,
      focused_task: current,
      messages: [message('user', '上次', null, 'user'), old, message('next-user', '今天又沟通了一次', null, 'user')]
    }), prepared(current)))
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onStage({ stage: 'structure', phase: 'start' })
      await new Promise<void>((resolve) => { finish = resolve })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '今天又沟通了一次')
    expect(wrapper.text()).toContain('已写入')
    expect(wrapper.text()).toContain('执行过程')
    expect(wrapper.text()).toContain('整理活动内容')
    expect(wrapper.text()).toContain('处理中')
    finish?.()
    await flushPromises()
    wrapper.unmount()
  })

  it('keeps the stage list after a known failure but does not say it was updated', async () => {
    const current = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    const failure = '跟进整理超时，尚未写入客户活动。原始内容已保存，本次没有产生 CRM 活动。'
    mocks.get.mockResolvedValue(view({
      version: 2,
      focused_task: current,
      messages: [{ ...message('failure', failure, current), outcome: 'failure' as const }]
    }))
    drive((handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'structure', phase: 'start', seq: 2 })
      handlers.onError({ code: 'UPSTREAM_TIMEOUT', retryable: true, message: failure, stage: 'structure', seq: 3 })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper)
    expect(wrapper.text()).toContain(failure)
    expect(wrapper.text()).toContain('执行过程')
    expect(wrapper.text()).toContain('原始内容已保存')
    expect(wrapper.text()).not.toContain('已更新')
    expect(wrapper.text()).not.toContain('本次跟进已写入')
    expect(wrapper.text()).not.toContain('已写入')
    wrapper.unmount()
  })

  it('keeps the process card for an unknown commit without pretending it succeeded', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    const notice = '客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。'
    const unknown = {
      ...message('unknown', notice, current),
      outcome: 'failure' as const,
      ui: resultEnvelope([{ id: 'b_notice_1', type: 'notice', tone: 'warning', title: '结果待核对', text: notice }])
    }
    mocks.get.mockResolvedValue(view({ version: 4, focused_task: current, messages: [message('user', '确认', null, 'user'), unknown] }))
    drive((handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'write', phase: 'start', seq: 2 })
      handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: notice, stage: 'write', seq: 3 })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('结果待核对')
    expect(wrapper.text()).toContain('执行过程')
    expect(wrapper.text()).toContain('写入客户活动')
    expect(wrapper.text()).not.toContain('已更新')
    expect(wrapper.text()).not.toContain('本次跟进已写入')
    expect(wrapper.text()).not.toContain('重新写入')
    wrapper.unmount()
  })

  it('keeps an unknown write reconciliation-only after the conversation read fails', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    mocks.get.mockRejectedValueOnce(new Error('read unavailable')).mockResolvedValue(initial)
    drive((handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: '结果待核对', seq: 2 })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('button').filter((button) => button.text() === '确认写入' && !button.element.disabled)).toHaveLength(0)
    expect(wrapper.find('[data-assistant-reconcile-status="checking"]').exists()).toBe(true)
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(mocks.stream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('fences the write when the terminal unknown result arrives by turn readback', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    mocks.get.mockResolvedValue(initial)
    drive((handlers) => handlers.onAccepted('atn_one', 1))
    mocks.turn.mockResolvedValue({
      turn_id: 'atn_one', status: 'FAILED', task: current,
      events: [{ seq: 2, event: 'error', data: { code: 'UNKNOWN_COMMIT_RESULT', message: '结果待核对' } }]
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('button').filter((button) => button.text() === '确认写入' && button.attributes('disabled') === undefined)).toHaveLength(0)
    expect(wrapper.find('[data-assistant-reconcile-status="checking"]').exists()).toBe(true)
    expect(mocks.stream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps an unknown result read-only when the current wait is suppressed', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    const suppressed = { ...current, waiting: null, reconciliation_required: true }
    mocks.get.mockResolvedValue(view({ version: 4, focused_task: suppressed }))
    drive((handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: '结果待核对', seq: 2 })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.get('textarea').element.disabled).toBe(true)
    expect(wrapper.find('[data-assistant-reconcile-status="checking"]').exists()).toBe(true)
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(mocks.stream).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('releases a null-wait local fence only for an explicitly reconciled newer signed wait', async () => {
    vi.useFakeTimers()
    const current = makeTask({ version: 2 })
    const unknown = {
      ...message('unknown', '结果待核对', current),
      outcome: 'failure' as const,
      ui: resultEnvelope([{ id: 'b_unknown', type: 'notice', tone: 'warning', title: '结果待核对', text: '不要重复提交' }])
    }
    const snapshot = (focused: typeof current) => view({
      version: focused.version + 10, focused_task: focused, has_pending_request: true,
      messages: [unknown, message('wait', '当前指令', focused)]
    })
    show(view({ version: 1, focused_task: current }))
    mocks.text.mockResolvedValue(reply(view({ version: 2, focused_task: current }), prepared(current)))
    mocks.get.mockResolvedValue(snapshot({ ...current, reconciliation_required: false }))
    mocks.turn.mockResolvedValue({ turn_id: 'atn_one', status: 'FAILED', events: [], task: current })
    drive((handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: '结果待核对', seq: 2 })
    })
    const wrapper = mount(SalesAssistantChat)
    try {
      await flushPromises()
      await send(wrapper)
      expect(wrapper.get('textarea').element.disabled).toBe(true)

      // Each automatic reconcile attempt answers with a still-unknown verdict carrying a newer snapshot.
      const reconcileWith = async (focused: typeof current, waitMs: number): Promise<void> => {
        mocks.reconcile.mockResolvedValue({ outcome: 'STILL_UNKNOWN', task: focused, message: '结果仍待核对', followup_turn_id: null })
        await vi.advanceTimersByTimeAsync(waitMs)
        await flushPromises()
      }
      await reconcileWith({ ...current, reconciliation_required: false, waiting: field({ expected_version: 2 }) }, 2_000)
      expect(wrapper.get('textarea').element.disabled).toBe(true)
      await reconcileWith({ ...current, version: 3, reconciliation_required: false }, 4_000)
      expect(wrapper.get('textarea').element.disabled).toBe(true)
      await reconcileWith({ ...current, version: 3, reconciliation_required: false, waiting: field({ action_id: null, expected_version: 3 }) }, 8_000)
      expect(wrapper.get('textarea').element.disabled).toBe(true)
      await reconcileWith({ ...current, version: 4, reconciliation_required: true, waiting: field({ action_id: 'fresh', expected_version: 4 }) }, 16_000)
      expect(wrapper.get('textarea').element.disabled).toBe(true)
      expect(mocks.reconcile).toHaveBeenCalledTimes(4)

      mocks.reconcile.mockResolvedValue({
        outcome: 'STILL_UNKNOWN', message: '结果仍待核对', followup_turn_id: null,
        task: { ...current, version: 5, reconciliation_required: false, waiting: field({ action_id: 'fresh', expected_version: 5 }) }
      })
      await button(wrapper, '查看结果')?.trigger('click')
      await flushPromises()
      expect(mocks.reconcile).toHaveBeenCalledTimes(5)
      expect(wrapper.text()).toContain('结果待核对')
      expect(wrapper.get('textarea').element.disabled).toBe(false)
      expect(button(wrapper, '重试同步')).toBeUndefined()
      expect(mocks.resume).not.toHaveBeenCalled()
      expect(mocks.text).toHaveBeenCalledTimes(1)
      expect(mocks.stream).toHaveBeenCalledTimes(1)
      expect(mocks.command).not.toHaveBeenCalled()
      expect(mocks.retry).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('rejects a Root retry action emitted while the focused task requires reconciliation', async () => {
    const retryAction = { type: 'retry' as const, action_id: 'retry:root', label: '重试' }
    const root = {
      ...message('root:reply', '模型服务响应超时'), outcome: 'failure' as const,
      ui: { ...resultEnvelope([{ id: 'b_error', type: 'error', code: 'UPSTREAM_TIMEOUT', title: '模型服务响应超时', message: '未接受输入', retryable: true }]),
        state: 'failed' as const, suggested_actions: [retryAction] }
    }
    show(view({ focused_task: makeTask({ reconciliation_required: true }), messages: [root] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    wrapper.getComponent(AgentUIMessage).vm.$emit('action', retryAction.action_id)
    expect(mocks.retryEntry).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('restores a read-only reconciliation fence on reload and clears it once auto reconcile restores a current action', async () => {
    vi.useFakeTimers()
    const current = { ...makeTask({ waiting: null }), reconciliation_required: true }
    const failure = { ...message('old', '结果待核对', current), outcome: 'failure' as const }
    show(view({ focused_task: current, messages: [failure] }))
    const resolved = { ...current, version: 2, waiting: field({ action_id: 'next', expected_version: 2 }), reconciliation_required: false }
    mocks.reconcile.mockResolvedValue({ outcome: 'NOT_WRITTEN', task: resolved, message: '未写入', followup_turn_id: null })
    mocks.get.mockResolvedValue(view({ version: 2, focused_task: resolved, messages: [failure] }))
    const wrapper = mount(SalesAssistantChat)
    try {
      await flushPromises()
      expect(wrapper.get('textarea').element.disabled).toBe(true)
      expect(mocks.reconcile).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(2_000)
      await flushPromises()
      expect(mocks.reconcile).toHaveBeenCalledWith(current.public_id)
      expect(wrapper.get('textarea').element.disabled).toBe(false)
      expect(mocks.command).not.toHaveBeenCalled()
      expect(mocks.stream).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
      vi.useRealTimers()
    }
  })

  it('keeps stage progress while a reloaded turn is still running', async () => {
    const current = makeTask({ processing_turn_id: 'atn_one', processing_turn_status: 'RUNNING' })
    show(view({ focused_task: current, messages: [message('user', '已收下的原句', null, 'user')] }))
    mocks.turn.mockResolvedValue({
      turn_id: 'atn_one', status: 'RUNNING', lease_version: 1, reprocess_allowed: false,
      events: [{ seq: 2, event: 'stage', data: { stage: 'write', phase: 'start' } }],
      task: current
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('写入客户活动')
    expect(wrapper.text()).toContain('处理中')
    expect(wrapper.text()).not.toContain('已更新')
    wrapper.unmount()
  })

  it('keeps a failed live context row failed while judging continues', async () => {
    const current = makeTask()
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    let finish: (() => void) | undefined
    drive(async (handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'context', phase: 'done', ms: 1200, score: 91 })
      handlers.onStage({ stage: 'context', phase: 'start' })
      handlers.onStage({ stage: 'context', phase: 'failed' })
      handlers.onStage({ stage: 'judge', phase: 'start' })
      handlers.onStage({ stage: 'context', phase: 'future' as StageEvent['phase'] })
      await new Promise<void>((resolve) => { finish = resolve })
    })
    const wrapper = mount(SalesAssistantChat)
    try {
      await flushPromises()
      await send(wrapper)
      expectContextFailureWhileJudging(wrapper)
      expect(wrapper.text()).toContain('处理中')
    } finally {
      wrapper.unmount()
      finish?.()
    }
  })

  it('replays a failed context stage from GET without turning an unknown phase into success', async () => {
    const current = makeTask({ processing_turn_id: 'atn_one', processing_turn_status: 'RUNNING' })
    show(view({ focused_task: current }))
    mocks.turn.mockResolvedValue({
      turn_id: 'atn_one', status: 'RUNNING', lease_version: 1, reprocess_allowed: false, task: current,
      events: [
        { seq: 1, event: 'stage', data: { stage: 'context', phase: 'start' } },
        { seq: 2, event: 'stage', data: { stage: 'context', phase: 'failed' } },
        { seq: 3, event: 'stage', data: { stage: 'judge', phase: 'start' } },
        { seq: 4, event: 'stage', data: { stage: 'context', phase: 'future', ms: 1200, score: 91 } },
        { seq: 5, event: 'stage', data: { stage: 'propose', phase: 'future' } }
      ]
    })
    const wrapper = mount(SalesAssistantChat)
    try {
      await flushPromises()
      expectContextFailureWhileJudging(wrapper)
      expect(stageRow(wrapper, '生成后续建议')).toBeUndefined()
      expect(wrapper.text()).toContain('处理中')
      expect(mocks.retry).not.toHaveBeenCalled()
      expect(mocks.stream).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('can submit on a new focus while the old unknown commit remains in history', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    const next = makeTask({ public_id: 'ast_new', version: 2, waiting: field({ action_id: 'new-action', expected_version: 2 }) })
    const unknown = {
      ...message('old-result', '结果待核对', current), outcome: 'failure' as const,
      ui: resultEnvelope([{ id: 'b_old_unknown', type: 'notice', tone: 'warning', title: '结果待核对', text: '不要重复提交' }])
    }
    const nextView = view({ version: 5, focused_task: next, messages: [unknown, message('new', '新沟通等待客户', next)] })
    mocks.get.mockResolvedValue(nextView)
    drive((handlers) => {
      handlers.onAccepted('atn_one', 1)
      handlers.onStage({ stage: 'write', phase: 'start', seq: 2 })
      handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, stage: 'write', message: '结果待核对', seq: 3 })
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('新沟通等待客户')
    expect(wrapper.text()).toContain('结果待核对')
    expect(wrapper.text()).not.toContain('执行过程')
    expect(wrapper.text()).not.toContain('原始内容已保存')
    expect(wrapper.get('textarea').element.disabled).toBe(false)

    const result = { ...next, version: 3, waiting: null }
    mocks.text.mockResolvedValue(reply(nextView, { ...prepared(next), turn_id: 'atn_new' }))
    mocks.get.mockResolvedValue(view({ ...nextView, version: 6, focused_task: result }))
    drive((handlers) => {
      handlers.onAccepted('atn_new', 1)
      handlers.onWaiting({ task: result, message: '已处理新沟通', seq: 2 })
    })
    await send(wrapper, '继续这条新沟通')
    expect(mocks.text).toHaveBeenCalledWith(expect.objectContaining({ text: '继续这条新沟通', expected_version: 5 }))
    expect(mocks.stream).toHaveBeenCalledTimes(2)
    expect(mocks.stream).toHaveBeenLastCalledWith('ast_new', expect.objectContaining({ kind: 'text' }), expect.any(Object), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(mocks.resume).not.toHaveBeenCalled()
    expect(mocks.retry).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
