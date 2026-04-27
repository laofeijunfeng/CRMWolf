import request from '@/utils/request'

export type ApprovalAction = 'APPROVE' | 'REJECT' | 'ROLLBACK'

const approvalApi = {
  getContractApprovalDetail: (contractId: number) => {
    return request.get(`/api/v1/approvals/contracts/${contractId}/detail`)
  },

  submitContractApproval: (contractId: number, data?: { comment?: string }) => {
    return request.post(`/api/v1/approvals/contracts/${contractId}/submit`, data || {})
  },

  approveContract: (contractId: number, data: { action: ApprovalAction; comment?: string }) => {
    return request.post(`/api/v1/approvals/contracts/${contractId}/approve`, data)
  },

  cancelContractApproval: (contractId: number) => {
    return request.post(`/api/v1/approvals/contracts/${contractId}/cancel`)
  }
}

export default approvalApi
