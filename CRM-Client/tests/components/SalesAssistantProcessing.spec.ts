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
    expect(wrapper.text()).toContain('整理内容')
    expect(wrapper.text()).toContain('Agent 正在处理')
    finish?.()
    await flushPromises()
    expect(wrapper.text()).toContain('请补充客户名称')
    expect(wrapper.text()).not.toContain('Agent 正在处理')
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

  it('reads the business result after the stream is lost without retrying the turn', async () => {
    const current = makeTask({ processing_turn_id: 'atn_one', processing_turn_status: 'RUNNING' })
    const finished = makeTask({ waiting: field() })
    mocks.text.mockResolvedValue(reply(view({ focused_task: current }), prepared(current)))
    mocks.get.mockResolvedValue(view({ focused_task: finished, messages: [message('user', '只收下一次的跟进', null, 'user'), message('result', '整理暂时没有完成，请稍后重试。', finished)] }))
    drive((handlers) => { handlers.onAccepted('atn_one', 1); handlers.onNetworkLost() })
    mocks.turn.mockResolvedValue({
      turn_id: 'atn_one', status: 'SUCCEEDED', lease_version: 1, reprocess_allowed: false,
      events: [{ seq: 2, event: 'waiting', data: { message: '整理暂时没有完成，请稍后重试。' } }],
      task: finished
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '只收下一次的跟进')
    expect(mocks.retry).not.toHaveBeenCalled()
    expect(mocks.turn).toHaveBeenCalled()
    expect(wrapper.text()).toContain('整理暂时没有完成，请稍后重试。')
    expect(wrapper.text()).not.toContain('连接中断')
    expect(wrapper.text()).not.toContain('重试同步')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
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
