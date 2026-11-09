import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  getUserTeams: vi.fn(),
}))
vi.mock('@/utils/request', () => ({ default: { post: mocks.post } }))
vi.mock('@/api/team', () => ({ teamApi: { getUserTeams: mocks.getUserTeams } }))
vi.mock('@/stores/user', () => ({ useUserStore: (): { userInfo: { id: number } } => ({ userInfo: { id: 1 } }) }))

const cachedEntry = {
  level: 'info', context: '[Test]', action: 'cached', data: { ok: true },
  timestamp: 100, userId: 1, teamId: 7,
}

describe('logger team context and response boundaries', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.resetAllMocks()
    vi.useFakeTimers()
    localStorage.clear()
    // Global listeners are unrelated to these public info/flush behavior tests.
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(document, 'addEventListener').mockImplementation(() => undefined)
    mocks.getUserTeams.mockResolvedValue({ teams: [], current_team_id: null })
    mocks.post.mockResolvedValue({ received: 1 })
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('omits teamId when the backend reports no current team', async () => {
    const { logger } = await import('../logger')
    logger.info('[Test]', 'without-team', { ok: true })
    await vi.advanceTimersByTimeAsync(0)
    await logger.flush()
    expect(mocks.post).toHaveBeenCalledWith('/v1/logs/batch', expect.objectContaining({
      logs: [expect.objectContaining({ userId: 1, action: 'without-team' })],
    }))
    const payload: unknown = mocks.post.mock.calls[0]?.[1]
    expect(payload).toHaveProperty('logs.0.userId', 1)
    expect(payload).not.toHaveProperty('logs.0.teamId')
  })

  it('keeps the numeric team ID on log entries', async () => {
    mocks.getUserTeams.mockResolvedValue({ teams: [], current_team_id: 7 })
    const { logger } = await import('../logger')
    logger.info('[Test]', 'with-team', {})
    await vi.advanceTimersByTimeAsync(0)
    await logger.flush()
    expect(mocks.post).toHaveBeenCalledWith('/v1/logs/batch', expect.objectContaining({
      logs: [expect.objectContaining({ userId: 1, teamId: 7 })],
    }))
  })

  it('preserves valid cached logs and accepts the backend received=0/error acknowledgement', async () => {
    localStorage.setItem('crm_frontend_logs', JSON.stringify([cachedEntry]))
    mocks.post.mockResolvedValue({ received: 0, error: 'disk full' })
    const { logger } = await import('../logger')
    await logger.flush()
    expect(mocks.post).toHaveBeenCalledWith('/v1/logs/batch', expect.objectContaining({ logs: [cachedEntry] }))
    expect(localStorage.getItem('crm_frontend_logs')).toBeNull()
    await vi.advanceTimersByTimeAsync(2000)
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })

  it('does not send malformed cached log entries', async () => {
    localStorage.setItem('crm_frontend_logs', JSON.stringify([{ level: 'info', timestamp: 'bad' }]))
    const { logger } = await import('../logger')
    await logger.flush()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('buffers and retries after a malformed batch acknowledgement using the existing retry delay', async () => {
    mocks.post.mockResolvedValueOnce({ received: '1' }).mockResolvedValueOnce({ received: 1 })
    const { logger } = await import('../logger')
    logger.info('[Test]', 'bad-ack', {})
    await vi.advanceTimersByTimeAsync(0)
    await logger.flush()
    expect(JSON.parse(localStorage.getItem('crm_frontend_logs') ?? 'null')).toEqual([
      expect.objectContaining({ action: 'bad-ack', userId: 1 }),
    ])
    await vi.advanceTimersByTimeAsync(2000)
    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(localStorage.getItem('crm_frontend_logs')).toBeNull()
  })
})
