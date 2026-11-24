import { describe, expect, it } from 'vitest'

import { AssistantTaskViewSchema } from '@/schemas/assistant-contracts'

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
const preview = {
  customer_name: '虚构星河科技', activity_kind: 'OTHER_FOLLOW_UP', title: '部署沟通', summary: '确认部署计划',
  content_json: {}, source_content: '确认部署计划', score: 85, score_reason: '要素完整',
  next_action: null, next_follow_time: null, next_follow_time_text: ''
}
const candidate = {
  kind: 'follow_up_task_create', key: 'task-key', evidence_quote: '发送方案', payload: { action: '发送方案' },
  activity_id: 1, customer_id: 42, source_revision: 1, action_id: 'fictional-action'
}
const confirmation = (field: string, confirmation_payload: unknown) => ({
  type: 'CONFIRMATION', field, question_id: 'q-current', action_id: 'action-current', expected_version: 6,
  prompt: '确认这项变更？', fingerprint: null, candidates: [], confirmation_payload
})

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

  it('preserves historical activity receipts without inventing a customer binding', () => {
    const historical = { kind: 'customer_activity', public_id: 'act_fictional_history' }
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [historical] }).committed).toEqual([historical])
  })

  it('accepts the legacy refusal shape without inventing a resource', () => {
    const legacy = { ...task, public_id: 'ast_legacy', committed: [{ kind: 'refused:opportunity' }] }
    expect(AssistantTaskViewSchema.parse(legacy).committed).toEqual([{ kind: 'refused:opportunity' }])
  })

  it('rejects one unreadable task without affecting the readable one', () => {
    const broken = { ...task, public_id: 'ast_broken', committed: [{ kind: 'customer_activity' }] }
    expect(AssistantTaskViewSchema.safeParse(broken).success).toBe(false)
    expect(AssistantTaskViewSchema.safeParse({ ...task, committed: [activityReceipt] }).success).toBe(true)
  })

  it('loads a disposition card scoped to its customer and still rejects unknown card fields', () => {
    const disposition = {
      status: 'ACTIVE', customer_name: '虚构星河科技', customer_public_id: 'cus_fictional', activity_kind_label: '跟进',
      total: 1, current_index: null, visible_count: 1,
      items: [{ item_id: 'i1', task_public_id: 'fut_fictional', title: '确认预算', related: true, state: 'waiting' }]
    }
    const parsed = AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt], follow_up_disposition: disposition })
    expect(parsed.follow_up_disposition?.customer_public_id).toBe('cus_fictional')
    expect(AssistantTaskViewSchema.safeParse({ ...task, committed: [activityReceipt], follow_up_disposition: { ...disposition, extra: 1 } }).success).toBe(false)
  })
})

describe('current assistant confirmation commands', () => {
  it('parses the exact activity preview and preserves proposal identity without adding missing fields', () => {
    const activity = AssistantTaskViewSchema.parse({ ...task, committed: [], waiting: confirmation('activity_write', { kind: 'activity_write', preview }) })
    expect(activity.waiting?.confirmation_payload).toEqual({ kind: 'activity_write', preview })
    const proposal = { kind: 'proposal', proposal_kind: 'follow_up_task_create', candidate }
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt], waiting: confirmation('proposal:follow_up_task_create', proposal) }).waiting?.confirmation_payload).toEqual(proposal)
  })

  it('accepts exact canonical CRM preview kinds and rejects task kinds or invented kinds', () => {
    for (const activity_kind of ['PHONE_FOLLOW_UP', 'WECHAT_FOLLOW_UP', 'EMAIL_FOLLOW_UP', 'VISIT_FOLLOW_UP', 'OTHER_FOLLOW_UP', 'ONLINE_MEETING', 'OFFLINE_MEETING']) {
      const payload = { kind: 'activity_write', preview: { ...preview, activity_kind } }
      expect(AssistantTaskViewSchema.parse({ ...task, committed: [], waiting: confirmation('activity_write', payload) }).waiting?.confirmation_payload).toEqual(payload)
    }
    for (const activity_kind of ['FOLLOW_UP', 'PHONE_CALL', 'VIDEO_CALL', 'arbitrary_kind']) {
      expect(AssistantTaskViewSchema.safeParse({ ...task, committed: [], waiting: confirmation('activity_write', { kind: 'activity_write', preview: { ...preview, activity_kind } }) }).success).toBe(false)
    }
  })

  it('fails closed per row for unknown commands, wrong fields, and mismatched proposal kinds', () => {
    const invalid = [
      confirmation('activity_write', { kind: 'execute_anything', preview }),
      confirmation('proposal:follow_up_task_create', { kind: 'activity_write', preview }),
      confirmation('proposal:follow_up_task_create', { kind: 'proposal', proposal_kind: 'follow_up_task_create', candidate: { ...candidate, kind: 'opportunity_create' } }),
      confirmation('activity_write', { kind: 'activity_write', preview: { ...preview, arbitrary_command: true } }),
      confirmation('activity_write', null)
    ].map((waiting, index) => ({ ...task, public_id: `invalid-${index}`, committed: [], waiting }))
    for (const row of invalid) expect(AssistantTaskViewSchema.safeParse(row).success).toBe(false)
    const current = { ...task, committed: [activityReceipt], waiting: confirmation('proposal:follow_up_task_create', { kind: 'proposal', proposal_kind: 'follow_up_task_create', candidate }) }
    expect(AssistantTaskViewSchema.safeParse(current).success).toBe(true)
  })


  it('requires an exact bound target for existing-object proposal commands', () => {
    const payload = { kind: 'proposal', proposal_kind: 'opportunity_stage', candidate: { ...candidate, kind: 'opportunity_stage', payload: { stage_template_id: 3 } } }
    expect(AssistantTaskViewSchema.safeParse({ ...task, committed: [], waiting: confirmation('proposal:opportunity_stage', payload) }).success).toBe(false)
    const bound = { ...payload, candidate: { ...payload.candidate, target_public_id: 'opp_fictional', prior_version: 2 } }
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [], waiting: confirmation('proposal:opportunity_stage', bound) }).waiting?.confirmation_payload).toEqual(bound)
  })

  it('keeps loading a task that still waits on a retired proposal kind', () => {
    for (const kind of ['customer_fact', 'follow_up_task']) {
      const payload = { kind: 'proposal', proposal_kind: kind, candidate: { ...candidate, kind, target_public_id: 'fut_fictional' } }
      const parsed = AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt], waiting: confirmation(`proposal:${kind}`, payload) })
      expect(parsed.waiting?.confirmation_payload).toEqual(payload)
    }
  })
  it('requires a typed processing pointer pair and accepts an active internal turn', () => {
    const running = { ...task, committed: [activityReceipt], processing_turn_id: 'atn_internal', processing_turn_status: 'RUNNING' }
    expect(AssistantTaskViewSchema.parse(running).processing_turn_id).toBe('atn_internal')
    expect(AssistantTaskViewSchema.safeParse({ ...running, processing_turn_status: null }).success).toBe(false)
    expect(AssistantTaskViewSchema.safeParse({ ...running, processing_turn_id: null }).success).toBe(false)
    expect(AssistantTaskViewSchema.safeParse({ ...running, processing_turn_status: 'UNKNOWN' }).success).toBe(false)
  })
})
