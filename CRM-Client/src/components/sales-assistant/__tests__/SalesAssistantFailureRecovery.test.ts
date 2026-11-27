import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { AssistantTurn, SubmitStreamHandlers } from '@/api/assistant'
import type * as AssistantApi from '@/api/assistant'
import type { AssistantTaskView, ConversationView } from '@/schemas/assistant-contracts'

const api = vi.hoisted(() => ({
  openConversation: vi.fn(), getConversation: vi.fn(), getTurn: vi.fn(),
  conversationText: vi.fn(), retryTurn: vi.fn(), getTask: vi.fn(), reconcileTask: vi.fn(), resumeConversation: vi.fn(),
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

  it('replays new failure events automatically via weak-network backoff when a turn is temporarily unreadable', async () => {
    api.getTurn.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(failedTurn())
    const mounted = await open()
    expect(mounted.text()).toContain('网络波动，正在自动恢复进度…')
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)
    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()
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
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)
  })

  it('keeps tracking through prolonged weak-network outages without a 180s cutoff and recovers on online', async () => {
    api.getTurn.mockResolvedValueOnce(runningTurn(stageEvents)).mockRejectedValue(new Error('offline'))
    api.getConversation.mockResolvedValue(conversation(runningTask()))
    const mounted = await open()
    await vi.advanceTimersByTimeAsync(181_000)
    await flushPromises()
    expect(mounted.text()).toContain('网络波动，正在自动恢复进度…')
    expect(mounted.text()).not.toContain('请点刷新状态')
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)

    api.getTurn.mockResolvedValueOnce(failedTurn())
    window.dispatchEvent(new Event('online'))
    await flushPromises()
    failedStage(mounted)
  })

  it('keeps following a long turn with unbounded backoff even when progress pauses beyond 180s', async () => {
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
    expect(mounted.text()).not.toContain('处理结果待确认')
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)
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

  it('auto-reconciles UNKNOWN_COMMIT_RESULT via reconcileTask without 刷新状态 and restores confirmation on NOT_WRITTEN', async () => {
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
    expect(mounted.find('[data-assistant-reconcile="checking"]').exists()).toBe(true)
    expect(mounted.find('[data-assistant-reconcile-lock]').text()).toContain('正在核对上一条保存结果，暂不可输入')
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeDefined()
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)

    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect(api.reconcileTask).toHaveBeenCalledWith('task-1')
    expect(api.getTurn).not.toHaveBeenCalled()
    expect(mounted.get('textarea').attributes('disabled')).toBeUndefined()
    expect(mounted.find('[data-assistant-reconcile="not_written"]').text()).toContain('刚才未能完成保存，内容都在，可以重新确认。')
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)
  })

  it('auto-reconciles UNKNOWN_COMMIT_RESULT and follows the spawned followup turn when WRITTEN', async () => {
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
    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect(api.reconcileTask).toHaveBeenCalledWith('task-1')
    expect(api.getTurn).toHaveBeenCalledWith('task-1', 'turn-followup', 0)
    expect(mounted.get('textarea').attributes('disabled')).toBeUndefined()
  })

  it('falls back to unified unconfirmed copy with 查看结果 after 2/4/8/16s auto-reconcile exhaustion', async () => {
    const lockedTask = task({ version: 2, reconciliation_required: true, waiting: null })
    const restoredTask = task({ version: 3, reconciliation_required: false, waiting: null })
    api.reconcileTask
      .mockResolvedValueOnce({
        outcome: 'STILL_UNKNOWN',
        task: lockedTask,
        message: '客户活动写入结果待核对。',
        followup_turn_id: null,
      })
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({
        outcome: 'STILL_UNKNOWN',
        task: lockedTask,
        message: '客户活动写入结果待核对。',
        followup_turn_id: null,
      })
      .mockResolvedValueOnce({
        outcome: 'STILL_UNKNOWN',
        task: lockedTask,
        message: '客户活动写入结果待核对。',
        followup_turn_id: null,
      })
      .mockResolvedValueOnce({
        outcome: 'NOT_WRITTEN',
        task: restoredTask,
        message: '未写入',
        followup_turn_id: null,
      })
    api.getConversation.mockResolvedValue(conversation(restoredTask))

    const mounted = await open(lockedTask)
    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()

    expect(api.reconcileTask).toHaveBeenCalledTimes(4)
    expect(mounted.find('[data-assistant-reconcile="unconfirmed"]').text()).toContain('结果暂时未确认，为避免重复，先不要再次提交。')
    expect(mounted.get('button[aria-label="发送"]').attributes('disabled')).toBeDefined()
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)
    expect(mounted.findAll('button').some((button) => button.text() === '重新处理')).toBe(false)

    await click(mounted, '查看结果')
    expect(api.reconcileTask).toHaveBeenCalledTimes(5)
    expect(mounted.get('textarea').attributes('disabled')).toBeUndefined()
    expect(mounted.findAll('button').some((button) => button.text() === '查看结果')).toBe(false)
  })

  it('shows offline banner with 重试连接 and auto-recovers via background sync on network disconnect', async () => {
    api.openConversation
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockResolvedValueOnce(conversation(task()))
    const mounted = mount(SalesAssistantChat)
    wrapper = mounted
    await flushPromises()

    expect(mounted.text()).toContain('网络已断开，已有内容都还在。网络恢复后会自动同步。')
    expect(mounted.findAll('button').some((button) => button.text() === '重试连接')).toBe(true)
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)

    await vi.advanceTimersByTimeAsync(2_000)
    await flushPromises()

    expect(api.openConversation).toHaveBeenCalledTimes(2)
    expect(mounted.text()).not.toContain('网络已断开')
  })

  it('auto-resumes interrupted route once on load and falls back to 继续处理 on failure', async () => {
    const pendingView: ConversationView = { ...conversation(task()), has_pending_request: true }
    api.openConversation.mockResolvedValue(pendingView)
    api.getConversation.mockResolvedValue(pendingView)
    api.resumeConversation.mockRejectedValueOnce(new Error('Network Error'))
    const mounted = mount(SalesAssistantChat)
    wrapper = mounted
    await flushPromises()

    expect(api.resumeConversation).toHaveBeenCalledTimes(1)
    expect(mounted.find('[data-assistant-pending-resume="failed"]').text()).toContain('上一条发送尚未完成')
    expect(mounted.findAll('button').some((button) => button.text() === '继续处理')).toBe(true)
    expect(mounted.findAll('button').some((button) => button.text() === '刷新状态')).toBe(false)
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
    expect(mounted.get('textarea').attributes('disabled')).toBeUndefined()
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
