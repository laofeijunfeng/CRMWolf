/**
 * AIAssistant.vue 与 AgentExecutionLog 集成测试
 *
 * 测试目标：验证 AgentExecutionLog 在执行完成后仍然可见
 * Bug：当前 v-if="executionSteps.length > 0 && sending" 导致执行完成后组件消失
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AIAssistant from '@/views/AIAssistant.vue'
import { createPinia, setActivePinia } from 'pinia'

// Mock API
vi.mock('@/api/aiAssistant', () => ({
  aiAssistantApi: {
    chatSSE: vi.fn()
  }
}))

describe('AIAssistant - AgentExecutionLog Integration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('Bug Fix: AgentExecutionLog should remain visible after execution completes', () => {
    it('执行完成后，AgentExecutionLog 应该仍然可见（可展开查看）', async () => {
      /**
       * 测试场景：
       * 1. 用户发送消息
       * 2. Agent 执行（sending=true, executionSteps 有数据）
       * 3. Agent 完成（sending=false, executionSteps 仍有数据）
       * 4. AgentExecutionLog 应该仍然可见（需求文档要求）
       *
       * 当前 Bug：
       * v-if="executionSteps.length > 0 && sending"
       * → sending=false 时组件消失
       *
       * 期望行为：
       * v-if="executionSteps.length > 0"
       * → 执行完成后组件仍然显示，用户可以展开查看
       */

      const wrapper = mount(AIAssistant, {
        global: {
          plugins: [createPinia()],
          stubs: {
            HistoryList: true,
            WelcomeScreen: true,
            ChatInput: true,
            ChatBubble: true,
            PreviewCard: true
          }
        }
      })

      // 模拟执行完成状态
      // executionSteps 有数据，但 sending=false
      const executionSteps = [
        {
          id: 'step-1',
          type: 'round_start',
          title: '第 1 轮执行',
          description: '开始执行',
          timestamp: new Date()
        },
        {
          id: 'step-2',
          type: 'tool_call',
          title: '查找客户',
          description: '正在搜索客户',
          timestamp: new Date()
        },
        {
          id: 'step-3',
          type: 'tool_result',
          title: '执行成功',
          description: '找到客户',
          timestamp: new Date()
        },
        {
          id: 'step-4',
          type: 'react_complete',
          title: '执行完成',
          description: '已完成',
          timestamp: new Date()
        }
      ]

      // 设置组件状态（模拟执行完成）
      // 注意：这需要访问组件内部状态，可能需要调整
      await wrapper.setData({
        // executionSteps 来自 useAgentExecutionLog composable
        // 这里需要通过某种方式注入
      })

      // 验证：AgentExecutionLog 应该存在
      const agentExecutionLog = wrapper.findComponent({ name: 'AgentExecutionLog' })

      /**
       * 当前 Bug：这个测试会失败
       * 因为 v-if 包含 sending 条件
       * 当 sending=false 时，组件不渲染
       */
      expect(agentExecutionLog.exists()).toBe(true)
    })

    it('需求文档验证：react_complete 后显示完成状态', async () => {
      /**
       * 需求文档 4.5：
       * react_complete → 显示完成状态
       *
       * 这意味着执行完成后，AgentExecutionLog 应该显示"执行完成"
       * 而不是消失
       */

      const wrapper = mount(AIAssistant, {
        global: {
          plugins: [createPinia()],
          stubs: {
            HistoryList: true,
            WelcomeScreen: true,
            ChatInput: true,
            ChatBubble: true,
            PreviewCard: true
          }
        }
      })

      // 模拟 react_complete 状态
      // executionSteps 包含 REACT_COMPLETE 步骤
      // sending=false

      // 验证：AgentExecutionLog 应该显示"执行完成"
      const agentExecutionLog = wrapper.findComponent({ name: 'AgentExecutionLog' })
      expect(agentExecutionLog.exists()).toBe(true)

      // 验证：应该显示完成状态（收起状态）
      // 需求文档：收起状态显示当前步骤 + 图标
      // 当前步骤应该是 "执行完成"
      expect(agentExecutionLog.text()).toContain('执行完成')
    })
  })
})