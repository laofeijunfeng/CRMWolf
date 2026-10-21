import type { InvoiceApplicationResponse } from '@/api/invoice'
import { downloadInvoiceFile, downloadInvoiceReissueFile } from '@/api/fileUpload'
import { buildInvoiceDownloadFileName } from '@/utils/invoiceFileName'

export const RED_OFFSET_INVOICE_DOWNLOAD_MESSAGE = '原蓝字发票已红冲，不能下载'
export const MISSING_INVOICE_FILE_MESSAGE = '该发票暂无可下载文件'

export interface InvoiceDownloadRequest {
  kind: 'original' | 'reissue_new'
  applicationId: number
  reissueId: number | null
  fileName: string
}

export const hasDownloadableInvoiceFile = (application: InvoiceApplicationResponse): boolean => {
  if (application.invoice_effective_status === 'RED_OFFSET') return false
  const filePath = application.current_invoice_file_path ?? application.invoice_file_path
  return application.status === 'ISSUED' && (filePath?.trim() ?? '') !== ''
}

export const resolveInvoiceDownload = (
  application: InvoiceApplicationResponse,
  date: Date = new Date(),
): InvoiceDownloadRequest | string => {
  if (application.invoice_effective_status === 'RED_OFFSET') {
    return RED_OFFSET_INVOICE_DOWNLOAD_MESSAGE
  }

  const filePath = (application.current_invoice_file_path ?? application.invoice_file_path)?.trim() ?? ''
  if (filePath === '') return MISSING_INVOICE_FILE_MESSAGE

  const fileName = buildInvoiceDownloadFileName(application.customer_name, filePath, date)
  if (
    application.current_invoice_file_kind === 'reissue_new'
    && application.current_reissue_id !== null
    && application.current_reissue_id !== undefined
  ) {
    return {
      kind: 'reissue_new',
      applicationId: application.id,
      reissueId: application.current_reissue_id,
      fileName,
    }
  }

  return {
    kind: 'original',
    applicationId: application.id,
    reissueId: null,
    fileName,
  }
}

export const downloadResolvedInvoice = async (request: InvoiceDownloadRequest): Promise<void> => {
  if (request.kind === 'reissue_new' && request.reissueId !== null) {
    await downloadInvoiceReissueFile(request.reissueId, 'new', request.fileName)
    return
  }
  await downloadInvoiceFile(request.applicationId, request.fileName)
}
