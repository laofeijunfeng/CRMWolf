// CRM-Client/src/components/__tests__/CompactExecutionLog.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CompactExecutionLog from '../CompactExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('CompactExecutionLog', () => {
  const mockSteps: ExecutionStep[] = [
    {
      id: 'step-1',
      type: ExecutionStepType.TOOL_CALL,
      title: '查找客户信息',
      description: '用户想跟进光大证券，需要先找到客户',
      timestamp: new Date(),
      round: 1
    }
  ]

  it('should show EmptyState when steps.length === 0', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: [],
        expanded: false
      }
    })

    // ← 验证空状态组件
    const emptyState = wrapper.findComponent({ name: 'EmptyState' })
    expect(emptyState.exists()).toBe(true)
  })

  it('should show CollapsedView when steps.length > 0 && !expanded', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: mockSteps,
        expanded: false
      }
    })

    // ← 验证收起状态组件
    const collapsedView = wrapper.findComponent({ name: 'CollapsedView' })
    expect(collapsedView.exists()).toBe(true)
  })

  it('should show ExpandedView when steps.length > 0 && expanded', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: mockSteps,
        expanded: true
      }
    })

    // ← 验证展开状态组件
    const expandedView = wrapper.findComponent({ name: 'ExpandedView' })
    expect(expandedView.exists()).toBe(true)
  })

  it('should show SmartBoundaryLine when steps.length > 0 && isRunning', () => {
    const runningSteps = [
      { ...mockSteps[0], type: ExecutionStepType.TOOL_CALL }
    ]

    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: runningSteps,
        expanded: false
      }
    })

    // ← 验证智能边界线（Signature 元素）
    const boundaryLine = wrapper.findComponent({ name: 'SmartBoundaryLine' })
    expect(boundaryLine.exists()).toBe(true)
    expect(boundaryLine.props('active')).toBe(true)
  })

  it('should emit toggle-expand event from child components', async () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: mockSteps,
        expanded: false
      }
    })

    // ← 模拟子组件触发 toggle-expand
    const collapsedView = wrapper.findComponent({ name: 'CollapsedView' })
    await collapsedView.vm.$emit('toggle-expand')

    expect(wrapper.emitted('toggle-expand')).toBeTruthy()
  })

  it('should have correct ARIA attributes on container', () => {
    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: mockSteps,
        expanded: false
      }
    })

    const container = wrapper.find('.agent-execution-log')
    expect(container.attributes('role')).toBe('log')
    expect(container.attributes('aria-label')).toBe('AI 执行进度')
  })

  it('should not show SmartBoundaryLine when not running', () => {
    const completedSteps = [
      { ...mockSteps[0], type: ExecutionStepType.TOOL_RESULT, success: true }
    ]

    const wrapper = mount(CompactExecutionLog, {
      props: {
        steps: completedSteps,
        expanded: false
      }
    })

    // ← 验证智能边界线不显示
    const boundaryLine = wrapper.findComponent({ name: 'SmartBoundaryLine' })
    expect(boundaryLine.exists()).toBe(false)
  })
})