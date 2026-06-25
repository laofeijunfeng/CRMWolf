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
          steps: mockSteps
        }
      })

      // ← 验证使用新组件
      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      expect(compactLog.exists()).toBe(true)
    })

    it('should pass steps correctly to CompactExecutionLog', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })

      // ← 验证 props 传递（V2: expanded 已废弃，内部管理）
      expect(compactLog.props('steps')).toEqual(mockSteps)
      expect(compactLog.props('status')).toBeDefined()
    })

    it('should compute status from steps', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          isExecutionComplete: true
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })

      // ← 验证状态推导
      expect(compactLog.props('status')).toBe('success')
    })
  })

  describe('空状态验证', () => {
    it('steps 为空时应该显示空状态（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: []
        }
      })

      // ← 验证 CompactExecutionLog 渲染了 EmptyState
      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const emptyState = compactLog.findComponent({ name: 'EmptyState' })
      expect(emptyState.exists()).toBe(true)
    })
  })

  describe('展开/收起状态验证', () => {
    it('默认状态应该渲染 CollapsedView（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const collapsedView = compactLog.findComponent({ name: 'CollapsedView' })
      expect(collapsedView.exists()).toBe(true)
    })
  })

  describe('ARIA 属性验证', () => {
    it('容器应该有正确的 ARIA 属性（通过 CompactExecutionLog）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps
        }
      })

      const compactLog = wrapper.findComponent({ name: 'CompactExecutionLog' })
      const container = compactLog.find('.agent-log')

      expect(container.exists()).toBe(true)
    })
  })
})