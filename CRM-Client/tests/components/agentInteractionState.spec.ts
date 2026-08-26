import { describe, expect, it } from 'vitest'

import {
  compactTaskActionState,
  findCompactTaskAction,
  isCompactTaskCompletionAction,
  optimisticallyCompleteCompactTask,
  restoreCompactTaskAction,
} from '@/components/agent/agentInteractionState'
import { AgentUIEnvelopeSchema } from '@/schemas/agent-contracts'

const message = AgentUIEnvelopeSchema.parse({
  schema_version: 'crm.agent.ui.v1',
  message_id: 1,
  turn_id: 'turn_1',
  role: 'assistant',
  state: 'final',
  blocks: [
    {
      id: 'b_task_1',
      type: 'interaction',
      interaction_id: 'int_task_1',
      interaction_type: 'choice',
      presentation: 'COMPACT_TASK_COMPLETION',
      state: 'ACTIVE',
      prompt: '完成待办一？',
      fields: [],
      options: [{ value: '已完成', label: '标记完成', description: null, disabled: false }],
      selection_mode: 'single',
      min_selections: 1,
      max_selections: 1,
      submit_on_select: true,
      submit_action_id: 'act_task_1',
    },
    {
      id: 'b_task_2',
      type: 'interaction',
      interaction_id: 'int_task_2',
      interaction_type: 'choice',
      presentation: 'COMPACT_TASK_COMPLETION',
      state: 'ACTIVE',
      prompt: '完成待办二？',
      fields: [],
      options: [{ value: '已完成', label: '标记完成', description: null, disabled: false }],
      selection_mode: 'single',
      min_selections: 1,
      max_selections: 1,
      submit_on_select: true,
      submit_action_id: 'act_task_2',
    },
  ],
  suggested_actions: [],
  metadata: { route: 'WORKFLOW' },
})

describe('compact task interaction state', () => {
  it('finds the action reference and reports authoritative action states', () => {
    const action = findCompactTaskAction([message], 'act_task_1')

    expect(action).toEqual({
      actionId: 'act_task_1',
      messageId: 1,
      blockId: 'b_task_1',
    })
    expect(action === undefined ? 'UNKNOWN' : compactTaskActionState([message], action)).toBe('ACTIVE')

    const submitted = optimisticallyCompleteCompactTask([message], 'act_task_1')
    expect(action === undefined ? 'UNKNOWN' : compactTaskActionState(submitted, action)).toBe('SUBMITTED')
    expect(findCompactTaskAction([message], 'act_missing')).toBeUndefined()
    expect(compactTaskActionState([], {
      actionId: 'act_task_1',
      messageId: 1,
      blockId: 'b_task_1',
    })).toBe('UNKNOWN')
  })

  it('recognizes compact task actions and completes only the selected row optimistically', () => {
    expect(isCompactTaskCompletionAction([message], 'act_task_1')).toBe(true)
    expect(isCompactTaskCompletionAction([message], 'act_other')).toBe(false)

    const projected = optimisticallyCompleteCompactTask([message], 'act_task_1')
    expect(projected[0]?.blocks[0]).toMatchObject({ state: 'SUBMITTED', submit_action_id: null })
    expect(projected[0]?.blocks[1]).toMatchObject({ state: 'ACTIVE', submit_action_id: 'act_task_2' })
    expect(message.blocks[0]).toMatchObject({ state: 'ACTIVE', submit_action_id: 'act_task_1' })
  })


  it('restores only the failed action without overwriting another concurrent completion', () => {
    const firstAndSecondCompleted = optimisticallyCompleteCompactTask(
      optimisticallyCompleteCompactTask([message], 'act_task_1'),
      'act_task_2',
    )

    const restored = restoreCompactTaskAction(firstAndSecondCompleted, [message], 'act_task_1')

    expect(restored[0]?.blocks[0]).toMatchObject({
      state: 'ACTIVE',
      submit_action_id: 'act_task_1',
    })
    expect(restored[0]?.blocks[1]).toMatchObject({
      state: 'SUBMITTED',
      submit_action_id: null,
    })
    expect(firstAndSecondCompleted[0]?.blocks[0]).toMatchObject({
      state: 'SUBMITTED',
      submit_action_id: null,
    })
  })
})
