import request from '@/utils/request'
import {
  WorkflowDetailSchema,
  WorkflowSummarySchema,
  type WorkflowDetail,
  type WorkflowDsl,
  type WorkflowSummary,
} from '@/schemas/workflow'

export type { WorkflowDetail, WorkflowDsl, WorkflowSummary } from '@/schemas/workflow'

export interface WorkflowCreateInput {
  name: string
  description?: string | null
  dsl: WorkflowDsl
}

export interface WorkflowUpdateInput extends WorkflowCreateInput {
  expected_last_modified_time: string
}

export type WorkflowStatus = WorkflowDetail['status']

export interface WorkflowStatusUpdateInput {
  status: WorkflowStatus
}

const workflowApi = {
  list: async (): Promise<WorkflowSummary[]> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get('/v1/workflows')
    return WorkflowSummarySchema.array().parse(response)
  },

  create: async (data: WorkflowCreateInput): Promise<WorkflowDetail> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.post('/v1/workflows', data)
    return WorkflowDetailSchema.parse(response)
  },

  get: async (workflowId: number): Promise<WorkflowDetail> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.get(`/v1/workflows/${workflowId}`)
    return WorkflowDetailSchema.parse(response)
  },

  update: async (workflowId: number, data: WorkflowUpdateInput): Promise<WorkflowDetail> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.put(`/v1/workflows/${workflowId}`, data)
    return WorkflowDetailSchema.parse(response)
  },

  remove: async (workflowId: number): Promise<void> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    await request.delete(`/v1/workflows/${workflowId}`)
  },

  updateStatus: async (workflowId: number, data: WorkflowStatusUpdateInput): Promise<WorkflowDetail> => {
    // eslint-disable-next-line crmwolf/require-zod-schema
    const response: unknown = await request.put(`/v1/workflows/${workflowId}/status`, data)
    return WorkflowDetailSchema.parse(response)
  },
}

export default workflowApi
