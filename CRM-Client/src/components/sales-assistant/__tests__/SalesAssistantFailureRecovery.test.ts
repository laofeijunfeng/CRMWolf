import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AssistantTurn, SubmitStreamHandlers } from '@/api/assistant'
import type * as AssistantApi from '@/api/assistant'
import type { AssistantTaskView, ConversationView } from '@/schemas/assistant-contracts'

const api = vi.hoisted(() => ({
  openConversation: vi.fn(), getConversation: vi.fn(), getTurn: vi.fn(),
  conversationText: vi.fn(), retryTurn: vi.fn(), getTask: vi.fn(), reconcileTask: vi.fn(),
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
// 步骤行 = 标题所在的 li：标题、说明与右侧元信息都在里面。
const stageRow = (wrapper: VueWrapper, label: string): Element | null | undefined =>
  wrapper.findAll('span').find((span) => span.text() === label)?.element.closest('li')
// 步骤行本身不着状态色；完成、失败的语义色只落在该行的图标上。
const stageIconTone = (wrapper: VueWrapper, label: string): string => (
  stageRow(wrapper, label)?.querySelector('svg')?.getAttribute('class') ?? ''
)
const failedStage = (wrapper: VueWrapper): void => {
  expect(stageIconTone(wrapper, '判断活动类型')).toContain('text-tone-success')
  expect(stageRow(wrapper, '整理活动内容')?.textContent).toContain('失败')
  expect(stageRow(wrapper, '整理活动内容')?.textContent).not.toContain('进行中')
  expect(stageIconTone(wrapper, '整理活动内容')).toContain('text-tone-danger')
  expect(stageIconTone(wrapper, '评估记录质量')).not.toContain('text-tone-success')
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
  await button?.trigger('click')
  await flushPromises()
}

beforeEach(() => {
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
    await vi.advanceTimersByTimeAsync(181_000)
    await flushPromises()
    expect(mounted.text()).not.toContain('进行中…')
    expect(mounted.text()).toContain('待确认')
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(true)
  })

  it('keeps following a long turn while it reports progress, and stops waiting once progress stalls', async () => {
    let seq = 3
    let advancing = true
    api.getTurn.mockImplementation(() => {
      if (advancing) seq += 1
      const index = Math.min(seq - 3, 9)
      return Promise.resolve(runningTurn([...stageEvents, {
        seq, event: 'stage', data: { stage: 'structure', phase: 'start', segment: { index, total: 9 } },
      }]))
    })
    api.getConversation.mockResolvedValue(conversation(runningTask()))
    const mounted = await open()
    await vi.advanceTimersByTimeAsync(240_000)
    await flushPromises()
    expect(mounted.text()).not.toContain('处理结果待确认')
    expect(stageRow(mounted, '整理活动内容')?.textContent).toContain('第 9/9 段 · 进行中…')
    advancing = false
    await vi.advanceTimersByTimeAsync(181_000)
    await flushPromises()
    expect(mounted.text()).toContain('处理结果待确认')
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
    expect(stageRow(mounted, '整理活动内容')?.textContent).not.toContain('失败')
  })

  it('reconciles UNKNOWN_COMMIT_RESULT via reconcileTask when clicking 刷新状态 and restores confirmation on NOT_WRITTEN', async () => {
    const lockedTask = task({ version: 2, reconciliation_required: true, waiting: null })
    const restoredWaiting: AssistantTaskView['waiting'] = {
      type: 'CONFIRMATION',
      field: 'activity_write',
      question_id: 'q_confirm_task-1_3',
      action_id: 'awa_restored',
      expected_version: 3,
      prompt: '请确认写入客户活动。',
      confirmation_payload: {
        kind: 'activity_write',
        preview: {
          customer_name: '测试客户',
          activity_kind: 'PHONE_FOLLOW_UP',
          summary: '讨论项目推进',
          content_json: {},
          source_content: '今天和客户讨论了项目',
          score: 80,
          score_reason: '记录完整',
          next_action: '周三回访',
        },
      },
    }
    const restoredTask = task({ version: 3, reconciliation_required: false, waiting: restoredWaiting })
    api.reconcileTask.mockResolvedValue({
      outcome: 'NOT_WRITTEN',
      task: restoredTask,
      message: '已核对：上次确认未写入客户活动，已恢复确认卡片，可继续确认、修改或取消。',
      followup_turn_id: null,
    })
    api.getConversation.mockResolvedValue(conversation(restoredTask))

    const mounted = await open(lockedTask)
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeDefined()
    await click(mounted, '刷新状态')

    expect(api.reconcileTask).toHaveBeenCalledWith('task-1')
    expect(api.getTurn).not.toHaveBeenCalled()
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeUndefined()
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)
  })

  it('follows the spawned followup turn when reconcileTask proves WRITTEN', async () => {
    const lockedTask = task({ version: 2, reconciliation_required: true, waiting: null })
    const followupTask = task({
      version: 3,
      reconciliation_required: false,
      committed: [{ kind: 'customer_activity', public_id: '9001', customer_id: 1, customer_public_id: 'cus_1' }],
      processing_turn_id: 'turn-followup',
      processing_turn_status: 'RUNNING',
    })
    const settledTask = task({
      version: 4,
      status: 'COMPLETED',
      reconciliation_required: false,
      committed: [{ kind: 'customer_activity', public_id: '9001', customer_id: 1, customer_public_id: 'cus_1' }],
    })
    api.reconcileTask.mockResolvedValue({
      outcome: 'WRITTEN',
      task: followupTask,
      message: '已核对：客户活动已写入，正在继续后续整理。',
      followup_turn_id: 'turn-followup',
    })
    api.getConversation
      .mockResolvedValueOnce(conversation(followupTask))
      .mockResolvedValue(conversation(settledTask))
    api.getTurn.mockResolvedValue({
      turn_id: 'turn-followup',
      status: 'SUCCEEDED',
      lease_version: 1,
      reprocess_allowed: false,
      events: [{ seq: 1, event: 'stage', data: { stage: 'propose', phase: 'done', ms: 50 } }],
      task: settledTask,
    })

    const mounted = await open(lockedTask)
    await click(mounted, '刷新状态')

    expect(api.reconcileTask).toHaveBeenCalledWith('task-1')
    expect(api.getTurn).toHaveBeenCalledWith('task-1', 'turn-followup', 0)
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeUndefined()
  })

  it('stays fail-closed and shows notice when reconcileTask returns STILL_UNKNOWN or errors', async () => {
    const lockedTask = task({ version: 2, reconciliation_required: true, waiting: null })
    api.reconcileTask
      .mockResolvedValueOnce({
        outcome: 'STILL_UNKNOWN',
        task: lockedTask,
        message: '客户活动写入结果待核对。请先刷新或查询结果，不要重复提交。',
        followup_turn_id: null,
      })
      .mockRejectedValueOnce(new Error('network down'))
    api.getConversation.mockResolvedValue(conversation(lockedTask))

    const mounted = await open(lockedTask)
    await click(mounted, '刷新状态')
    expect(mounted.text()).toContain('客户活动写入结果待核对')
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeDefined()
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)

    await click(mounted, '刷新状态')
    expect(mounted.text()).toContain('核对请求暂时失败，请稍后再点刷新状态。')
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeDefined()
  })

  it('does not re-lock a reconciled task when replaying a historical UNKNOWN_COMMIT_RESULT turn', async () => {
    const reconciledTask = task({ version: 3, reconciliation_required: false, waiting: null })
    api.getTurn.mockResolvedValue(failedTurn({
      events: [{ seq: 1, event: 'error', data: { code: 'UNKNOWN_COMMIT_RESULT', message: '结果待核对', retryable: false } }],
      reprocess_allowed: false,
      task: reconciledTask,
    }))
    api.getConversation.mockResolvedValue(conversation(reconciledTask))

    const mounted = await open(task({ version: 2, processing_turn_id: 'turn-1', processing_turn_status: 'RUNNING', reconciliation_required: false }))
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeUndefined()
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)
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
