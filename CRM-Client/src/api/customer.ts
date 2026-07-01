import request from '@/utils/request'

export interface CustomerIndustryOption {
  value: string
  label: string
}

export interface ConvertLeadToCustomer {
  lead_id: number
  account_name?: string | null
  address?: string | null
  default_procurement_method_id?: number | null
}

export interface ConvertResponse {
  customer_id: number
  contact_id: number
  message: string
}

export interface CustomerCreate {
  account_name: string
  city: string
  address?: string | null
  company_scale?: string | null
  source?: string | null
  default_procurement_method_id?: number | null
}

export interface CustomerUpdate {
  account_name?: string | null
  city?: string | null
  address?: string | null
  company_scale?: string | null
  source?: string | null
  default_procurement_method_id?: number | null
  // 档案字段（支持手动编辑）
  company_background?: string | null
  company_website?: string | null
  main_business?: string | null
  project_background?: string | null
}

export type CustomerStatus = 0 | 1 | 2 | 3

export interface CustomerStatusUpdate {
  status: CustomerStatus
}

export interface UserBasicInfo {
  id: number
  name: string
  feishu_open_id: string
}

export interface ProcurementMethodInfo {
  id: number
  code: string
  name: string
  is_active: number
}

export interface CustomerIndustryInfo {
  code: string
  name: string  // 完整路径名称，如 "金融/证券"
  primary_code?: string | null  // 一级行业编码
  primary_name?: string | null  // 一级行业名称
  secondary_name?: string | null  // 二级行业名称（如果是二级行业）
}

export interface CustomerResponse {
  id: number
  account_name: string
  industry: string | null
  industry_info?: CustomerIndustryInfo | null
  city: string
  address: string | null
  company_scale: string | null
  source: string | null
  status: CustomerStatus
  owner_id: string | null
  source_lead_id: number | null
  default_procurement_method_id: number | null
  default_procurement_method_info?: ProcurementMethodInfo | null
  loss_reason: string | null
  return_reason: string | null
  returned_time: string | null
  creator_id: string
  created_time: string
  last_modified_time: string
  version: number
  owner_info?: UserBasicInfo
  creator_info?: UserBasicInfo
}

export interface ContactResponse {
  id: number
  customer_id: number
  name: string
  gender: number | null
  position: string | null
  is_decision_maker: boolean
  mobile: string
  email: string | null
  wechat_id: string | null
  remark: string | null
  reports_to: number | null
  is_primary: boolean
  created_time: string
}

export interface CustomerDetailResponse {
  id: number
  account_name: string
  industry: string | null
  industry_info?: CustomerIndustryInfo | null
  city: string
  address: string | null
  company_scale: string | null
  source: string | null
  status: CustomerStatus
  owner_id: string
  source_lead_id: number | null
  default_procurement_method_id: number | null
  default_procurement_method_info?: ProcurementMethodInfo | null
  creator_id: string
  created_time: string
  last_modified_time: string
  version: number
  contacts: ContactResponse[]
  owner_info?: UserBasicInfo
  creator_info?: UserBasicInfo
  // 档案字段
  company_background: string | null
  company_website: string | null
  main_business: string | null
  similar_customers: string | null  // JSON string
  project_background: string | null
  profile_status: string | null  // PENDING | GENERATING | COMPLETED | FAILED
  profile_generated_time: string | null
  profile_error_message: string | null
}

export interface ContactCreate {
  name: string
  gender?: string | null
  position?: string | null
  is_decision_maker?: boolean
  mobile: string
  email?: string | null
  wechat_id?: string | null
  remark?: string | null
  reports_to?: number | null
}

export interface ContactUpdate {
  name?: string | null
  gender?: string | null
  position?: string | null
  is_decision_maker?: boolean | null
  mobile?: string | null
  email?: string | null
  wechat_id?: string | null
  remark?: string | null
  reports_to?: number | null
}

export interface CustomerStatistics {
  total_customers: number
  by_status: {
    status: number
    count: number
  }[]
  by_industry: {
    industry: string | null
    count: number
  }[]
  by_city: {
    city: string
    count: number
  }[]
}

export interface CustomerTrend {
  date: string
  count: number
}

export interface CustomerQueryParams {
  skip?: number
  limit?: number
  status?: CustomerStatus
  industry?: string
  city?: string
  owner_id?: string
  keyword?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export type ReturnReasonEnum = '丢单' | '无意向' | '信息错误' | '长期未跟进' | '预算不足' | '其他'

export interface CustomerReturnRequest {
  return_reason: ReturnReasonEnum
  detailed_reason: string
}

export interface CustomerReturnResponse {
  customer_id: number
  previous_owner: string
  returned_time: string
  return_reason: string
  message: string
}

export interface CustomerClaimRequest {
  owner_id: string
}

export interface CustomerLoseRequest {
  loss_reason: string
}

export interface OwnerFilterOption {
  owner_id: string
  owner_name: string
  is_me: boolean
}

export interface PublicCustomerQueryParams {
  skip?: number
  limit?: number
  status?: CustomerStatus
  city?: string
  keyword?: string
  order_by?: string
  order_dir?: 'asc' | 'desc'
}

export interface ContractListResponse {
  id: number
  contract_number: string
  contract_name: string
  customer_id: number
  opportunity_id: number | null
  signing_contact_id: number | null
  user_count: number
  total_amount: string
  license_type: string
  license_type_name?: string
  subscription_years: number | null
  standard_unit_price: string
  status: string
  status_info?: {
    name: string
  }
  signing_date: string | null
  effective_date: string | null
  expiry_date: string | null
  created_time: string
  last_modified_time: string
  customer_name?: string
  opportunity_name?: string
  owner_info?: UserBasicInfo
}

export interface PaymentPlanResponse {
  id: number
  stage_name: string
  planned_amount: number
  due_date: string
  notes: string | null
  contract_id: number
  status: string
  created_time: string
  last_modified_time: string
  paid_amount: number | null
  remaining_amount: number | null
  contract_name?: string
  customer_name?: string
  opportunity_name?: string
}

export interface InvoiceApplicationResponse {
  id: number
  application_number: string
  customer_id: number
  contract_id: number
  opportunity_id: number
  payment_plan_id: number
  invoice_title_id: number
  invoice_amount: string
  invoice_type: string
  payment_record_id: number | null
  status: string
  approval_status: string
  rejection_reason: string | null
  applicant_id: string
  created_time: string
  last_modified_time: string
  contract_name?: string
  contract_number?: string
  stage_name?: string
  planned_amount?: number
  applicant_name?: string
}

const customerApi = {
  convertLeadToCustomer: (data: ConvertLeadToCustomer) => {
    return request.post<ConvertResponse>('/v1/customers/convert-from-lead', data)
  },

  createCustomer: (data: CustomerCreate) => {
    return request.post<CustomerResponse>('/v1/customers/', data)
  },

  getCustomers: (params?: CustomerQueryParams) => {
    return request.get<CustomerResponse[]>('/v1/customers/', { params })
  },

  getCustomerDetail: (customerId: number) => {
    return request.get<CustomerDetailResponse>(`/v1/customers/${customerId}`)
  },

  updateCustomer: (customerId: number, data: CustomerUpdate) => {
    return request.put<CustomerResponse>(`/v1/customers/${customerId}`, data)
  },

  updateCustomerStatus: (customerId: number, data: CustomerStatusUpdate) => {
    return request.patch<CustomerResponse>(`/v1/customers/${customerId}/status`, data)
  },

  markAsLost: (customerId: number, data: CustomerLoseRequest) => {
    return request.patch<CustomerResponse>(`/v1/customers/${customerId}/lose`, data)
  },

  deleteCustomer: (customerId: number) => {
    return request.delete<{ message: string }>(`/v1/customers/${customerId}`)
  },

  returnToPool: (customerId: number, data: CustomerReturnRequest) => {
    return request.post<CustomerReturnResponse>(`/v1/customers/${customerId}/return-to-pool`, data)
  },

  claimCustomer: (customerId: number, data: CustomerClaimRequest) => {
    return request.post<CustomerResponse>(`/v1/customers/${customerId}/claim`, data)
  },

  getPublicCustomers: (params?: PublicCustomerQueryParams) => {
    return request.get<CustomerResponse[]>('/v1/customers/public/list', { params })
  },

  getOwnerFilterOptions: () => {
    return request.get<OwnerFilterOption[]>('/v1/filter-options/owners')
  },

  getIndustryOptions: () => {
    return request.get<CustomerIndustryOption[]>('/v1/customers/industries')
  },

  createContact: (customerId: number, data: ContactCreate) => {
    return request.post<ContactResponse>(`/v1/customers/${customerId}/contacts`, data)
  },

  getContacts: (customerId: number) => {
    return request.get<ContactResponse[]>(`/v1/customers/${customerId}/contacts`)
  },

  updateContact: (contactId: number, data: ContactUpdate) => {
    return request.put<ContactResponse>(`/v1/customers/contacts/${contactId}`, data)
  },

  setPrimaryContact: (contactId: number) => {
    return request.patch<ContactResponse>(`/v1/customers/contacts/${contactId}/set-primary`)
  },

  deleteContact: (contactId: number) => {
    return request.delete<{ message: string }>(`/v1/customers/contacts/${contactId}`)
  },

  getStatistics: () => {
    return request.get<CustomerStatistics>('/v1/customers/statistics/summary')
  },

  getTrend: (days = 30) => {
    return request.get<CustomerTrend[]>('/v1/customers/statistics/trend', {
      params: { days }
    })
  },

  getContracts: (customerId: number, params?: { status?: string | null; skip?: number; limit?: number }) => {
    return request.get<ContractListResponse[]>(`/v1/customers/${customerId}/contracts`, { params })
  },

  getPaymentPlans: (customerId: number, params?: { status?: string | null; skip?: number; limit?: number }) => {
    return request.get<PaymentPlanResponse[]>(`/v1/customers/${customerId}/payment-plans`, { params })
  },

  getInvoices: (customerId: number, params?: { status?: string | null; skip?: number; limit?: number }) => {
    return request.get<InvoiceApplicationResponse[]>(`/v1/customers/${customerId}/invoices`, { params })
  },

  regenerateProfile: (customerId: number) => {
    return request.post<{ message: string }>(`/v1/customers/${customerId}/regenerate-profile`)
  }
}

export default customerApi
