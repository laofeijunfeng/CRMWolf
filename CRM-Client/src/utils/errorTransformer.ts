/**
 * 错误信息转换器
 * 将技术报错（Pydantic validation errors）转换为易懂的业务提示
 */

/**
 * 字段中文映射
 */
export const FIELD_LABELS: Record<string, string> = {
  // 商机相关
  total_amount: '预计成交金额',
  license_type: '授权模式',
  purchase_type: '采购类型',
  expected_closing_date: '预计成交日期',
  user_count: '采购用户数',
  subscription_years: '订阅年限',
  opportunity_name: '商机名称',

  // 客户相关
  customer_name: '客户名称',
  account_name: '客户名称',

  // 合同相关
  contract_name: '合同名称',
  contract_amount: '合同金额',
  signed_date: '签订日期',

  // 联系人相关
  contact_name: '联系人姓名',
  contact_phone: '联系电话',

  // 线索相关
  lead_name: '线索名称',

  // 回款相关
  planned_amount: '计划金额',
  actual_amount: '实际金额',
  payment_date: '付款日期',

  // 发票相关
  invoice_amount: '开票金额',
  invoice_type: '发票类型',

  // 跟进相关
  content: '跟进内容',
  method: '跟进方式',
  next_follow_time: '下次跟进时间',
  next_action: '下一步动作',

  // 通用
  owner_id: '负责人',
  team_id: '团队',
  remarks: '备注'
}

/**
 * 工具名称中文映射
 */
export const TOOL_LABELS: Record<string, string> = {
  follow_up_customer: '创建跟进记录',
  follow_up_lead: '创建跟进记录',
  create_opportunity: '创建商机',
  win_opportunity: '标记赢单',
  lose_opportunity: '标记输单',
  update_opportunity_stage: '推进商机阶段',
  create_contract: '创建合同',
  query_contracts: '查询合同',
  get_contract_detail: '获取合同详情',
  update_contract_status: '更新合同状态',
  create_payment_plan: '创建回款计划',
  create_payment_record: '登记回款',
  query_payment_records: '查询回款记录',
  confirm_payment: '确认回款',
  create_invoice_application: '申请开票',
  query_invoice_applications: '查询开票申请',
  get_invoice_application_detail: '获取开票申请详情',
  get_entity_context: '获取上下文',
  ask_user: '询问用户'
}

/**
 * 转换后的错误信息结构
 */
export interface TransformedError {
  title: string           // 业务标题
  summary: string         // 概要描述
  missingFields: string[] // 缺失字段列表（中文）
  suggestion: string      // 庐议操作
  originalError: string   // 原始错误（用于查看详情）
}

/**
 * 转换 Pydantic validation error 为业务提示
 *
 * @param error 原始错误信息
 * @param toolName 工具名称（可选，用于生成标题）
 * @returns 转换后的错误信息
 */
export function transformValidationError(
  error: string,
  toolName?: string
): TransformedError {
  // 解析 Pydantic 错误格式
  // 示例: "4 validation errors for OpportunityCreate total_amount Field required..."

  const missingFields: string[] = []
  const errorLines = error.split('\n')

  // 提取 Field required 的字段名
  for (const line of errorLines) {
    const fieldRequiredMatch = line.match(/(\w+)\s+Field required/)
    if (fieldRequiredMatch) {
      const fieldName = fieldRequiredMatch[1]
      const chineseName = FIELD_LABELS[fieldName] || fieldName
      missingFields.push(chineseName)
    }

    // 其他错误类型
    const validationMatch = line.match(/(\w+)\s+validation error/)
    if (validationMatch && !missingFields.includes(validationMatch[1])) {
      const fieldName = validationMatch[1]
      const chineseName = FIELD_LABELS[fieldName] || fieldName
      missingFields.push(chineseName)
    }
  }

  // 生成标题
  const toolLabel = toolName ? TOOL_LABELS[toolName] || toolName : '操作'
  const title = `${toolLabel}受阻`

  // 生成概要
  let summary = '缺少必要信息，无法继续执行'
  if (missingFields.length === 1) {
    summary = `缺少「${missingFields[0]}」`
  } else if (missingFields.length > 1) {
    summary = `缺少 ${missingFields.length} 项必要信息`
  }

  // 生成建议
  let suggestion = ''
  if (missingFields.length > 0) {
    suggestion = `请补充：${missingFields.join('、')}`
  } else {
    suggestion = '请检查输入信息是否正确'
  }

  return {
    title,
    summary,
    missingFields,
    suggestion,
    originalError: error
  }
}

/**
 * 转换通用错误信息
 *
 * @param error 原始错误信息
 * @param toolName 工具名称（可选）
 * @returns 转换后的错误信息
 */
export function transformGenericError(
  error: string,
  toolName?: string
): TransformedError {
  const toolLabel = toolName ? TOOL_LABELS[toolName] || toolName : '操作'

  // 检查是否是 validation error
  if (error.includes('validation error') || error.includes('Field required')) {
    return transformValidationError(error, toolName)
  }

  // 其他错误类型
  let summary = error

  // 简化常见错误
  if (error.includes('not found') || error.includes('不存在')) {
    summary = '找不到指定的记录'
  } else if (error.includes('permission') || error.includes('权限')) {
    summary = '没有操作权限'
  } else if (error.includes('timeout') || error.includes('超时')) {
    summary = '操作超时，请稍后重试'
  } else if (error.includes('network') || error.includes('网络')) {
    summary = '网络异常，请检查连接'
  }

  return {
    title: `${toolLabel}失败`,
    summary,
    missingFields: [],
    suggestion: '请稍后重试，或联系管理员',
    originalError: error
  }
}

/**
 * 转换执行结果为状态卡片数据
 *
 * @param result 工具执行结果
 * @returns 状态卡片所需数据
 */
export function transformToolResult(result: {
  tool: string
  success: boolean
  message?: string
}): {
  type: 'success' | 'warning' | 'error'
  title: string
  summary: string
  missingFields?: string[]
} {
  const toolLabel = TOOL_LABELS[result.tool] || result.tool

  if (result.success) {
    return {
      type: 'success',
      title: `${toolLabel}成功`,
      summary: result.message || '操作已完成'
    }
  }

  // 解析失败原因
  if (result.message?.includes('validation error') || result.message?.includes('Field required')) {
    const transformed = transformValidationError(result.message, result.tool)
    return {
      type: 'warning',
      title: transformed.title,
      summary: transformed.summary,
      missingFields: transformed.missingFields
    }
  }

  return {
    type: 'error',
    title: `${toolLabel}失败`,
    summary: result.message || '操作未成功'
  }
}