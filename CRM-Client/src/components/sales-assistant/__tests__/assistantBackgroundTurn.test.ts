import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import type { Router } from 'vue-router'
import type { AssistantTurn } from '@/api/assistant'

const toastMock = vi.hoisted(() => vi.fn())
const getTurn = vi.hoisted(() => vi.fn())
vi.mock('vue-sonner', () => ({ toast: toastMock }))
vi.mock('@/api/assistant', () => ({ assistantApi: { getTurn } }))

import { handOffAssistantTurn, reclaimAssistantTurn, watchAssistantBackgroundTurn } from '../assistantBackgroundTurn'

const turn = (status: AssistantTurn['status'], disposition: Record<string, unknown> | null = null): AssistantTurn => ({
  turn_id: 'turn-1',
  status,
  events: [{ seq: 3, event: 'stage', data: {} }],
  task: { public_id: 'task-1', waiting: null, follow_up_disposition: disposition }
} as unknown as AssistantTurn)

const routerAt = (name: string): { router: Router; push: ReturnType<typeof vi.fn>; route: { value: { name: string } } } => {
  const route = ref({ name })
  const push = vi.fn()
  return { router: { currentRoute: route, push } as unknown as Router, push, route }
}

describe('assistant background turn', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  })
  afterEach(() => {
    vi.useRealTimers()
    toastMock.mockReset()
    getTurn.mockReset()
  })

  it('announces a finished hand-off once and links back to the assistant', async () => {
    const { router, push } = routerAt('CustomerList')
    getTurn.mockResolvedValueOnce(turn('RUNNING')).mockResolvedValue(turn('SUCCEEDED', {
      status: 'ACTIVE', customer_name: '星河科技', activity_kind_label: '会议', total: 1
    }))
    handOffAssistantTurn({ targetId: 'task-1', turnId: 'turn-1' })
    const stop = watchAssistantBackgroundTurn(router)
    for (let i = 0; i < 4; i += 1) await vi.advanceTimersByTimeAsync(5000)
    stop()

    expect(getTurn).toHaveBeenNthCalledWith(1, 'task-1', 'turn-1', 0)
    expect(getTurn).toHaveBeenNthCalledWith(2, 'task-1', 'turn-1', 3)
    expect(getTurn).toHaveBeenCalledTimes(2)
    expect(toastMock).toHaveBeenCalledTimes(1)
    const [title, options] = toastMock.mock.calls[0] as [string, { description: string; action: { label: string; onClick: () => void } }]
    expect(title).toBe('会议内容已经整理完')
    expect(options.description).toBe('星河科技 · 1 条跟进记录待确认')
    expect(options.action.label).toBe('去确认')
    options.action.onClick()
    expect(push).toHaveBeenCalledWith('/assistant')
  })

  it('stays quiet on the assistant page and after the chat reclaims the turn', async () => {
    const { router, route } = routerAt('SalesAssistant')
    getTurn.mockResolvedValue(turn('SUCCEEDED'))
    handOffAssistantTurn({ targetId: 'task-1', turnId: 'turn-1' })
    const stop = watchAssistantBackgroundTurn(router)
    await vi.advanceTimersByTimeAsync(5000)
    reclaimAssistantTurn()
    route.value = { name: 'CustomerList' }
    await vi.advanceTimersByTimeAsync(5000)
    stop()

    expect(getTurn).not.toHaveBeenCalled()
    expect(toastMock).not.toHaveBeenCalled()
  })

  it('does not announce the same turn twice across tabs of one session', async () => {
    const { router } = routerAt('CustomerList')
    getTurn.mockResolvedValue(turn('SUCCEEDED'))
    handOffAssistantTurn({ targetId: 'task-1', turnId: 'turn-1' })
    const stop = watchAssistantBackgroundTurn(router)
    await vi.advanceTimersByTimeAsync(5000)
    handOffAssistantTurn({ targetId: 'task-1', turnId: 'turn-1' })
    await vi.advanceTimersByTimeAsync(5000)
    stop()

    expect(toastMock).toHaveBeenCalledTimes(1)
  })
})
