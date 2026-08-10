/* eslint-disable crmwolf/require-zod-schema */
/**
 * 发票文件下载 API
 *
 * 上传发票文件由审批中心流程负责；发票管理和发票详情只保留下载能力。
 */
import { BlobPartResponseSchema } from '@/schemas/common'
import request from '@/utils/request'

const toBlob = (response: Blob | ArrayBuffer | string): Blob =>
  response instanceof Blob ? response : new Blob([response])

const resolveDownloadFileName = (fileName: string | undefined, fallback: string): string => {
  const trimmedFileName = fileName?.trim()
  return trimmedFileName !== undefined && trimmedFileName.length > 0 ? trimmedFileName : fallback
}

const getInvoiceFilePath = (invoiceId: number): string =>
  `/v1/invoice-applications/${invoiceId}/file`

const getInvoiceReissueFilePath = (reissueId: number, fileKind: 'red' | 'new'): string =>
  `/v1/invoice-applications/reissues/${reissueId}/${fileKind}-file`

const getInvoiceRedOffsetFilePath = (redOffsetId: number): string =>
  `/v1/invoice-applications/red-offsets/${redOffsetId}/file`

const getContractFilePath = (contractId: number): string =>
  `/v1/contracts/${contractId}/file`

export const createInvoiceFileObjectUrl = async (invoiceId: number): Promise<string> => {
  const response = BlobPartResponseSchema.parse(
    await request.get<unknown>(getInvoiceFilePath(invoiceId), {
      responseType: 'blob'
    })
  )
  const blob = toBlob(response)
  return window.URL.createObjectURL(blob)
}

export const downloadInvoiceFile = async (invoiceId: number, fileName?: string): Promise<void> => {
  const response = BlobPartResponseSchema.parse(
    await request.get<unknown>(getInvoiceFilePath(invoiceId), {
      responseType: 'blob'
    })
  )
  const blob = toBlob(response)
  const url = window.URL.createObjectURL(blob)
  const link = window.document.createElement('a')

  link.href = url
  link.download = resolveDownloadFileName(fileName, `invoice-${invoiceId}`)
  window.document.body.appendChild(link)
  link.click()
  window.document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export const downloadInvoiceReissueFile = async (
  reissueId: number,
  fileKind: 'red' | 'new',
  fileName?: string
): Promise<void> => {
  const response = BlobPartResponseSchema.parse(
    await request.get<unknown>(getInvoiceReissueFilePath(reissueId, fileKind), {
      responseType: 'blob'
    })
  )
  const blob = toBlob(response)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = resolveDownloadFileName(fileName, `invoice-reissue-${reissueId}-${fileKind}`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export const downloadInvoiceRedOffsetFile = async (
  redOffsetId: number,
  fileName?: string
): Promise<void> => {
  const response = BlobPartResponseSchema.parse(
    await request.get<unknown>(getInvoiceRedOffsetFilePath(redOffsetId), {
      responseType: 'blob'
    })
  )
  const blob = toBlob(response)
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = resolveDownloadFileName(fileName, `invoice-red-offset-${redOffsetId}`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export const createContractFileObjectUrl = async (contractId: number): Promise<string> => {
  const response = BlobPartResponseSchema.parse(
    await request.get<unknown>(getContractFilePath(contractId), {
      responseType: 'blob'
    })
  )
  const blob = toBlob(response)
  return window.URL.createObjectURL(blob)
}

export const downloadContractFile = async (contractId: number, fileName?: string): Promise<void> => {
  const response = BlobPartResponseSchema.parse(
    await request.get<unknown>(getContractFilePath(contractId), {
      responseType: 'blob'
    })
  )
  const blob = toBlob(response)
  const url = window.URL.createObjectURL(blob)
  const link = window.document.createElement('a')

  link.href = url
  link.download = resolveDownloadFileName(fileName, `contract-${contractId}`)
  window.document.body.appendChild(link)
  link.click()
  window.document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}
