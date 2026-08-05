/* eslint-disable crmwolf/require-zod-schema */
import request from '@/utils/request'
import { ApiResponseSchema } from '@/schemas/common'

export interface ProcurementMethod {
  id: number
  code: string
  name: string
  is_active: number
  sort_order: number
  description?: string
  created_time: string
  updated_time: string
}

export interface ProcurementMethodOption {
  id: number
  code: string
  name: string
}

export interface ProcurementMethodCreate {
  code: string
  name: string
  sort_order: number
  description?: string
}

export interface ProcurementMethodUpdate {
  name?: string
  is_active?: number
  sort_order?: number
  description?: string
}

export type ProcurementMethodResponse = ProcurementMethod

export interface ProcurementMethodWithStages extends ProcurementMethod {
  stage_templates: ProcurementStageTemplate[]
}

export interface ProcurementStageTemplate {
  id: number
  procurement_method_id: number
  stage_code: string
  stage_name: string
  win_probability: number
  sort_order: number
  is_default: number
  can_skip: number
  is_active: number
  description?: string
  created_time: string
  updated_time: string
}

export interface ProcurementStageTemplateCreate {
  procurement_method_id: number
  stage_code: string
  stage_name: string
  win_probability: number
  sort_order: number
  is_default: number
  can_skip: number
  description?: string
}

export interface ProcurementStageTemplateUpdate {
  stage_name?: string
  win_probability?: number
  sort_order?: number
  is_default?: number
  can_skip?: number
  is_active?: number
  description?: string
}

export type ProcurementStageTemplateResponse = ProcurementStageTemplate

export interface StageTemplateBatchUpdate {
  id?: number | null
  template_code: string
  stage_name: string
  win_probability: number
  sort_order: number
  is_default_start?: number
  can_skip?: number
  description?: string | null
  mark_delete?: boolean
}

export interface ProcurementMethodWithStagesUpdate {
  method?: ProcurementMethodUpdate | null
  stages: StageTemplateBatchUpdate[]
}

export interface BatchUpdateStagesRequest {
  stages: StageTemplateBatchUpdate[]
}

export interface ProcurementMethodListParams {
  is_active?: number
  page?: number
  page_size?: number
}

export interface StageTemplateListParams {
  procurement_method_id: number
}

export interface StageTemplateChangeLog {
  id: number
  stage_template_id: number
  change_type: string
  old_values?: Record<string, unknown> | string | null
  new_values?: Record<string, unknown> | string | null
  operator_id?: string | null
  created_time: string
}

export interface ActiveOpportunitiesByStageResponse {
  stage_template_id: number
  active_opportunities: Record<string, unknown>[]
  count: number
}

const ProcurementMethodListResponseSchema = ApiResponseSchema<ProcurementMethodResponse[]>()
const ProcurementMethodResponseSchema = ApiResponseSchema<ProcurementMethodResponse>()
const ProcurementMethodWithStagesSchema = ApiResponseSchema<ProcurementMethodWithStages>()
const ProcurementStageTemplateListResponseSchema = ApiResponseSchema<ProcurementStageTemplateResponse[]>()
const ProcurementStageTemplateResponseSchema = ApiResponseSchema<ProcurementStageTemplateResponse>()
const MessageResponseSchema = ApiResponseSchema<{ message: string }>()
const TemplateChangeLogListSchema = ApiResponseSchema<StageTemplateChangeLog[]>()
const TemplateChangeAssessmentSchema = ApiResponseSchema<{ opportunity_count: number; active_opportunity_count: number }>()
const BatchMigrateResponseSchema = ApiResponseSchema<{ message: string; migrated_count: number; failed_count: number }>()
const ActiveOpportunitiesByStageResponseSchema = ApiResponseSchema<ActiveOpportunitiesByStageResponse>()
const OpportunityStageSnapshotSchema = ApiResponseSchema<OpportunityStageSnapshot>()
const OpportunityStageSnapshotListSchema = ApiResponseSchema<OpportunityStageSnapshot[]>()
const ProcurementStageTemplateListSchema = ApiResponseSchema<ProcurementStageTemplate[]>()
const OpportunityProcurementStageInfoListSchema = ApiResponseSchema<OpportunityProcurementStageInfo[]>()
const OpportunityMoveStageResponseSchema = ApiResponseSchema<Record<string, unknown>>()
const ProcurementMethodOptionListSchema = ApiResponseSchema<ProcurementMethodOption[]>()
const NullableProcurementMethodResponseSchema = ApiResponseSchema<ProcurementMethodResponse | null>()

const procurementApi = {
  getProcurementMethods: async (params?: ProcurementMethodListParams): Promise<ProcurementMethodResponse[]> => {
    return ProcurementMethodListResponseSchema.parse(await request.get<ProcurementMethodResponse[]>('/v1/procurement-methods/', { params }))
  },

  getProcurementMethod: async (methodId: number): Promise<ProcurementMethodWithStages> => {
    return ProcurementMethodWithStagesSchema.parse(await request.get<ProcurementMethodWithStages>(`/v1/procurement-methods/${methodId}`))
  },

  createProcurementMethod: async (data: ProcurementMethodCreate): Promise<ProcurementMethodResponse> => {
    return ProcurementMethodResponseSchema.parse(await request.post<ProcurementMethodResponse>('/v1/procurement-methods/', data))
  },

  updateProcurementMethod: async (methodId: number, data: ProcurementMethodUpdate): Promise<ProcurementMethodResponse> => {
    return ProcurementMethodResponseSchema.parse(await request.put<ProcurementMethodResponse>(`/v1/procurement-methods/${methodId}`, data))
  },

  fullUpdateProcurementMethod: async (methodId: number, data: ProcurementMethodWithStagesUpdate): Promise<ProcurementMethodWithStages> => {
    return ProcurementMethodWithStagesSchema.parse(await request.put<ProcurementMethodWithStages>(`/v1/procurement-methods/${methodId}/full`, data))
  },

  batchUpdateStages: async (methodId: number, data: BatchUpdateStagesRequest): Promise<ProcurementStageTemplateResponse[]> => {
    return ProcurementStageTemplateListResponseSchema.parse(await request.put<ProcurementStageTemplateResponse[]>(`/v1/procurement-methods/${methodId}/stages`, data))
  },

  deleteProcurementMethod: async (methodId: number): Promise<{ message: string }> => {
    return MessageResponseSchema.parse(await request.delete<{ message: string }>(`/v1/procurement-methods/${methodId}`))
  },

  getStageTemplates: async (params: StageTemplateListParams): Promise<ProcurementStageTemplateResponse[]> => {
    return ProcurementStageTemplateListResponseSchema.parse(await request.get<ProcurementStageTemplateResponse[]>('/v1/procurement-stage-templates/', { params }))
  },

  getStageTemplate: async (templateId: number): Promise<ProcurementStageTemplateResponse> => {
    return ProcurementStageTemplateResponseSchema.parse(await request.get<ProcurementStageTemplateResponse>(`/v1/procurement-stage-templates/${templateId}`))
  },

  createStageTemplate: async (data: ProcurementStageTemplateCreate): Promise<ProcurementStageTemplateResponse> => {
    return ProcurementStageTemplateResponseSchema.parse(await request.post<ProcurementStageTemplateResponse>('/v1/procurement-stage-templates/', data))
  },

  updateStageTemplate: async (templateId: number, data: ProcurementStageTemplateUpdate): Promise<ProcurementStageTemplateResponse> => {
    return ProcurementStageTemplateResponseSchema.parse(await request.put<ProcurementStageTemplateResponse>(`/v1/procurement-stage-templates/${templateId}`, data))
  },

  deleteStageTemplate: async (templateId: number): Promise<{ message: string }> => {
    return MessageResponseSchema.parse(await request.delete<{ message: string }>(`/v1/procurement-stage-templates/${templateId}`))
  },

  setOpportunityProcurementMethod: async (opportunityId: string, procurementMethodId: number): Promise<{ message: string }> => {
    return MessageResponseSchema.parse(await request.post<{ message: string }>(`/v1/opportunities/${opportunityId}/set-procurement-method`, {
      procurement_method_id: procurementMethodId
    }))
  },

  getStageTemplateChangeLogs: async (templateId: number): Promise<StageTemplateChangeLog[]> => {
    return TemplateChangeLogListSchema.parse(await request.get<StageTemplateChangeLog[]>(`/v1/procurement-stage-templates/${templateId}/change-logs`))
  },

  setCustomerDefaultProcurementMethod: async (customerId: string, procurementMethodId: number | null): Promise<{ message: string }> => {
    return MessageResponseSchema.parse(await request.post<{ message: string }>(`/v1/customers/${customerId}/set-default-procurement-method`, {
      procurement_method_id: procurementMethodId
    }))
  },

  getCustomerDefaultProcurementMethod: async (customerId: string): Promise<ProcurementMethodResponse | null> => {
    return NullableProcurementMethodResponseSchema.parse(await request.get<ProcurementMethodResponse | null>(`/v1/customers/${customerId}/default-procurement-method`))
  },

  assessTemplateChange: async (templateId: number): Promise<{ opportunity_count: number; active_opportunity_count: number }> => {
    return TemplateChangeAssessmentSchema.parse(await request.get<{ opportunity_count: number; active_opportunity_count: number }>(`/v1/procurement-admin/assess-template-change/${templateId}`))
  },

  batchMigrateOpportunities: async (sourceMethodId: number, targetMethodId: number, opportunityIds?: number[]): Promise<{ message: string; migrated_count: number; failed_count: number }> => {
    return BatchMigrateResponseSchema.parse(await request.post<{ message: string; migrated_count: number; failed_count: number }>('/v1/procurement-admin/batch-migrate-opportunities', {
      source_method_id: sourceMethodId,
      target_method_id: targetMethodId,
      opportunity_ids: opportunityIds
    }))
  },

  rollbackTemplate: async (templateId: number, logId: number): Promise<{ message: string }> => {
    return MessageResponseSchema.parse(await request.post<{ message: string }>(`/v1/procurement-admin/rollback-template/${templateId}`, {
      log_id: logId
    }))
  },

  getActiveOpportunities: async (stageTemplateId: number): Promise<ActiveOpportunitiesByStageResponse> => {
    return ActiveOpportunitiesByStageResponseSchema.parse(await request.get<ActiveOpportunitiesByStageResponse>(`/v1/procurement-admin/active-opportunities/${stageTemplateId}`))
  },

  getOpportunityCurrentStage: async (opportunityId: string): Promise<OpportunityStageSnapshot> => {
    return OpportunityStageSnapshotSchema.parse(await request.get<OpportunityStageSnapshot>(`/v1/opportunities/${opportunityId}/current-stage`))
  },

  getOpportunityStageHistory: async (opportunityId: string): Promise<OpportunityStageSnapshot[]> => {
    return OpportunityStageSnapshotListSchema.parse(await request.get<OpportunityStageSnapshot[]>(`/v1/opportunities/${opportunityId}/stage-history`))
  },

  getAvailableStages: async (opportunityId: string): Promise<ProcurementStageTemplate[]> => {
    return ProcurementStageTemplateListSchema.parse(await request.get<ProcurementStageTemplate[]>(`/v1/opportunities/${opportunityId}/available-stages`))
  },

  getOpportunityProcurementStages: async (opportunityId: string): Promise<OpportunityProcurementStageInfo[]> => {
    return OpportunityProcurementStageInfoListSchema.parse(await request.get<OpportunityProcurementStageInfo[]>(`/v1/opportunities/${opportunityId}/procurement-stages`))
  },

  moveOpportunityStage: async (opportunityId: string, data: OpportunityMoveStageRequest): Promise<Record<string, unknown>> => {
    return OpportunityMoveStageResponseSchema.parse(await request.post<Record<string, unknown>>(`/v1/opportunities/${opportunityId}/move-stage`, data))
  },

  getProcurementMethodOptions: async (): Promise<ProcurementMethodOption[]> => {
    return ProcurementMethodOptionListSchema.parse(await request.get<ProcurementMethodOption[]>('/v1/procurement-methods/options'))
  }
}

export interface OpportunityStageSnapshot {
  id: number
  opportunity_id: string
  procurement_stage_template_id: number
  stage_code: string
  stage_name: string
  win_probability: number
  entered_at: string
  exited_at: string | null
  created_at: string
}

export interface OpportunityProcurementStageInfo {
  id: number
  stage_name: string
  win_probability: number
  sort_order: number
  is_current: boolean
  is_default_start: boolean
  can_skip: boolean
}

export interface OpportunityMoveStageRequest {
  stage_template_id: number
}

export default procurementApi
