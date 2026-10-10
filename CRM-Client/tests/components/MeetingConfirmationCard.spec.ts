import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MeetingConfirmationCard from '@/components/sales-assistant/MeetingConfirmationCard.vue'
import type { AssistantTaskView } from '@/schemas/assistant-contracts'

const meetingTask: AssistantTaskView = {
  public_id: 'ast_m1',
  status: 'ACTIVE',
  goal: '今天下午的线上会议原文',
  activity_kind: 'ONLINE_MEETING',
  draft: {
    customer: { status: 'ACCEPTED', value: '广州睿狐科技有限公司' },
    content: { status: 'CANDIDATE', value: '客户方 · 王总：POC 方案可行，预算进下季度；客户方 · 李经理：先交安全测评报告再立项；我方 · 张工：周五前交数据出境说明' },
    next_action: { status: 'CANDIDATE', value: '张工承诺：周五前交数据出境说明；下周三王总反馈立项批复' },
    next_follow_time: { status: 'MISSING' },
    meeting_subject: { status: 'CANDIDATE', value: 'POC 部署方案评审' },
    participants: { status: 'CANDIDATE', value: '客户方：王总、李经理；我方：张工' },
    quality_score: { status: 'CANDIDATE', value: '86' }
  },
  waiting: { type: 'CONFIRMATION', field: 'activity_write', question_id: 'q1', prompt: '确认后写入这条客户活动？' },
  committed: [],
  budget_steps: 5,
  budget_max_steps: 50,
  version: 5
}

describe('MeetingConfirmationCard', () => {
  it('renders subject, discussion lines, participants, and action rows', () => {
    const wrapper = mount(MeetingConfirmationCard, {
      props: { task: meetingTask, waiting: meetingTask.waiting!, replayed: false, busy: false }
    })
    const text = wrapper.text()
    expect(text).toContain('线上会议')
    expect(text).toContain('POC 部署方案评审')
    expect(text).toContain('王总')
    expect(text).toContain('李经理')
    expect(text).toContain('参会角色')
    expect(text).toContain('行动项')
    expect(text).toContain('86 / 100')
    expect(text).toContain('已绑定')
  })

  it('shows confirm and cancel buttons for the live card', () => {
    const wrapper = mount(MeetingConfirmationCard, {
      props: { task: meetingTask, waiting: meetingTask.waiting!, replayed: false, busy: false }
    })
    const confirm = wrapper.findAll('button').find((b) => b.text() === '确认写入')
    const cancel = wrapper.findAll('button').find((b) => b.text() === '取消')
    expect(confirm).toBeDefined()
    expect(cancel).toBeDefined()
  })

  it('renders read-only when replayed', () => {
    const wrapper = mount(MeetingConfirmationCard, {
      props: { task: meetingTask, waiting: meetingTask.waiting!, replayed: true, busy: false }
    })
    expect(wrapper.text()).toContain('历史记录')
    expect(wrapper.findAll('button').filter((b) => b.text() === '确认写入').length).toBe(0)
  })

  it('falls back gracefully when meeting slots are empty', () => {
    const sparse = {
      ...meetingTask,
      draft: {
        ...meetingTask.draft,
        meeting_subject: { status: 'MISSING' },
        participants: { status: 'MISSING' },
        quality_score: { status: 'MISSING' }
      }
    }
    const wrapper = mount(MeetingConfirmationCard, {
      props: { task: sparse, waiting: sparse.waiting!, replayed: false, busy: false }
    })
    expect(wrapper.text()).toContain('会议纪要确认')
    expect(wrapper.text()).toContain('（未提供）')
    expect(wrapper.text()).not.toContain('/ 100')
  })
  it('shows the frozen write candidate instead of a subsequently changed draft', () => {
    const task: AssistantTaskView = {
      ...meetingTask,
      draft: { ...meetingTask.draft, customer: { status: 'ACCEPTED', value: '新客户' }, participants: { status: 'CANDIDATE', value: '后来参会人' }, content: { status: 'CANDIDATE', value: '新摘要' }, next_action: { status: 'CANDIDATE', value: '新行动' }, quality_score: { status: 'CANDIDATE', value: '42' } }
    }
    const waiting = {
      type: 'CONFIRMATION' as const, field: 'activity_write', question_id: 'q1', prompt: '确认写入？',
      confirmation_payload: { kind: 'activity_write' as const, preview: { customer_name: '原客户', activity_kind: 'ONLINE_MEETING' as const, title: '原主题', summary: '原摘要', content_json: { participants: { internal: ['虚构同事甲'], customer: ['虚构客户乙'] } }, source_content: '原文记录', score: 88, score_reason: '依据', next_action: '原行动' } }
    }
    const wrapper = mount(MeetingConfirmationCard, { props: { task, waiting, replayed: false, busy: false } })
    expect(wrapper.text()).toContain('原客户')
    expect(wrapper.text()).toContain('原主题')
    expect(wrapper.text()).toContain('原摘要')
    expect(wrapper.text()).toContain('原行动')
    expect(wrapper.text()).toContain('88 / 100')
    expect(wrapper.text()).toContain('我方：虚构同事甲')
    expect(wrapper.text()).toContain('客户方：虚构客户乙')
    expect(wrapper.text()).not.toContain('后来参会人')
    expect(wrapper.text()).not.toContain('新客户')
    expect(wrapper.text()).not.toContain('新摘要')
    expect(wrapper.text()).not.toContain('新行动')
    expect(wrapper.text()).not.toContain('42 / 100')
  })
  it('does not replace absent frozen action and summary with mutable draft values', () => {
    const task: AssistantTaskView = { ...meetingTask, draft: { ...meetingTask.draft, content: { status: 'CANDIDATE', value: '后来讨论' }, next_action: { status: 'CANDIDATE', value: '后来行动' } } }
    const waiting = {
      type: 'CONFIRMATION' as const, field: 'activity_write', question_id: 'q1', prompt: '确认写入？',
      confirmation_payload: { kind: 'activity_write' as const, preview: { customer_name: '睿狐', activity_kind: 'ONLINE_MEETING' as const, title: '会面', summary: null, content_json: {}, source_content: '原文', score: 82, score_reason: '依据', next_action: null } }
    }
    const wrapper = mount(MeetingConfirmationCard, { props: { task, waiting, replayed: false, busy: false } })
    expect(wrapper.text()).not.toContain('后来讨论')
    expect(wrapper.text()).not.toContain('后来行动')
    expect(wrapper.text()).not.toContain('客户方：王总、李经理')
    expect(wrapper.text()).toContain('未提供行动项')
  })
})
