import type { VueWrapper } from '@vue/test-utils'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type * as AssistantApiModule from '@/api/assistant'
import type { SubmitAssistantInput } from '@/api/assistant'
import { InteractionBlockSchema } from '@/schemas/agent-contracts'
import type { AssistantTaskView, ConversationReply, ConversationView, TaskWaiting } from '@/schemas/assistant-contracts'
import { assistantCommandReplyLabel } from '../replyLabel'
import type { InteractionBlock } from '../replyLabel'

const openConversation = vi.hoisted(() => vi.fn())
const getConversation = vi.hoisted(() => vi.fn())
const conversationCommand = vi.hoisted(() => vi.fn())
const pendingDrafts = vi.hoisted(() => vi.fn())

vi.mock('@/api/assistant', async (importOriginal) => ({
  ...(await importOriginal<typeof AssistantApiModule>()),
  assistantApi: {
    openConversation,
    getConversation,
    conversationCommand,
    pendingDrafts,
    resumeConversation: vi.fn(),
  },
  submitInputStream: vi.fn(),
}))

import SalesAssistantChat from '../SalesAssistantChat.vue'

const makeWaiting = (
  type: TaskWaiting['type'],
  overrides: Partial<TaskWaiting> = {}
): TaskWaiting => ({
  type,
  question_id: 'q_1',
  prompt: '请选择',
  action_id: 'act_1',
  expected_version: 2,
  ...overrides,
})

const makeTask = (
  publicId: string,
  waiting: TaskWaiting,
  overrides: Partial<AssistantTaskView> = {}
): AssistantTaskView => ({
  public_id: publicId,
  task_kind: 'customer_activity',
  goal: '记录客户沟通',
  status: 'ACTIVE',
  draft: {
    customer: { status: 'MISSING' },
    content: { status: 'MISSING' },
    next_action: { status: 'MISSING' },
    next_follow_time: { status: 'MISSING' },
  },
  committed: [],
  budget_steps: 1,
  budget_max_steps: 10,
  version: 2,
  processing_turn_id: null,
  processing_turn_status: null,
  reprocess_turn_id: null,
  waiting,
  ...overrides,
})

const makeView = (
  task: AssistantTaskView,
  block: InteractionBlock,
  text: string,
  version = 3
): ConversationView => ({
  public_id: 'asc_1',
  version,
  focused_task: task,
  pending_choice: null,
  has_pending_request: false,
  older_cursor: null,
  messages: [
    {
      id: `acm_${version}:reply`,
      role: 'assistant',
      text,
      at: '2026-11-27T10:00:00',
      task,
      boundary: null,
      outcome: null,
      ui: {
        schema_version: 'crm.agent.ui.v1',
        message_id: version,
        turn_id: `acm_${version}:reply`,
        role: 'assistant',
        state: 'final',
        blocks: [block],
        suggested_actions: [],
        metadata: { display: 'MESSAGE', route: 'WORKFLOW' },
      },
    },
  ],
})

const userBubbleTexts = (wrapper: VueWrapper): string[] =>
  wrapper.findAll('div.flex.justify-end').map((node) => node.text().trim())

describe('assistantCommandReplyLabel', () => {
  it.each<[string, SubmitAssistantInput, TaskWaiting | null, string]>([
    [
      'OBJECT_SELECTION account_name',
      { kind: 'submit_field', choice: 'cus_1' },
      makeWaiting('OBJECT_SELECTION', {
        field: 'customer',
        candidates: [{ id: 'cus_1', account_name: '睿狐科技' }],
      }),
      '睿狐科技',
    ],
    [
      'OBJECT_SELECTION label (__new_customer__)',
      { kind: 'submit_field', choice: '__new_customer__' },
      makeWaiting('OBJECT_SELECTION', {
        field: 'customer',
        candidates: [
          { id: 'cus_1', label: '睿狐科技' },
          { id: '__new_customer__', label: '新建客户' },
        ],
      }),
      '新建客户',
    ],
    [
      'OBJECT_SELECTION opportunity label',
      { kind: 'submit_field', choice: 'opp_1' },
      makeWaiting('OBJECT_SELECTION', {
        field: 'opportunity',
        candidates: [{ id: 'opp_1', label: '二期扩容项目' }],
      }),
      '二期扩容项目',
    ],
    [
      'OBJECT_SELECTION fallback by field',
      { kind: 'submit_field', choice: 'missing' },
      makeWaiting('OBJECT_SELECTION', { field: 'opportunity', candidates: [] }),
      '选择商机',
    ],
    [
      'ENTITY_DEFERRED resume',
      { kind: 'submit_field', choice: 'resume' },
      makeWaiting('ENTITY_DEFERRED', {
        field: 'resume',
        candidates: [{ id: 'resume', label: '继续填写' }, { id: 'cancel', label: '不要了' }],
      }),
      '继续填写',
    ],
    [
      'ENTITY_DEFERRED cancel',
      { kind: 'submit_field', choice: 'cancel' },
      makeWaiting('ENTITY_DEFERRED', {
        field: 'resume',
        candidates: [{ id: 'resume', label: '继续填写' }, { id: 'cancel', label: '不要了' }],
      }),
      '不要了',
    ],
    [
      'ACTIVITY_KIND FOLLOW_UP uses 普通跟进',
      { kind: 'submit_field', choice: 'FOLLOW_UP' },
      makeWaiting('ACTIVITY_KIND', { field: 'activity_kind' }),
      '普通跟进',
    ],
    [
      'revise_activity_kind FOLLOW_UP',
      { kind: 'revise_activity_kind', choice: 'FOLLOW_UP' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '改为普通跟进',
    ],
    [
      'revise_activity_kind ONLINE_MEETING',
      { kind: 'revise_activity_kind', choice: 'ONLINE_MEETING' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '改为线上会议',
    ],
    [
      'revise_activity_kind unknown fallback',
      { kind: 'revise_activity_kind', choice: 'UNKNOWN_KIND' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '修改活动类型',
    ],
    [
      'confirm activity_write',
      { kind: 'confirm', choice: 'confirm' },
      makeWaiting('CONFIRMATION', {
        field: 'activity_write',
        confirmation_payload: {
          kind: 'activity_write',
          preview: {
            activity_kind: 'PHONE_FOLLOW_UP',
            customer_name: '睿狐科技',
            summary: '确认部署计划',
            content_json: { summary: '确认部署计划' },
            source_content: '电话沟通确认部署计划',
            score: 80,
            score_reason: '内容完整',
          },
        },
      }),
      '确认写入',
    ],
    [
      'confirm proposal',
      { kind: 'confirm', choice: 'confirm' },
      makeWaiting('CONFIRMATION', {
        field: 'proposal:customer_fact',
        confirmation_payload: {
          kind: 'proposal',
          proposal_kind: 'customer_fact',
          candidate: {
            kind: 'customer_fact',
            key: 'fact:company_size',
            payload: { fact_type: 'company_size', value: '200人' },
            evidence_quote: '客户约 200 人',
            activity_id: 1,
            customer_id: 10,
            source_revision: 1,
          },
        },
      }),
      '确认',
    ],
    [
      'reject without reason',
      { kind: 'confirm', choice: 'reject' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '取消',
    ],
    [
      'reject wrong_customer',
      { kind: 'confirm', choice: 'reject', reason: 'wrong_customer' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '取消（客户不对）',
    ],
    [
      'reject wrong_content',
      { kind: 'confirm', choice: 'reject', reason: 'wrong_content' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '取消（内容不对）',
    ],
    [
      'reject should_not_record',
      { kind: 'confirm', choice: 'reject', reason: 'should_not_record' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '取消（不该记录）',
    ],
    [
      'reject other',
      { kind: 'confirm', choice: 'reject', reason: 'other' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '取消（其他）',
    ],
    [
      'request_edit',
      { kind: 'request_edit' },
      makeWaiting('CONFIRMATION', { field: 'activity_write' }),
      '修改内容',
    ],
    [
      'cancel',
      { kind: 'cancel' },
      makeWaiting('FIELD', { field: 'content' }),
      '算了，不记了',
    ],
    [
      'submit_form submit',
      { kind: 'submit_form', form_revision: 1, values: { name: '王敏' } },
      makeWaiting('ENTITY_FORM', { field: 'contact_create', form_revision: 1 }),
      '提交',
    ],
    [
      'submit_form defer',
      { kind: 'submit_form', form_revision: 1, choice: 'defer' },
      makeWaiting('ENTITY_FORM', { field: 'contact_create', form_revision: 1 }),
      '稍后补充',
    ],
    [
      'submit_form cancel ENTITY_FORM',
      { kind: 'submit_form', form_revision: 1, choice: 'cancel' },
      makeWaiting('ENTITY_FORM', { field: 'contact_create', form_revision: 1 }),
      '取消',
    ],
    [
      'submit_form cancel CONFIRMATION_EDIT',
      { kind: 'submit_form', form_revision: 1, choice: 'cancel' },
      makeWaiting('CONFIRMATION_EDIT', { field: 'activity_write', form_revision: 1 }),
      '取消修改',
    ],
    [
      'temporal_choice candidate',
      { kind: 'submit_field', choice: '2026-11-26' },
      makeWaiting('FIELD', {
        field: 'temporal_choice',
        candidates: [{ id: '2026-11-26', label: '昨天（11月26日）' }],
      }),
      '昨天（11月26日）',
    ],
    [
      'EXPLICITLY_NONE with text',
      { kind: 'submit_field', choice: 'EXPLICITLY_NONE', text: '暂不安排下一步' },
      makeWaiting('FIELD', { field: 'next_action' }),
      '暂不安排下一步',
    ],
    [
      'EXPLICITLY_NONE fallback',
      { kind: 'submit_field', choice: 'EXPLICITLY_NONE' },
      makeWaiting('FIELD', { field: 'next_action' }),
      '暂无下一步行动',
    ],
  ])('formats %s identically to server command_label', (_name, input, waiting, expected) => {
    expect(assistantCommandReplyLabel(input, waiting)).toBe(expected)
  })

  it.each<[string[], boolean, string]>([
    [['item_1'], false, '标记完成：发送报价单'],
    [['item_1'], true, '标记完成：发送报价单 · 本周不再提示'],
    [['item_1', 'item_2'], false, '标记完成 2 项：发送报价单 等'],
    [['item_1', 'item_2'], true, '标记完成 2 项：发送报价单 等 · 本周不再提示'],
    [[], false, '暂不标记完成'],
    [[], true, '本周不再提示'],
  ])('formats FOLLOW_UP_DISPOSITION choices=%j suppress=%s', (choices, suppressWeek, expected) => {
    const waiting = makeWaiting('FOLLOW_UP_DISPOSITION', {
      field: 'open_follow_up',
      candidates: [
        { id: 'item_1', label: '发送报价单' },
        { id: 'item_2', label: '约技术评审' },
      ],
    })
    expect(assistantCommandReplyLabel({ kind: 'submit_field', choices, suppress_week: suppressWeek }, waiting)).toBe(expected)
  })

  it('formats PROFILE_PROPOSALS from block options and from task profileProposals fallback', () => {
    const waiting = makeWaiting('PROFILE_PROPOSALS', {
      field: 'profile_proposals',
      candidates: [
        { id: 'go:0', label: '去补充' },
        { id: 'skip:0', label: '不保存' },
        { id: 'none', label: '都不需要' },
      ],
    })
    const block: Pick<InteractionBlock, 'options'> = {
      options: [
        { value: 'go:0', label: '去补充', group: '联系人：王敏 13800138000', description: '原话：王敏负责对接', disabled: false },
        { value: 'skip:0', label: '不保存', group: '联系人：王敏 13800138000', disabled: false },
        { value: 'none', label: '都不需要', group: '全部', disabled: false },
      ],
    }

    expect(assistantCommandReplyLabel({ kind: 'submit_field', choice: 'go:0' }, waiting, { block }))
      .toBe('去补充：联系人：王敏 13800138000')
    expect(assistantCommandReplyLabel({ kind: 'submit_field', choice: 'skip:0' }, waiting, { block }))
      .toBe('不保存：联系人：王敏 13800138000')
    expect(assistantCommandReplyLabel({ kind: 'submit_field', choice: 'none' }, waiting, { block }))
      .toBe('都不需要')

    // Fallback without block options computes the exact same group from profileProposals.
    expect(assistantCommandReplyLabel({ kind: 'submit_field', choice: 'go:0' }, waiting, {
      profileProposals: [
        {
          index: 0,
          kind: 'contact_create',
          label: '联系人',
          summary: '联系人：王敏 13800138000',
          quote: '王敏负责对接',
          decision: 'pending',
        },
      ],
    })).toBe('去补充：联系人：王敏 13800138000')
  })
})

describe('SalesAssistantChat optimistic user reply bubbles', () => {
  let mounted: VueWrapper | undefined

  beforeEach(() => {
    openConversation.mockReset()
    getConversation.mockReset()
    conversationCommand.mockReset()
    pendingDrafts.mockReset()
    pendingDrafts.mockResolvedValue([])
    conversationCommand.mockReturnValue(new Promise<ConversationReply>(() => undefined))
  })

  afterEach(() => {
    mounted?.unmount()
    mounted = undefined
  })

  it('echoes concrete group copy for PROFILE_PROPOSALS before server response returns', async () => {
    const waiting = makeWaiting('PROFILE_PROPOSALS', {
      field: 'profile_proposals',
      prompt: '以下客户资料是否需要保存？',
      candidates: [
        { id: 'go:0', label: '去补充' },
        { id: 'skip:0', label: '不保存' },
        { id: 'none', label: '都不需要' },
      ],
    })
    const task = makeTask('ast_profile', waiting, {
      profile_proposals: [
        {
          index: 0,
          kind: 'contact_create',
          label: '联系人',
          summary: '王敏（采购总监）',
          quote: '联系王敏',
          decision: 'pending',
        },
      ],
    })
    const block = InteractionBlockSchema.parse({
      id: 'blk_profile',
      type: 'interaction',
      interaction_id: 'q_1',
      interaction_type: 'choice',
      state: 'ACTIVE',
      business_action: 'choose_profile_proposal',
      selection_mode: 'single',
      min_selections: 1,
      max_selections: 1,
      submit_action_id: 'act_1',
      submit_on_select: true,
      prompt: '以下客户资料是否需要保存？',
      options: [
        { value: 'go:0', label: '去补充', group: '联系人：王敏（采购总监）', disabled: false },
        { value: 'skip:0', label: '不保存', group: '联系人：王敏（采购总监）', disabled: false },
        { value: 'none', label: '都不需要', group: '全部', disabled: false },
      ],
    })

    openConversation.mockResolvedValue(makeView(task, block, '以下客户资料是否需要保存？', 3))
    mounted = mount(SalesAssistantChat)
    await flushPromises()

    const goButton = mounted.findAll('button').find((button) => button.text().includes('去补充'))
    expect(goButton).toBeDefined()
    await goButton?.trigger('click')
    await flushPromises()

    expect(userBubbleTexts(mounted)).toContain('去补充：联系人：王敏（采购总监）')
    expect(conversationCommand).toHaveBeenCalledTimes(1)
  })

  it('echoes 确认写入, 修改内容, 取消（客户不对）, and 改为电话跟进 for activity confirmation actions', async () => {
    const waiting = makeWaiting('CONFIRMATION', {
      field: 'activity_write',
      prompt: '请确认写入这条沟通记录',
      confirmation_payload: {
        kind: 'activity_write',
        preview: {
          activity_kind: 'OTHER_FOLLOW_UP',
          customer_name: '睿狐科技',
          summary: '讨论二期扩容',
          content_json: { summary: '讨论二期扩容' },
          source_content: '沟通讨论二期扩容',
          score: 80,
          score_reason: '内容完整',
        },
      },
    })
    const makeConfirmView = (): ConversationView => {
      const task = makeTask('ast_confirm', waiting)
      const block = InteractionBlockSchema.parse({
        id: 'blk_confirm',
        type: 'interaction',
        interaction_id: 'q_1',
        interaction_type: 'confirmation',
        state: 'ACTIVE',
        business_action: 'confirm_activity_write',
        selection_mode: 'single',
        submit_action_id: 'act_1',
        submit_on_select: true,
        prompt: '请确认写入这条沟通记录',
        facts: [
          { key: 'customer', label: '客户', value: '睿狐科技', group: 'write' },
          {
            key: 'activity_kind',
            label: '活动类型',
            value: '普通跟进',
            group: 'activity_kind',
            options: [
              { value: 'PHONE_FOLLOW_UP', label: '电话跟进' },
              { value: 'WECHAT_FOLLOW_UP', label: '微信跟进' },
            ],
          },
        ],
        options: [
          { value: 'confirm', label: '确认写入' },
          { value: 'cancel', label: '取消' },
        ],
        secondary_action: { value: 'request_edit', label: '修改内容' },
        cancel_reasons: [
          { value: 'wrong_customer', label: '客户不对' },
          { value: 'wrong_content', label: '内容不对' },
        ],
      })
      return makeView(task, block, '请确认写入这条沟通记录', 4)
    }

    // 1) Confirm write -> 确认写入
    openConversation.mockResolvedValue(makeConfirmView())
    mounted = mount(SalesAssistantChat)
    await flushPromises()
    const confirmBtn = mounted.findAll('button').find((button) => button.text().trim() === '确认写入')
    expect(confirmBtn).toBeDefined()
    await confirmBtn?.trigger('click')
    await flushPromises()
    expect(userBubbleTexts(mounted)).toContain('确认写入')
    mounted.unmount()

    // 2) Request edit -> 修改内容 (not 修改活动内容)
    openConversation.mockResolvedValue(makeConfirmView())
    mounted = mount(SalesAssistantChat)
    await flushPromises()
    const editBtn = mounted.findAll('button').find((button) => button.text().trim() === '修改内容')
    expect(editBtn).toBeDefined()
    await editBtn?.trigger('click')
    await flushPromises()
    expect(userBubbleTexts(mounted)).toContain('修改内容')
    expect(userBubbleTexts(mounted)).not.toContain('修改活动内容')
    mounted.unmount()

    // 3) Reject with reason -> 取消（客户不对）
    openConversation.mockResolvedValue(makeConfirmView())
    mounted = mount(SalesAssistantChat)
    await flushPromises()
    const cancelBtn = mounted.findAll('button').find((button) => button.text().trim() === '取消')
    expect(cancelBtn).toBeDefined()
    await cancelBtn?.trigger('click')
    await flushPromises()
    const reasonBtn = mounted.findAll('button').find((button) => button.text().trim() === '客户不对')
    expect(reasonBtn).toBeDefined()
    await reasonBtn?.trigger('click')
    await flushPromises()
    expect(userBubbleTexts(mounted)).toContain('取消（客户不对）')
    mounted.unmount()

    // 4) Revise activity kind -> 改为电话跟进 (not 修改活动类型)
    openConversation.mockResolvedValue(makeConfirmView())
    mounted = mount(SalesAssistantChat)
    await flushPromises()
    const kindToggle = mounted.findAll('button').find((button) => button.text().trim() === '修改活动类型')
    expect(kindToggle).toBeDefined()
    await kindToggle?.trigger('click')
    await flushPromises()
    const phoneOption = mounted.findAll('[role="radio"]').find((node) => node.text().trim() === '电话跟进')
    expect(phoneOption).toBeDefined()
    await phoneOption?.trigger('click')
    await flushPromises()
    expect(userBubbleTexts(mounted)).toContain('改为电话跟进')
    expect(userBubbleTexts(mounted)).not.toContain('修改活动类型')
  })

  it('echoes concrete selected follow-up title instead of 提交跟进处理', async () => {
    const waiting = makeWaiting('FOLLOW_UP_DISPOSITION', {
      field: 'open_follow_up',
      prompt: '是否标记以下待办完成？',
      candidates: [
        { id: 'item_1', label: '发送报价单' },
        { id: 'item_2', label: '约技术评审' },
      ],
    })
    const task = makeTask('ast_disp', waiting, {
      follow_up_disposition: {
        batch_id: 'batch_1',
        status: 'ACTIVE',
        customer_name: '睿狐科技',
        activity_kind_label: '电话跟进',
        total: 2,
        current_index: 1,
        items: [
          { item_id: 'item_1', title: '发送报价单', related: true, state: 'current' },
          { item_id: 'item_2', title: '约技术评审', related: false, state: 'waiting' },
        ],
      },
    })
    const block = InteractionBlockSchema.parse({
      id: 'blk_disp',
      type: 'interaction',
      interaction_id: 'q_1',
      interaction_type: 'choice',
      business_action: 'settle_follow_up_disposition',
      presentation: 'OPEN_FOLLOW_UP_DISPOSITION',
      state: 'ACTIVE',
      prompt: '是否标记以下待办完成？',
      selection_mode: 'multiple',
      min_selections: 0,
      max_selections: 2,
      submit_on_select: false,
      submit_action_id: 'act_1',
      secondary_action: { value: 'suppress_week', label: '本周不再提示' },
      disposition_visible_count: 2,
      options: [
        { value: 'item_1', label: '发送报价单' },
        { value: 'item_2', label: '约技术评审' },
      ],
      disposition_items: [
        { item_id: 'item_1', title: '发送报价单', related: true, state: 'current' },
        { item_id: 'item_2', title: '约技术评审', related: false, state: 'waiting' },
      ],
    })

    openConversation.mockResolvedValue(makeView(task, block, '是否标记以下待办完成？', 5))
    mounted = mount(SalesAssistantChat)
    await flushPromises()

    const checkbox = mounted.find('input[type="checkbox"][value="item_1"]')
    expect(checkbox.exists()).toBe(true)
    await checkbox.trigger('change')
    const submitButton = mounted.findAll('button').find((btn) => btn.text().trim() === block.submit_label)
    if (!submitButton) throw new Error('submit button not found')
    await submitButton.trigger('click')
    await flushPromises()

    expect(userBubbleTexts(mounted)).toContain('标记完成：发送报价单')
    expect(userBubbleTexts(mounted)).not.toContain('提交跟进处理')
  })
})
