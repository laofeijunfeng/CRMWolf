import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useDataTableExport } from '../useDataTableExport'
import { downloadBlob } from '@/utils/downloadBlob'

const handleApiError = vi.fn()
const toastSuccess = vi.fn()

vi.mock('@/utils/errorHandler', () => ({
  handleApiError,
}))

vi.mock('vue-sonner', () => ({
  toast: { success: toastSuccess },
}))

vi.mock('@/utils/downloadBlob', () => ({
  downloadBlob: vi.fn(),
}))

describe('useDataTableExport', () => {
  beforeEach(() => {
    vi.mocked(downloadBlob).mockClear()
    handleApiError.mockClear()
    toastSuccess.mockClear()
  })

  it('downloads once, toasts, and resets exporting on success', async () => {
    const request = vi.fn(async () => new Blob(['xlsx']))
    const { exporting, exportFields } = useDataTableExport({
      request,
      fileName: () => '客户列表.xlsx',
    })

    await exportFields(['account_name'])

    expect(request).toHaveBeenCalledTimes(1)
    expect(request).toHaveBeenCalledWith(['account_name'])
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), '客户列表.xlsx')
    expect(toastSuccess).toHaveBeenCalledWith('导出完成')
    expect(exporting.value).toBe(false)
  })

  it('ignores a second call while pending', async () => {
    let resolveRequest: ((blob: Blob) => void) | undefined
    const request = vi.fn(() => new Promise<Blob>((resolve) => { resolveRequest = resolve }))
    const { exportFields } = useDataTableExport({
      request,
      fileName: () => '客户列表.xlsx',
    })

    const first = exportFields(['account_name'])
    await exportFields(['account_name'])
    resolveRequest?.(new Blob(['xlsx']))
    await first

    expect(request).toHaveBeenCalledTimes(1)
    expect(downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('reports the error, rethrows for the dialog, and still resets exporting', async () => {
    const request = vi.fn(() => Promise.reject(new Error('network down')))
    const { exporting, exportFields } = useDataTableExport({
      request,
      fileName: () => '客户列表.xlsx',
    })

    await expect(exportFields(['account_name'])).rejects.toThrow('network down')

    expect(handleApiError).toHaveBeenCalledTimes(1)
    expect(handleApiError).toHaveBeenCalledWith(expect.any(Error), '导出 Excel')
    expect(downloadBlob).not.toHaveBeenCalled()
    expect(exporting.value).toBe(false)
  })
})
