// CRM-Client/src/components/__tests__/CollapsedView.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CollapsedView from '../CollapsedView.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('CollapsedView', () => {
  const mockSteps: ExecutionStep[] = [
    {
      id: 'step-1',
      type: ExecutionStepType.ROUND_START,
      title: '第 1 轮执行开始',
      description: '开始第 1 轮执行',
      timestamp: new Date('2026-01-01T10:00:00'),
      round: 1
    },
    {
      id: 'step-2',
      type: ExecutionStepType.TOOL_CALL,
      title: '查找客户信息',
      description: '正在搜索客户',
      timestamp: new Date('2026-01-01T10:00:05'),
      round: 1,
      tool: 'search_customer'
    }
  ]

  it('should display progress count "Round N/M"', () => {
    const wrapper = mount(CollapsedView, {
      props: { steps: mockSteps }
    })

    // ← 验证进度计数（设计要求）
    expect(wrapper.text()).toContain('Round 1/1')
  })

  it('should display current step title', () => {
    const wrapper = mount(CollapsedView, {
      props: { steps: mockSteps }
    })

    // ← 验证当前步骤显示
    expect(wrapper.text()).toContain('查找客户信息')
  })

  it('should show loading icon when running', () => {
    const wrapper = mount(CollapsedView, {
      props: { steps: mockSteps }
    })

    const icon = wrapper.find('.status-icon')
    expect(icon.classes()).toContain('is-running')
  })

  it('should emit toggle-expand event on click', async () => {
    const wrapper = mount(CollapsedView, {
      props: { steps: mockSteps }
    })

    await wrapper.find('.collapsed-view').trigger('click')

    expect(wrapper.emitted('toggle-expand')).toBeTruthy()
  })

  it('should support keyboard navigation (Enter/Space)', async () => {
    const wrapper = mount(CollapsedView, {
      props: { steps: mockSteps }
    })

    await wrapper.find('.collapsed-view').trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('toggle-expand')).toBeTruthy()
  })

  it('should have focus-visible style', () => {
    const wrapper = mount(CollapsedView, {
      props: { steps: mockSteps }
    })

    const view = wrapper.find('.collapsed-view')
    expect(view.attributes('tabindex')).toBe('0')
  })

  it('should use correct status colors', () => {
    // ← 思考中状态
    const thinkingSteps: ExecutionStep[] = [
      {
        id: 'step-1',
        type: ExecutionStepType.ROUND_START,
        title: '第 1 轮执行开始',
        description: '开始第 1 轮执行',
        timestamp: new Date('2026-01-01T10:00:00'),
        round: 1
      }
    ]
    const wrapperThinking = mount(CollapsedView, {
      props: { steps: thinkingSteps }
    })

    const iconThinking = wrapperThinking.find('.status-icon')
    expect(iconThinking.classes()).toContain('is-thinking')

    // ← 成功状态
    const successSteps: ExecutionStep[] = [
      {
        id: 'step-1',
        type: ExecutionStepType.ROUND_START,
        title: '第 1 轮执行开始',
        description: '开始第 1 轮执行',
        timestamp: new Date('2026-01-01T10:00:00'),
        round: 1
      },
      {
        id: 'step-2',
        type: ExecutionStepType.TOOL_RESULT,
        title: '工具执行完成',
        description: '执行成功',
        timestamp: new Date('2026-01-01T10:00:05'),
        round: 1,
        success: true
      }
    ]
    const wrapperSuccess = mount(CollapsedView, {
      props: { steps: successSteps }
    })

    const iconSuccess = wrapperSuccess.find('.status-icon')
    expect(iconSuccess.classes()).toContain('is-success')
  })
})