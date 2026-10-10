import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AssistantTaskSidebar from '@/components/sales-assistant/AssistantTaskSidebar.vue'
import type { AssistantTaskView } from '@/schemas/assistant-contracts'

const baseTask: AssistantTaskView = {
  public_id: 'ast_test1',
  status: 'ACTIVE',
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

  it('keeps the committed activity visible through pending and cancelled follow-up work', async () => {
    const wrapper = mount(AssistantTaskSidebar, { props: { task: baseTask } })
    expect(wrapper.text()).not.toContain('活动已写入')
    const written: AssistantTaskView = {
      ...baseTask,
      committed: [{ kind: 'customer_activity', public_id: 'activity_fictional', customer_id: 42 }],
      waiting: { type: 'CONFIRMATION', field: 'proposal:follow_up_task_create', question_id: 'q_next', prompt: '创建跟进任务？' }
    }
    await wrapper.setProps({ task: written })
    expect(wrapper.text()).toContain('活动已写入')
    expect(wrapper.text()).toContain('后续事项待确认')
    await wrapper.setProps({ task: { ...written, status: 'CANCELLED', waiting: null } })
    expect(wrapper.text()).toContain('活动已写入')
    await wrapper.setProps({ task: { ...baseTask, status: 'COMPLETED' } })
    expect(wrapper.text()).not.toContain('活动已写入')
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


  it('flags pending follow-up proposals in the hint', () => {
    const wrapper = mount(AssistantTaskSidebar, {
      props: {
        task: {
          ...baseTask,
          draft: { ...baseTask.draft, content: { status: 'ACCEPTED', value: '已写入' } },
          waiting: { type: 'CONFIRMATION', field: 'proposal:opportunity_create', question_id: 'q2', prompt: '创建商机？',
            confirmation_payload: { kind: 'proposal', proposal_kind: 'opportunity_create', candidate: {
              kind: 'opportunity_create', key: 'fictional-opportunity', payload: { opportunity_name: '虚构商机' },
              evidence_quote: '计划采购虚构系统', activity_id: 1, customer_id: 42, source_revision: 1
            } }
          }
        }
      }
    })
    expect(wrapper.text()).toContain('后续事项待确认')
  })

})

void vi
