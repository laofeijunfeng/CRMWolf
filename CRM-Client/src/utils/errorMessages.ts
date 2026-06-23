/**
 * CRMWolf 统一错误提示生成器
 *
 * 设计原则（符合 frontend-design skill）：
 * - 具体 + 方向性（不是 generic + apologetic）
 * - 从用户视角写（"请检查网络"，不是"网络错误"）
 * - 不道歉（专业语气）
 */

import { ElMessage } from 'element-plus'

/**
 * 提取 HTTP 状态码
 */
function extractHttpStatus(message: string): number | null {
  const statusMatch = message.match(/HTTP error: (\d+)/)
  return statusMatch ? parseInt(statusMatch[1]) : null
}

/**
 * ✅ Signature: 统一的错误提示生成（具体化 + 方向性）
 *
 * @param error - 错误对象
 * @param context - 操作上下文（"保存客户"、"加载审批流程"等）
 * @returns 具体化的错误提示文案
 */
export function getErrorMessage(error: unknown, context: string): string {
  const err = error as Error
  const message = err.message || ''

  // HTTP 错误（具体的状态码提示）
  const status = extractHttpStatus(message)
  if (status) {
    if (status === 401) return '登录已过期，请重新登录'
    if (status === 403) return '无权限访问，请联系管理员'
    if (status === 404) return `${context}不存在，请检查后重试`
    if (status === 500) return '服务暂时不可用，请稍后再试'
  }

  // 网络连接错误
  if (message.includes('fetch') || message.includes('network') || message.includes('Network Error')) {
    return '网络连接中断，请检查网络后刷新页面'
  }

  // 超时错误
  if (message.includes('timeout') || message.includes('Timeout')) {
    return '操作超时，请等待片刻后重新尝试'
  }

  // 保存操作错误
  if (context.includes('保存') || context.includes('提交')) {
    return '保存失败，请检查必填项或联系技术支持'
  }

  // 加载操作错误
  if (context.includes('加载') || context.includes('获取')) {
    return `${context}失败，请刷新页面或稍后重试`
  }

  // 删除操作错误
  if (context.includes('删除')) {
    return '删除失败，请确认数据状态或联系管理员'
  }

  // 默认：具体化但不是 generic
  return `${context}遇到问题，请刷新页面或联系支持`
}

/**
 * ✅ Signature: 成功提示生成（具体化，不是 generic）
 *
 * @param action - 操作类型（"保存"、"删除"、"创建"等）
 * @param target - 操作对象（"客户"、"审批流程"等）
 * @returns 具体化的成功提示文案
 */
export function getSuccessMessage(action: string, target?: string): string {
  const actionMap: Record<string, string> = {
    '保存': '已保存',
    '创建': '已创建',
    '删除': '已删除',
    '更新': '已更新',
    '提交': '已提交',
    '审批': '已审批通过'
  }

  const verb = actionMap[action] || action

  if (target) {
    return `${target}${verb}，可以继续下一步操作`
  }

  return `操作${verb}，可以继续下一步`
}

/**
 * ✅ Signature: 空状态提示生成（invitation to act，不是 mood）
 *
 * @param context - 空状态的上下文（"审批节点"、"客户列表"等）
 * @returns Invitation to act 的提示文案
 */
export function getEmptyStateMessage(context: string): { title: string; description: string } {
  const emptyStateMap: Record<string, { title: string; description: string }> = {
    '审批节点': {
      title: '设置审批流程',
      description: '点击添加审批节点，配置审批权限'
    },
    '审批流程': {
      title: '创建审批流程',
      description: '点击新建按钮，定义审批规则'
    },
    '客户列表': {
      title: '添加客户',
      description: '点击新建客户，开始管理销售业务'
    },
    '商机列表': {
      title: '创建商机',
      description: '点击新建商机，跟进销售机会'
    },
    '合同列表': {
      title: '创建合同',
      description: '点击新建合同，管理合同签署'
    },
    '待办事项': {
      title: '添加待办',
      description: '点击创建待办，规划日常工作'
    },
    '跟进记录': {
      title: '记录跟进',
      description: '点击添加跟进，维护客户关系'
    }
  }

  // 返回匹配的提示，或默认 invitation
  return emptyStateMap[context] || {
    title: `开始添加${context}`,
    description: `点击操作按钮，创建新${context}`
  }
}

/**
 * 便捷方法：显示错误提示
 */
export function showError(error: unknown, context: string): void {
  ElMessage.error(getErrorMessage(error, context))
}

/**
 * 便捷方法：显示成功提示
 */
export function showSuccess(action: string, target?: string): void {
  ElMessage.success(getSuccessMessage(action, target))
}