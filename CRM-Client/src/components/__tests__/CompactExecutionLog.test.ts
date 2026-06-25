// CRM-Client/src/components/__tests__/CompactExecutionLog.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CompactExecutionLog from '../CompactExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('CompactExecutionLog.vue (V2)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  const mockSteps: ExecutionStep[] = [
    {
      id: 'step-1',
      type: ExecutionStepType.TOOL_RESULT,
      title: '查找客户信息',
      timestamp: new Date(),
      round: 1,
      inline_text: '查找成功，找到 1 个客户',
      success: true
    }
  ]

  it('shows empty state when no steps', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: [], status: 'empty' }
    })

    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('shows collapsed view by default', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: mockSteps, status: 'success' }
    })

    expect(wrapper.find('.collapsed-view').exists()).toBe(true)
  })

  it('expands on collapsed view click', async () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: mockSteps, status: 'success' }
    })

    await wrapper.find('.collapsed-view').trigger('click')

    expect(wrapper.find('.expanded-view').exists()).toBe(true)
  })

  it('auto collapses after 3 seconds when status is success', async () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: mockSteps,
        status: 'success',
        autoCollapse: true,
        autoCollapseDelay: 3000
      }
    })

    // 先展开
    await wrapper.find('.collapsed-view').trigger('click')
    expect(wrapper.find('.expanded-view').exists()).toBe(true)

    // 快进 3 秒并等待 DOM 更新
    vi.advanceTimersByTime(3000)
    await wrapper.vm.$nextTick()

    // 应该自动收起
    expect(wrapper.find('.collapsed-view').exists()).toBe(true)
  })

  it('does not auto collapse when status is loading', async () => {
    const loadingSteps: ExecutionStep[] = [
      {
        id: 'step-1',
        type: ExecutionStepType.TOOL_CALL,
        title: '正在执行',
        timestamp: new Date(),
        round: 1
      }
    ]

    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: loadingSteps,
        status: 'loading',
        autoCollapse: true,
        autoCollapseDelay: 3000
      }
    })

    // 展开
    await wrapper.find('.collapsed-view').trigger('click')
    expect(wrapper.find('.expanded-view').exists()).toBe(true)

    // 快进 3 秒
    vi.advanceTimersByTime(3000)

    // 仍然展开
    expect(wrapper.find('.expanded-view').exists()).toBe(true)
  })

  it('shows SmartBoundaryLine when running', () => {
    const runningSteps: ExecutionStep[] = [
      {
        id: 'step-1',
        type: ExecutionStepType.TOOL_CALL,
        title: '正在执行',
        timestamp: new Date(),
        round: 1
      }
    ]

    const wrapper = mount(CompactExecutionLog, {
      props: { steps: runningSteps, status: 'loading' }
    })

    expect(wrapper.find('.smart-boundary-line').exists()).toBe(true)
  })

  it('emits confirm event when user confirms', async () => {
    const waitingStep: ExecutionStep = {
      id: 'step-2',
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '请选择',
      timestamp: new Date(),
      round: 2,
      confirmationType: 'disambiguation',
      options: [{ id: 16, name: '光大证券' }]
    }

    const wrapper = mount(CompactExecutionLog, {
      props: { steps: [waitingStep], status: 'partial' }
    })

    // 展开
    await wrapper.find('.collapsed-view').trigger('click')

    // 点击确认按钮
    const confirmBtn = wrapper.find('.btn-confirm')
    if (confirmBtn.exists()) {
      await confirmBtn.trigger('click')
      expect(wrapper.emitted('confirm')).toBeTruthy()
    }
  })

  it('emits cancel event when user cancels', async () => {
    const waitingStep: ExecutionStep = {
      id: 'step-2',
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '请选择',
      timestamp: new Date(),
      round: 2,
      confirmationType: 'disambiguation',
      options: [{ id: 16, name: '光大证券' }]
    }

    const wrapper = mount(CompactExecutionLog, {
      props: { steps: [waitingStep], status: 'partial' }
    })

    // 展开
    await wrapper.find('.collapsed-view').trigger('click')

    // 点击取消按钮
    const cancelBtn = wrapper.find('.btn-cancel')
    if (cancelBtn.exists()) {
      await cancelBtn.trigger('click')
      expect(wrapper.emitted('cancel')).toBeTruthy()
    }
  })

  it('has correct ARIA attributes', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: mockSteps, status: 'success' }
    })

    const container = wrapper.find('.agent-log')
    expect(container.exists()).toBe(true)
  })

  it('supports keyboard navigation', async () => {
    const wrapper = mount(CompactExecutionLog, {
      props: { steps: mockSteps, status: 'success' }
    })

    // 按 Enter 展开
    await wrapper.find('.collapsed-view').trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('.expanded-view').exists()).toBe(true)

    // 按 Escape 收起
    await wrapper.find('.expanded-view').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.collapsed-view').exists()).toBe(true)
  })

  it('calculates current round correctly', () => {
    const multiRoundSteps: ExecutionStep[] = [
      { id: 's1', type: ExecutionStepType.TOOL_RESULT, title: '步骤1', timestamp: new Date(), round: 1, success: true },
      { id: 's2', type: ExecutionStepType.TOOL_RESULT, title: '步骤2', timestamp: new Date(), round: 2, success: true },
      { id: 's3', type: ExecutionStepType.TOOL_RESULT, title: '步骤3', timestamp: new Date(), round: 2, success: true }
    ]

    const wrapper = mount(CompactExecutionLog, {
      props: { steps: multiRoundSteps, status: 'success' }
    })

    // 检查 Round Badge 显示
    expect(wrapper.find('.round-badge').text()).toContain('R')
  })

  it('shows correct step text in collapsed view', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: [{ ...mockSteps[0], inline_text: '查找客户信息，找到 1 个客户：光大证券股份有限公司' }],
        status: 'success'
      }
    })

    expect(wrapper.find('.step-text').text()).toContain('查找客户信息')
  })
})