import request from '@/utils/request'
import {
  ApprovalDetailSchema,
  MessageResponseSchema,
  type ApprovalDetail,
  type MessageResponse
} from '@/schemas/approval'

export type ApprovalAction = 'APPROVE' | 'REJECT' | 'ROLLBACK'

const approvalApi = {
  getContractApprovalDetail: async (contractId: number): Promise<ApprovalDetail> => {
    return ApprovalDetailSchema.parse(await request.get(`/v1/approvals/contracts/${contractId}/detail`))
  },

  submitContractApproval: async (contractId: number, data?: { comment?: string }): Promise<ApprovalDetail> => {
    return ApprovalDetailSchema.parse(await request.post(`/v1/approvals/contracts/${contractId}/submit`, data ?? {}))
  },

  approveContract: async (contractId: number, data: { action: ApprovalAction; comment?: string }): Promise<ApprovalDetail> => {
    return ApprovalDetailSchema.parse(await request.post(`/v1/approvals/contracts/${contractId}/approve`, data))
  },

  cancelContractApproval: async (contractId: number): Promise<MessageResponse> => {
    return MessageResponseSchema.parse(await request.post(`/v1/approvals/contracts/${contractId}/cancel`))
  }
}

export default approvalApi
