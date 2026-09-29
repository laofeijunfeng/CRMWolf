import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const submitStreamMock = vi.fn()
const createTaskMock = vi.fn()
const listTasksMock = vi.fn()
const latestActiveMock = vi.fn()
const listActionsMock = vi.fn()

const getTurnMock = vi.fn()
const getTaskMock = vi.fn()
vi.mock('@/api/assistant', () => ({
  assistantApi: {
    createTask: (...args: unknown[]) => createTaskMock(...args),
    listTasks: (...args: unknown[]) => listTasksMock(...args),
    latestActiveTask: (...args: unknown[]) => latestActiveMock(...args),
    getTask: (...args: unknown[]) => getTaskMock(...args),
    getTurn: (...args: unknown[]) => getTurnMock(...args),
    listTaskActions: (...args: unknown[]) => listActionsMock(...args)
  },
  submitInputStream: (...args: unknown[]) => submitStreamMock(...args)
}))

import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'
import { AssistantTaskViewSchema, type AssistantTaskView } from '@/schemas/assistant-contracts'

const emptyDraft = {
  customer: { status: 'MISSING' },
  content: { status: 'MISSING' },
  next_action: { status: 'MISSING' },
  next_follow_time: { status: 'MISSING' }
}

const makeTask = (overrides: Partial<AssistantTaskView> = {}): AssistantTaskView => ({
  public_id: 'ast_p1',
  status: 'ACTIVE',
  goal: '记录跟进',
  activity_kind: null,
  draft: emptyDraft,
  waiting: null,
  committed: [],
  budget_steps: 0,
  budget_max_steps: 50,
  version: 0,
  ...overrides
})

/** Drive submitInputStream by invoking the captured handlers. */
async function driveStream(phases: Array<(h: Record<string, (arg?: never) => void>) => void>): Promise<void> {
  submitStreamMock.mockImplementation(async (_id: string, _input: unknown, handlers: Record<string, (arg?: never) => void>) => {
    for (const phase of phases) phase(handlers)
  })
}

beforeEach(() => {
  submitStreamMock.mockReset()
  createTaskMock.mockReset()
  listTasksMock.mockReset()
  latestActiveMock.mockReset()
  getTurnMock.mockReset()
  getTaskMock.mockReset()
  listActionsMock.mockReset()
  listActionsMock.mockResolvedValue([])
  latestActiveMock.mockResolvedValue(null)
  listTasksMock.mockResolvedValue([])
})

describe('SSE processing visibility', () => {
  it('renders only server-issued customer choices and submits the selected ID with waiting identity', async () => {
    const awaiting = AssistantTaskViewSchema.parse(makeTask({
      waiting: {
        type: 'OBJECT_SELECTION', field: 'customer', question_id: 'customer_q', action_id: 'action_customer',
        expected_version: 4, prompt: '选择客户', candidates: [
          { id: 'cus_a', account_name: '睿狐科技' },
          { id: 'cus_b', account_name: '睿狐集团' }
        ]
      }, version: 4
    }))
    latestActiveMock.mockResolvedValue(awaiting)
    await driveStream([(h) => h.onWaiting?.({ task: makeTask({ waiting: null, version: 5 }), message: '已绑定客户' })])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('睿狐科技')
    expect(wrapper.text()).toContain('睿狐集团')
    await wrapper.findAll('button').find((button) => button.text().includes('睿狐集团'))?.trigger('click')
    await flushPromises()
    expect(submitStreamMock.mock.calls[0]?.[1]).toMatchObject({
      kind: 'submit_field', choice: 'cus_b', action_id: 'action_customer', expected_version: 4
    })
  })
  it('ignores a previous task turn response after navigating to another task', async () => {
    const old = makeTask()
    const other = makeTask({ public_id: 'ast_other', goal: '另一条客户记录', waiting: null })
    latestActiveMock.mockResolvedValue(old)
    listTasksMock.mockResolvedValue([other])
    let resolveTurn: ((result: unknown) => void) | undefined
    getTurnMock.mockReturnValue(new Promise<unknown>((resolve) => { resolveTurn = resolve }))
    await driveStream([(h) => { h.onAccepted?.('turn_old', 1); h.onNetworkLost?.() }])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.find('textarea').setValue('先提交旧任务')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(getTurnMock).toHaveBeenCalledWith('ast_p1', 'turn_old', 1)
    getTaskMock.mockResolvedValue(other)
    await wrapper.findComponent({ name: 'AssistantTaskSidebar' }).vm.$emit('select-task', 'ast_other')
    await flushPromises()
    resolveTurn?.({ turn_id: 'turn_old', status: 'RUNNING', events: [], task: old })
    await flushPromises()
    expect(wrapper.findComponent({ name: 'AssistantTaskSidebar' }).props('task')).toMatchObject({ public_id: 'ast_other' })
    expect(wrapper.text()).not.toContain('重试同步')
    expect(wrapper.text()).not.toContain('连接中断')
  })
  it('runs the preset stages for a text turn and clears on waiting', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    const finalTask = makeTask({
      activity_kind: 'FOLLOW_UP',
      waiting: { type: 'CONFIRMATION', field: 'activity_write', question_id: 'q1', prompt: '确认写入？' }
    })
    await driveStream([
      (h) => h.onAccepted?.(),
      (h) => h.onStage?.({ stage: 'classify', phase: 'start' }),
      (h) => h.onStage?.({ stage: 'classify', phase: 'done', ms: 900 }),
      (h) => h.onStage?.({ stage: 'quality_gate', phase: 'done', ms: 1400, score: 82 }),
      (h) => h.onWaiting?.({ task: finalTask, message: '确认后写入这条客户活动？' })
    ])

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天聊了跟进')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('确认后写入')
    // Processing UI (stage list + hint) clears once waiting arrives.
    expect(text).not.toContain('Agent 正在处理')
    expect(text).not.toContain('判断活动类型')
  })

  it('clears loading when a completed stream has no waiting event', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    getTurnMock.mockResolvedValue({
      turn_id: 'turn_done',
      status: 'SUCCEEDED',
      events: [],
      task: makeTask({ status: 'COMPLETED', version: 2 })
    })
    await driveStream([(h) => h.onAccepted?.('turn_done', 1)])
    const wrapper = mount(SalesAssistantChat)
    await wrapper.find('textarea').setValue('今天的会议记录')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.text()).not.toContain('连接中断')
    expect(wrapper.text()).not.toContain('重试同步')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })

  it('shows the processing hint while the stream is mid-flight', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    const never = new Promise<void>(() => undefined)
    submitStreamMock.mockReturnValue(never)

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('慢轮次')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.text()).toContain('Agent 正在处理')
    // stage preset for text turn is visible
    expect(wrapper.text()).toContain('整理内容')
  })

  it('presets quality_gate and write for a confirm turn', async () => {
    const confirmTask = makeTask({
      waiting: { type: 'CONFIRMATION', field: 'activity_write', question_id: 'q1', prompt: '确认？' }
    })
    latestActiveMock.mockResolvedValue(confirmTask)
    await driveStream([
      (h) => h.onStage?.({ stage: 'quality_gate', phase: 'done', ms: 500, score: 88 }),
      (h) => h.onStage?.({ stage: 'write', phase: 'done', ms: 300 }),
      (h) => h.onWaiting?.({ task: makeTask({ status: 'ACTIVE' }), message: '已记录这条客户活动。' })
    ])

    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const confirm = wrapper.findAll('button').find((b) => b.text() === '确认写入')
    expect(confirm).toBeDefined()
    await confirm?.trigger('click')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('活动确认')
    expect(text).toContain('已记录这条客户活动。')
    expect(text).not.toContain('判断活动类型')
  })
  it('marks stages done with score while mid-flight', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    let release: (() => void) | undefined
    const gate = new Promise<void>((res) => {
      release = res
    })
    submitStreamMock.mockImplementation(async (_id, _input, handlers) => {
      handlers.onStage({ stage: 'classify', phase: 'start' })
      handlers.onStage({ stage: 'classify', phase: 'done', ms: 900 })
      handlers.onStage({ stage: 'quality_gate', phase: 'done', ms: 1400, score: 82 })
      await gate
    })

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('中途阶段')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('判断活动类型')
    expect(text).toContain('0.9s')
    expect(text).toContain('82 分')
    release?.()
  })

  it('surfaces a retryable error message from the stream', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    await driveStream([
      (h) => h.onAccepted?.(),
      (h) => h.onError?.({ code: 'AI_UNAVAILABLE', retryable: true, message: 'AI 服务暂时不可用，请稍后重试' })
    ])

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('触发降级')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.text()).toContain('AI 服务暂时不可用')
    expect(wrapper.text()).not.toContain('Agent 正在处理')
  })

  it('reconciles an interrupted accepted turn and presents only the authoritative waiting card', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    const recovered = makeTask({
      version: 3,
      waiting: { type: 'CONFIRMATION', field: 'activity_write', question_id: 'q3', action_id: 'a3', expected_version: 3, prompt: '确认写入？' }
    })
    getTurnMock.mockResolvedValue({ turn_id: 'turn_1', status: 'SUCCEEDED', events: [], task: recovered })
    getTaskMock.mockResolvedValue(recovered)
    await driveStream([(h) => h.onAccepted?.('turn_1'), (h) => h.onNetworkLost?.()])

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('断网测试')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    expect(getTurnMock).toHaveBeenCalledWith('ast_p1', 'turn_1', 0)
    expect(wrapper.text()).toContain('确认写入？')
    expect(wrapper.text()).not.toContain('没有提交')
    expect(wrapper.findAll('button').filter((button) => button.text() === '确认写入')).toHaveLength(1)
  })
  it('polls the accepted running turn without resubmitting a pending request', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    getTurnMock.mockResolvedValueOnce({ turn_id: 'turn_2', status: 'RUNNING', events: [], task: makeTask() })
      .mockResolvedValueOnce({ turn_id: 'turn_2', status: 'SUCCEEDED', events: [], task: makeTask({
        version: 2,
        waiting: { type: 'FIELD', field: 'next_action', question_id: 'q2', action_id: 'a2', expected_version: 2, prompt: '下一步？' }
      }) })
    await driveStream([(h) => h.onAccepted?.('turn_2'), (h) => h.onNetworkLost?.()])

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('慢速提交')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.text()).toContain('处理结果待确认')

    const retry = wrapper.findAll('button').find((button) => button.text() === '重试同步')
    expect(retry).toBeDefined()
    await retry?.trigger('click')
    await flushPromises()
    expect(getTurnMock).toHaveBeenNthCalledWith(2, 'ast_p1', 'turn_2', 0)
    expect(submitStreamMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('下一步？')
    expect(wrapper.text()).not.toContain('重试同步')
  })
  it('keeps an accepted running turn pending when refreshed, rather than POSTing again', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    getTurnMock.mockResolvedValue({ turn_id: 'turn_3', status: 'RUNNING', events: [], task: makeTask() })
    await driveStream([(h) => h.onAccepted?.('turn_3'), (h) => h.onNetworkLost?.()])
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('慢速提交')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '重试同步')?.trigger('click')
    await flushPromises()
    expect(getTurnMock).toHaveBeenCalledTimes(2)
    expect(submitStreamMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('重试同步')
  })
  it('renders the frozen follow-up candidate rather than mutable draft values', async () => {
    const active = makeTask({
      activity_kind: 'FOLLOW_UP',
      draft: {
        customer: { status: 'ACCEPTED', value: '后来客户' },
        content: { status: 'CANDIDATE', value: '后来内容' },
        next_action: { status: 'CANDIDATE', value: '后来行动' },
        next_follow_time: { status: 'CANDIDATE', value: '后来日期' }
      },
      waiting: {
        type: 'CONFIRMATION', field: 'activity_write', question_id: 'q4', action_id: 'a4', expected_version: 4, prompt: '确认？',
        confirmation_payload: { customer_name: '冻结客户', activity_kind: 'FOLLOW_UP', title: '冻结标题', summary: '冻结内容', content_json: {}, source_content: '原始沟通', score: 91, score_reason: '信息完整', next_action: '冻结行动', next_follow_time: '冻结日期' }
      }
    })
    latestActiveMock.mockResolvedValue(active)
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const text = wrapper.text()
    for (const value of ['冻结客户', '冻结内容', '冻结行动', '冻结日期', '91 / 100']) expect(text).toContain(value)
    for (const value of ['后来客户', '后来内容', '后来行动', '后来日期']) expect(text).not.toContain(value)
  })
  it('keeps the original request pending after disconnect before accepted and replays its key', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    const recovered = makeTask({ version: 1, waiting: { type: 'FIELD', field: 'next_action', question_id: 'q1', action_id: 'a1', expected_version: 1, prompt: '下一步？' } })
    getTaskMock.mockResolvedValue(recovered)
    await driveStream([(h) => h.onNetworkLost?.()])
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('断网前提交')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    const originalKey = submitStreamMock.mock.calls[0]?.[1].client_request_id
    expect(getTaskMock).toHaveBeenCalledWith('ast_p1')
    expect(wrapper.text()).toContain('重试同步')
    expect(submitStreamMock).toHaveBeenCalledTimes(1)
    await wrapper.findAll('button').find((button) => button.text() === '重试同步')?.trigger('click')
    await flushPromises()
    expect(submitStreamMock).toHaveBeenCalledTimes(2)
    expect(submitStreamMock.mock.calls[1]?.[1].client_request_id).toBe(originalKey)
  })
  it('offers recovery after an uncertain create-task response', async () => {
    createTaskMock.mockRejectedValue(new Error('连接断开'))
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天开了会')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.text()).toContain('提交状态待确认')
    expect(wrapper.findAll('button').some((button) => button.text() === '重试同步')).toBe(true)
    const firstCreateId = createTaskMock.mock.calls[0]?.[1]
    createTaskMock.mockResolvedValueOnce(makeTask())
    getTaskMock.mockResolvedValueOnce(makeTask())
    await driveStream([(h) => h.onWaiting?.({ task: makeTask({ version: 1, waiting: { type: 'FIELD', field: 'next_action', question_id: 'q1', prompt: '下一步？' } }), message: '下一步？' })])
    await wrapper.findAll('button').find((button) => button.text() === '重试同步')?.trigger('click')
    await flushPromises()
    expect(createTaskMock).toHaveBeenNthCalledWith(2, '今天开了会', firstCreateId)
    expect(submitStreamMock).toHaveBeenCalledTimes(1)
    expect(submitStreamMock.mock.calls[0]?.[1].client_request_id).not.toBe(firstCreateId)
    expect(wrapper.text()).not.toContain('重试同步')
  })
  it('does not replace the selected task when a disconnected old turn finishes later', async () => {
    createTaskMock.mockResolvedValue(makeTask())
    getTurnMock.mockResolvedValue({ turn_id: 'turn_old', status: 'RUNNING', events: [], task: makeTask() })
    await driveStream([(h) => h.onAccepted?.('turn_old'), (h) => h.onNetworkLost?.()])
    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('旧提交')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    getTaskMock.mockResolvedValue(makeTask({ public_id: 'ast_new', goal: '新任务' }))
    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_new')
    await flushPromises()
    getTurnMock.mockResolvedValue({ turn_id: 'turn_old', status: 'SUCCEEDED', events: [], task: makeTask({ goal: '旧提交', version: 4 }) })
    await wrapper.findAll('button').find((button) => button.text() === '重试同步')?.trigger('click')
    await flushPromises()
    expect(sidebar.props('task').public_id).toBe('ast_new')
  })
})
