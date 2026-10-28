// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { confirmation, field, makeTask, message, mocks, show, view } from './assistantChatHarness'
import SalesAssistantChat from '@/components/sales-assistant/SalesAssistantChat.vue'

describe('owned historical conversation projection', () => {
  it('shows original text and human prompts, not internal action names', async () => {
    show(view({ messages: [message('u', '今天和客户复盘部署', null, 'user'), message('a', '请补充客户名称'), message('r', '已记录这条客户活动。')] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('今天和客户复盘部署')
    expect(wrapper.text()).toContain('请补充客户名称')
    expect(wrapper.text()).not.toMatch(/ask_confirmation|submit_field|confirm_write/)
  })

  it('binds an archived meeting card to its own frozen snapshot rather than the current task', async () => {
    const old = makeTask({ public_id: 'ast_old', status: 'COMPLETED', activity_kind: 'ONLINE_MEETING', waiting: confirmation({ confirmation_payload: { kind: 'activity_write', preview: {
      customer_name: '原客户', activity_kind: 'ONLINE_MEETING', title: '原会议主题', summary: '原会议讨论',
      content_json: {}, source_content: '原始记录', score: 88, score_reason: '原评分'
    } } }) })
    const current = makeTask({ public_id: 'ast_new', waiting: field(), draft: { ...old.draft, customer: { status: 'ACCEPTED', value: '新客户' } } })
    show(view({ focused_task: current, messages: [message('old', '会议确认', old), message('new', '当前提示', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const meeting = wrapper.findAllComponents({ name: 'AgentUIMessage' })[0]
    expect(meeting?.text()).toContain('原会议主题')
    expect(meeting?.text()).toContain('原会议讨论')
    expect(meeting?.text()).toContain('原客户')
    expect(meeting?.text()).not.toContain('新客户')
  })

  it('keeps legacy field/kind labels readable from the server projection', async () => {
    show(view({ messages: [message('one', '客户名称：睿狐科技', null, 'user'), message('two', '线上会议', null, 'user')] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.text()).toContain('客户名称：睿狐科技')
    expect(wrapper.text()).toContain('线上会议')
  })

  it('does not let an archived card confirm or change the focused activity kind', async () => {
    const old = makeTask({ status: 'COMPLETED', waiting: confirmation() })
    show(view({ focused_task: makeTask({ public_id: 'ast_new' }), messages: [message('old', '已归档', old)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.findAll('button').filter((b) => /确认写入|改为线下/.test(b.text()) && b.attributes('disabled') === undefined)).toHaveLength(0)
    expect(mocks.kind).not.toHaveBeenCalled()
  })

  it('restores one live authoritative wait while older matching cards stay archived', async () => {
    const current = makeTask({ waiting: confirmation() })
    show(view({ focused_task: current, messages: [message('old', '旧提示', current), message('new', '当前提示', current)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    expect(wrapper.findAll('button').filter((b) => b.text() === '确认写入' && b.attributes('disabled') === undefined)).toHaveLength(1)
  })

  it('preserves the old draft field chips instead of taking values from a new focus', async () => {
    const old = makeTask({ public_id: 'ast_old', waiting: field(), draft: { ...makeTask().draft, customer: { status: 'ACCEPTED', value: '旧客户' } } })
    const next = makeTask({ public_id: 'ast_next', waiting: field(), draft: { ...makeTask().draft, customer: { status: 'ACCEPTED', value: '新客户' } } })
    show(view({ focused_task: next, messages: [message('old', '旧稿问题', old), message('new', '新稿问题', next)] }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    const gaps = wrapper.findAllComponents({ name: 'AgentUIMessage' })
    expect(gaps[0]?.text()).toContain('旧客户')
    expect(gaps[0]?.text()).not.toContain('新客户')
  })

  it('loads earlier conversation by cursor without dropping the latest results', async () => {
    show(view({ messages: [message('new', '最近结果')], older_cursor: 31 }))
    mocks.get.mockResolvedValue(view({ messages: [message('old', '更早结果')], older_cursor: null }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '查看更早对话')?.trigger('click')
    await flushPromises()
    expect(mocks.get).toHaveBeenCalledWith(31)
    expect(wrapper.text()).toContain('更早结果')
    expect(wrapper.text()).toContain('最近结果')
  })
})

describe('conversation snapshot fences', () => {
  it('does not restore a next history cursor after all earlier pages were loaded', async () => {
    show(view({ version: 1, messages: [message('new', '最近结果')], older_cursor: 31 }))
    mocks.get.mockResolvedValueOnce(view({ version: 1, messages: [message('old', '最早结果')], older_cursor: null }))
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '查看更早对话')?.trigger('click')
    await flushPromises()
    mocks.text.mockResolvedValue({ conversation: view({ version: 2, messages: [message('new', '最近结果'), message('next', '新的回复')], older_cursor: 31 }), submission: null })
    await wrapper.find('textarea').setValue('下一件')
    await wrapper.find('textarea').trigger('keydown.enter', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.text()).toContain('最早结果')
    expect(wrapper.text()).toContain('新的回复')
    expect(wrapper.findAll('button').find((b) => b.text() === '查看更早对话')).toBeUndefined()
  })

  it('persists activity-kind changes through the owned conversation, without clearing history', async () => {
    const current = makeTask({ waiting: confirmation() })
    show(view({ version: 3, focused_task: current, messages: [message('old', '此前的沟通'), message('card', '确认？', current)] }))
    mocks.kind.mockResolvedValue({ conversation: view({ version: 4, focused_task: { ...current, version: 2, activity_kind: 'ONLINE_MEETING', waiting: null }, messages: [message('old', '此前的沟通'), message('kind', '已切换为线上会议，请重新描述这次沟通。')] }), submission: null })
    const wrapper = mount(SalesAssistantChat)
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '改为线下 / 跟进')?.trigger('click')
    await flushPromises()
    expect(mocks.kind).toHaveBeenCalledWith(expect.objectContaining({ task_public_id: 'ast_one', kind: 'ONLINE_MEETING', task_version: 1, expected_version: 3 }))
    expect(wrapper.text()).toContain('此前的沟通')
    expect(wrapper.text()).toContain('已切换为线上会议')
  })
})
