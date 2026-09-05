import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { AgentAsyncOperation, AgentAsyncOperationStatus } from '@/api/agent'

import AgentAsyncOperationCard from '../AgentAsyncOperationCard.vue'

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
  it('distinguishes a completed operation that needs verification', async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: {
        operation: makeOperation('DEGRADED', {
          summary: '客户档案已更新',
        }),
      },
    })

    expect(wrapper.text()).toContain('已完成，待核查')

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('已完成，但部分结果待核查')
    expect(wrapper.text()).toContain('客户档案已更新，部分结果待核查。')
  })

  it('shows the current step and finished time without runtime internals', async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: {
        operation: makeOperation('SUCCEEDED', {
          current_step: '同步客户画像',
          finished_time: '2026-09-05T12:34:56Z',
        }),
      },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('当前阶段')
    expect(wrapper.text()).toContain('同步客户画像')
    expect(wrapper.text()).toContain('完成时间：')
    expect(wrapper.text()).not.toContain('graph_thread_id')
    expect(wrapper.text()).not.toContain('checkpoint')
  })

  it('explains that a failed operation was not completed', async () => {
    const wrapper = mount(AgentAsyncOperationCard, {
      props: {
        operation: makeOperation('FAILED', {
          error_message: '客户数据暂时不可用',
        }),
      },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('未完成，请根据原因处理')
    expect(wrapper.text()).toContain('客户数据暂时不可用')
  })
})
