import request from '@/utils/request'

export interface PaymentPlanCreate {
  stage_name: string
  planned_amount: number
  due_date: string
  notes?: string
}

export interface PaymentPlanBatchCreate {
  plans: PaymentPlanCreate[]
}

export interface PaymentRecordInfo {
  id: number
  actual_amount: number
  payment_date: string
  proof_attachment?: string
  creator_name?: string
  notes?: string
  created_time: string
}

export type PaymentPlanStatus = 'PENDING' | 'OVERDUE' | 'PARTIAL' | 'COMPLETED'

export type PaymentStatus = 'UNPAID' | 'PARTIAL' | 'COMPLETED' | 'OVERDUE'

export interface PaymentPlanResponse {
  id: number
  contract_id: number
  stage_name: string
  planned_amount: number
  due_date: string
  notes?: string
  status: PaymentPlanStatus
  paid_amount?: number
  remaining_amount?: number
  payment_records: PaymentRecordInfo[]
  created_time: string
  last_modified_time: string
}

export interface ContractPaymentSummary {
  contract_id: number
  contract_name: string
  total_amount: number
  total_paid_amount: number
  payment_status: PaymentStatus
  payment_plans_count: number
  completed_plans_count: number
  overdue_plans_count: number
  remaining_amount: number
}

export interface PaymentRecordCreate {
  actual_amount: number
  payment_date: string
  proof_attachment?: string
  notes?: string
}

export interface PaymentRecordUpdate {
  actual_amount?: number
  payment_date?: string
  proof_attachment?: string
  notes?: string
}

export interface PaymentRecordResponse {
  id: number
  plan_id: number
  actual_amount: number
  payment_date: string
  proof_attachment?: string
  notes?: string
  creator_name?: string
  created_time: string
  last_modified_time: string
}

export interface PaymentPlanUpdate {
  stage_name?: string
  planned_amount?: number
  due_date?: string
  notes?: string
}

export interface UpcomingPayment {
  contract_id: number
  contract_name: string
  plan_id: number
  stage_name: string
  planned_amount: number
  due_date: string
  days_until_due: number
  owner_name?: string
}

export interface OverduePayment {
  contract_id: number
  contract_name: string
  plan_id: number
  stage_name: string
  planned_amount: number
  paid_amount: number
  due_date: string
  days_overdue: number
  owner_name?: string
}

export interface PaymentPlanListParams {
  status?: PaymentPlanStatus
  owner_id?: string
  me?: boolean
  due_date_start?: string
  due_date_end?: string
  page?: number
  page_size?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PaymentPlanWithDetails extends PaymentPlanResponse {
  contract_name?: string
  customer_name?: string
  owner_id?: string
  owner_name?: string
}

export interface PaymentRecordListParams {
  contract_id?: number
  payment_plan_id?: number
  payment_date_start?: string
  payment_date_end?: string
  min_amount?: number
  creator_id?: string
  me?: boolean
  page?: number
  page_size?: number
}

export interface PaymentRecordWithDetails extends PaymentRecordResponse {
  contract_name?: string
  stage_name?: string
}

const paymentApi = {
  getPaymentSummary: (contractId: number) => {
    return request.get<ContractPaymentSummary>(`/v1/payments/contracts/${contractId}/payment-summary`)
  },

  getPaymentPlans: (contractId: number, status?: PaymentPlanStatus) => {
    const params = status ? { status } : {}
    return request.get<PaymentPlanResponse[]>(`/v1/payments/contracts/${contractId}/payment-plans`, { params })
  },

  createPaymentPlans: (contractId: number, data: PaymentPlanBatchCreate) => {
    return request.post<PaymentPlanResponse[]>(`/v1/payments/contracts/${contractId}/payment-plans`, data)
  },

  updatePaymentPlan: (planId: number, data: PaymentPlanUpdate) => {
    return request.put<PaymentPlanResponse>(`/v1/payments/payment-plans/${planId}`, data)
  },

  deletePaymentPlan: (planId: number) => {
    return request.delete(`/v1/payments/payment-plans/${planId}`)
  },

  getPaymentRecords: (planId: number) => {
    return request.get<PaymentRecordInfo[]>(`/v1/payments/payment-plans/${planId}/records`)
  },

  createPaymentRecord: (planId: number, data: PaymentRecordCreate) => {
    return request.post<PaymentRecordResponse>(`/v1/payments/payment-plans/${planId}/records`, data)
  },

  updatePaymentRecord: (recordId: number, data: PaymentRecordUpdate) => {
    return request.put<PaymentRecordResponse>(`/v1/payments/payment-records/${recordId}`, data)
  },

  deletePaymentRecord: (recordId: number) => {
    return request.delete(`/v1/payments/payment-records/${recordId}`)
  },

  getUpcomingPayments: (days?: number) => {
    const params = days ? { days } : {}
    return request.get<UpcomingPayment[]>('/v1/payments/reminders/upcoming', { params })
  },

  getOverduePayments: () => {
    return request.get<OverduePayment[]>('/v1/payments/reminders/overdue')
  },

  listPaymentPlans: (params: PaymentPlanListParams) => {
    return request.get<PaginatedResponse<PaymentPlanWithDetails>>('/v1/payments/payment-plans', { params })
  },

  listPaymentRecords: (params: PaymentRecordListParams) => {
    return request.get<PaginatedResponse<PaymentRecordWithDetails>>('/v1/payments/payment-records', { params })
  }
}

export default paymentApi
