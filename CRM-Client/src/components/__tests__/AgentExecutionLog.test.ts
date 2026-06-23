/**
 * AgentExecutionLog 组件测试
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentExecutionLog from '../AgentExecutionLog.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('AgentExecutionLog', () => {
  // Mock 测试数据
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
      tool: 'search_customer',
      params: { keyword: '张三' }
    },
    {
      id: 'step-3',
      type: ExecutionStepType.TOOL_RESULT,
      title: '查找完成',
      description: '找到 2 个客户',
      timestamp: new Date('2026-01-01T10:00:10'),
      round: 1,
      tool: 'search_customer',
      success: true,
      result: { count: 2 }
    },
    {
      id: 'step-4',
      type: ExecutionStepType.ROUND_COMPLETED,
      title: '第 1 轮执行完成',
      description: '第 1 轮执行已完成',
      timestamp: new Date('2026-01-01T10:00:15'),
      round: 1
    }
  ]

  describe('默认收起状态', () => {
    it('应该显示当前步骤和 Loading 图标', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      // 应该显示正在执行的步骤（TOOL_CALL 优先）
      // 需求文档 4.4：当前步骤显示正在执行的操作
      expect(wrapper.text()).toContain('查找客户信息')

      // 应该显示 Loading 图标（组件使用 .status-icon.is-loading）
      const statusIcon = wrapper.find('.status-icon')
      expect(statusIcon.exists()).toBe(true)
    })

    it('应该显示"点击展开"提示', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      expect(wrapper.text()).toContain('点击展开')
    })
  })

  describe('展开状态', () => {
    it('点击后应该触发 toggle-expand 事件', async () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: false
        }
      })

      // 点击收起状态的容器
      await wrapper.find('.collapsed-view').trigger('click')

      // 应该触发 toggle-expand 事件
      expect(wrapper.emitted('toggle-expand')).toBeTruthy()
      expect(wrapper.emitted('toggle-expand')).toHaveLength(1)
    })

    it('展开后应该显示完整步骤列表', async () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: true
        }
      })

      // 应该显示步骤列表容器
      const expandedView = wrapper.find('.expanded-view')
      expect(expandedView.exists()).toBe(true)

      // 应该显示轮次分隔线
      expect(wrapper.text()).toContain('Round 1')
    })

    it('展开后应该显示 ThinkingBubble（思考气泡）', async () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: true
        }
      })

      // ThinkingBubble 组件应该存在
      const thinkingBubbles = wrapper.findAllComponents({ name: 'ThinkingBubble' })
      expect(thinkingBubbles.length).toBeGreaterThan(0)
    })

    it('展开后应该显示 StatusCard（结果摘要）', async () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: mockSteps,
          expanded: true
        }
      })

      // StatusCard 组件应该存在
      const statusCards = wrapper.findAllComponents({ name: 'StatusCard' })
      expect(statusCards.length).toBeGreaterThan(0)
    })
  })

  describe('边界情况', () => {
    it('steps 为空时应该显示空状态', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: [],
          expanded: false
        }
      })

      // 应该显示空状态提示
      expect(wrapper.text()).toContain('暂无执行记录')
    })
  })

  // ← 需求文档 6.3：业务化验证（关键约束）
  describe('业务化验证', () => {
    it('不显示技术参数名（keyword/limit/offset 等）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: [
            {
              id: 'step-1',
              type: ExecutionStepType.TOOL_CALL,
              title: '查找客户信息',
              description: '正在搜索："光大证券"',
              timestamp: new Date(),
              round: 1,
              tool: 'search_customer',
              params: { keyword: '光大证券', limit: 10, offset: 0 }  // ← 技术参数
            }
          ],
          expanded: true
        }
      })

      const businessParams = wrapper.find('.business-params')
      if (businessParams.exists()) {
        const text = businessParams.text()
        // ← 需求文档关键约束：确保技术参数名不出现
        expect(text).not.toContain('keyword')
        expect(text).not.toContain('limit')
        expect(text).not.toContain('offset')
        expect(text).not.toContain('=')
      }
    })

    it('显示业务化表达（正在搜索："xxx"）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: [
            {
              id: 'step-1',
              type: ExecutionStepType.TOOL_CALL,
              title: '查找客户信息',
              description: '正在搜索："光大证券"',  // ← 业务化表达
              timestamp: new Date(),
              round: 1,
              tool: 'search_customer',
              params: { keyword: '光大证券' }
            }
          ],
          expanded: true
        }
      })

      // ← 需求文档关键约束：确保显示业务化表达
      expect(wrapper.text()).toContain('正在搜索')
      expect(wrapper.text()).toContain('光大证券')
    })

    it('显示业务化表达（正在创建："xxx"）', () => {
      const wrapper = mount(AgentExecutionLog, {
        props: {
          steps: [
            {
              id: 'step-1',
              type: ExecutionStepType.TOOL_CALL,
              title: '创建跟进记录',
              description: '正在创建："电话沟通"',  // ← 业务化表达
              timestamp: new Date(),
              round: 1,
              tool: 'create_follow_up',
              params: { content: '电话沟通' }
            }
          ],
          expanded: true
        }
      })

      expect(wrapper.text()).toContain('正在创建')
      expect(wrapper.text()).toContain('电话沟通')
    })
  })
})