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
const preview = {
  customer_name: '虚构星河科技', activity_kind: 'OTHER_FOLLOW_UP', title: '部署沟通', summary: '确认部署计划',
  content_json: {}, source_content: '确认部署计划', score: 85, score_reason: '要素完整',
  next_action: null, next_follow_time: null, next_follow_time_text: ''
}
const candidate = {
  kind: 'customer_fact', key: 'fact-key', evidence_quote: '使用虚构系统', payload: { fact_type: 'system', content: '使用虚构系统' },
  activity_id: 1, customer_id: 42, source_revision: 1, prior_fact_version: null, action_id: 'fictional-action'
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

  it('counts a server-isolated unreadable list row while retaining a validated row', () => {
    const unreadable = { ...task, public_id: 'ast_unreadable', draft: null, waiting: null, committed: [], processing_turn_id: null, processing_turn_status: null }
    const readable = { ...task, committed: [activityReceipt] }
    const result = parseAssistantTaskList([unreadable, readable])
    expect(result.skipped).toEqual([0])
    expect(result.tasks.map((row) => row.public_id)).toEqual(['ast_123'])
    expect(result.tasks[0]?.committed).toEqual([activityReceipt])
  })
})

describe('current assistant confirmation commands', () => {
  it('parses the exact activity preview and preserves proposal identity without adding missing fields', () => {
    const activity = AssistantTaskViewSchema.parse({ ...task, committed: [], waiting: confirmation('activity_write', { kind: 'activity_write', preview }) })
    expect(activity.waiting?.confirmation_payload).toEqual({ kind: 'activity_write', preview })
    const proposal = { kind: 'proposal', proposal_kind: 'customer_fact', candidate }
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [activityReceipt], waiting: confirmation('proposal:customer_fact', proposal) }).waiting?.confirmation_payload).toEqual(proposal)
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
      confirmation('proposal:customer_fact', { kind: 'activity_write', preview }),
      confirmation('proposal:customer_fact', { kind: 'proposal', proposal_kind: 'customer_fact', candidate: { ...candidate, kind: 'opportunity_create' } }),
      confirmation('activity_write', { kind: 'activity_write', preview: { ...preview, arbitrary_command: true } }),
      confirmation('activity_write', null)
    ].map((waiting, index) => ({ ...task, public_id: `invalid-${index}`, committed: [], waiting }))
    const current = { ...task, committed: [activityReceipt], waiting: confirmation('proposal:customer_fact', { kind: 'proposal', proposal_kind: 'customer_fact', candidate }) }
    const parsed = parseAssistantTaskList([...invalid, current])
    expect(parsed.skipped).toEqual([0, 1, 2, 3, 4])
    expect(parsed.tasks.map((row) => row.public_id)).toEqual(['ast_123'])
  })


  it('requires an exact bound target for existing-object proposal commands', () => {
    const payload = { kind: 'proposal', proposal_kind: 'opportunity_stage', candidate: { ...candidate, kind: 'opportunity_stage', payload: { stage_template_id: 3 } } }
    expect(AssistantTaskViewSchema.safeParse({ ...task, committed: [], waiting: confirmation('proposal:opportunity_stage', payload) }).success).toBe(false)
    const bound = { ...payload, candidate: { ...payload.candidate, target_public_id: 'opp_fictional', prior_version: 2 } }
    expect(AssistantTaskViewSchema.parse({ ...task, committed: [], waiting: confirmation('proposal:opportunity_stage', bound) }).waiting?.confirmation_payload).toEqual(bound)
  })
  it('requires a typed processing pointer pair and accepts an active internal turn', () => {
    const running = { ...task, committed: [activityReceipt], processing_turn_id: 'atn_internal', processing_turn_status: 'RUNNING' }
    expect(AssistantTaskViewSchema.parse(running).processing_turn_id).toBe('atn_internal')
    expect(AssistantTaskViewSchema.safeParse({ ...running, processing_turn_status: null }).success).toBe(false)
    expect(AssistantTaskViewSchema.safeParse({ ...running, processing_turn_id: null }).success).toBe(false)
    expect(AssistantTaskViewSchema.safeParse({ ...running, processing_turn_status: 'UNKNOWN' }).success).toBe(false)
  })
})
