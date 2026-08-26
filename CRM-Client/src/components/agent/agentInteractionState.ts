import type { AgentUIBlock, AgentUIEnvelope } from '@/schemas/agent-contracts'

type InteractionBlock = Extract<AgentUIBlock, { type: 'interaction' }>

export interface CompactTaskActionRef {
  actionId: string
  messageId: number
  blockId: string
}

export type CompactTaskActionState = 'ACTIVE' | 'SUBMITTED' | 'UNKNOWN'

export const findCompactTaskAction = (
  messages: AgentUIEnvelope[],
  actionId: string,
): CompactTaskActionRef | undefined => {
  for (const message of messages) {
    const block = message.blocks.find(candidate => (
      candidate.type === 'interaction'
      && candidate.presentation === 'COMPACT_TASK_COMPLETION'
      && candidate.submit_action_id === actionId
    ))
    if (block !== undefined) {
      return { actionId, messageId: message.message_id, blockId: block.id }
    }
  }
  return undefined
}

export const compactTaskActionState = (
  messages: AgentUIEnvelope[],
  action: CompactTaskActionRef,
): CompactTaskActionState => {
  const message = messages.find(candidate => candidate.message_id === action.messageId)
  const block = message?.blocks.find(candidate => candidate.id === action.blockId)
  if (block?.type !== 'interaction' || block.presentation !== 'COMPACT_TASK_COMPLETION') return 'UNKNOWN'
  if (block.state === 'SUBMITTED') return 'SUBMITTED'
  if (block.state === 'ACTIVE' && block.submit_action_id === action.actionId) return 'ACTIVE'
  return 'UNKNOWN'
}

export const isCompactTaskCompletionAction = (
  messages: AgentUIEnvelope[],
  actionId: string,
): boolean => messages.some(message => message.blocks.some(block => (
  block.type === 'interaction'
  && block.presentation === 'COMPACT_TASK_COMPLETION'
  && block.submit_action_id === actionId
)))

export const optimisticallyCompleteCompactTask = (
  messages: AgentUIEnvelope[],
  actionId: string,
): AgentUIEnvelope[] => messages.map(message => ({
  ...message,
  blocks: message.blocks.map(block => (
    block.type === 'interaction'
    && block.presentation === 'COMPACT_TASK_COMPLETION'
    && block.submit_action_id === actionId
      ? { ...block, state: 'SUBMITTED' as const, submit_action_id: null }
      : block
  )),
}))


export const restoreCompactTaskAction = (
  currentMessages: AgentUIEnvelope[],
  previousMessages: AgentUIEnvelope[],
  actionId: string,
): AgentUIEnvelope[] => {
  let previousBlock: InteractionBlock | undefined
  let previousMessageId: number | undefined

  for (const message of previousMessages) {
    const block = message.blocks.find(candidate => (
      candidate.type === 'interaction'
      && candidate.presentation === 'COMPACT_TASK_COMPLETION'
      && candidate.submit_action_id === actionId
    ))
    if (block !== undefined && block.type === 'interaction') {
      previousBlock = block
      previousMessageId = message.message_id
      break
    }
  }

  if (previousBlock === undefined || previousMessageId === undefined) return currentMessages

  return currentMessages.map(message => (
    message.message_id !== previousMessageId
      ? message
      : {
          ...message,
          blocks: message.blocks.map(block => (
            block.id === previousBlock.id
            && block.type === 'interaction'
            && block.presentation === 'COMPACT_TASK_COMPLETION'
              ? previousBlock
              : block
          )),
        }
  ))
}
