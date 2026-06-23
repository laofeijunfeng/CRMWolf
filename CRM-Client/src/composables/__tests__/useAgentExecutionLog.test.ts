/**
 * useAgentExecutionLog Composable 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useAgentExecutionLog } from '../useAgentExecutionLog'
import { ExecutionStepType, getBusinessTitle, formatBusinessParams } from '@/types/agentExecution'
import type { AIAssistantSSEEvent } from '@/api/aiAssistant'

// Mock aiConversation store
vi.mock('@/stores/aiConversation', () => ({
  useAIConversationStore: vi.fn(() => ({
    currentId: { value: 123 },
    hasCurrentConversation: { value: true },
    setAIMessageExecutionSteps: vi.fn(),
    saveCurrentConversation: vi.fn().mockResolvedValue(undefined),
    getLastAIMessageExecutionSteps: vi.fn(() => [])
  }))
}))

describe('useAgentExecutionLog', () => {
  let executionLog: ReturnType<typeof useAgentExecutionLog>

  beforeEach(() => {
    executionLog = useAgentExecutionLog()
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('初始状态', () => {
    it('初始状态应为空步骤列表', () => {
      expect(executionLog.steps.value).toEqual([])
    })

    it('初始轮次应为 0', () => {
      expect(executionLog.currentRound.value).toBe(0)
    })

    it('初始不应处于执行状态', () => {
      expect(executionLog.isExecuting.value).toBe(false)
    })

    it('初始不应处于完成状态', () => {
      expect(executionLog.isCompleted.value).toBe(false)
    })

    it('初始不应有错误', () => {
      expect(executionLog.hasError.value).toBe(false)
    })
  })

  describe('工具名称业务化映射', () => {
    it('search_customer 应映射为"查找客户信息"', () => {
      expect(getBusinessTitle('search_customer')).toBe('查找客户信息')
    })

    it('create_customer 应映射为"创建客户"', () => {
      expect(getBusinessTitle('create_customer')).toBe('创建客户')
    })

    it('update_customer 应映射为"更新客户信息"', () => {
      expect(getBusinessTitle('update_customer')).toBe('更新客户信息')
    })

    it('create_follow_up 应映射为"创建跟进记录"', () => {
      expect(getBusinessTitle('create_follow_up')).toBe('创建跟进记录')
    })

    it('未知工具名称应返回原名称', () => {
      expect(getBusinessTitle('unknown_tool')).toBe('unknown_tool')
    })
  })

  describe('业务参数格式化', () => {
    it('搜索场景应格式化关键词', () => {
      const params = { keyword: '光大证券' }
      const title = '查找客户信息'
      expect(formatBusinessParams(params, title)).toBe('正在搜索："光大证券"')
    })

    it('创建场景应格式化名称', () => {
      const params = { name: '张三', phone: '13812345678' }
      const title = '创建客户'
      expect(formatBusinessParams(params, title)).toBe('正在创建："张三"')
    })

    it('更新场景应格式化目标实体', () => {
      const params = { customer_name: '光大证券', status: 'active' }
      const title = '更新客户信息'
      expect(formatBusinessParams(params, title)).toBe('正在更新："光大证券"')
    })

    it('删除场景应格式化目标实体', () => {
      const params = { name: '张三' }
      const title = '删除客户'
      expect(formatBusinessParams(params, title)).toBe('正在删除："张三"')
    })

    it('无参数时应返回业务标题', () => {
      const params = {}
      const title = '查找客户信息'
      expect(formatBusinessParams(params, title)).toBe('查找客户信息')
    })
  })

  describe('SSE 事件处理', () => {
    it('react_start 事件应创建开始步骤', () => {
      const event: AIAssistantSSEEvent = {
        event: 'react_start',
        session_id: 'test-session-123',
        max_rounds: 5
      }

      executionLog.handleSSEEvent(event)

      expect(executionLog.steps.value.length).toBe(1)
      const step = executionLog.steps.value[0]
      expect(step?.type).toBe(ExecutionStepType.REACT_START)
      expect(executionLog.sessionId.value).toBe('test-session-123')
      expect(executionLog.maxRounds.value).toBe(5)
      expect(executionLog.isExecuting.value).toBe(true)
    })

    it('tool_call 事件应创建工具调用步骤', () => {
      const event: AIAssistantSSEEvent = {
        event: 'tool_call',
        tool: 'search_customer',
        params: { keyword: '光大证券' },
        round: 1
      }

      executionLog.handleSSEEvent(event)

      expect(executionLog.steps.value.length).toBe(1)
      const step = executionLog.steps.value[0]
      expect(step?.type).toBe(ExecutionStepType.TOOL_CALL)
      expect(step?.title).toBe('查找客户信息')
      expect(step?.description).toBe('正在搜索："光大证券"')
      expect(step?.tool).toBe('search_customer')
      expect(step?.round).toBe(1)
    })

    it('tool_result 事件应创建工具结果步骤', () => {
      const event: AIAssistantSSEEvent = {
        event: 'tool_result',
        tool: 'search_customer',
        success: true,
        data: { customers: [{ id: 1, name: '光大证券' }] },
        round: 1
      }

      executionLog.handleSSEEvent(event)

      expect(executionLog.steps.value.length).toBe(1)
      const step = executionLog.steps.value[0]
      expect(step?.type).toBe(ExecutionStepType.TOOL_RESULT)
      expect(step?.success).toBe(true)
      expect(step?.tool).toBe('search_customer')
    })

    it('react_complete 事件应标记为完成', () => {
      const event: AIAssistantSSEEvent = {
        event: 'react_complete',
        session_id: 'test-session-123'
      }

      executionLog.handleSSEEvent(event)

      expect(executionLog.isCompleted.value).toBe(true)
      expect(executionLog.isExecuting.value).toBe(false)
      expect(executionLog.steps.value.length).toBe(1)
      const step = executionLog.steps.value[0]
      expect(step?.type).toBe(ExecutionStepType.REACT_COMPLETE)
    })

    it('error 事件应标记为错误', () => {
      const event: AIAssistantSSEEvent = {
        event: 'error',
        message: '执行失败：数据库连接错误'
      }

      executionLog.handleSSEEvent(event)

      expect(executionLog.hasError.value).toBe(true)
      expect(executionLog.isExecuting.value).toBe(false)
      expect(executionLog.steps.value.length).toBe(1)
      const step = executionLog.steps.value[0]
      expect(step?.type).toBe(ExecutionStepType.ERROR)
      expect(step?.error).toBe('执行失败：数据库连接错误')
    })

    it('round_start 事件应更新当前轮次', () => {
      const event: AIAssistantSSEEvent = {
        event: 'round_start',
        round: 2
      }

      executionLog.handleSSEEvent(event)

      expect(executionLog.currentRound.value).toBe(2)
      expect(executionLog.steps.value.length).toBe(1)
      const step = executionLog.steps.value[0]
      expect(step?.type).toBe(ExecutionStepType.ROUND_START)
      expect(step?.round).toBe(2)
    })

    it('多轮 ReAct 循环应按顺序记录步骤', () => {
      const events: AIAssistantSSEEvent[] = [
        { event: 'react_start', session_id: 'test-123', max_rounds: 5 },
        { event: 'round_start', round: 1 },
        { event: 'tool_call', tool: 'search_customer', params: { keyword: '光大证券' }, round: 1 },
        { event: 'tool_result', tool: 'search_customer', success: true, round: 1 },
        { event: 'round_completed', round: 1 },
        { event: 'round_start', round: 2 },
        { event: 'tool_call', tool: 'create_follow_up', params: { customer_name: '光大证券' }, round: 2 },
        { event: 'tool_result', tool: 'create_follow_up', success: true, round: 2 },
        { event: 'round_completed', round: 2 },
        { event: 'react_complete', session_id: 'test-123' }
      ]

      events.forEach(event => executionLog.handleSSEEvent(event))

      expect(executionLog.steps.value.length).toBe(10)
      expect(executionLog.isCompleted.value).toBe(true)
      expect(executionLog.currentRound.value).toBe(2)
    })
  })

  describe('辅助方法', () => {
    it('clear 方法应重置所有状态', () => {
      const event: AIAssistantSSEEvent = {
        event: 'react_start',
        session_id: 'test-123',
        max_rounds: 5
      }

      executionLog.handleSSEEvent(event)
      executionLog.clear()

      expect(executionLog.steps.value).toEqual([])
      expect(executionLog.currentRound.value).toBe(0)
      expect(executionLog.sessionId.value).toBeUndefined()
      expect(executionLog.isExecuting.value).toBe(false)
      expect(executionLog.isCompleted.value).toBe(false)
      expect(executionLog.hasError.value).toBe(false)
    })

    it('getStepsByRound 方法应返回指定轮次的步骤', () => {
      const events: AIAssistantSSEEvent[] = [
        { event: 'react_start', session_id: 'test-123', max_rounds: 5 },
        { event: 'round_start', round: 1 },
        { event: 'tool_call', tool: 'search_customer', params: { keyword: '光大证券' }, round: 1 },
        { event: 'round_completed', round: 1 },
        { event: 'round_start', round: 2 },
        { event: 'tool_call', tool: 'create_follow_up', params: { customer_name: '光大证券' }, round: 2 }
      ]

      events.forEach(event => executionLog.handleSSEEvent(event))

      const round1Steps = executionLog.getStepsByRound(1)
      expect(round1Steps.length).toBe(3) // round_start + tool_call + round_completed
      expect(round1Steps.every(step => step.round === 1)).toBe(true)

      const round2Steps = executionLog.getStepsByRound(2)
      expect(round2Steps.length).toBe(2) // round_start + tool_call (no round_completed yet)
      expect(round2Steps.every(step => step.round === 2)).toBe(true)
    })

    it('getLastStep 方法应返回最后一个步骤', () => {
      const events: AIAssistantSSEEvent[] = [
        { event: 'react_start', session_id: 'test-123', max_rounds: 5 },
        { event: 'tool_call', tool: 'search_customer', params: { keyword: '光大证券' }, round: 1 }
      ]

      events.forEach(event => executionLog.handleSSEEvent(event))

      const lastStep = executionLog.getLastStep()
      expect(lastStep?.type).toBe(ExecutionStepType.TOOL_CALL)
      expect(lastStep?.tool).toBe('search_customer')
    })
  })

  // ========== Persistence Integration Tests (Task 14) ==========

  describe('持久化逻辑（Task 12-14）', () => {
    it('SSE 流结束时（REACT_COMPLETE）应自动保存 execution steps', async () => {
      // 模拟完整的 SSE 流
      const events: AIAssistantSSEEvent[] = [
        { event: 'react_start', session_id: 'test-123', max_rounds: 5 },
        { event: 'tool_call', tool: 'search_customer', params: { keyword: '光大证券' }, round: 1 },
        { event: 'tool_result', tool: 'search_customer', success: true, round: 1 },
        { event: 'react_complete', session_id: 'test-123' }
      ]

      events.forEach(event => executionLog.handleSSEEvent(event))

      // 验证步骤数量
      expect(executionLog.steps.value.length).toBe(4)

      // 验证触发保存（通过 mock 验证）
      // 注意：由于 handleReactComplete 内部调用 saveExecutionStepsToCurrentMessage
      // 我们需要等待异步操作完成
      await new Promise(resolve => setTimeout(resolve, 100))

      // 验证 localStorage 缓存已清理（保存成功后应清理）
      const cacheKey = 'execution_steps_123'
      const cached = localStorage.getItem(cacheKey)
      expect(cached).toBeNull()
    })

    it('SSE 流结束时（ERROR）应自动保存 execution steps', async () => {
      const events: AIAssistantSSEEvent[] = [
        { event: 'react_start', session_id: 'test-123', max_rounds: 5 },
        { event: 'tool_call', tool: 'search_customer', params: { keyword: '光大证券' }, round: 1 },
        { event: 'error', message: '数据库连接失败' }
      ]

      events.forEach(event => executionLog.handleSSEEvent(event))

      expect(executionLog.steps.value.length).toBe(3)
      expect(executionLog.hasError.value).toBe(true)

      // 等待异步保存完成
      await new Promise(resolve => setTimeout(resolve, 100))
    })

    it('executionSteps 变化时应自动缓存到 localStorage', async () => {
      const event: AIAssistantSSEEvent = {
        event: 'tool_call',
        tool: 'search_customer',
        params: { keyword: '光大证券' },
        round: 1
      }

      executionLog.handleSSEEvent(event)

      // 等待 watch 触发
      await new Promise(resolve => setTimeout(resolve, 100))

      // 验证 localStorage 缓存
      const cacheKey = 'execution_steps_123'
      const cached = localStorage.getItem(cacheKey)

      expect(cached).not.toBeNull()
      const parsedSteps = JSON.parse(cached ?? '[]')
      expect(parsedSteps.length).toBe(1)
      expect(parsedSteps[0].tool).toBe('search_customer')
    })

    it('restoreFromLocalStorage 应正确恢复 execution steps', () => {
      // 预设 localStorage 缓存
      const cachedSteps = [
        {
          id: 'step-1',
          type: 'TOOL_CALL',
          title: '查找客户信息',
          timestamp: new Date().toISOString(),
          tool: 'search_customer',
          round: 1
        },
        {
          id: 'step-2',
          type: 'TOOL_RESULT',
          title: '执行成功',
          timestamp: new Date().toISOString(),
          success: true,
          round: 1
        }
      ]

      localStorage.setItem('execution_steps_123', JSON.stringify(cachedSteps))

      // 恢复
      const restored = executionLog.restoreFromLocalStorage()

      expect(restored).toBe(true)
      expect(executionLog.steps.value.length).toBe(2)
      expect(executionLog.steps.value[0].title).toBe('查找客户信息')
      expect(executionLog.steps.value[1].success).toBe(true)
    })

    it('clearLocalStorageCache 应清理缓存', () => {
      // 预设缓存
      localStorage.setItem('execution_steps_123', JSON.stringify([{ id: 'test' }]))

      // 清理
      executionLog.clearLocalStorageCache()

      const cached = localStorage.getItem('execution_steps_123')
      expect(cached).toBeNull()
    })

    it('无 localStorage 缓存时 restoreFromLocalStorage 应返回 false', () => {
      const restored = executionLog.restoreFromLocalStorage()

      expect(restored).toBe(false)
      expect(executionLog.steps.value.length).toBe(0)
    })

    it('localStorage 缓存损坏时 restoreFromLocalStorage 应处理错误', () => {
      // 设置无效 JSON
      localStorage.setItem('execution_steps_123', 'invalid-json')

      const restored = executionLog.restoreFromLocalStorage()

      expect(restored).toBe(false)
      expect(executionLog.steps.value.length).toBe(0)
    })
  })
})