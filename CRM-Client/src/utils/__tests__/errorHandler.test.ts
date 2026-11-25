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

describe('duplicate record errors', () => {
  const duplicateResponse = (status: number, data: unknown): unknown => ({
    message: `Request failed with status code ${status}`,
    response: { status, data },
  })
  const body = {
    error_code: 'DUPLICATE_RECORD',
    detail: '该客户下已有这个手机号的联系人：张三',
    path: '/api/v1/customers/cus_1/contacts',
    duplicate: { entity: 'contact', existing_id: 7, existing_name: '张三' },
  }

  it('reads the existing record from a 409 duplicate response', async () => {
    const { parseDuplicateRecordError } = await import('../errorHandler')

    expect(parseDuplicateRecordError(duplicateResponse(409, body))).toEqual({
      entity: 'contact',
      existingId: 7,
      existingName: '张三',
      detail: '该客户下已有这个手机号的联系人：张三',
    })
  })

  it.each([
    [duplicateResponse(409, { error_code: 'VERSION_CONFLICT', detail: '已被他人修改' }), 'other 409'],
    [duplicateResponse(400, body), 'non-409 status'],
    [duplicateResponse(409, { ...body, duplicate: { entity: 'customer', existing_id: 7, existing_name: '张三' } }), 'unknown entity'],
    [{ message: 'Network Error' }, 'no response'],
  ])('ignores %s (%s)', async (error, _label) => {
    const { parseDuplicateRecordError } = await import('../errorHandler')
    expect(parseDuplicateRecordError(error)).toBeNull()
  })
})
