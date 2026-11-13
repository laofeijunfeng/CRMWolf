import { beforeEach, describe, expect, it, vi } from 'vitest'
import request from '@/utils/request'
import {
  createInvoiceRedOffsetFileObjectUrl,
  createInvoiceReissueFileObjectUrl,
} from '../fileUpload'

vi.mock('@/utils/request', () => ({
  default: { get: vi.fn() },
}))

const requestGet = vi.mocked(request.get)

beforeEach(() => {
  requestGet.mockReset()
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:invoice-preview'),
  })
})

describe('invoice persisted preview file helpers', () => {
  it('loads each reissue file through its existing endpoint and creates an object URL', async () => {
    const blob = new Blob(['pdf'])
    requestGet.mockResolvedValue(blob)

    await expect(createInvoiceReissueFileObjectUrl(42, 'red')).resolves.toBe('blob:invoice-preview')
    expect(requestGet).toHaveBeenCalledWith('/v1/invoice-applications/reissues/42/red-file', { responseType: 'blob' })

    await expect(createInvoiceReissueFileObjectUrl(42, 'new')).resolves.toBe('blob:invoice-preview')
    expect(requestGet).toHaveBeenLastCalledWith('/v1/invoice-applications/reissues/42/new-file', { responseType: 'blob' })
  })

  it('loads a red-offset file through its existing endpoint and creates an object URL', async () => {
    requestGet.mockResolvedValue(new Blob(['pdf']))

    await expect(createInvoiceRedOffsetFileObjectUrl(7)).resolves.toBe('blob:invoice-preview')
    expect(requestGet).toHaveBeenCalledWith('/v1/invoice-applications/red-offsets/7/file', { responseType: 'blob' })
  })
})
