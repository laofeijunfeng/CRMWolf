import { describe, expect, it } from 'vitest'

import { parseAssistantTaskList, AssistantTaskViewSchema } from '@/schemas/assistant-contracts'

const task = {
  public_id: 'ast_123',
  status: 'ACTIVE',
  goal: '记录客户跟进并创建后续任务',
  activity_kind: 'FOLLOW_UP',
  draft: {
    customer: { status: 'ACCEPTED', value: '睿狐科技' },
    content: { status: 'ACCEPTED', value: '讨论部署进展' },
    next_action: { status: 'CANDIDATE', value: '安排下次沟通' },
    next_follow_time: { status: 'MISSING' }
  },
  waiting: null,
  budget_steps: 3,
  budget_max_steps: 50,
  version: 6,
  last_modified_time: '2026-09-28T09:00:00'
}

const activityReceipt = { kind: 'customer_activity', public_id: '123', customer_id: 42 }
const proposalReceipt = { kind: 'follow_up_task_create', public_id: 'fut_123', proposal_key: 'sha256:abc' }

describe('assistant task committed projection', () => {
  it('requires the server-provided empty committed list before any write', () => {
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [] }).committed).toEqual([])
    expect(AssistantTaskViewSchema.safeParse(task).success).toBe(false)
  })

  it('preserves the committed activity receipt and subsequent accepted proposal receipt', () => {
    const afterActivity = AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt] })
    expect(afterActivity.committed).toEqual([activityReceipt])

    const afterProposal = AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt, proposalReceipt] })
    expect(afterProposal.committed).toEqual([activityReceipt, proposalReceipt])
  })

  it('accepts refused proposal receipts without inventing a CRM resource, but rejects unexpected receipt fields', () => {
    const refusal = { kind: 'refused:opportunity_create', proposal_key: 'sha256:def' }
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt, refusal] }).committed).toEqual([activityReceipt, refusal])
    expect(AssistantTaskViewSchema.safeParse({ ...task, committed: [{ ...activityReceipt, extra: 'not-a-receipt' }] }).success).toBe(false)
  })

  it('keeps readable tasks when one historical refusal uses the legacy shape', () => {
    const legacy = { ...task, public_id: 'ast_legacy', committed: [{ kind: 'refused:opportunity' }] }
    const current = { ...task, public_id: 'ast_current', committed: [activityReceipt] }
    const result = parseAssistantTaskList([legacy, current])

    expect(result.tasks.map((item) => item.public_id)).toEqual(['ast_legacy', 'ast_current'])
    expect(result.tasks[0]?.committed).toEqual([{ kind: 'refused:opportunity' }])
    expect(result.tasks[1]?.committed).toEqual([activityReceipt])
    expect(result.skipped).toEqual([])
  })

  it('drops one unreadable historical task without hiding the readable tasks', () => {
    const broken = { ...task, public_id: 'ast_broken', committed: [{ kind: 'customer_activity' }] }
    const current = { ...task, public_id: 'ast_current', committed: [activityReceipt] }

    expect(parseAssistantTaskList([broken, current])).toEqual({
      tasks: [{ ...current, committed: [activityReceipt] }],
      skipped: [0],
    })
  })
})
