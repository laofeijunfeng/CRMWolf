import request from '@/utils/request'

export interface AccountAging {
  range: string
  amount: string
  count: number
}

export interface AccountAgingAnalysis {
  aging_data: AccountAging[]
  total_overdue: string
  analysis_date: string
}

export interface OverduePaymentAlert {
  contract_id: number
  contract_name: string
  customer_name: string
  stage_name: string
  planned_amount: string
  overdue_days: number
  due_date: string
  owner_name: string
}

export interface ContractRevenueStats {
  contract_id: number
  contract_name: string
  customer_name: string
  total_amount: string
  paid_amount: string
  remaining_amount: string
  payment_progress: number
  signing_date: string
}

export interface PendingPaymentConfirmation {
  id: number
  contract_name: string
  customer_name: string
  stage_name: string
  actual_amount: string
  payment_date: string
  creator_name: string
  created_time: string
  notes: string
}

export interface PaymentConfirmationRequest {
  action: 'confirm' | 'dispute'
  notes?: string
  invoice_application_ids?: number[]
}

export interface DashboardStats {
  pending_invoice_approvals: number
  pending_payment_confirmations: number
  monthly_expected_revenue: string
  confirmed_revenue: string
  overdue_amount: string
}

const financeApi = {
  getAccountAgingAnalysis: async (params?: { start_date?: string; end_date?: string }) => {
    return request.get<AccountAgingAnalysis>('/v1/finance/receivables/aging-analysis', { params })
  },

  getOverduePaymentAlerts: async (params?: { days_overdue_min?: number; days_overdue_max?: number; min_amount?: number; skip?: number; limit?: number }) => {
    return request.get<OverduePaymentAlert[]>('/v1/finance/receivables/overdue-alerts', { params })
  },

  getContractRevenueStats: async (params?: { start_date?: string; end_date?: string; group_by?: string }) => {
    return request.get<ContractRevenueStats[]>('/v1/finance/reports/contract-revenue', { params })
  },

  getPendingPaymentConfirmations: async (params?: { skip?: number; limit?: number }) => {
    return request.get<PendingPaymentConfirmation[]>('/v1/finance/pending-confirmations', { params })
  },

  confirmPayment: (recordId: number, data: PaymentConfirmationRequest) => {
    return request.post(`/api/v1/finance/payment-records/${recordId}/confirm`, data)
  },

  getDashboardStats: async () => {
    return request.get<DashboardStats>('/v1/finance/dashboard-stats')
  }
}

export default financeApi