import request from '@/utils/request'

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

export interface ProcurementMethodResponse extends ProcurementMethod {}

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

export interface ProcurementStageTemplateResponse extends ProcurementStageTemplate {}

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

const procurementApi = {
  getProcurementMethods: (params?: ProcurementMethodListParams) => {
    return request.get<ProcurementMethodResponse[]>('/api/v1/procurement-methods/', { params })
  },

  getProcurementMethod: (methodId: number) => {
    return request.get<ProcurementMethodWithStages>(`/api/v1/procurement-methods/${methodId}`)
  },

  createProcurementMethod: (data: ProcurementMethodCreate) => {
    return request.post<ProcurementMethodResponse>('/api/v1/procurement-methods/', data)
  },

  updateProcurementMethod: (methodId: number, data: ProcurementMethodUpdate) => {
    return request.put<ProcurementMethodResponse>(`/api/v1/procurement-methods/${methodId}`, data)
  },

  fullUpdateProcurementMethod: (methodId: number, data: ProcurementMethodWithStagesUpdate) => {
    return request.put<ProcurementMethodWithStages>(`/api/v1/procurement-methods/${methodId}/full`, data)
  },

  batchUpdateStages: (methodId: number, data: BatchUpdateStagesRequest) => {
    return request.put<ProcurementStageTemplateResponse[]>(`/api/v1/procurement-methods/${methodId}/stages`, data)
  },

  deleteProcurementMethod: (methodId: number) => {
    return request.delete<{ message: string }>(`/api/v1/procurement-methods/${methodId}`)
  },

  getStageTemplates: (params: StageTemplateListParams) => {
    return request.get<ProcurementStageTemplateResponse[]>('/api/v1/procurement-stage-templates/', { params })
  },

  getStageTemplate: (templateId: number) => {
    return request.get<ProcurementStageTemplateResponse>(`/api/v1/procurement-stage-templates/${templateId}`)
  },

  createStageTemplate: (data: ProcurementStageTemplateCreate) => {
    return request.post<ProcurementStageTemplateResponse>('/api/v1/procurement-stage-templates/', data)
  },

  updateStageTemplate: (templateId: number, data: ProcurementStageTemplateUpdate) => {
    return request.put<ProcurementStageTemplateResponse>(`/api/v1/procurement-stage-templates/${templateId}`, data)
  },

  deleteStageTemplate: (templateId: number) => {
    return request.delete<{ message: string }>(`/api/v1/procurement-stage-templates/${templateId}`)
  },

  setOpportunityProcurementMethod: (opportunityId: number, procurementMethodId: number) => {
    return request.post<{ message: string }>(`/api/v1/opportunities/${opportunityId}/set-procurement-method`, {
      procurement_method_id: procurementMethodId
    })
  },

  getStageTemplateChangeLogs: (templateId: number) => {
    return request.get<any[]>(`/api/v1/procurement-stage-templates/${templateId}/change-logs`)
  },

  setCustomerDefaultProcurementMethod: (customerId: number, procurementMethodId: number | null) => {
    return request.post<{ message: string }>(`/api/v1/customers/${customerId}/set-default-procurement-method`, {
      procurement_method_id: procurementMethodId
    })
  },

  getCustomerDefaultProcurementMethod: (customerId: number) => {
    return request.get<ProcurementMethodResponse | null>(`/api/v1/customers/${customerId}/default-procurement-method`)
  },

  assessTemplateChange: (templateId: number) => {
    return request.get<{ opportunity_count: number; active_opportunity_count: number }>(`/api/v1/procurement-admin/assess-template-change/${templateId}`)
  },

  batchMigrateOpportunities: (sourceMethodId: number, targetMethodId: number, opportunityIds?: number[]) => {
    return request.post<{ message: string; migrated_count: number; failed_count: number }>('/api/v1/procurement-admin/batch-migrate-opportunities', {
      source_method_id: sourceMethodId,
      target_method_id: targetMethodId,
      opportunity_ids: opportunityIds
    })
  },

  rollbackTemplate: (templateId: number, logId: number) => {
    return request.post<{ message: string }>(`/api/v1/procurement-admin/rollback-template/${templateId}`, {
      log_id: logId
    })
  },

  getActiveOpportunities: (stageTemplateId: number) => {
    return request.get<any[]>(`/api/v1/procurement-admin/active-opportunities/${stageTemplateId}`)
  },

  getOpportunityCurrentStage: (opportunityId: number) => {
    return request.get<OpportunityStageSnapshot>(`/api/v1/opportunities/${opportunityId}/current-stage`)
  },

  getOpportunityStageHistory: (opportunityId: number) => {
    return request.get<OpportunityStageSnapshot[]>(`/api/v1/opportunities/${opportunityId}/stage-history`)
  },

  getAvailableStages: (opportunityId: number) => {
    return request.get<ProcurementStageTemplate[]>(`/api/v1/opportunities/${opportunityId}/available-stages`)
  },

  advanceStage: (opportunityId: number, data: AdvanceStageRequest) => {
    return request.post<OpportunityStageSnapshot>(`/api/v1/opportunities/${opportunityId}/advance-stage`, data)
  },

  getOpportunityProcurementStages: (opportunityId: number) => {
    return request.get<OpportunityProcurementStageInfo[]>(`/api/v1/opportunities/${opportunityId}/procurement-stages`)
  },

  moveOpportunityStage: (opportunityId: number, data: OpportunityMoveStageRequest) => {
    return request.post<any>(`/api/v1/opportunities/${opportunityId}/move-stage`, data)
  },

  getProcurementMethodOptions: () => {
    return request.get<ProcurementMethodOption[]>('/api/v1/procurement-methods/options')
  }
}

export interface OpportunityStageSnapshot {
  id: number
  opportunity_id: number
  procurement_stage_template_id: number
  stage_code: string
  stage_name: string
  win_probability: number
  entered_at: string
  exited_at: string | null
  created_at: string
}

export interface AdvanceStageRequest {
  target_stage_id: number
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
