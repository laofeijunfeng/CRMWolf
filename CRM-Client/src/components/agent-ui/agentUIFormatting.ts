import type { AgentUIValue } from '@/schemas/agent-contracts'

export function formatAgentUIValue(item: AgentUIValue): string {
  if (item.display !== undefined && item.display !== null && item.display.length > 0) {
    return item.display
  }
  if (item.value === null) return '-'
  if (item.kind === 'boolean' && typeof item.value === 'boolean') {
    return item.value ? '是' : '否'
  }
  if (item.kind === 'money' && typeof item.value === 'number') {
    const currency = item.currency ?? 'CNY'
    try {
      return new Intl.NumberFormat('zh-CN', { style: 'currency', currency }).format(item.value)
    } catch {
      return `${currency} ${item.value.toLocaleString('zh-CN')}`
    }
  }
  if (item.kind === 'number' && typeof item.value === 'number') {
    return item.value.toLocaleString('zh-CN')
  }
  if ((item.kind === 'date' || item.kind === 'datetime') && typeof item.value === 'string') {
    const parsed = new Date(item.value)
    if (!Number.isNaN(parsed.getTime())) {
      return item.kind === 'date'
        ? parsed.toLocaleDateString('zh-CN')
        : parsed.toLocaleString('zh-CN', { hour12: false })
    }
  }
  return String(item.value)
}
