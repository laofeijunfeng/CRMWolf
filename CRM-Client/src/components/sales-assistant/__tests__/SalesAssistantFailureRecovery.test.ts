import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AssistantTurn, SubmitStreamHandlers } from '@/api/assistant'
import type * as AssistantApi from '@/api/assistant'
import type { AssistantTaskView, ConversationView } from '@/schemas/assistant-contracts'

const api = vi.hoisted(() => ({
  openConversation: vi.fn(), getConversation: vi.fn(), getTurn: vi.fn(),
  conversationText: vi.fn(), retryTurn: vi.fn(), getTask: vi.fn(),
}))
const stream = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...await importOriginal<typeof AssistantApi>(),
  assistantApi: api,
  submitInputStream: stream,
}))

vi.mock('@/utils/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'

const task = (overrides: Partial<AssistantTaskView> = {}): AssistantTaskView => ({
  public_id: 'task-1', status: 'ACTIVE', goal: '记录客户沟通',
  draft: {
    customer: { status: 'MISSING' }, content: { status: 'MISSING' },
    next_action: { status: 'MISSING' }, next_follow_time: { status: 'MISSING' },
  },
  committed: [], budget_steps: 1, budget_max_steps: 10, version: 1,
  processing_turn_id: null, processing_turn_status: null, reprocess_turn_id: null,
  ...overrides,
})
const runningTask = (): AssistantTaskView => task({ processing_turn_id: 'turn-1', processing_turn_status: 'RUNNING' })
const userMessage: ConversationView['messages'][number] = {
  id: 'entry-1:user', role: 'user', text: '今天和客户讨论了项目',
  at: '2026-11-09T01:00:00', task: null, boundary: null, outcome: null, ui: null,
}
const conversation = (focusedTask = task()): ConversationView => ({
  public_id: 'conversation-1', version: 1, focused_task: focusedTask,
  pending_choice: null, has_pending_request: false, older_cursor: null, messages: [userMessage],
})
const stageEvents: AssistantTurn['events'] = [
  { seq: 1, event: 'stage', data: { stage: 'classify', phase: 'start' } },
  { seq: 2, event: 'stage', data: { stage: 'classify', phase: 'done', ms: 100 } },
  { seq: 3, event: 'stage', data: { stage: 'structure', phase: 'start' } },
]
const failedTurn = (overrides: Partial<AssistantTurn> = {}): AssistantTurn => ({
  turn_id: 'turn-1', status: 'FAILED', lease_version: 1, reprocess_allowed: false,
  events: [...stageEvents, {
    seq: 4, event: 'error', data: { code: 'UPSTREAM_TIMEOUT', message: '模型服务响应超时', stage: 'structure' },
  }],
  task: task(), ...overrides,
})
const runningTurn = (events: AssistantTurn['events'] = []): AssistantTurn => ({
  turn_id: 'turn-1', status: 'RUNNING', lease_version: 2, reprocess_allowed: false,
  events, task: runningTask(),
})
const stageRow = (wrapper: VueWrapper, label: string): HTMLElement | null | undefined =>
  wrapper.findAll('span').find((span) => span.text() === label)?.element.parentElement
const failedStage = (wrapper: VueWrapper): void => {
  expect(stageRow(wrapper, '正在判断活动类型')?.className).toContain('text-success')
  expect(stageRow(wrapper, '正在整理活动内容')?.textContent).toContain('失败')
  expect(stageRow(wrapper, '正在整理活动内容')?.textContent).not.toContain('进行中')
  expect(stageRow(wrapper, '正在评估记录质量')?.className ?? '').not.toContain('text-success')
  expect(wrapper.text()).not.toContain('正在整理，内容较长')
}
let wrapper: VueWrapper | undefined
const open = async (focusedTask = runningTask()): Promise<VueWrapper> => {
  api.openConversation.mockResolvedValue(conversation(focusedTask))
  wrapper = mount(SalesAssistantChat)
  await flushPromises()
  return wrapper
}
const send = async (): Promise<VueWrapper> => {
  const mounted = await open(task())
  await mounted.get('textarea').setValue('今天和客户讨论了项目')
  await mounted.get('button[aria-label="发送"]').trigger('click')
  await flushPromises()
  return mounted
}
const click = async (mounted: VueWrapper, label: string): Promise<void> => {
  const button = mounted.findAll('button').find((item) => item.text() === label)
  expect(button).toBeDefined()
  ensureDomEventConstructor()
  await button?.trigger('click')
  await flushPromises()
}
const ensureDomEventConstructor = (): void => {
  const constructors: Record<string, unknown> = {
    Event: globalThis.Event,
    MouseEvent: globalThis.MouseEvent,
    KeyboardEvent: globalThis.KeyboardEvent,
    FocusEvent: globalThis.FocusEvent,
    CustomEvent: globalThis.CustomEvent,
  }
  for (const [name, constructor] of Object.entries(constructors)) {
    if (typeof constructor === 'function') Object.defineProperty(window, name, { configurable: true, value: constructor })
  }
}

beforeEach(() => {
  ensureDomEventConstructor()
  vi.useFakeTimers()
  Object.values(api).forEach((mock) => mock.mockReset())
  stream.mockReset()
  api.getConversation.mockResolvedValue(conversation())
  api.conversationText.mockResolvedValue({
    conversation: conversation(task()),
    submission: { task_public_id: 'task-1', turn_id: 'turn-1', input: { kind: 'text', text: userMessage.text, client_request_id: 'request-1' } },
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
})

describe('SalesAssistant failure recovery', () => {
  it('terminates the failed stage during readKnownTurn replay while preserving completed stages', async () => {
    api.getTurn.mockResolvedValue(failedTurn())
    const mounted = await open()
    failedStage(mounted)
  })

  it('terminates live stream failure and removes the long organize hint', async () => {
    let handlers: SubmitStreamHandlers | undefined
    let finish: (() => void) | undefined
    stream.mockImplementation((_id: string, _input: unknown, next: SubmitStreamHandlers) => {
      handlers = next
      next.onStage({ stage: 'classify', phase: 'done', ms: 100, seq: 2 })
      next.onStage({ stage: 'structure', phase: 'start', seq: 3 })
      return new Promise<void>((resolve) => { finish = resolve })
    })
    const mounted = await send()
    await vi.advanceTimersByTimeAsync(31_000)
    handlers?.onError({ code: 'UPSTREAM_TIMEOUT', retryable: true, message: '处理失败', stage: 'structure', seq: 4 })
    finish?.()
    await flushPromises()
    failedStage(mounted)
  })

  it('fails the running stage when the error frame carries no stage', async () => {
    let handlers: SubmitStreamHandlers | undefined
    let finish: (() => void) | undefined
    stream.mockImplementation((_id: string, _input: unknown, next: SubmitStreamHandlers) => {
      handlers = next
      next.onStage({ stage: 'classify', phase: 'done', ms: 100, seq: 2 })
      next.onStage({ stage: 'structure', phase: 'start', seq: 3 })
      return new Promise<void>((resolve) => { finish = resolve })
    })
    const mounted = await send()
    await vi.advanceTimersByTimeAsync(31_000)
    handlers?.onError({ code: 'INTERNAL_ERROR', retryable: true, message: '处理失败', seq: 4 })
    finish?.()
    await flushPromises()
    failedStage(mounted)
  })

  it('replays terminal HTTP fallback events before publishing the task', async () => {
    stream.mockResolvedValue(undefined)
    api.getTurn.mockResolvedValue(failedTurn())
    const mounted = await send()
    failedStage(mounted)
  })

  it('replays new failure events when manually syncing a previously unreadable turn', async () => {
    api.getTurn.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(failedTurn())
    const mounted = await open()
    await click(mounted, '刷新状态')
    failedStage(mounted)
  })

  it('keeps disconnected running work awaiting authoritative state, not failed', async () => {
    stream.mockImplementation((_id: string, _input: unknown, handlers: SubmitStreamHandlers) => {
      handlers.onStage({ stage: 'structure', phase: 'start', seq: 3 })
      handlers.onNetworkLost()
      return Promise.resolve()
    })
    api.getTurn.mockResolvedValue(runningTurn())
    api.getConversation.mockResolvedValue(conversation(runningTask()))
    const mounted = await send()
    expect(mounted.text()).toContain('正在确认处理结果')
    expect(mounted.text()).not.toContain('处理失败')
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)
  })

  it('shows awaiting state, not an indefinitely running stage, if recovery is unreadable', async () => {
    api.getTurn.mockResolvedValueOnce(runningTurn(stageEvents)).mockRejectedValue(new Error('offline'))
    api.getConversation.mockResolvedValue(conversation(runningTask()))
    const mounted = await open()
    await vi.advanceTimersByTimeAsync(91_000)
    await flushPromises()
    expect(mounted.text()).not.toContain('进行中…')
    expect(mounted.text()).not.toContain('正在整理，内容较长')
    expect(mounted.text()).toContain('待确认')
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(true)
  })

  it('never exposes safe reprocessing for UNKNOWN_COMMIT_RESULT even if retryable or stale authorization is present', async () => {
    const unknownTask = task({ reprocess_turn_id: 'turn-1' })
    api.getTurn.mockResolvedValue(failedTurn({
      events: [{ seq: 1, event: 'error', data: { code: 'UNKNOWN_COMMIT_RESULT', message: '结果待核对', retryable: true } }],
      reprocess_allowed: true, task: unknownTask,
    }))
    api.getConversation.mockResolvedValue(conversation(unknownTask))
    const mounted = await open()
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)
    expect(api.retryTurn).not.toHaveBeenCalled()
  })

  it('restarts the same turn without replaying old failure into the new attempt or repeating user input', async () => {
    const failedTask = task({ reprocess_turn_id: 'turn-1' })
    api.getTurn.mockResolvedValueOnce(failedTurn({ reprocess_allowed: true, task: failedTask }))
      .mockResolvedValueOnce(failedTurn({ reprocess_allowed: true, task: failedTask }))
      .mockResolvedValue(runningTurn())
    api.getConversation.mockResolvedValueOnce(conversation(failedTask)).mockResolvedValue(conversation(runningTask()))
    api.retryTurn.mockResolvedValue(runningTurn([
      ...failedTurn().events,
      { seq: 5, event: 'stage', data: { stage: 'structure', phase: 'start' } },
    ]))
    const mounted = await open()
    const userBubbles = mounted.findAll('.justify-end').length
    await click(mounted, '重新处理')
    expect(api.retryTurn).toHaveBeenCalledWith('task-1', 'turn-1', 1, 4)
    expect(api.conversationText).not.toHaveBeenCalled()
    expect(stream).not.toHaveBeenCalled()
    expect(mounted.findAll('.justify-end')).toHaveLength(userBubbles)
    expect(stageRow(mounted, '正在整理活动内容')?.textContent).not.toContain('失败')
  })
})

describe('assistant stream stage metadata', () => {
  it('delivers the validated failure stage from an actual SSE error frame', async () => {
    setActivePinia(createPinia())
    const actual = await vi.importActual<typeof AssistantApi>('@/api/assistant')
    const onError = vi.fn()
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(new ReadableStream({
      start(controller): void {
        controller.enqueue(new TextEncoder().encode('event: error\ndata: {"code":"UPSTREAM_TIMEOUT","retryable":true,"message":"处理失败","stage":"structure"}\n\n'))
        controller.close()
      },
    })))
    try {
      await actual.submitInputStream('task-1', { kind: 'text', client_request_id: 'request-1' }, {
        onAccepted: vi.fn(), onStage: vi.fn(), onWaiting: vi.fn(), onError, onNetworkLost: vi.fn(),
      })
    } finally {
      fetchSpy.mockRestore()
    }
    expect(onError.mock.calls[0]?.[0]).toMatchObject({ code: 'UPSTREAM_TIMEOUT', stage: 'structure' })
  })
})
