import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()

vi.mock('@/utils/request', () => ({
  default: {
    get,
  },
}))

describe('paymentApi result recovery', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('retries only when the result resolver temporarily returns 404', async () => {
    get
      .mockRejectedValueOnce({ response: { status: 404 } })
      .mockResolvedValueOnce({ id: 101, approval_phase: 'pending_review' })

    const { default: paymentApi } = await import('../payment')
    const result = await paymentApi.resolvePaymentRecordWithRetry('hidden-key', {
      attempts: 2,
      delaysMs: [0],
    })

    expect(result).toEqual({ id: 101, approval_phase: 'pending_review' })
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('stops after the configured number of temporary 404s', async () => {
    const notFound = { response: { status: 404 } }
    get.mockRejectedValue(notFound)

    const { default: paymentApi } = await import('../payment')
    await expect(
      paymentApi.resolvePaymentRecordWithRetry('hidden-key', {
        attempts: 3,
        delaysMs: [0],
      }),
    ).rejects.toBe(notFound)

    expect(get).toHaveBeenCalledTimes(3)
  })

  it('does not retry a non-404 resolver error', async () => {
    const serverError = { response: { status: 500 } }
    get.mockRejectedValue(serverError)

    const { default: paymentApi } = await import('../payment')
    await expect(
      paymentApi.resolvePaymentRecordWithRetry('hidden-key', {
        attempts: 3,
        delaysMs: [0],
      }),
    ).rejects.toBe(serverError)

    expect(get).toHaveBeenCalledTimes(1)
  })
})
