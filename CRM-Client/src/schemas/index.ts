/**
 * Zod Schema - Index
 *
 * @description Schema 导出入口
 */

// Common
export * from './common'

// Customer
export * from './customer'

// Lead
export * from './lead'

// Opportunity
export * from './opportunity'

// Contract
export {
  ContractStatusSchema,
  ContractStatusMap,
  ContractResponseSchema,
  ContractCreateSchema,
  ContractUpdateSchema,
  ContractApprovalRequestSchema,
  type ContractResponse,
  type ContractCreate,
  type ContractUpdate,
  type ContractApprovalRequest,
  ContractListResponseSchema as ContractPaginatedListResponseSchema,
  type ContractListResponse as ContractPaginatedListResponse
} from './contract'

// Payment
export {
  PaymentStatusSchema,
  PaymentStatusMap,
  PaymentResponseSchema,
  PaymentListResponseSchema,
  PaymentCreateSchema,
  type PaymentResponse,
  type PaymentListResponse,
  type PaymentCreate,
  PaymentPlanResponseSchema as ContractPaymentPlanResponseSchema,
  type PaymentPlanResponse as ContractPaymentPlanResponse
} from './payment'

// Invoice
export * from './invoice'
