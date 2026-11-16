import request from '@/utils/request'
import {
  AccountAgingAnalysisSchema,
  ContractRevenueResponseSchema,
  DashboardStatsSchema,
  OverduePaymentAlertsResponseSchema,
  PaymentConfirmationResponseSchema,
  PendingPaymentConfirmationsResponseSchema,
  type AccountAgingAnalysis,
  type ContractRevenueResponse,
  type DashboardStats,
  type OverduePaymentAlertsResponse,
  type PaymentConfirmationResponse,
  type PendingPaymentConfirmationsResponse
} from '@/schemas/finance'

export type {
  AccountAging,
  AccountAgingAnalysis,
  OverduePaymentAlert,
  ContractRevenueStats,
  PendingPaymentConfirmation,
  DashboardStats
} from '@/schemas/finance'

export interface PaymentConfirmationRequest {
  action: 'confirm' | 'dispute'
  notes?: string
  invoice_application_ids?: number[]
}

const financeApi = {
  getAccountAgingAnalysis: async (params?: { start_date?: string; end_date?: string }): Promise<AccountAgingAnalysis> =>
    AccountAgingAnalysisSchema.parse(await request.get('/v1/finance/receivables/aging-analysis', { params })),

  getOverduePaymentAlerts: async (params?: { days_overdue_min?: number; days_overdue_max?: number; min_amount?: number; skip?: number; limit?: number }): Promise<OverduePaymentAlertsResponse> =>
    OverduePaymentAlertsResponseSchema.parse(await request.get('/v1/finance/receivables/overdue-alerts', { params })),

  getContractRevenueStats: async (params?: { start_date?: string; end_date?: string; group_by?: string }): Promise<ContractRevenueResponse> =>
    ContractRevenueResponseSchema.parse(await request.get('/v1/finance/reports/contract-revenue', { params })),

  getPendingPaymentConfirmations: async (params?: { skip?: number; limit?: number }): Promise<PendingPaymentConfirmationsResponse> =>
    PendingPaymentConfirmationsResponseSchema.parse(await request.get('/v1/finance/pending-confirmations', { params })),

  confirmPayment: async (recordId: number, data: PaymentConfirmationRequest): Promise<PaymentConfirmationResponse> =>
    PaymentConfirmationResponseSchema.parse(await request.post(`/v1/finance/payment-records/${recordId}/confirm`, data)),

  getDashboardStats: async (): Promise<DashboardStats> =>
    DashboardStatsSchema.parse(await request.get('/v1/finance/dashboard-stats'))
}

export default financeApi
