// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { confirmation, field, makeTask, message, mocks, reply, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'

async function send(wrapper: ReturnType<typeof mount>, text: string): Promise<void> {
  await wrapper.find('textarea').setValue(text)
  await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
  await flushPromises()
}

describe('continuous conversation public interactions', () => {
  it('removes task management instead of replacing it with hidden task controls', async () => {
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).not.toMatch(/最近任务|新任务|取消任务/)
    expect(wrapper.find('[class*="240px"]').exists()).toBe(false)
  })

  it('routes the next communication after a committed activity and keeps the result above it', async () => {
    const completed = makeTask({ status: 'COMPLETED', committed: [{ kind: 'customer_activity', public_id: 'act_one' }] })
    const old = { ...message('old', '已记录这条客户活动。', completed), outcome: 'activity_written' as const }
    show(view({ focused_task: completed, messages: [old] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const current = makeTask({ public_id: 'ast_two', waiting: field() })
    mocks.text.mockResolvedValue(reply(view({ version: 1, focused_task: current, messages: [old, message('user2', '第二次电话', null, 'user'), message('new', '请补充客户名称', current)] })))
    await send(wrapper, '第二次电话')
    expect(mocks.text).toHaveBeenCalledWith(expect.objectContaining({ text: '第二次电话', expected_version: 0 }))
    expect(wrapper.text()).toContain('已写入')
    expect(wrapper.text()).toContain('第二次电话')
    expect(wrapper.text()).toContain('请补充客户名称')
  })

  it('sends a FIELD answer to Root rather than unconditionally patching the focused task', async () => {
    const current = makeTask({ waiting: field() })
    show(view({ focused_task: current, messages: [message('one', current.waiting?.prompt ?? '', current)] }))
    mocks.text.mockResolvedValue(reply(view({ version: 1 })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await send(wrapper, '河南双汇')
    expect(mocks.text).toHaveBeenCalledWith(expect.objectContaining({ text: '河南双汇' }))
    expect(mocks.command).not.toHaveBeenCalled()
  })

  it('keeps the composer available while a confirmation is on the table', async () => {
    const current = makeTask({ waiting: confirmation() })
    show(view({ focused_task: current, messages: [message('one', '确认？', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })

  it('sends only server-issued activity choices with current waiting identity', async () => {
    const current = makeTask({ waiting: field({ type: 'ACTIVITY_KIND', field: 'activity_kind', prompt: '属于哪种活动？' }) })
    show(view({ focused_task: current, messages: [message('one', '选择类型', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('线上会议'))?.trigger('click')
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({ input: expect.objectContaining({ kind: 'submit_field', choice: 'ONLINE_MEETING', action_id: 'action1', expected_version: 1 }) }))
  })

  it.each(['确认写入', '取消'])('preserves the frozen confirmation command for %s', async (label) => {
    const current = makeTask({ waiting: confirmation() })
    show(view({ focused_task: current, messages: [message('one', '确认？', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === label)?.trigger('click')
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({ input: expect.objectContaining({ kind: 'confirm', choice: label === '确认写入' ? 'confirm' : 'reject', action_id: 'action1', expected_version: 1 }) }))
  })

  it('cancels only the current item and never clears existing history', async () => {
    const current = makeTask({ waiting: field() })
    const history = [message('old', '上一条结果'), message('one', '客户名称？', current)]
    show(view({ focused_task: current, messages: history }))
    mocks.command.mockResolvedValue(reply(view({ version: 1, focused_task: { ...current, status: 'CANCELLED', waiting: null }, messages: [...history, message('done', '当前这件已停下。')] })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().endsWith('算了'))?.trigger('click')
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({ input: expect.objectContaining({ kind: 'cancel' }) }))
    expect(wrapper.text()).toContain('上一条结果')
    expect(wrapper.text()).toContain('当前这件已停下')
  })

  it('issues one two-choice card and consumes the structured choice without resending the raw text', async () => {
    const boundary = { entry_id: 'acm_one', prompt: '这句是接着刚才的睿狐科技，还是另记一件？' }
    const messages = [{ ...message('ambiguous', boundary.prompt), boundary }]
    show(view({ version: 3, pending_choice: boundary, messages }))
    mocks.choice.mockResolvedValue(reply(view({ version: 4, messages: [...messages, message('new', '下面开始记这一件。')] })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text().match(/这句是接着刚才的睿狐科技/g)).toHaveLength(1)
    await wrapper.findAll('button').find((b) => b.text() === '另记一件')?.trigger('click')
    await flushPromises()
    expect(mocks.choice).toHaveBeenCalledWith(expect.objectContaining({ entry_id: 'acm_one', choice: 'NEW', expected_version: 3 }))
    expect(mocks.text).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('下面开始记这一件')
    expect(wrapper.text()).toContain('历史交互不再提供可再次提交的确认按钮。')
    expect(wrapper.findAll('button').filter((b) => b.text() === '另记一件' && b.attributes('disabled') === undefined)).toHaveLength(0)
  })

  it('never makes two old/new versions of the same wait interactive', async () => {
    const old = makeTask({ waiting: confirmation() })
    const current = makeTask({ version: 2, waiting: confirmation({ action_id: 'action2', expected_version: 2 }) })
    show(view({ focused_task: current, messages: [message('old', '旧确认', old), message('new', '新确认', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const enabled = wrapper.findAll('button').filter((b) => b.text() === '确认写入' && b.attributes('disabled') === undefined)
    expect(enabled).toHaveLength(1)
    await enabled[0]?.trigger('click')
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({ input: expect.objectContaining({ action_id: 'action2', expected_version: 2 }) }))
  })
})

describe('pending boundary cancellation', () => {
  it('cancels only the pending original input, never the previous activity', async () => {
    const boundary = { entry_id: 'acm_pending', prompt: '这句是接着刚才，还是另记一件？' }
    const previous = makeTask({ status: 'COMPLETED', committed: [{ kind: 'customer_activity', public_id: 'act_old' }] })
    const messages = [message('receipt', '已记录这条客户活动。'), { ...message('choice', boundary.prompt), boundary }]
    show(view({ version: 3, focused_task: previous, pending_choice: boundary, messages }))
    mocks.choice.mockResolvedValue(reply(view({ version: 4, focused_task: previous, messages: [...messages, message('cancel', '当前这件已停下，之前的对话仍保留。')] })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().endsWith('算了'))?.trigger('click')
    await flushPromises()
    expect(mocks.choice).toHaveBeenCalledWith(expect.objectContaining({ entry_id: 'acm_pending', choice: 'CANCEL' }))
    expect(mocks.command).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已记录这条客户活动。')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })
})


describe('conversation load failures', () => {
  async function loadError(error: unknown): Promise<string> {
    mocks.open.mockRejectedValue(error)
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(mocks.text).not.toHaveBeenCalled()
    expect(mocks.command).not.toHaveBeenCalled()
    return wrapper.get('[role="alert"]').text()
  }

  it('classifies a schema mismatch without starting a new record', async () => {
    const text = await loadError({
      isAxiosError: true,
      response: { status: 500, data: { error_code: 'DATABASE_SCHEMA_MISMATCH' } }
    })
    expect(text).toContain('数据库结构与当前版本不一致，请联系管理员执行数据库迁移后重试；不会自动开始新的记录。')
  })

  it('asks the user to sign in again when the session is gone', async () => {
    const text = await loadError({ isAxiosError: true, response: { status: 401, data: {} } })
    expect(text).toContain('登录状态已失效，请重新登录后重试；不会自动开始新的记录。')
  })

  it('keeps a retryable network message when the server cannot be reached', async () => {
    const text = await loadError({ isAxiosError: true, response: undefined })
    expect(text).toContain('服务或网络暂时不可用，请检查网络后重试；不会自动开始新的记录。')
  })

  it('keeps the original failure sentence for an unclassified error', async () => {
    const text = await loadError(new Error('boom'))
    expect(text).toContain('对话加载失败，请重试；不会自动开始新的记录。')
  })
})


function rejectedCommand(status: number, message = 'rejected'): Error {
  return Object.assign(new Error(message), { isAxiosError: true, response: { status, data: {} } })
}

async function submitCardText(wrapper: ReturnType<typeof mount>, value: string): Promise<void> {
  const input = wrapper.find('input[type="text"]')
  expect(input.exists()).toBe(true)
  await input.setValue(value)
  const button = wrapper.findAll('button').find((item) => item.text() === '提交')
  expect(button).toBeDefined()
  await button?.trigger('click')
  await flushPromises()
}

describe('customer name text input', () => {
  it('submits trimmed text_input values with the current waiting gate', async () => {
    const prompt = '未找到对应客户，请核对并提供客户准确名称。'
    const current = makeTask({ waiting: field({ field: 'customer', prompt }) })
    const next = makeTask({ waiting: field({ field: 'content', prompt: '请补充沟通内容', action_id: 'action2', expected_version: 2, question_id: 'q2' }) })
    show(view({ focused_task: current, messages: [message('one', prompt, current)] }))
    mocks.command.mockResolvedValue(reply(view({
      version: 1,
      focused_task: next,
      messages: [message('one', prompt, current), message('two', '请补充沟通内容', next)]
    })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await submitCardText(wrapper, '  星河  科技  ')
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({
      expected_version: 0,
      input: expect.objectContaining({
        kind: 'submit_field',
        text: '星河  科技',
        action_id: 'action1',
        expected_version: 1,
        client_request_id: expect.any(String)
      })
    }))
    const requestId = mocks.command.mock.calls[0]?.[0].input.client_request_id as string
    expect(requestId.length).toBeGreaterThanOrEqual(8)
    expect(wrapper.text()).toContain('请补充沟通内容')
    expect(wrapper.text()).not.toContain('提交处理中')
  })

  it('reads the text payload for a non-customer text input', async () => {
    const current = makeTask({ waiting: field({ field: 'next_action', prompt: '请补充下一步' }) })
    show(view({ focused_task: current, messages: [message('one', '请补充下一步', current)] }))
    mocks.command.mockResolvedValue(reply(view({ version: 1, focused_task: current, messages: [message('one', '请补充下一步', current)] })))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await submitCardText(wrapper, '周三复盘')
    expect(mocks.command).toHaveBeenCalledWith(expect.objectContaining({
      input: expect.objectContaining({ kind: 'submit_field', text: '周三复盘', action_id: 'action1', expected_version: 1 })
    }))
  })

  it('keeps a blank customer name on the card and does not send it', async () => {
    const prompt = '未找到对应客户，请核对并提供客户准确名称。'
    const current = makeTask({ waiting: field({ field: 'customer', prompt }) })
    show(view({ focused_task: current, messages: [message('one', prompt, current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await submitCardText(wrapper, '   ')
    expect(mocks.command).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请填写客户名称')
    expect(wrapper.text()).not.toContain('提交处理中')
    expect(wrapper.findAll('button').some((button) => button.text() === '提交' && button.attributes('disabled') === undefined)).toBe(true)
  })

  it('unlocks the card after an explicit validation failure and does not replay it', async () => {
    const prompt = '未找到对应客户，请核对并提供客户准确名称。'
    const current = makeTask({ waiting: field({ field: 'customer', prompt }) })
    show(view({ focused_task: current, messages: [message('one', prompt, current)] }))
    mocks.command.mockRejectedValueOnce(rejectedCommand(422))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await submitCardText(wrapper, '星河科技')
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="alert"]').text()).toContain('这次提交没有被接受，请按当前提示修改后再提交。')
    expect(wrapper.text()).not.toContain('提交处理中')
    await wrapper.get('[role="alert"]').get('button').trigger('click')
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledTimes(1)
    mocks.command.mockResolvedValue(reply(view({ version: 1, focused_task: current, messages: [message('one', prompt, current)] })))
    await submitCardText(wrapper, '星河科技')
    expect(mocks.command).toHaveBeenCalledTimes(2)
  })

  it('uses the existing conflict and login sentences for explicit 409 and 401', async () => {
    const prompt = '未找到对应客户，请核对并提供客户准确名称。'
    const current = makeTask({ waiting: field({ field: 'customer', prompt }) })
    show(view({ focused_task: current, messages: [message('one', prompt, current)] }))
    mocks.command.mockRejectedValueOnce(rejectedCommand(409, 'conflict'))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await submitCardText(wrapper, '星河科技')
    expect(wrapper.get('[role="alert"]').text()).toContain('会话已更新，请查看当前提示；未接受的内容可重新发送。')
    expect(wrapper.text()).not.toContain('提交处理中')
    expect(mocks.command).toHaveBeenCalledTimes(1)

    mocks.command.mockRejectedValueOnce(rejectedCommand(401, 'unauthorized'))
    await submitCardText(wrapper, '另一家公司')
    expect(wrapper.get('[role="alert"]').text()).toContain('登录状态已失效，请重新登录后重试；不会自动开始新的记录。')
    expect(mocks.command).toHaveBeenCalledTimes(2)
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledTimes(2)
  })

  it('keeps an unknown network result locked and does not send it again', async () => {
    const prompt = '未找到对应客户，请核对并提供客户准确名称。'
    const current = makeTask({ waiting: field({ field: 'customer', prompt }) })
    show(view({ focused_task: current, messages: [message('one', prompt, current)] }))
    mocks.command.mockRejectedValue(Object.assign(new Error('Network Error'), { isAxiosError: true, response: undefined }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await submitCardText(wrapper, '星河科技')
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="alert"]').text()).toContain('发送状态待确认：Network Error')
    expect(wrapper.text()).toContain('提交处理中')
    await flushPromises()
    expect(mocks.command).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('button').some((button) => button.text() === '重试同步')).toBe(true)
  })
})
