import { describe, expect, it, vi } from 'vitest'

const toastWarning = vi.fn<(title: string, options: { description: string }) => void>()
const logger = vi.hoisted(() => ({
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  trace: vi.fn(),
}))

vi.mock('@/utils/logger', () => ({ logger }))

vi.mock('vue-sonner', () => ({
  toast: {
    warning: toastWarning,
  },
}))

describe('payment write outcome errors', () => {
  it.each([
    [{ code: 'ECONNABORTED', message: 'timeout of 10s exceeded' }, 'timeout'],
    [{ code: 'ERR_NETWORK', message: 'Network Error' }, 'network code'],
    [{ message: 'Network Error' }, 'network message'],
  ])('treats %s as outcome unknown (%s)', async (error, _label) => {
    const { isOutcomeUnknown } = await import('../errorHandler')
    expect(isOutcomeUnknown(error)).toBe(true)
  })

  it.each([
    [{ response: { status: 400 }, message: 'invalid amount' }, 'business error'],
    [{ response: { status: 422 }, message: 'validation failed' }, 'validation error'],
    [{ response: { status: 500 }, message: 'server error' }, 'server error'],
  ])('does not treat %s as outcome unknown (%s)', async (error, _label) => {
    const { isOutcomeUnknown } = await import('../errorHandler')
    expect(isOutcomeUnknown(error)).toBe(false)
  })

  it('uses a recovery-oriented warning instead of a failure toast', async () => {
    const { handleOutcomeUnknown } = await import('../errorHandler')

    handleOutcomeUnknown('回款登记')

    expect(toastWarning).toHaveBeenCalledTimes(1)
    expect(toastWarning.mock.calls[0]?.[0]).toBe('登记结果暂未确认')
    expect(toastWarning.mock.calls[0]?.[1].description).toContain('不要重复填写或提交')
  })
})
