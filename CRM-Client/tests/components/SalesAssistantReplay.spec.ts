import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getTaskMock = vi.fn()
const listActionsMock = vi.fn()
const listTasksMock = vi.fn()
const latestActiveMock = vi.fn()
const createTaskMock = vi.fn()
const submitInputMock = vi.fn()

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    getTask: (...args: unknown[]) => getTaskMock(...args),
    listTaskActions: (...args: unknown[]) => listActionsMock(...args),
    listTasks: (...args: unknown[]) => listTasksMock(...args),
    latestActiveTask: (...args: unknown[]) => latestActiveMock(...args),
    createTask: (...args: unknown[]) => createTaskMock(...args),
    submitInput: (...args: unknown[]) => submitInputMock(...args)
  }
}))

import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'
import type { AssistantTaskAction, AssistantTaskView } from '@/api/assistant'
import type { TaskWaiting } from '@/schemas/assistant-contracts'

const draft = {
  customer: { status: 'ACCEPTED', value: '广州睿狐科技有限公司' },
  content: { status: 'ACCEPTED', value: '客户确认 POC 可行' },
  next_action: { status: 'ACCEPTED', value: '下周三确认批复' },
  next_follow_time: { status: 'MISSING' }
}

const makeTask = (overrides: Partial<AssistantTaskView> = {}): AssistantTaskView => ({
  public_id: 'ast_hist',
  status: 'COMPLETED',
  goal: '记录会议纪要',
  activity_kind: 'ONLINE_MEETING',
  draft,
  waiting: null,
  committed: [],
  budget_steps: 8,
  budget_max_steps: 50,
  version: 8,
  ...overrides
})

const act = (actor: string, action: string, input: Record<string, unknown> = {}, result: Record<string, unknown> = {}, eventType: string | null = null): AssistantTaskAction => ({
  actor,
  action,
  input,
  result,
  event_type: eventType,
  created_time: '2026-09-24T21:00:00'
})

beforeEach(() => {
  getTaskMock.mockReset()
  listActionsMock.mockReset()
  listTasksMock.mockReset()
  latestActiveMock.mockReset()
  createTaskMock.mockReset()
  submitInputMock.mockReset()
  latestActiveMock.mockResolvedValue(null)
  listTasksMock.mockResolvedValue({ tasks: [], skipped: [] })
})

describe('history replay readability', () => {
  it('shows submitted text and human prompts instead of raw action names', async () => {
    getTaskMock.mockResolvedValue(makeTask())
    listActionsMock.mockResolvedValue([
      act('SYSTEM', 'set_activity_kind', {}, { kind: 'ONLINE_MEETING' }),
      act('SYSTEM', 'ask_confirmation', {}, { prompt: '确认后写入这条客户活动？' }),
      act('USER', 'confirm_write', {}, { activity_public_id: 'act_1' }),
      act('SYSTEM', 'offer_proposal', {}, { prompt: '为这个客户创建商机吗？' }),
      act('USER', 'refuse_proposal', { kind: 'opportunity' }, {}),
      act('SYSTEM', 'complete_after_proposals', {}, { reason: 'no_more_proposals' })
    ])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_hist')
    await flushPromises()

    const text = wrapper.text()
    // Historical actions remain readable, but only the current projection renders an interactive card.
    expect(text).toContain('会议纪要确认')
    expect(text).toContain('已记录这条客户活动。')
    expect(text).toContain('为这个客户创建商机吗？')
    expect(text).not.toContain('ask_')
    expect(text).not.toContain('confirm_write')
  })

  it('keeps the confirmed meeting card with full content from the saved snapshot', async () => {
    getTaskMock.mockResolvedValue(makeTask({ status: 'COMPLETED', activity_kind: 'ONLINE_MEETING' }))
    listActionsMock.mockResolvedValue([
      act('SYSTEM', 'ask_confirmation', {}, { prompt: '确认后写入这条客户活动？', field: 'activity_write' }),
      act('USER', 'confirm_choice', {}, { label: '确认' }, 'user_choice'),
      act('USER', 'confirm_write', {}, {
        activity_public_id: 'act_9',
        confirmation: {
          prompt: '确认后写入这条客户活动？',
          confirmation_payload: { kind: 'activity_write', preview: { customer_name: '广州睿狐科技有限公司', activity_kind: 'ONLINE_MEETING', title: 'POC 部署方案评审', summary: '客户确认 POC 可行', content_json: {}, source_content: '原文记录', score: 69, score_reason: '依据充分', next_action: '周五前提交数据出境说明' } }
        },
      }),
      act('SYSTEM', 'show_write_receipt', {}, { label: '已记录这条客户活动。' }, 'receipt'),
    ])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findComponent({ name: 'AssistantTaskSidebar' }).vm.$emit('select-task', 'ast_hist')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('POC 部署方案评审')
    expect(text).toContain('确认')
    expect(text).toContain('广州睿狐科技有限公司')
    expect(text).toContain('已记录这条客户活动。')
  })

  it('uses field labels when legacy actions carry no text', async () => {
    getTaskMock.mockResolvedValue(makeTask({ status: 'CANCELLED' }))
    listActionsMock.mockResolvedValue([
      act('SYSTEM', 'ask_quality_gap', { field: 'content' }, {}),
      act('USER', 'submit_field', { field: 'content' }, { accepted: true })
    ])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_hist')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('请补充沟通内容。')
    expect(text).toContain('（补充沟通内容）')
    expect(text).not.toContain('content')
  })

  it('renders no confirmation buttons for finished tasks', async () => {
    const waiting: TaskWaiting = {
      type: 'CONFIRMATION',
      field: 'proposal:opportunity_create',
      question_id: 'q9',
      prompt: '为这个客户创建商机吗？',
      confirmation_payload: { kind: 'proposal', proposal_kind: 'opportunity_create', candidate: {
        kind: 'opportunity_create', key: 'fictional-opportunity', payload: { opportunity_name: '虚构商机' },
        evidence_quote: '计划采购虚构系统', activity_id: 1, customer_id: 42, source_revision: 1
      } }
    }
    getTaskMock.mockResolvedValue(makeTask({ status: 'COMPLETED', waiting }))
    listActionsMock.mockResolvedValue([
      act('SYSTEM', 'offer_proposal', {}, { prompt: '为这个客户创建商机吗？' })
    ])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_hist')
    await flushPromises()

    const buttons = wrapper.findAll('button').filter((b) => b.text() === '确认' || b.text() === '取消')
    expect(buttons.length).toBe(0)
  })

  it('keeps the live waiting card for an active task', async () => {
    const waiting: TaskWaiting = {
      type: 'CONFIRMATION',
      field: 'activity_write',
      question_id: 'q8',
      prompt: '确认后写入这条客户活动？',
      confirmation_payload: { kind: 'activity_write', preview: {
        customer_name: '虚构星河科技', activity_kind: 'ONLINE_MEETING', content_json: {}, source_content: '会议原文', score: 82, score_reason: '内容完整'
      } }
    }
    getTaskMock.mockResolvedValue(makeTask({ status: 'ACTIVE', waiting }))
    listActionsMock.mockResolvedValue([
      act('SYSTEM', 'ask_confirmation', {}, { prompt: '确认后写入这条客户活动？' })
    ])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_hist')
    await flushPromises()

    // Live task: the restored waiting surfaces in the composer's controlled label.
    expect(wrapper.text()).toContain('正在回答：确认操作')
  })

  it('replays kind selection with its Chinese label', async () => {
    getTaskMock.mockResolvedValue(makeTask())
    listActionsMock.mockResolvedValue([act('USER', 'select_activity_kind', { kind: 'ONLINE_MEETING' }, {})])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()

    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_hist')
    await flushPromises()

    expect(wrapper.text()).toContain('线上会议')
  })
  it('keeps the most recently selected task if an older task request finishes later', async () => {
    let releaseOld: ((task: AssistantTaskView) => void) | undefined
    getTaskMock.mockImplementation((publicId: string) => publicId === 'ast_old'
      ? new Promise<AssistantTaskView>((resolve) => { releaseOld = resolve })
      : Promise.resolve(makeTask({ public_id: 'ast_new', goal: '新任务' })))
    listActionsMock.mockResolvedValue([])
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const sidebar = wrapper.findComponent({ name: 'AssistantTaskSidebar' })
    await sidebar.vm.$emit('select-task', 'ast_old')
    await sidebar.vm.$emit('select-task', 'ast_new')
    await flushPromises()
    releaseOld?.(makeTask({ public_id: 'ast_old', goal: '旧任务' }))
    await flushPromises()
    expect(sidebar.props('task').public_id).toBe('ast_new')
    expect(wrapper.text()).not.toContain('旧任务')
  })
})
