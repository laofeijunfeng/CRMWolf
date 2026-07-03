import request from '@/utils/request'

export interface ApprovalNode {
  id?: number
  node_name: string
  node_code: string
  node_order: number
  description?: string
  approve_role: string
  is_required: number
}

export interface ApprovalFlow {
  id?: number
  flow_name: string
  flow_code: string
  description?: string
  min_amount?: number | null
  max_amount?: number | null
  license_type?: string | null
  business_type: 'CONTRACT' | 'PAYMENT' | 'INVOICE' // 业务类型：合同/回款/发票
  is_active?: number
  created_time?: string
  last_modified_time?: string
  nodes?: ApprovalNode[]
}

export interface ApprovalFlowDetail extends ApprovalFlow {
  nodes: ApprovalNode[]
}

const approvalFlowApi = {
  getApprovalFlows: (params?: { skip?: number; limit?: number; is_active?: boolean | null }) => {
    return request.get('/v1/approvals/flows', { params })
  },

  getApprovalFlowDetail: (flowId: number) => {
    return request.get(`/v1/approvals/flows/${flowId}`)
  },

  createApprovalFlow: (data: ApprovalFlow) => {
    return request.post('/v1/approvals/flows', data)
  },

  updateApprovalFlow: (flowId: number, data: Partial<ApprovalFlow>) => {
    return request.put(`/v1/approvals/flows/${flowId}`, data)
  },

  deleteApprovalFlow: (flowId: number) => {
    return request.delete(`/v1/approvals/flows/${flowId}`)
  }
}

export default approvalFlowApi
