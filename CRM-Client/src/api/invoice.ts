import request from '@/utils/request'

export type TitleType = 'COMPANY' | 'PERSONAL'

export type InvoiceApplicationStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'ISSUED' | 'CANCELLED'

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
  customer_id: number
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

export interface InvoiceApplicationResponse {
  id: number
  application_number: string
  customer_id: number
  contract_id: number | null
  opportunity_id: number | null
  payment_plan_id: number | null
  invoice_title_id: number
  invoice_type: InvoiceType
  invoice_amount: string
  payment_record_id: number | null
  status: InvoiceApplicationStatus
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
  created_time: string
  last_modified_time: string
  customer_name: string | null
  contract_name: string | null
  opportunity_name: string | null
  payment_plan_stage_name: string | null
  invoice_title_title: string | null
  applicant_name: string | null
  reviewer_name: string | null
}

export interface InvoiceApplicationListResponse {
  items: InvoiceApplicationResponse[]
  total: number
  page: number
  page_size: number
}

export interface InvoiceApplicationQueryParams {
  customer_id?: number
  contract_id?: number
  payment_plan_id?: number
  status?: InvoiceApplicationStatus
  keyword?: string
  page?: number
  page_size?: number
}

export interface FinanceApprovalRequest {
  approved: boolean
  remark?: string
}

const invoiceApi = {
  createInvoiceTitle: (customerId: number, data: InvoiceTitleCreate) => {
    return request.post<InvoiceTitleResponse>('/v1/invoice-titles', data, {
      params: { customer_id: customerId }
    })
  },

  getInvoiceTitles: (customerId: number) => {
    return request.get<InvoiceTitleListResponse>('/v1/invoice-titles', {
      params: { customer_id: customerId }
    })
  },

  getInvoiceTitle: (titleId: number) => {
    return request.get<InvoiceTitleResponse>(`/v1/invoice-titles/${titleId}`)
  },

  updateInvoiceTitle: (titleId: number, data: InvoiceTitleUpdate) => {
    return request.put<InvoiceTitleResponse>(`/v1/invoice-titles/${titleId}`, data)
  },

  deleteInvoiceTitle: (titleId: number) => {
    return request.delete<{ message: string }>(`/v1/invoice-titles/${titleId}`)
  },

  setDefaultInvoiceTitle: (titleId: number) => {
    return request.patch<InvoiceTitleResponse>(`/v1/invoice-titles/${titleId}/set-default`)
  },

  createInvoiceApplication: (data: InvoiceApplicationCreate) => {
    return request.post<InvoiceApplicationResponse>('/v1/invoice-applications', data)
  },

  getInvoiceApplications: (params?: InvoiceApplicationQueryParams) => {
    return request.get<InvoiceApplicationListResponse>('/v1/invoice-applications', { params })
  },

  getInvoiceApplication: (applicationId: number) => {
    return request.get<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}`)
  },

  updateInvoiceApplication: (applicationId: number, data: InvoiceApplicationUpdate) => {
    return request.put<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}`, data)
  },

  deleteInvoiceApplication: (applicationId: number) => {
    return request.delete<{ message: string }>(`/v1/invoice-applications/${applicationId}`)
  },

  submitInvoiceApplication: (applicationId: number) => {
    return request.post<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}/submit`)
  },

  financeApprovalInvoiceApplication: (applicationId: number, data: FinanceApprovalRequest) => {
    return request.post<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}/finance-approval`, data)
  },

  markAsInvoiced: (applicationId: number, invoiceNumber: string) => {
    return request.post<InvoiceApplicationResponse>(`/v1/invoice-applications/${applicationId}/mark-invoiced`, {
      invoice_number: invoiceNumber
    })
  },

  getPaymentPlanInvoices: (paymentPlanId: number) => {
    return request.get<InvoiceApplicationResponse[]>(`/v1/payment-plans/${paymentPlanId}/invoices`)
  }
}

export default invoiceApi