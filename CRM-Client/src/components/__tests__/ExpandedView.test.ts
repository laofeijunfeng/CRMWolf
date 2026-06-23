// CRM-Client/src/components/__tests__/ExpandedView.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ExpandedView from '../ExpandedView.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('ExpandedView', () => {
  const mockSteps: ExecutionStep[] = [
    {
      id: 'step-1',
      type: ExecutionStepType.ROUND_START,
      title: '第 1 轮执行开始',
      description: '',
      timestamp: new Date('2026-01-01T10:00:00'),
      round: 1
    },
    {
      id: 'step-2',
      type: ExecutionStepType.TOOL_CALL,
      title: '查找客户信息',
      description: '正在搜索："光大证券"',
      timestamp: new Date('2026-01-01T10:00:05'),
      round: 1,
      tool: 'search_customer',
      params: { keyword: '光大证券' }
    },
    {
      id: 'step-3',
      type: ExecutionStepType.TOOL_RESULT,
      title: '查找完成',
      description: '找到 2 个客户',
      timestamp: new Date('2026-01-01T10:00:10'),
      round: 1,
      success: true
    }
  ]

  it('should display round separators', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    // ← 验证轮次分隔线
    expect(wrapper.text()).toContain('Round 1')
  })

  it('should display ThinkingBubble for TOOL_CALL steps', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    // ← 验证 ThinkingBubble 组件存在
    const thinkingBubbles = wrapper.findAllComponents({ name: 'ThinkingBubble' })
    expect(thinkingBubbles.length).toBeGreaterThan(0)
  })

  it('should display StatusCard for TOOL_RESULT steps', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    // ← 验证 StatusCard 组件存在
    const statusCards = wrapper.findAllComponents({ name: 'StatusCard' })
    expect(statusCards.length).toBeGreaterThan(0)
  })

  it('should emit toggle-expand event when clicking collapse button', async () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    await wrapper.find('.collapse-button').trigger('click')

    expect(wrapper.emitted('toggle-expand')).toBeTruthy()
  })

  it('should support keyboard navigation (Escape to collapse)', async () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    await wrapper.find('.expanded-view').trigger('keydown', { key: 'Escape' })

    expect(wrapper.emitted('toggle-expand')).toBeTruthy()
  })

  it('should display business-params (业务化表达)', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    // ← 验证业务化表达显示
    expect(wrapper.text()).toContain('正在搜索')
    expect(wrapper.text()).toContain('光大证券')

    // ← 验证技术参数名不出现（需求文档关键约束）
    expect(wrapper.text()).not.toContain('keyword')
  })

  it('should have focus-visible style for step items', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    const stepItems = wrapper.findAll('.step-item')
    expect(stepItems.length).toBeGreaterThan(0)

    // ← 验证 tabindex 属性
    const firstStepItem = stepItems[0]
    expect(firstStepItem).toBeDefined()
    expect(firstStepItem?.attributes('tabindex')).toBe('0')
  })

  it('should have correct ARIA attributes', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    const view = wrapper.find('.expanded-view')
    expect(view.attributes('aria-live')).toBe('polite')
  })
})