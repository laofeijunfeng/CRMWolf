/**
 * 发票文件下载 API
 *
 * 上传发票文件由审批中心流程负责；发票管理和发票详情只保留下载能力。
 */
import request from '@/utils/request'

const getInvoiceFilePath = (invoiceId: number): string =>
  `/v1/invoice-applications/${invoiceId}/file`

export const createInvoiceFileObjectUrl = async (invoiceId: number): Promise<string> => {
  const response = await request.get<Blob>(getInvoiceFilePath(invoiceId), {
    responseType: 'blob'
  })
  const blob = response instanceof Blob ? response : new Blob([response])
  return window.URL.createObjectURL(blob)
}

export const downloadInvoiceFile = async (invoiceId: number, fileName?: string): Promise<void> => {
  const response = await request.get<Blob>(getInvoiceFilePath(invoiceId), {
    responseType: 'blob'
  })
  const blob = response instanceof Blob ? response : new Blob([response])
  const url = window.URL.createObjectURL(blob)
  const link = window.document.createElement('a')

  link.href = url
  link.download = fileName?.trim() || `invoice-${invoiceId}`
  window.document.body.appendChild(link)
  link.click()
  window.document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}
