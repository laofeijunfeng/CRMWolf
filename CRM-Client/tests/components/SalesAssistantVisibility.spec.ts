import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const submitStreamMock = vi.fn()
const createTaskMock = vi.fn()

const streamWillResolveOnce = (v: unknown): void => {
  submitStreamMock.mockImplementationOnce(async (_id, _input, handlers) => {
    handlers.onWaiting(v)
  })
}
const streamWillResolve = (v: unknown): void => {
  submitStreamMock.mockImplementation(async (_id, _input, handlers) => {
    handlers.onWaiting(v)
  })
}
const streamWillReturn = (p: Promise<unknown>): void => {
  submitStreamMock.mockReturnValue(p)
}
const listTasksMock = vi.fn()
const latestActiveMock = vi.fn()

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    createTask: (...args: unknown[]) => createTaskMock(...args),
    listTasks: (...args: unknown[]) => listTasksMock(...args),
    latestActiveTask: (...args: unknown[]) => latestActiveMock(...args),
    getTask: vi.fn()
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
  public_id: 'ast_t9',
  status: 'ACTIVE',
  goal: '记录会议',
  activity_kind: null,
  draft: emptyDraft,
  waiting: null,
  committed: [],
  budget_steps: 0,
  budget_max_steps: 50,
  version: 0,
  ...overrides
})

beforeEach(() => {
  submitStreamMock.mockReset()
  createTaskMock.mockReset()
  listTasksMock.mockReset()
  latestActiveMock.mockReset()
  latestActiveMock.mockResolvedValue(null)
  listTasksMock.mockResolvedValue({ tasks: [], skipped: [] })
})

describe('message visibility regression', () => {
  it('keeps every user bubble and assistant reply across multiple turns', async () => {
    const gapWaiting = makeTask({
      waiting: { type: 'FIELD', field: 'next_action', question_id: 'q1', prompt: '下一步？' }
    })
    createTaskMock.mockResolvedValue(gapWaiting)
    streamWillResolveOnce({ task: gapWaiting, message: '补充下一步' })
    const wrapper = mount(SalesAssistantChat)

    // Turn 1
    const textarea = wrapper.find('textarea')
    await textarea.setValue('今天开了个会')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    // Turn 2: answer the field
    const answered = makeTask({
      waiting: { type: 'CONFIRMATION', field: 'activity_write', question_id: 'q2', prompt: '确认？' },
      draft: { ...emptyDraft, content: { status: 'CANDIDATE', value: '整理稿' } }
    })
    streamWillResolveOnce({ task: answered, message: '确认后写入？' })
    await textarea.setValue('下周三找王总')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    const bubbles = wrapper.findAll('.bg-primary') // user bubbles
    const cards = wrapper.findAll('.bg-card') // assistant text
    expect(bubbles.length).toBeGreaterThanOrEqual(2)
    expect(cards.length).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).toContain('今天开了个会')
    expect(wrapper.text()).toContain('下周三找王总')
    expect(wrapper.text()).toContain('补充下一步')
    expect(wrapper.text()).toContain('确认后写入')
  })

  it('keeps the user bubble visible while the model is still working', async () => {
    let finishTurn: (() => void) | undefined
    const turnGate = new Promise<void>((resolve) => {
      finishTurn = resolve
    })
    createTaskMock.mockResolvedValue(makeTask())
    submitStreamMock.mockImplementation(async (_id, _input, handlers) => {
      await turnGate
      handlers.onWaiting({ task: makeTask(), message: '收到' })
    })
    void finishTurn

    const wrapper = mount(SalesAssistantChat)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('慢回复测试')
    await textarea.trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()

    // Reply not arrived yet — user bubble must already be visible.
    expect(wrapper.text()).toContain('慢回复测试')
    finishTurn?.()
    await flushPromises()
    expect(wrapper.text()).toContain('收到')
  })

  it('shows recent tasks in the sidebar after load', async () => {
    listTasksMock.mockResolvedValue({
      tasks: [
        makeTask({ status: 'COMPLETED', goal: '已完成的任务' }),
        makeTask({ status: 'CANCELLED', goal: '已取消的任务' })
      ],
      skipped: [2]
    })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('最近任务')
    expect(wrapper.text()).toContain('已完成的任务')
    expect(wrapper.text()).toContain('已取消的任务')
    expect(wrapper.text()).toContain('1 条历史任务无法识别，已跳过。')
  })
})
