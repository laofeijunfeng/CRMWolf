import type { AgentUIBlock } from '@/schemas/agent-contracts'

export type ProcessBlock = Extract<AgentUIBlock, { type: 'process' }>
export type ProcessItem = ProcessBlock['items'][number]
export type ProcessItemStatus = ProcessItem['status']

/** 步骤行右侧的元信息：耗时、评分或状态词；tone 只给需要变色的状态词。 */
export interface ProcessItemMeta {
  text: string
  tone?: 'danger' | 'brand'
}

/** 宿主没有实时数据时，状态词由服务端给定的步骤状态推出。 */
export const processStatusLabel = (status: ProcessItemStatus): string => ({
  PENDING: '待执行',
  RUNNING: '执行中',
  COMPLETED: '已完成',
  WAITING: '等待中',
  FAILED: '失败',
  CANCELLED: '已取消',
  SKIPPED: '已跳过',
})[status]
