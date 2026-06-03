/**
 * AI Skill 配置管理 API
 */
import request from '@/utils/request'

// Skill 类型
export interface Skill {
  id: number
  skill_name: string
  display_name: string
  description: string
  module_type: string
  is_active: number
  sort_order: number
  action_count: number
  created_time?: string
  updated_time?: string
  actions?: SkillAction[]
}

// Skill Action 类型
export interface SkillAction {
  id: number
  skill_id: number
  action_name: string
  display_name: string
  description: string
  handler_type: string
  handler_config: Record<string, any>
  required_params: string[]
  optional_params: string[]
  permission_code: string
  result_template?: string
  is_active: number
  sort_order: number
}

// CRUD 映射类型
export interface CRUDMapping {
  id: number
  mapping_name: string
  crud_module: string
  crud_instance_name: string
  model_class: string
  schema_create_class?: string
  schema_update_class?: string
  owner_field?: string
  status_field?: string
  name_field?: string
}

// Enum 映射类型
export interface EnumMapping {
  id: number
  enum_name: string
  display_name: string
  enum_class: string
  values: Record<string, string>
}

// 创建 Skill 参数
export interface SkillCreate {
  skill_name: string
  display_name: string
  description: string
  module_type: string
  is_active?: number
  sort_order?: number
}

// 创建 Action 参数
export interface SkillActionCreate {
  action_name: string
  display_name: string
  description: string
  handler_type: string
  handler_config: Record<string, any>
  required_params?: string[]
  optional_params?: string[]
  permission_code: string
  result_template?: string
  is_active?: number
  sort_order?: number
}

// API 函数
export const aiSkillsApi = {
  // Skill 管理
  getSkills: (params?: { module_type?: string; is_active?: number }) =>
    request.get('/v1/ai/skills', { params }),

  getSkill: (skillId: number) =>
    request.get(`/api/v1/ai/skills/${skillId}`),

  createSkill: (data: SkillCreate) =>
    request.post('/v1/ai/skills', data),

  updateSkill: (skillId: number, data: Partial<SkillCreate>) =>
    request.put(`/api/v1/ai/skills/${skillId}`, data),

  deleteSkill: (skillId: number) =>
    request.delete(`/api/v1/ai/skills/${skillId}`),

  // Action 管理
  getActions: (skillId: number) =>
    request.get(`/api/v1/ai/skills/${skillId}/actions`),

  createAction: (skillId: number, data: SkillActionCreate) =>
    request.post(`/api/v1/ai/skills/${skillId}/actions`, data),

  updateAction: (skillId: number, actionId: number, data: Partial<SkillActionCreate>) =>
    request.put(`/api/v1/ai/skills/${skillId}/actions/${actionId}`, data),

  deleteAction: (skillId: number, actionId: number) =>
    request.delete(`/api/v1/ai/skills/${skillId}/actions/${actionId}`),

  // CRUD 映射管理
  getCRUDMappings: () =>
    request.get('/v1/ai/skills/crud-mappings'),

  createCRUDMapping: (data: Partial<CRUDMapping>) =>
    request.post('/v1/ai/skills/crud-mappings', data),

  // Enum 映射管理
  getEnumMappings: () =>
    request.get('/v1/ai/skills/enum-mappings'),

  createEnumMapping: (data: Partial<EnumMapping>) =>
    request.post('/v1/ai/skills/enum-mappings', data),

  // Handler 类型列表
  getHandlerTypes: () =>
    request.get('/v1/ai/skills/handler-types'),

  // AI 辅助生成 - 分析需求（POST SSE 流式）
  analyzeSkill: async (
    requirement: string,
    onEvent: (event: AnalyzeEvent) => void
  ): Promise<void> => {
    const token = localStorage.getItem('token')
    const response = await fetch(
      `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/skills/analyze`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ requirement })
      }
    )

    if (!response.ok) {
      if (response.status === 403) {
        onEvent({ event: 'error', message: '无权限使用 AI Skill 生成功能' })
      } else {
        onEvent({ event: 'error', message: `请求失败: ${response.status}` })
      }
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      onEvent({ event: 'error', message: '无法读取响应' })
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            onEvent(data)
          } catch {
            continue
          }
        }
      }
    }
  },

  // AI 辅助生成 - 生成配置（使用 fetch POST SSE）
  generateSkill: async (
    configPrompt: string,
    onEvent: (event: GenerateEvent) => void
  ): Promise<void> => {
    const token = localStorage.getItem('token')
    const response = await fetch(
      `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/ai/skills/generate`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ config_prompt: configPrompt })
      }
    )

    if (!response.ok) {
      onEvent({ event: 'error', message: `请求失败: ${response.status}` })
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      onEvent({ event: 'error', message: '无法读取响应' })
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            onEvent(data)
          } catch {
            continue
          }
        }
      }
    }
  }
}

// SSE 事件类型
export interface AnalyzeEvent {
  event: 'progress' | 'result' | 'error'
  message?: string
  supported?: boolean
  operation_type?: 'create_skill' | 'add_action'
  skill_name?: string
  skill_display_name?: string
  existing_actions?: string[]
  missing_actions?: string[]
  config_prompt?: string
}

export interface GenerateEvent {
  event: 'progress' | 'skill' | 'action' | 'skip' | 'complete' | 'error'
  message?: string
  operation_type?: 'create_skill' | 'add_action'
  skill_id?: number
  skill_name?: string
  display_name?: string
  action_id?: number
  action_name?: string
  handler_type?: string
  action_count?: number
  skip_count?: number
}