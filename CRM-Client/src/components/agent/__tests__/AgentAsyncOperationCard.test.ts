import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { AgentAsyncOperation, AgentAsyncOperationStatus } from '@/api/agent'

import AgentAsyncOperationCard from '../AgentAsyncOperationCard.vue'
import { getAgentAsyncOperationStatusMeta } from '../agentAsyncOperations'

const makeOperation = (
  status: AgentAsyncOperationStatus,
  overrides: Partial<AgentAsyncOperation> = {},
): AgentAsyncOperation => ({
  public_id: 'operation-1',
  request_id: 'request-1',
  team_id: 1,
  user_id: 1,
  session_id: 1,
  source_user_message_id: 1,
  source_assistant_message_id: 2,
  operation_type: 'customer_intelligence_refresh',
  resource_type: 'customer',
  resource_id: 1,
  resource_public_id: 'customer-1',
  status,
  summary: null,
  current_step: null,
  graph_thread_id: null,
  result: {},
  error_message: null,
  started_time: null,
  finished_time: null,
  next_retry_at: null,
  attempt_count: 0,
  created_time: '2026-09-05T10:00:00Z',
  updated_time: '2026-09-05T10:00:00Z',
  events: [],
  ...overrides,
})

describe('AgentAsyncOperationCard', () => {
  it('updates accessible status when an active operation completes with verification needed', async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: { operation: makeOperation('RUNNING') },
    })
    const trigger = wrapper.get('button')
    expect(trigger.attributes('aria-label')).toContain(getAgentAsyncOperationStatusMeta('RUNNING').label)

    await wrapper.setProps({
      operation: makeOperation('DEGRADED', { summary: '客户智能处理已更新' }),
    })

    expect(trigger.attributes('aria-label')).toContain(getAgentAsyncOperationStatusMeta('DEGRADED').label)
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.text()).not.toContain('客户智能处理已更新')
    await trigger.trigger('click')
    expect(wrapper.get('.agent-async-operation__details').text()).toBe('客户智能处理已更新')
    wrapper.unmount()
  })

  it('discloses only public progress messages instead of internal steps and lifecycle events', async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: {
        operation: makeOperation('SUCCEEDED', {
          summary: '后台摘要',
          current_step: 'refresh_customer_brief',
          graph_thread_id: 'private-thread-id',
          events: [
            {
              sequence: 1, event_key: 'started', event_type: 'STARTED',
              status: 'RUNNING',
              step: 'private-step', message: '内部生命周期事件', payload: {},
              occurred_at: '2026-09-05T10:00:00Z',
            },
            {
              sequence: 2, event_key: 'progress', event_type: 'PROGRESS',
              status: 'RUNNING',
              step: 'private-step', message: '客户画像同步完成', payload: {},
              occurred_at: '2026-09-05T10:00:01Z',
            },
          ],
        }),
      },
    })

    await wrapper.get('button').trigger('click')
    expect(wrapper.findAll('ol li').map(event => event.text())).toEqual(['客户画像同步完成'])
    expect(wrapper.text()).not.toContain('内部生命周期事件')
    expect(wrapper.text()).not.toContain('refresh_customer_brief')
    expect(wrapper.text()).not.toContain('private-thread-id')
    expect(wrapper.text()).not.toContain('后台摘要')
    wrapper.unmount()
  })

  it('reveals a failure reason only on disclosure and updates when the operation is cancelled', async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: { operation: makeOperation('FAILED', { error_message: '客户数据暂时不可用' }) },
    })

    expect(wrapper.text()).not.toContain('客户数据暂时不可用')
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('.agent-async-operation__notice').text()).toBe('客户数据暂时不可用')

    await wrapper.setProps({ operation: makeOperation('CANCELLED', { summary: '用户取消了任务' }) })
    expect(wrapper.get('button').attributes('aria-label')).toContain(getAgentAsyncOperationStatusMeta('CANCELLED').label)
    expect(wrapper.get('.agent-async-operation__details').text()).toBe('用户取消了任务')
    expect(wrapper.find('.agent-async-operation__notice').exists()).toBe(false)
    wrapper.unmount()
  })
})
