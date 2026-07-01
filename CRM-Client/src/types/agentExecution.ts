/**
 * Agent Execution Log 类型定义
 *
 * 用于将 SSE 事件流映射为业务化的执行步骤展示
 */

/**
 * 执行步骤类型枚举
 */
export enum ExecutionStepType {
  /** ReAct 循环开始 */
  REACT_START = 'react_start',

  /** 轮次开始 */
  ROUND_START = 'round_start',

  /** 工具调用 */
  TOOL_CALL = 'tool_call',

  /** 工具结果 */
  TOOL_RESULT = 'tool_result',

  /** 等待用户输入 */
  WAITING_FOR_USER = 'waiting_for_user',

  /** 消歧请求 */
  DISAMBIGUATION_REQUIRED = 'disambiguation_required',

  /** 等待确认 */
  AWAITING_CONFIRMATION = 'awaiting_confirmation',

  /** 轮次完成 */
  ROUND_COMPLETED = 'round_completed',

  /** ReAct 循环完成 */
  REACT_COMPLETE = 'react_complete',

  /** 达到最大轮数 */
  MAX_ROUNDS_REACHED = 'max_rounds_reached',

  /** 错误 */
  ERROR = 'error'
}

/**
 * 执行步骤接口
 *
 * 定义单个执行步骤的数据结构
 */
export interface ExecutionStep {
  /** 步骤唯一标识 */
  id: string

  /** 步骤类型 */
  type: ExecutionStepType

  /** 业务化标题 */
  title: string

  /**
   * 步骤描述
   *
   * TOOL_CALL: AI 推理过程（如"用户想跟进光大证券，需要先找到客户..."）
   * TOOL_RESULT: 执行结果摘要（如"找到 5 个客户"）
   */
  description: string

  /** 时间戳 */
  timestamp: Date

  /** 轮次编号（可选） */
  round?: number

  /** 工具名称（可选） */
  tool?: string

  /** 工具参数（可选） */
  params?: Record<string, unknown>

  /**
   * 业务化参数描述（可选）
   *
   * 需求文档 4.4：业务参数显示格式化的工具参数
   * 如："正在搜索："光大证券""
   *
   * 仅 TOOL_CALL 步骤使用，与 description（AI 推理过程）分离
   */
  businessParams?: string

  /** 执行结果（可选） */
  result?: unknown

  /** 是否成功（可选） */
  success?: boolean

  /** 错误信息（可选） */
  error?: string

  /** 相关数据（可选） */
  data?: unknown

  /** ReAct 会话 ID（可选） */
  sessionId?: string

  // ===== V2 新增字段（向后兼容） =====
  /** Inline 显示文本（单行合并） */
  inline_text?: string

  /** AI 推理过程 */
  thinking?: string

  /** 业务化摘要 */
  summary?: string

  /** 摘要参数（简化版） */
  summary_params?: Record<string, string>

  /** 详情参数（完整版） */
  detail_params?: Record<string, { value: string; isEntity?: boolean }>

  /** 确认类型：disambiguation | confirmation | info_gap */
  confirmationType?: 'disambiguation' | 'confirmation' | 'info_gap'

  /** 风险等级：low | medium | high */
  riskLevel?: 'low' | 'medium' | 'high'

  /** 候选列表（V2 格式） */
  options?: {
    id: number
    name: string
    entity_info_inline?: string
    entity_info_detail?: Record<string, string>
  }[]
}

/**
 * Execution Log 状态接口
 *
 * 定义整个执行日志的状态管理
 */
export interface ExecutionLogState {
  /** 执行步骤列表 */
  steps: ExecutionStep[]

  /** 当前轮次 */
  currentRound: number

  /** 最大轮次 */
  maxRounds: number

  /** 是否正在执行 */
  isExecuting: boolean

  /** 是否已完成 */
  isCompleted: boolean

  /** 是否有错误 */
  hasError: boolean

  /** ReAct 会话 ID */
  sessionId?: string
}

/**
 * 工具名称业务化映射表
 *
 * 将技术工具名称映射为用户友好的业务表达
 */
export const ToolTitleMap: Record<string, string> = {
  search_customer: '查找客户信息',
  create_customer: '创建客户',
  update_customer: '更新客户信息',
  delete_customer: '删除客户',
  search_opportunity: '查找商机信息',
  create_opportunity: '创建商机',
  update_opportunity: '更新商机',
  delete_opportunity: '删除商机',
  search_lead: '查找线索信息',
  create_lead: '创建线索',
  update_lead: '更新线索',
  delete_lead: '删除线索',
  search_contract: '查找合同信息',
  create_contract: '创建合同',
  update_contract: '更新合同',
  delete_contract: '删除合同',
  // ===== 新增：匹配后端工具名称（follow_up_customer/follow_up_lead） =====
  follow_up_customer: '创建跟进记录',
  follow_up_lead: '创建线索跟进',
  // ===== 保留旧映射（兼容性） =====
  create_follow_up: '创建跟进记录',
  update_follow_up: '更新跟进记录',
  delete_follow_up: '删除跟进记录',
  send_email: '发送邮件',
  schedule_meeting: '安排会议',
  generate_report: '生成报告',
  // ===== 新增：其他可能使用的工具名称 =====
  set_reminder: '设置提醒',
  win_opportunity: '标记商机赢单',
  lose_opportunity: '标记商机输单',
  update_stage: '更新商机阶段'
}

/**
 * 获取工具的业务化标题
 *
 * @param toolName - 工具名称
 * @returns 业务化标题
 */
export function getBusinessTitle(toolName: string): string {
  return ToolTitleMap[toolName] ?? toolName
}

/**
 * 格式化业务参数
 *
 * @param params - 工具参数
 * @param businessTitle - 业务化标题
 * @returns 业务化的参数描述
 */
export function formatBusinessParams(
  params: Record<string, unknown>,
  businessTitle: string
): string {
  // 根据不同的业务场景格式化参数
  if (businessTitle.includes('查找') || businessTitle.includes('搜索')) {
    // 搜索场景：提取关键词
    const keyword = params['keyword'] ?? params['name'] ?? params['query']
    if (keyword !== undefined && keyword !== null) {
      return `正在搜索："${String(keyword)}"`
    }
  }

  if (businessTitle.includes('创建')) {
    // 创建场景：提取主要字段
    const name = params['name'] ?? params['customer_name'] ?? params['title']
    if (name !== undefined && name !== null) {
      return `正在创建："${String(name)}"`
    }
  }

  if (businessTitle.includes('更新') || businessTitle.includes('修改')) {
    // 更新场景：提取目标实体和更新字段
    const targetName = params['name'] ?? params['customer_name'] ?? params['title']
    if (targetName !== undefined && targetName !== null) {
      return `正在更新："${String(targetName)}"`
    }
  }

  if (businessTitle.includes('删除')) {
    // 删除场景：提取目标实体
    const targetName = params['name'] ?? params['customer_name'] ?? params['title']
    if (targetName !== undefined && targetName !== null) {
      return `正在删除："${String(targetName)}"`
    }
  }

  // 默认：返回通用描述
  return businessTitle
}

/**
 * 获取错误解决建议
 *
 * 将错误信息映射为业务友好的解决建议（需求文档 5.2）
 *
 * @param tool - 工具名称
 * @param errorMessage - 错误信息
 * @returns 业务化的解决建议
 */
export function getSuggestion(tool: string, errorMessage: string): string {
  // 未找到/不存在场景
  if (errorMessage.includes('未找到') || errorMessage.includes('不存在')) {
    if (tool.includes('customer')) return '建议：请提供更精确的客户名称'
    if (tool.includes('opportunity')) return '建议：请先创建商机'
    if (tool.includes('lead')) return '建议：请先创建线索'
    if (tool.includes('contract')) return '建议：请先创建合同'
    return '建议：请确认目标是否存在'
  }

  // 权限场景
  if (errorMessage.includes('权限') || errorMessage.includes('无权限')) {
    return '建议：请联系管理员获取权限'
  }

  // 重复/已存在场景
  if (errorMessage.includes('已存在') || errorMessage.includes('重复')) {
    return '建议：请使用不同的名称或标识'
  }

  // 格式错误场景
  if (errorMessage.includes('格式') || errorMessage.includes('无效')) {
    return '建议：请检查输入格式是否正确'
  }

  // 默认建议
  return '建议：请检查输入信息是否正确'
}