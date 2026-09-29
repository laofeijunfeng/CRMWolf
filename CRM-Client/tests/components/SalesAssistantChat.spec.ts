import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const submitStreamMock = vi.fn()
const createTaskMock = vi.fn()
const changeKindMock = vi.fn()
const getTaskMock = vi.fn()
const resolveWith = vi.fn()
const streamCalls: Array<{ id: string; input: Record<string, unknown> }> = []

const stubStream = (): void => {
  submitStreamMock.mockImplementation(async (id: string, input: Record<string, unknown>, handlers: Record<string, (arg?: never) => void>) => {
    streamCalls.push({ id, input })
    const result = await resolveWith()
    if (result !== undefined) {
      handlers.onWaiting(result)
    }
  })
}

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    createTask: (...args: unknown[]) => createTaskMock(...args),
    getTask: (...args: unknown[]) => getTaskMock(...args),
    changeKind: (...args: unknown[]) => changeKindMock(...args)
  },
  submitInputStream: (...args: unknown[]) => submitStreamMock(...args)
}))

import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'
import type { AssistantTaskView } from '@/schemas/assistant-contracts'

const emptyDraft = {
  customer: { status: 'MISSING' },
  content: { status: 'MISSING' },
  next_action: { status: 'MISSING' },
  next_follow_time: { status: 'MISSING' }
}

const makeTask = (overrides: Partial<AssistantTaskView> = {}): AssistantTaskView => ({
  public_id: 'ast_t1',
  status: 'ACTIVE',
  goal: '记录睿狐科技的会议',
  activity_kind: null,
  draft: emptyDraft,
  waiting: null,
  committed: [],
  budget_steps: 0,
  budget_max_steps: 50,
  version: 0,
  ...overrides
})

const kindWaiting = makeTask({
  waiting: { type: 'ACTIVITY_KIND', field: 'activity_kind', question_id: 'q1', prompt: '哪种活动？' }
})

const confirmWaiting = makeTask({
  activity_kind: 'ONLINE_MEETING',
  draft: { ...emptyDraft, content: { status: 'CANDIDATE', value: '已整理' } },
  waiting: { type: 'CONFIRMATION', field: 'activity_write', question_id: 'q2', prompt: '确认后写入？' }
})

beforeEach(() => {
  submitStreamMock.mockReset()
  streamCalls.length = 0
  resolveWith.mockReset()
  stubStream()
  createTaskMock.mockReset()
  changeKindMock.mockReset()
  getTaskMock.mockReset()
})

describe('SalesAssistantChat waiting interactions', () => {
  it('sends a closed enum choice when the kind question is on the table', async () => {
    createTaskMock.mockResolvedValue(kindWaiting)
    resolveWith.mockResolvedValueOnce({ task: kindWaiting, message: '请选择活动类型' })
    const wrapper = mount(SalesAssistantChat)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天开了个会')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    const meeting = wrapper.findAll('button').find((b) => b.text().includes('线上会议'))
    expect(meeting).toBeDefined()
    resolveWith.mockResolvedValueOnce({ task: makeTask({ activity_kind: 'ONLINE_MEETING' }), message: '已选择' })
    await meeting?.trigger('click')
    await flushPromises()
    expect(streamCalls.at(-1)?.input).toMatchObject({ kind: 'submit_field', choice: 'ONLINE_MEETING' })
    expect(streamCalls.at(-1)?.input['client_request_id']).toEqual(expect.any(String))
  })

  it('sends confirm and reject payloads from the confirmation card', async () => {
    resolveWith.mockResolvedValue({ task: confirmWaiting, message: '等待确认' })
    const wrapper = mount(SalesAssistantChat, { props: { optionalMarker: true } })
    await wrapper.setProps({})
    // seed task through the exposed flow: simulate prop-free internal state
    // by driving the component through its public entry (submit text)
    createTaskMock.mockResolvedValue(confirmWaiting)
    resolveWith.mockResolvedValueOnce({ task: confirmWaiting, message: '整理完成' })

    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天和睿狐开了个会')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    const confirm = wrapper.findAll('button').find((b) => b.text() === '确认写入')
    const reject = wrapper.findAll('button').find((b) => b.text() === '取消')
    expect(confirm).toBeDefined()
    expect(reject).toBeDefined()

    resolveWith.mockResolvedValueOnce({ task: makeTask({ status: 'COMPLETED' }), message: '已记录' })
    await confirm?.trigger('click')
    await flushPromises()
    expect(streamCalls.at(-1)?.input).toMatchObject({ kind: 'confirm', choice: 'confirm' })
    expect(streamCalls.at(-1)?.input['client_request_id']).toEqual(expect.any(String))
  })

  it('sends a field answer only to the waiting field, not as new text', async () => {
    const gapWaiting = makeTask({
      waiting: { type: 'FIELD', field: 'next_action', question_id: 'q3', prompt: '下一步是什么？' }
    })
    createTaskMock.mockResolvedValue(gapWaiting)
    resolveWith.mockResolvedValueOnce({ task: gapWaiting, message: '补充下一步' })
    const wrapper = mount(SalesAssistantChat)

    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天开了个会')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    await textarea.setValue('下周三找王总')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    expect(streamCalls[1]?.input).toMatchObject({ kind: 'submit_field', text: '下周三找王总' })
    expect(streamCalls[1]?.input['client_request_id']).toEqual(expect.any(String))
  })

  it('sends cancel from the give-up button', async () => {
    const cancelled = makeTask({ status: 'CANCELLED' })
    createTaskMock.mockResolvedValue(kindWaiting)
    resolveWith.mockResolvedValueOnce({ task: kindWaiting, message: '选择类型' })
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('记一下')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    resolveWith.mockResolvedValueOnce({ task: cancelled, message: '已取消' })
    const giveUp = wrapper.findAll('button').find((b) => b.text().includes('算了'))
    await giveUp?.trigger('click')
    await flushPromises()
    expect(streamCalls.at(-1)?.input).toMatchObject({ kind: 'cancel' })
    expect(streamCalls.at(-1)?.input['client_request_id']).toEqual(expect.any(String))
  })

  it('submits only the current wait identity when the same question gets a newer action', async () => {
    const first = makeTask({ version: 1, waiting: { type: 'FIELD', field: 'next_action', question_id: 'q3', action_id: 'a1', expected_version: 1, prompt: '下一步？' } })
    const second = makeTask({ version: 2, waiting: { type: 'FIELD', field: 'next_action', question_id: 'q3', action_id: 'a2', expected_version: 2, prompt: '请补充下一步？' } })
    createTaskMock.mockResolvedValue(first)
    resolveWith.mockResolvedValueOnce({ task: first, message: '下一步？' })
      .mockResolvedValueOnce({ task: second, message: '请补充下一步？' })
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天会面')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    await textarea.setValue('明天回访')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(streamCalls[1]?.input).toMatchObject({ kind: 'submit_field', text: '明天回访', action_id: 'a1', expected_version: 1 })
    expect(wrapper.findAll('button').filter((button) => button.text() === '这条没有下一步')).toHaveLength(1)
    expect(wrapper.text()).toContain('请补充下一步？')
    resolveWith.mockResolvedValueOnce({ task: makeTask({ status: 'COMPLETED', version: 3 }), message: '已完成' })
    await wrapper.findAll('button').find((button) => button.text() === '这条没有下一步')?.trigger('click')
    await textarea.setValue('等待客户内部审批，批准前不安排新动作')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(streamCalls[2]?.input).toMatchObject({ kind: 'submit_field', choice: 'EXPLICITLY_NONE', text: '等待客户内部审批，批准前不安排新动作', action_id: 'a2', expected_version: 2 })
    expect(streamCalls[2]?.input['client_request_id']).not.toBe(streamCalls[1]?.input['client_request_id'])
  })
  it('does not show two interactive cards when a field wait is repeated unchanged', async () => {
    const current = makeTask({ version: 1, waiting: { type: 'FIELD', field: 'next_action', question_id: 'q1', action_id: 'a1', expected_version: 1, prompt: '下一步？' } })
    createTaskMock.mockResolvedValue(current)
    resolveWith.mockResolvedValue({ task: current, message: '下一步？' })
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('拜访客户')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    await textarea.setValue('待确认')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.findAll('button').filter((button) => button.text() === '这条没有下一步')).toHaveLength(1)
  })
  it('shows the waiting label with the field name while paused on a field', async () => {
    const gapWaiting = makeTask({
      waiting: { type: 'FIELD', field: 'next_action', question_id: 'q3', prompt: '下一步是什么？' }
    })
    createTaskMock.mockResolvedValue(gapWaiting)
    resolveWith.mockResolvedValueOnce({ task: gapWaiting, message: '补充下一步' })
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('记一下')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.text()).toContain('正在回答：下一步行动')
  })
  it('refreshes authoritative task after changing activity kind', async () => {
    createTaskMock.mockResolvedValue(confirmWaiting)
    resolveWith.mockResolvedValueOnce({ task: confirmWaiting, message: '整理完成' })
    const stale = makeTask({ ...confirmWaiting, activity_kind: 'FOLLOW_UP' })
    const authoritative = makeTask({ activity_kind: 'FOLLOW_UP', version: 3, draft: emptyDraft })
    changeKindMock.mockResolvedValue(stale)
    getTaskMock.mockResolvedValue(authoritative)
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('开会讨论')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('改为'))?.trigger('click')
    await flushPromises()
    expect(changeKindMock).toHaveBeenCalledWith('ast_t1', 'FOLLOW_UP')
    expect(getTaskMock).toHaveBeenCalledWith('ast_t1')
    expect(wrapper.findComponent({ name: 'AssistantTaskSidebar' }).props('task')).toMatchObject({ version: 3, waiting: null })
    expect(wrapper.findAll('button').some((button) => button.text() === '确认写入')).toBe(false)
  })

  it('clears the whole conversation when starting a new task', async () => {
    createTaskMock.mockResolvedValue(kindWaiting)
    resolveWith.mockResolvedValueOnce({ task: kindWaiting, message: '哪种活动？' })
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('和睿狐开了个会')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.text()).toContain('和睿狐开了个会')

    await wrapper.findComponent({ name: 'AssistantTaskSidebar' }).vm.$emit('new-task')
    await flushPromises()
    expect(wrapper.find('.space-y-3').text()).not.toContain('和睿狐开了个会')
    expect(wrapper.text()).toContain('发送一句话开始，例如')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.findComponent({ name: 'AssistantTaskSidebar' }).props('task')).toBeNull()
  })
})
