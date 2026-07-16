import { toast } from 'vue-sonner'

function extractHttpStatus(message: string): number | null {
  const statusMatch = message.match(/HTTP error: (\d+)/)
  return statusMatch === null ? null : Number.parseInt(statusMatch[1], 10)
}

export function getErrorMessage(error: unknown, context: string): string {
  const message = error instanceof Error ? error.message : ''
  const status = extractHttpStatus(message)

  if (status === 401) return '登录已过期，请重新登录'
  if (status === 403) return '无权限访问，请联系管理员'
  if (status === 404) return `${context}不存在，请检查后重试`
  if (status === 500) return '服务暂时不可用，请稍后再试'

  if (message.includes('fetch') || message.includes('network') || message.includes('Network Error')) {
    return '网络连接中断，请检查网络后刷新页面'
  }

  if (message.includes('timeout') || message.includes('Timeout')) {
    return '操作超时，请等待片刻后重新尝试'
  }

  if (context.includes('保存') || context.includes('提交')) {
    return '保存失败，请检查必填项或联系技术支持'
  }

  if (context.includes('加载') || context.includes('获取')) {
    return `${context}失败，请刷新页面或稍后重试`
  }

  if (context.includes('删除')) {
    return '删除失败，请确认数据状态或联系管理员'
  }

  return `${context}遇到问题，请刷新页面或联系支持`
}

export function getSuccessMessage(action: string, target?: string): string {
  const actionMap: Record<string, string> = {
    保存: '已保存',
    创建: '已创建',
    删除: '已删除',
    更新: '已更新',
    提交: '已提交',
    审批: '已审批通过',
  }
  const verb = actionMap[action] ?? action
  return target !== undefined && target.length > 0
    ? `${target}${verb}，可以继续下一步操作`
    : `操作${verb}，可以继续下一步`
}

export function getEmptyStateMessage(context: string): { title: string; description: string } {
  const emptyStateMap: Record<string, { title: string; description: string }> = {
    审批节点: { title: '设置审批流程', description: '点击添加审批节点，配置审批权限' },
    审批流程: { title: '创建审批流程', description: '点击新建按钮，定义审批规则' },
    客户列表: { title: '添加客户', description: '点击新建客户，开始管理销售业务' },
    商机列表: { title: '创建商机', description: '点击新建商机，跟进销售机会' },
    合同列表: { title: '创建合同', description: '点击新建合同，管理合同签署' },
    待办事项: { title: '添加待办', description: '点击创建待办，规划日常工作' },
    跟进记录: { title: '记录跟进', description: '点击添加跟进，维护客户关系' },
  }

  return emptyStateMap[context] ?? {
    title: `开始添加${context}`,
    description: `点击操作按钮，创建新${context}`,
  }
}

export function showError(error: unknown, context: string): void {
  toast.error(getErrorMessage(error, context))
}

export function showSuccess(action: string, target?: string): void {
  toast.success(getSuccessMessage(action, target))
}
