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

export type PaymentConfirmationStatus = 'PENDING' | 'CONFIRMED' | 'DISPUTED'

// Task 8.2: Approval info types
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface ApprovalNodeInfo {
  id: number
  node_order: number
  node_name: string
  approve_role: string
  status: ApprovalStatus
  approver_id?: string
  approver_name?: string
  approved_time?: string
  comment?: string
}

export interface ApprovalInfo {
  id: number
  status: ApprovalStatus
  submitter_id: string
  submitter_name: string
  created_time: string
  nodes: ApprovalNodeInfo[]
  // Reject reason (from the rejected node)
  reject_reason?: string
}

export interface PaymentRecordInfo {
  id: number
  actual_amount: number
  payment_date: string
  proof_attachment?: string
  creator_name?: string
  notes?: string
  confirmation_status?: PaymentConfirmationStatus
  created_time: string
  // Task 7.2: Approval info for payment record
  approval_id?: number
  approval_status?: ApprovalStatus
  current_approver_name?: string
  invoice_application_count?: number  // Task 7.2: Number of invoice applications linked
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
  status_name?: string
  paid_amount?: number
  remaining_amount?: number
  payment_records: PaymentRecordInfo[]
  contract_name?: string
  customer_id?: number
  customer_name?: string
  opportunity_id?: number
  opportunity_name?: string
  creator_id?: string
  is_invoiced?: boolean
  invoice_count?: number
  invoiced_amount?: number
  created_time: string
  last_modified_time: string
  // Task 8.2: Approval info for latest payment record
  latest_record_id?: number
  latest_approval?: ApprovalInfo
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
  payment_plan_id: number  // 修复：与后端 schema 字段名一致
  actual_amount: number
  payment_date: string
  proof_attachment?: string
  notes?: string
  creator_id?: string
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
  customer_name?: string
  // Task 7.2: Approval and invoice info
  approval_id?: number
  approval_status?: ApprovalStatus
  current_approver_name?: string
  invoice_application_count?: number
  confirmation_status?: PaymentConfirmationStatus
}

export interface BadgeCounts {
  pending: number           // 未登记的计划数
  partial: number           // 部分回款的计划数
  overdue: number           // 逾期计划数
  pending_submit: number    // 待提交审批的记录数
  pending_approval: number  // 审批中的记录数（团队总数）
  pending_approval_me: number  // Task 8.3: 待我审批的数量（与审批中心一致）
}

/* eslint-disable @typescript-eslint/explicit-function-return-type, @typescript-eslint/explicit-module-boundary-types, crmwolf/require-zod-schema */
// TODO: Add Zod schema validation for API responses in future iteration

const paymentApi = {
  getPaymentSummary: (contractId: number): Promise<ContractPaymentSummary> => {
    return request.get<ContractPaymentSummary>(`/v1/payments/contracts/${contractId}/payment-summary`)
  },

  getPaymentPlans: (contractId: number, status?: PaymentPlanStatus): Promise<PaymentPlanResponse[]> => {
    const params = status ? { status } : {}
    return request.get<PaymentPlanResponse[]>(`/v1/payments/contracts/${contractId}/payment-plans`, { params })
  },

  getPaymentPlanDetail: (planId: number): Promise<PaymentPlanResponse> => {
    return request.get<PaymentPlanResponse>(`/v1/payments/payment-plans/${planId}`)
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
    const params = days !== undefined && days !== null ? { days } : {}
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
  },

  getBadgeCounts: (): Promise<BadgeCounts> => {
    return request.get<BadgeCounts>('/v1/payments/payment-plans/badge-counts')
  }
}

export default paymentApi
