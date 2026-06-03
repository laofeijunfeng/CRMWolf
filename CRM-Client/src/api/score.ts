/**
 * 热力值 API 接口
 *
 * 提供热力值查询和权重配置管理的接口
 */
import request from '@/utils/request'

// ============== 热力值查询接口 ==============

/**
 * 热力值响应类型
 */
export interface ScoreResponse {
  score: number | null
  score_level: string | null
  updated_at: string | null
  details: ScoreDetail[]
}

/**
 * 热力值明细类型
 */
export interface ScoreDetail {
  id: number
  factor_key: string
  factor_name: string
  weight_value: number
  actual_value: string | null
  score_change: number
  reason: string | null
  calculated_time: string
}

/**
 * 热力值等级信息
 */
export interface ScoreLevelInfo {
  score: number
  level: string
  icon: string
  color: string
}

/**
 * 获取线索热力值
 */
export function getLeadScore(leadId: number): Promise<ScoreResponse> {
  return request.get(`/v1/scores/lead/${leadId}`)
}

/**
 * 获取客户热力值
 */
export function getCustomerScore(customerId: number): Promise<ScoreResponse> {
  return request.get(`/v1/scores/customer/${customerId}`)
}

/**
 * 刷新线索热力值
 */
export function refreshLeadScore(leadId: number): Promise<ScoreResponse> {
  return request.post(`/v1/scores/lead/${leadId}/refresh`)
}

/**
 * 刷新客户热力值
 */
export function refreshCustomerScore(customerId: number): Promise<ScoreResponse> {
  return request.post(`/v1/scores/customer/${customerId}/refresh`)
}

/**
 * 批量刷新团队热力值
 */
export function batchRefreshTeamScores(): Promise<{
  message: string
  leads_updated: number
  customers_updated: number
}> {
  return request.post('/v1/scores/batch-refresh/team')
}

// ============== 权重配置接口 ==============

/**
 * 权重配置类型
 */
export interface WeightConfig {
  id: number
  team_id: number | null
  module_type: string
  factor_key: string
  factor_name: string
  weight_value: number
  is_enabled: number
  condition_rules: string | null
  sort_order: number
  created_by: string
  created_time: string
  updated_by: string | null
  updated_time: string
}

/**
 * 权重配置列表响应
 */
export interface WeightConfigListResponse {
  module_type: string
  weights: WeightConfig[]
  is_system_default: boolean
}

/**
 * 权重配置更新请求
 */
export interface WeightConfigUpdateRequest {
  weight_value?: number
  is_enabled?: number
  condition_rules?: string
}

/**
 * 获取权重配置列表
 */
export function getWeightConfigs(moduleType: 'LEAD' | 'CUSTOMER'): Promise<WeightConfigListResponse> {
  return request.get(`/v1/score-weights/${moduleType}`)
}

/**
 * 更新权重配置
 */
export function updateWeightConfig(
  weightId: number,
  data: WeightConfigUpdateRequest
): Promise<WeightConfig> {
  return request.put(`/v1/score-weights/${weightId}`, data)
}

/**
 * 复制系统默认配置到团队
 */
export function copyFromSystem(
  moduleType?: 'LEAD' | 'CUSTOMER'
): Promise<{
  message: string
  count: number
  module_types: string[]
}> {
  const params = moduleType ? { module_type: moduleType } : {}
  return request.post('/v1/score-weights/copy-from-system', null, { params })
}

/**
 * 删除团队权重配置（恢复使用系统默认）
 */
export function deleteTeamWeights(
  moduleType: 'LEAD' | 'CUSTOMER'
): Promise<{
  message: string
  deleted_count: number
}> {
  return request.delete(`/v1/score-weights/${moduleType}`)
}

// ============== 工具函数 ==============

/**
 * 根据分数获取图标
 */
export function getScoreIcon(score: number | null): string {
  if (score === null) return '❓'
  if (score >= 80) return '🔥'
  if (score >= 60) return '⚡'
  if (score >= 40) return '✅'
  return '❄️'
}

/**
 * 根据分数获取颜色
 */
export function getScoreColor(score: number | null): string {
  if (score === null) return '#d9d9d9'
  if (score >= 80) return '#ff4d4f'
  if (score >= 60) return '#faad14'
  if (score >= 40) return '#52c41a'
  return '#d9d9d9'
}

/**
 * 根据分数获取等级文字
 */
export function getScoreLevel(score: number | null): string {
  if (score === null) return '未知'
  if (score >= 80) return '高'
  if (score >= 60) return '中'
  if (score >= 40) return '低'
  return '危险'
}

/**
 * 根据分数获取等级信息
 */
export function getScoreLevelInfo(score: number | null): ScoreLevelInfo {
  return {
    score: score ?? 0,
    level: getScoreLevel(score),
    icon: getScoreIcon(score),
    color: getScoreColor(score)
  }
}

/**
 * 格式化热力值明细为提示文字
 */
export function formatScoreDetails(details: ScoreDetail[]): string {
  if (!details || details.length === 0) {
    return '暂无计算明细'
  }

  const lines = details.map((d) => {
    const sign = d.score_change >= 0 ? '+' : ''
    return `${d.factor_name}: ${sign}${d.score_change}分 (${d.reason || ''})`
  })

  return lines.join('\n')
}