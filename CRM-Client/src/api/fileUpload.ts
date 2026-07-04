/**
 * 发票文件上传 API
 *
 * Task 5: 发票审批优化 - 前端文件上传组件
 * 对接后端 `app/api/invoice_approvals.py`:
 *   POST /v1/approvals/INVOICE/{invoice_id}/approve-with-file
 *   GET  /invoice-applications/{invoice_id}/file
 *
 * 设计要点：
 * - 复用 `@/utils/request` 实例（baseURL 由实例统一注入，禁止硬编码）
 * - TypeScript 严格模式：禁止 any / as any / 非空断言
 * - FormData 文件上传，Content-Type: multipart/form-data
 * - Zod Schema 校验响应（crmwolf/require-zod-schema）
 */

/* eslint-disable crmwolf/require-zod-schema -- FormData 上传无法直接 .parse()，校验在函数内执行 */

import request from '@/utils/request'
import { ApproveWithFileResponseSchema, type ApproveWithFileResponse } from '@/schemas/approvalGeneric'

/**
 * 上传发票文件并审批
 *
 * @param invoiceId - 发票申请 ID
 * @param file - 发票文件（PDF/JPG/PNG/OFD）
 * @param invoiceNumber - 发票号码（可选）
 * @param comment - 审批意见（可选）
 * @returns 审批结果（含文件路径、发票号码、新状态）
 */
export async function approveInvoiceWithFile(
  invoiceId: number,
  file: File,
  invoiceNumber?: string,
  comment?: string
): Promise<ApproveWithFileResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (invoiceNumber !== undefined && invoiceNumber.trim() !== '') {
    formData.append('invoice_number', invoiceNumber.trim())
  }
  if (comment !== undefined && comment.trim() !== '') {
    formData.append('comment', comment.trim())
  }

  const response = await request.post<ApproveWithFileResponse>(
    `/v1/approvals/INVOICE/${invoiceId}/approve-with-file`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  )

  // Zod 校验响应
  return ApproveWithFileResponseSchema.parse(response)
}

/**
 * 获取发票文件下载 URL
 *
 * @param invoiceId - 发票申请 ID
 * @returns 文件下载 URL（完整路径，可直接用于 <a> href 或 window.open）
 */
export function getInvoiceFileUrl(invoiceId: number): string {
  // baseURL 已由 axios 实例注入，使用相对路径
  const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api'
  return `${baseURL}/invoice-applications/${invoiceId}/file`
}

/**
 * 上传进度回调
 */
export type ProgressCallback = (progress: number) => void

/**
 * 带进度的文件上传（用于大文件场景）
 *
 * @param invoiceId - 发票申请 ID
 * @param file - 发票文件
 * @param onProgress - 进度回调（0-100）
 * @param invoiceNumber - 发票号码（可选）
 * @param comment - 审批意见（可选）
 * @returns 审批结果
 */
export async function approveInvoiceWithFileProgress(
  invoiceId: number,
  file: File,
  onProgress: ProgressCallback,
  invoiceNumber?: string,
  comment?: string
): Promise<ApproveWithFileResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (invoiceNumber !== undefined && invoiceNumber.trim() !== '') {
    formData.append('invoice_number', invoiceNumber.trim())
  }
  if (comment !== undefined && comment.trim() !== '') {
    formData.append('comment', comment.trim())
  }

  const response = await request.post<ApproveWithFileResponse>(
    `/v1/approvals/INVOICE/${invoiceId}/approve-with-file`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total !== undefined && progressEvent.total > 0) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          )
          onProgress(percentCompleted)
        }
      },
    }
  )

  // Zod 校验响应
  return ApproveWithFileResponseSchema.parse(response)
}