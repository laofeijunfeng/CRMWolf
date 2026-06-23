/**
 * AgentExecutionLog 组件测试（重构版）
 *
 * 重构后：AgentExecutionLog 成为容器组件，委托给 CompactExecutionLog
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentExecutionLog from '../AgentExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('AgentExecutionLog (重构后)', () => {
  const mockSteps: ExecutionStep[] = [
    {
      id: 'step-1',
      type: ExecutionStepType.TOOL_CALL,
      title: '查找客户信息',
      description: '正在搜索客户',
      timestamp: new Date(),
      round: 1,
      tool: 'search_customer'
    }
  ]

  describe('容器组件验证', () => {
    it('should use CompactExecutionLog component', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      // ← 验证使用新组件
      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      expect(compactLog.exists()).toBe(true)
    })

    it('should pass props correctly to CompactExecutionLog', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })

      // ← 验证 props 传递
      expect(compactLog.props('steps')).toEqual(mockSteps)
      expect(compactLog.props('expanded')).toBe(false)
    })

    it('should emit toggle-expand event', async () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      await compactLog.vm.$emit('toggle-expand')

      expect(wrapper.emitted('toggle-expand')).toBeTruthy()
    })
  })

  describe('空状态验证', () => {
    it('steps 为空时应该显示空状态（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: [],
          expanded: false
        }
      })

      // ← 验证 CompactExecutionLog 渲染了 EmptyState
      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const emptyState = compactLog.findComponent({ name: 'EmptyState' })
      expect(emptyState.exists()).toBe(true)
    })
  })

  describe('展开/收起状态验证', () => {
    it('expanded=false 时应该渲染 CollapsedView（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const collapsedView = compactLog.findComponent({ name: 'CollapsedView' })
      expect(collapsedView.exists()).toBe(true)
    })

    it('expanded=true 时应该渲染 ExpandedView（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: true
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const expandedView = compactLog.findComponent({ name: 'ExpandedView' })
      expect(expandedView.exists()).toBe(true)
    })
  })

  describe('ARIA 属性验证', () => {
    it('容器应该有正确的 ARIA 属性（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const container = compactLog.find('.agent-execution-log')

      expect(container.attributes('role')).toBe('log')
      expect(container.attributes('aria-label')).toBe('AI 执行进度')
    })
  })
})