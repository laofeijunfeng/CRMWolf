import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AssistantTaskSidebar from '@/components/sales-assistant/AssistantTaskSidebar.vue'
import type { AssistantTaskView } from '@/schemas/assistant-contracts'

const baseTask: AssistantTaskView = {
  public_id: 'ast_test1',
  status: 'ACTIVE',
  proposals_enabled: true,
  goal: '记录睿狐科技的会议',
  activity_kind: null,
  draft: {
    customer: { status: 'MISSING' },
    content: { status: 'MISSING' },
    next_action: { status: 'MISSING' },
    next_follow_time: { status: 'MISSING' }
  },
  waiting: null,
  committed: [],
  budget_steps: 0,
  budget_max_steps: 50,
  version: 0
}

const kindWaiting = (task: AssistantTaskView): AssistantTaskView => ({
  ...task,
  waiting: { type: 'ACTIVITY_KIND', field: 'activity_kind', question_id: 'q1', prompt: '哪种活动？' }
})

describe('AssistantTaskSidebar', () => {
  it('shows the empty state when no task exists', () => {
    const wrapper = mount(AssistantTaskSidebar, { props: { task: null } })
    expect(wrapper.text()).toContain('当前没有进行中的任务')
    expect(wrapper.find('button[disabled]').exists()).toBe(false)
  })

  it('shows compact progress without treating a completed task as a committed activity', async () => {
    const active = mount(AssistantTaskSidebar, { props: { task: kindWaiting(baseTask) } })
    expect(active.text()).toContain('进行中')
    expect(active.text()).not.toContain('类型确认')

    const task: AssistantTaskView = {
      ...baseTask,
      status: 'COMPLETED',
      activity_kind: 'ONLINE_MEETING',
      draft: {
        ...baseTask.draft,
        content: { status: 'ACCEPTED', value: '已写入' }
      }
    }
    const done = mount(AssistantTaskSidebar, { props: { task } })
    expect(done.text()).not.toContain('活动已写入')
    expect(done.text()).not.toContain('内容整理')
    await done.setProps({ task: { ...task, committed: [{ kind: 'customer_activity', public_id: 'act_1', customer_id: 1 }] } })
    expect(done.text()).toContain('活动已写入')
  })


  it('shows only a matching verified auto-win when a stage receipt remains unverified', async () => {
    const receipt = { kind: 'opportunity_stage' as const, public_id: 'opp_a',
      proposal_key: 'candidate', command_id: 'cmd_stage', auto_won: 'UNVERIFIED' as const }
    const task = { ...baseTask, status: 'COMPLETED' as const, committed: [receipt],
      verified_auto_wins: [] }
    const wrapper = mount(AssistantTaskSidebar, { props: { task } })
    expect(wrapper.text()).not.toContain('自动赢单已核实')
    await wrapper.setProps({ task: { ...task, verified_auto_wins: [{ command_id: 'other', public_id: 'opp_a' }] } })
    expect(wrapper.text()).not.toContain('自动赢单已核实')
    await wrapper.setProps({ task: { ...task, verified_auto_wins: [{ command_id: 'cmd_stage', public_id: 'opp_a' }] } })
    expect(wrapper.text()).toContain('自动赢单已核实')
    expect(wrapper.props('task')?.committed).toEqual([receipt])
  })

  it('disables the new-task button while the task is active', async () => {
    const wrapper = mount(AssistantTaskSidebar, { props: { task: baseTask } })
    const button = wrapper.findAll('button').find((b) => b.text().includes('新任务'))
    expect(button?.attributes('disabled')).toBeDefined()

    await wrapper.setProps({ task: { ...baseTask, status: 'COMPLETED' } })
    const enabled = wrapper.findAll('button').find((b) => b.text().includes('新任务'))
    expect(enabled?.attributes('disabled')).toBeUndefined()
  })

  it('emits new-task when the button is clicked on a finished task', async () => {
    const wrapper = mount(AssistantTaskSidebar, {
      props: { task: { ...baseTask, status: 'COMPLETED' } }
    })
    const button = wrapper.findAll('button').find((b) => b.text().includes('新任务'))
    await button?.trigger('click')
    expect(wrapper.emitted('new-task')).toHaveLength(1)
  })

  it('renders the failure tone for failed tasks', () => {
    const wrapper = mount(AssistantTaskSidebar, {
      props: { task: { ...baseTask, status: 'FAILED' } }
    })
    expect(wrapper.text()).toContain('失败')
    expect(wrapper.html()).toContain('text-destructive')
  })

  it('shows the last-modified time on recent rows when present', () => {
    const wrapper = mount(AssistantTaskSidebar, {
      props: {
        task: null,
        recentTasks: [
          { ...baseTask, status: 'COMPLETED', last_modified_time: '2026-09-27T10:30:00' }
        ]
      }
    })
    expect(wrapper.text()).toMatch(/\d{2}:\d{2}|\d{1,2}-\d{1,2}/)
  })

  it('renders the cancel-task button only for an active task', async () => {
    const wrapper = mount(AssistantTaskSidebar, { props: { task: baseTask } })
    expect(wrapper.text()).toContain('取消任务')
    await wrapper.setProps({ task: { ...baseTask, status: 'CANCELLED' } })
    expect(wrapper.text()).not.toContain('取消任务')
  })


  it('flags a typed offered follow-up without implying it was created', () => {
    const wrapper = mount(AssistantTaskSidebar, {
      props: {
        task: {
          ...baseTask,
          outcome_code: 'OFFERED',
          waiting: { type: 'CONFIRMATION', field: 'proposal:opportunity_create', question_id: 'q2', prompt: '创建商机？' }
        }
      }
    })
    expect(wrapper.text()).toContain('后续事项待确认')
    expect(wrapper.text()).not.toContain('商机已创建')
  })
  it('shows rollback as paused, preserves unresolved-claim warning, and does not offer cancellation', async () => {
    const paused = { ...baseTask, outcome_code: 'ROLLED_BACK' as const,
      committed: [{ kind: 'customer_activity' as const, public_id: 'act_1', customer_id: 1 }] }
    const wrapper = mount(AssistantTaskSidebar, { props: { task: paused, recentTasks: [paused] } })
    expect(wrapper.text()).toContain('后续建议已暂停')
    expect(wrapper.text()).toContain('暂停')
    expect(wrapper.text()).not.toContain('取消任务')
    await wrapper.setProps({ task: { ...paused, outcome_code: 'UNKNOWN' } })
    expect(wrapper.text()).toContain('CRM 结果待核对，请勿重复提交')
    expect(wrapper.text()).not.toContain('后续建议已暂停')
  })

})

void vi
