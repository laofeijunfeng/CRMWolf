import request from '@/utils/request'

export type LicenseApplicationStatus = 'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED' | 'ISSUED'
export type LicenseType = 'TRIAL' | 'OFFICIAL'

export interface LicenseApplicationCreate {
  customer_id: number
  deployment_info_id?: number | null
  contract_id?: number | null
  license_type: LicenseType
  expiry_date: string
}

export interface LicenseApplicationUpdate {
  deployment_info_id?: number | null
  contract_id?: number | null
  expiry_date?: string | null
}

export interface LicenseApplicationApprove {
  license_code: string
}

export interface LicenseApplicationResponse {
  id: number
  team_id: number
  application_number: string
  customer_id: number
  deployment_info_id: number | null
  contract_id: number | null
  expiry_date: string
  license_type: string
  license_code: string | null
  status: LicenseApplicationStatus
  applicant_id: string
  approver_id: string | null
  approved_time: string | null
  created_time: string
  last_modified_time: string
  customer_name?: string | null
  deployment_name?: string | null
  contract_name?: string | null
}

const licenseApplicationApi = {
  createApplication: (data: LicenseApplicationCreate) => {
    return request.post<LicenseApplicationResponse>('/v1/license-applications/', data)
  },

  getApplications: (customerId: number) => {
    return request.get<LicenseApplicationResponse[]>('/v1/license-applications/', {
      params: { customer_id: customerId }
    })
  },

  getApplication: (applicationId: number) => {
    return request.get<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}`)
  },

  updateApplication: (applicationId: number, data: LicenseApplicationUpdate) => {
    return request.put<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}`, data)
  },

  deleteApplication: (applicationId: number) => {
    return request.delete<void>(`/v1/license-applications/${applicationId}`)
  },

  submitApplication: (applicationId: number) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/submit`)
  },

  approveApplication: (applicationId: number, data: LicenseApplicationApprove) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/approve`, data)
  },

  rejectApplication: (applicationId: number) => {
    return request.post<LicenseApplicationResponse>(`/v1/license-applications/${applicationId}/reject`)
  }
}

export default licenseApplicationApi