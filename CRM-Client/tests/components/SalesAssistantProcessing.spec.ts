// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { confirmation, drive, field, makeTask, message, mocks, prepared, reply, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'

async function send(wrapper: ReturnType<typeof mount>, text = '今天客户沟通'): Promise<void> {
  await wrapper.find('textarea').setValue(text)
  await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
  await flushPromises()
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
    expect(wrapper.text()).toContain('正在整理跟进内容')
    expect(wrapper.text()).toContain('内容已保存，处理仍在后台继续；关闭或刷新不会取消')
    finish?.()
    await flushPromises()
    expect(wrapper.text()).toContain('请补充客户名称')
    expect(wrapper.text()).not.toContain('内容已保存，处理仍在后台继续；关闭或刷新不会取消')
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
      expect(wrapper.text()).toContain('内容已保存，处理仍在后台继续；关闭或刷新不会取消')
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

  it('replays the exact Root request key after an uncertain response instead of starting another item', async () => {
    mocks.text.mockRejectedValueOnce(new Error('断网')).mockResolvedValueOnce(reply(view({ messages: [message('user', '原句', null, 'user')] })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '原句')
    const request = mocks.text.mock.calls[0]?.[0]
    await wrapper.findAll('button').find((b) => b.text() === '重试同步')?.trigger('click')
    await flushPromises()
    expect(mocks.text.mock.calls[1]?.[0]).toEqual(request)
    expect(wrapper.text().match(/原句/g)).toHaveLength(1)
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

  it('follows a successor turn discovered from a completed original turn using GET only', async () => {
    const current = makeTask({ processing_turn_id: 'atn_original', processing_turn_status: 'RUNNING' })
    const next = makeTask({ processing_turn_id: 'atn_next', processing_turn_status: 'RUNNING' })
    show(view({ focused_task: current }))
    mocks.get.mockResolvedValue(view({ focused_task: next }))
    mocks.turn.mockResolvedValueOnce({ turn_id: 'atn_original', status: 'SUCCEEDED', events: [], task: next })
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
    expect(wrapper.text()).toContain('对话加载失败')
    await send(wrapper, '不要丢原会话')
    expect(mocks.text).not.toHaveBeenCalled()
  })
})

describe('shared conversation recovery', () => {
  it('can resume the persisted same-owner request after reopening another browser', async () => {
    show(view({ version: 1, has_pending_request: true, messages: [message('old', '上次发送的原句', null, 'user')] }))
    mocks.resume.mockResolvedValue(reply(view({ version: 1, messages: [message('old', '上次发送的原句', null, 'user'), message('done', '已恢复处理')] })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
    await wrapper.findAll('button').find((b) => b.text() === '重试同步')?.trigger('click')
    await flushPromises()
    expect(mocks.resume).toHaveBeenCalledTimes(1)
    expect(mocks.text).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已恢复处理')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })

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
    drive(async () => { await new Promise<void>((resolve) => { finish = resolve }) })
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
    expect(wrapper.text()).toContain('正在整理跟进内容')
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
    drive((handlers) => handlers.onError({ code: 'UPSTREAM_TIMEOUT', retryable: true, message: failure }))
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
    drive((handlers) => handlers.onError({ code: 'UNKNOWN_COMMIT_RESULT', retryable: false, message: notice }))
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

  it('drops the previous process card when the conversation moves to another item', async () => {
    const current = makeTask({ waiting: confirmation() })
    const initial = view({ version: 3, focused_task: current, messages: [message('one', '确认？', current)] })
    show(initial)
    mocks.command.mockResolvedValue(reply(initial, prepared(current, 'confirm')))
    const next = makeTask({ public_id: 'ast_new', version: 2, waiting: field({ action_id: 'new-action', expected_version: 2 }) })
    mocks.get.mockResolvedValue(view({ version: 5, focused_task: next, messages: [message('new', '新沟通等待客户', next)] }))
    drive((handlers) => { handlers.onStage({ stage: 'write', phase: 'start' }) })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '确认写入')?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('新沟通等待客户')
    expect(wrapper.text()).not.toContain('执行过程')
    expect(wrapper.text()).not.toContain('原始内容已保存')
    wrapper.unmount()
  })
})
