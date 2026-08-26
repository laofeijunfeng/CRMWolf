import { describe, expect, it } from 'vitest'
import { FollowUpConfirmationResolveResponseSchema } from '@/api/followUpTask'

const responseWithBackendLocalDatetimes = {
  case: {
    id: 'fuc_1',
    public_id: 'fuc_1',
    status: 'RESOLVED',
    question_text: '关联待办是否已经完成？',
    suggested_action: 'COMPLETE',
    owner_id: '2',
    creator_id: '2',
    customer: null,
    task: {
      id: 'fut_1',
      public_id: 'fut_1',
      title: '确认合同审批进展',
      description: null,
      status: 'COMPLETED',
      due_at: '2026-08-20T10:00:00',
      due_at_text: null,
      source_type: 'CUSTOMER_ACTIVITY',
      source_public_id: 'act_1',
    },
    expires_at: null,
    prompt_count: 1,
    last_prompted_at: '2026-08-20T09:00:00',
    unresolved_reply_count: 0,
    last_unresolved_reply_text: null,
    last_unresolved_reply_at: null,
    resolved_action: 'COMPLETE',
    resolved_due_at: null,
    resolved_due_at_text: null,
    expired_at: null,
    application_status: 'APPLIED',
    application_skip_reason: null,
    applied_at: '2026-08-21T17:40:00',
    created_time: '2026-08-20T08:00:00',
  },
  decision: {
    action: 'COMPLETE',
    confidence: 1,
    reason: '用户确认已完成',
    resolved: true,
    proposed_due_at: null,
    proposed_due_at_text: null,
  },
  application: {
    status: 'APPLIED',
    case_public_id: 'fuc_1',
    task_public_id: 'fut_1',
    action: 'COMPLETE',
    skip_reason: null,
    execution_results: [],
  },
  assistant_follow_up_prompt: null,
  usage_policy: {
    mutation_gate: 'follow_up_task_confirmation_application_service',
    rule: '用户自然语言回复只解析为确认意图。',
  },
}

describe('FollowUpConfirmationResolveResponseSchema', () => {
  it('accepts the backend local ISO datetimes returned after completing a linked follow-up task', () => {
    expect(() => FollowUpConfirmationResolveResponseSchema.parse(responseWithBackendLocalDatetimes)).not.toThrow()
  })
})
