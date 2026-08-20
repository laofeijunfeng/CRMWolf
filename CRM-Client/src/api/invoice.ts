/* eslint-disable crmwolf/require-zod-schema */
import request from '@/utils/request'
import { ApiResponseSchema } from '@/schemas/common'

export type TitleType = 'COMPANY' | 'PERSONAL'

export type InvoiceApplicationStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'ISSUED' | 'CANCELLED'
export type ApprovalPhase = 'draft' | 'pending_review' | 'approved' | 'rejected'

export interface InvoiceTitleCreate {
  title_type: TitleType
  title: string
  taxpayer_id: string
  bank_name?: string | null
  bank_account?: string | null
  address?: string | null
  phone?: string | null
}

export interface InvoiceTitleUpdate {
  title_type?: TitleType
  title?: string
  taxpayer_id?: string
  bank_name?: string | null
  bank_account?: string | null
  address?: string | null
  phone?: string | null
  is_default?: boolean
}

export interface InvoiceTitleResponse {
  id: number
  customer_id: string
  title_type: TitleType
  title: string
  taxpayer_id: string
  bank_name: string | null
  bank_account: string | null
  address: string | null
  phone: string | null
  is_default: boolean
  created_time: string
  last_modified_time: string
}

export interface InvoiceTitleListResponse {
  invoice_titles: InvoiceTitleResponse[]
}export interface InvoiceApplicationCreate {
  payment_plan_id: number
  invoice_title_id: number
  invoice_amount: number
  invoice_type: InvoiceType
  payment_record_id?: number
}

export interface InvoiceApplicationUpdate {
  payment_plan_id?: number
  invoice_title_id?: number
  invoice_amount?: number
  invoice_type?: InvoiceType
  payment_record_id?: number
}

export type InvoiceType = 'VAT_SPECIAL' | 'VAT_NORMAL'
export type InvoiceReissueApplicationStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'COMPLETED'
export type InvoiceReissueStatus = 'NONE' | 'REISSUE_PENDING' | 'REISSUED'
export type InvoiceEffectiveStatus = 'ACTIVE' | 'REISSUE_PENDING' | 'RED_OFFSET' | 'REISSUED'
export type CurrentInvoiceFileKind = 'original' | 'reissue_new'

export interface InvoiceReissueApplicationCreate {
  reason: string
  invoice_title_type: TitleType
  invoice_title_text: string
  invoice_taxpayer_id: string
  invoice_bank_name?: string | null
  invoice_bank_account?: string | null
  invoice_address?: string | null
  invoice_phone?: string | null
  invoice_amount: number
  invoice_type: InvoiceType
}

export interface InvoiceReissueApplicationUpdate {
  reason?: string
  invoice_title_type?: TitleType
  invoice_title_text?: string
  invoice_taxpayer_id?: string
  invoice_bank_name?: string | null
  invoice_bank_account?: string | null
  invoice_address?: string | null
  invoice_phone?: string | null
  invoice_amount?: number
  invoice_type?: InvoiceType
}

export interface InvoiceReissueApplicationResponse {
  id: number
  application_number: string
  original_invoice_application_id: number
  applicant_id: string
  applicant_name: string | null
  reason: string
  status: InvoiceReissueApplicationStatus
  approval_phase?: ApprovalPhase | null
  invoice_title_type: string
  invoice_title_text: string
  invoice_taxpayer_id: string
  invoice_bank_name: string | null
  invoice_bank_account: string | null
  invoice_address: string | null
  invoice_phone: string | null
  invoice_amount: string | number
  invoice_type: InvoiceType
  red_invoice_file_path: string | null
  red_invoice_number: string | null
  red_issued_time: string | null
  new_invoice_file_path: string | null
  new_invoice_number: string | null
  new_issued_time: string | null
  completed_time: string | null
  created_time: string
  last_modified_time: string
}

export interface InvoiceRedOffsetResponse {
  id: number
  invoice_application_id: number
  source_type: 'MANUAL' | 'REISSUE' | string
  reissue_application_id: number | null
  red_invoice_file_path: string
  red_invoice_number: string | null
  reason: string | null
  created_by: string
  created_by_name: string | null
  red_offset_time: string
  created_time: string
  last_modified_time: string
}

export interface InvoiceApplicationResponse {
  id: number
  application_number: string
  customer_id: string
  contract_id: number | null
  opportunity_id: number | null
  payment_plan_id: number | null
  invoice_title_id: number
  invoice_type: InvoiceType
  invoice_amount: string
  payment_record_id: number | null
  status: InvoiceApplicationStatus
  approval_phase?: ApprovalPhase | null
  applicant_id: string
  reviewer_id: string | null
  review_comment: string | null
  reviewed_time: string | null
  invoice_title_type: string
  invoice_title_text: string
  invoice_taxpayer_id: string
  invoice_bank_name: string | null
  invoice_bank_account: string | null
  invoice_address: string | null
  invoice_phone: string | null
  invoice_number: string | null
  // Task 6: 新增字段（发票文件上传）
  invoice_file_path: string | null
  issued_time: string | null
  created_time: string
  last_modified_time: string
  customer_name: string | null
  contract_name: string | null
  opportunity_name: string | null
  payment_plan_stage_name: string | null
  invoice_title_title: string | null
  applicant_name: string | null
  reviewer_name: string | null
  reissue_status?: InvoiceReissueStatus | null
  invoice_effective_status?: InvoiceEffectiveStatus | null
  current_invoice_file_kind?: CurrentInvoiceFileKind | null
  current_invoice_file_path?: string | null
  current_invoice_number?: string | null
  current_reissue_id?: number | null
  red_offsets: InvoiceRedOffsetResponse[]
  reissue_applications: InvoiceReissueApplicationResponse[]
}

export interface InvoiceApplicationListResponse {
  items: InvoiceApplicationResponse[]
  total: number
  page: number
  page_size: number
}

export interface InvoiceApplicationQueryParams {
  filters?: string
  sorts?: string
  customer_id?: string
  contract_id?: number
  payment_plan_id?: number
  status?: string
  status_exclude?: string
  invoice_type?: string
  invoice_type_exclude?: string
  invoice_effective_status?: string
  keyword?: string
  created_time_start?: string
  created_time_end?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface FinanceApprovalRequest {
  approved: boolean
  remark?: string
}

const InvoiceTitleResponseSchema = ApiResponseSchema<InvoiceTitleResponse>()
const InvoiceTitleListResponseSchema = ApiResponseSchema<InvoiceTitleListResponse>()
const InvoiceApplicationResponseSchema = ApiResponseSchema<InvoiceApplicationResponse>()
const InvoiceReissueApplicationResponseSchema = ApiResponseSchema<InvoiceReissueApplicationResponse>()
const InvoiceApplicationListResponseSchema = ApiResponseSchema<InvoiceApplicationListResponse>()
const DeleteResponseSchema = ApiResponseSchema<{ message: string }>()
const InvoiceApplicationArraySchema = ApiResponseSchema<InvoiceApplicationResponse[]>()

const invoiceApi = {
  createInvoiceTitle: async (customerId: string, data: InvoiceTitleCreate): Promise<InvoiceTitleResponse> => {
    return InvoiceTitleResponseSchema.parse(await request.post<InvoiceTitleResponse>('/v1/invoice-titles', data, {
      params: { customer_id: customerId }
    }))
  },

  getInvoiceTitles: async (customerId: string): Promise<InvoiceTitleListResponse> => {
    return InvoiceTitleListResponseSchema.parse(await request.get<InvoiceTitleListResponse>('/v1/invoice-titles', {
      params: { customer_id: customerId }
    }))
  },

  getInvoiceTitle: async (titleId: number): Promise<InvoiceTitleResponse> => {
    return InvoiceTitleResponseSchema.parse(await request.get<InvoiceTitleResponse>(`/v1/invoice-titles/${titleId}`))
  },

  updateInvoiceTitle: async (titleId: number, data: InvoiceTitleUpdate): Promise<InvoiceTitleResponse> => {
    return InvoiceTitleResponseSchema.parse(await request.put<InvoiceTitleResponse>(`/v1/invoice-titles/${titleId}`, data))
  },

  deleteInvoiceTitle: async (titleId: number): Promise<{ message: string }> => {
    return DeleteResponseSchema.parse(await request.delete<{ message: string }>(`/v1/invoice-titles/${titleId}`))
  },

  setDefaultInvoiceTitle: async (titleId: number): Promise<InvoiceTitleResponse> => {
    return InvoiceTitleResponseSchema.parse(await request.patch<InvoiceTitleResponse>(`/v1/invoice-titles/${titleId}/set-default`))
  },

  createInvoiceApplication: async (data: InvoiceApplicationCreate): Promise<InvoiceApplicationResponse> => {
    return InvoiceApplicationResponseSchema.parse(await request.post<InvoiceApplicationResponse>('/v1/invoice-applications', data))
  },

  getInvoiceApplications: async (params?: InvoiceApplicationQueryParams): Promise<InvoiceApplicationListResponse> => {
    return InvoiceApplicationListResponseSchema.parse(await request.get<InvoiceApplicationListResponse>('/v1/invoice-applications', { params }))
  },

  getInvoiceApplication: async (applicationId: number): Promise<InvoiceApplicationResponse> => {
    return InvoiceApplicationResponseSchema.parse(await request.get<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}`))
  },

  updateInvoiceApplication: async (applicationId: number, data: InvoiceApplicationUpdate): Promise<InvoiceApplicationResponse> => {
    return InvoiceApplicationResponseSchema.parse(await request.put<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}`, data))
  },

  createInvoiceReissueApplication: async (applicationId: number, data: InvoiceReissueApplicationCreate): Promise<InvoiceReissueApplicationResponse> => {
    return InvoiceReissueApplicationResponseSchema.parse(await request.post<InvoiceReissueApplicationResponse>(`/v1/invoice-applications/${applicationId}/reissues`, data))
  },

  updateInvoiceReissueApplication: async (reissueId: number, data: InvoiceReissueApplicationUpdate): Promise<InvoiceReissueApplicationResponse> => {
    return InvoiceReissueApplicationResponseSchema.parse(await request.put<InvoiceReissueApplicationResponse>(`/v1/invoice-applications/reissues/${reissueId}`, data))
  },

  completeInvoiceReissue: (reissueId: number, data: {
    red_file: File
    new_file: File
    red_invoice_number?: string
    new_invoice_number?: string
  }): Promise<InvoiceReissueApplicationResponse> => {
    const formData = new FormData()
    formData.append('red_file', data.red_file)
    formData.append('new_file', data.new_file)
    const redInvoiceNumber = data.red_invoice_number?.trim()
    const newInvoiceNumber = data.new_invoice_number?.trim()
    if (redInvoiceNumber !== undefined && redInvoiceNumber.length > 0) {
      formData.append('red_invoice_number', redInvoiceNumber)
    }
    if (newInvoiceNumber !== undefined && newInvoiceNumber.length > 0) {
      formData.append('new_invoice_number', newInvoiceNumber)
    }
    return request.post<InvoiceReissueApplicationResponse>(
      `/v1/invoice-applications/reissues/${reissueId}/complete`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' }
      }
    ).then((response) => InvoiceReissueApplicationResponseSchema.parse(response))
  },

  redOffsetInvoice: (applicationId: number, data: {
    file: File
    red_invoice_number?: string
    reason?: string
  }): Promise<InvoiceApplicationResponse> => {
    const formData = new FormData()
    formData.append('file', data.file)
    const redInvoiceNumber = data.red_invoice_number?.trim()
    const reason = data.reason?.trim()
    if (redInvoiceNumber !== undefined && redInvoiceNumber.length > 0) {
      formData.append('red_invoice_number', redInvoiceNumber)
    }
    if (reason !== undefined && reason.length > 0) {
      formData.append('reason', reason)
    }
    return request.post<InvoiceApplicationResponse>(
      `/v1/invoice-applications/${applicationId}/red-offset`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' }
      }
    ).then((response) => InvoiceApplicationResponseSchema.parse(response))
  },

  deleteInvoiceApplication: async (applicationId: number): Promise<{ message: string }> => {
    return DeleteResponseSchema.parse(await request.delete<{ message: string }>(`/v1/invoice-applications/${applicationId}`))
  },

  financeApprovalInvoiceApplication: async (applicationId: number, data: FinanceApprovalRequest): Promise<InvoiceApplicationResponse> => {
    return InvoiceApplicationResponseSchema.parse(await request.post<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}/finance-approval`, data))
  },

  /**
   * 发票开票（审批通过后调用）
   * @param applicationId 发票申请 ID
   * @param data 开票数据（文件和发票号均为可选）
   */
  markIssued: (applicationId: number, data: {
    file?: File
    invoice_number?: string
  }): Promise<InvoiceApplicationResponse> => {
    const formData = new FormData()
    if (data.file !== undefined) {
      formData.append('file', data.file)
    }
    if (data.invoice_number !== undefined && data.invoice_number !== '') {
      formData.append('invoice_number', data.invoice_number)
    }
    return request.post<InvoiceApplicationResponse>(
      `/v1/invoice-applications/${applicationId}/mark-issued`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' }
      }
    ).then((response) => InvoiceApplicationResponseSchema.parse(response))
  },

  getPaymentPlanInvoices: async (paymentPlanId: number): Promise<InvoiceApplicationResponse[]> => {
    return InvoiceApplicationArraySchema.parse(await request.get<InvoiceApplicationResponse[]>(`/v1/payment-plans/${paymentPlanId}/invoices`))
  }
}

export default invoiceApi
