/**
 * Sidebar 状态管理 Composable 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarState } from '../useSidebarState'
import { SidebarState } from '@/types/sidebar'

describe('useSidebarState', () => {
  let sidebarState: ReturnType<typeof useSidebarState>

  beforeEach(() => {
    // 每次测试前重新初始化
    sidebarState = useSidebarState()
  })

  describe('初始状态', () => {
    it('初始状态应为 IDLE', () => {
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
    })

    it('IDLE 状态应显示主输入框', () => {
      expect(sidebarState.uiConfig.value.showInputBox).toBe(true)
    })

    it('IDLE 状态应隐藏 Sidebar', () => {
      expect(sidebarState.uiConfig.value.showSidebar).toBe(false)
    })

    it('IDLE 状态不应显示停止/新对话按钮', () => {
      expect(sidebarState.uiConfig.value.showStopButton).toBe(false)
      expect(sidebarState.uiConfig.value.showNewChatButton).toBe(false)
    })
  })

  describe('状态转换', () => {
    it('用户提交意图应转换到 COLLECTING 状态', () => {
      const result = sidebarState.userSubmit('创建客户张三')
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.COLLECTING)
    })

    it('COLLECTING 状态应隐藏主输入框', () => {
      sidebarState.userSubmit('创建客户张三')
      expect(sidebarState.uiConfig.value.showInputBox).toBe(false)
      expect(sidebarState.uiConfig.value.showSidebar).toBe(true)
    })

    it('AI 完成意图收集应转换到 RESOLVING_ENTITY 状态', () => {
      sidebarState.userSubmit('创建客户张三')
      const result = sidebarState.aiCollectingDone({ intent: 'create_customer' })
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.RESOLVING_ENTITY)
    })

    it('RESOLVING_ENTITY 状态应显示停止按钮', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      expect(sidebarState.uiConfig.value.showStopButton).toBe(true)
    })

    it('AI 发现歧义应转换到 RESOLVING_AMBIGUITY 状态', () => {
      sidebarState.userSubmit('跟进张三')
      sidebarState.aiCollectingDone({ intent: 'follow_up' })
      const result = sidebarState.aiAmbiguityDetected([
        { id: 1, name: '张三' },
        { id: 2, name: '张三' }
      ])
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.RESOLVING_AMBIGUITY)
    })

    it('RESOLVING_AMBIGUITY 状态应显示实体选择界面', () => {
      sidebarState.userSubmit('跟进张三')
      sidebarState.aiCollectingDone({ intent: 'follow_up' })
      sidebarState.aiAmbiguityDetected([
        { id: 1, name: '张三' },
        { id: 2, name: '张三' }
      ])
      expect(sidebarState.uiConfig.value.showEntitySelect).toBe(true)
    })

    it('AI 生成 Preview 应转换到 PREVIEW 状态', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      const result = sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.PREVIEW)
    })

    it('PREVIEW 状态应显示 Preview 详情', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      expect(sidebarState.uiConfig.value.showPreviewDetails).toBe(true)
    })

    it('用户确认 Preview 应转换到 EXECUTING 状态', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      const result = sidebarState.userConfirm()
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.EXECUTING)
    })

    it('EXECUTING 状态应显示 Mini-map', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      sidebarState.userConfirm()
      expect(sidebarState.uiConfig.value.showMiniMap).toBe(true)
    })

    it('AI 完成执行应转换到 COMPLETED 状态', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      sidebarState.userConfirm()
      const result = sidebarState.aiExecutionDone({ customerId: 123 })
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.COMPLETED)
    })

    it('COMPLETED 状态应显示新对话按钮', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      sidebarState.userConfirm()
      sidebarState.aiExecutionDone({ customerId: 123 })
      expect(sidebarState.uiConfig.value.showNewChatButton).toBe(true)
    })

    it('用户点击新对话应返回 IDLE 状态', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({
        action: 'create_customer',
        params: { name: '张三', phone: '13812345678' }
      })
      sidebarState.userConfirm()
      sidebarState.aiExecutionDone({ customerId: 123 })
      sidebarState.userNewChat()
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
    })
  })

  describe('状态转换合法性检查', () => {
    it('非法转换应返回 false', () => {
      // 尝试从 IDLE 直接跳到 EXECUTING（非法）
      const result = sidebarState.transitionTo(
        SidebarState.EXECUTING,
        'user_submit',
        {}
      )
      expect(result).toBe(false)
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
    })

    it('合法转换应返回 true', () => {
      const result = sidebarState.userSubmit('创建客户张三')
      expect(result).toBe(true)
      expect(sidebarState.state.value).toBe(SidebarState.COLLECTING)
    })
  })

  describe('用户停止操作', () => {
    it('用户停止操作应返回 IDLE 状态', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.userStop()
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
    })
  })

  describe('辅助方法', () => {
    it('isState 应正确判断当前状态', () => {
      expect(sidebarState.isState(SidebarState.IDLE)).toBe(true)
      expect(sidebarState.isState(SidebarState.COLLECTING)).toBe(false)
    })

    it('isActive 应正确判断活跃状态', () => {
      expect(sidebarState.isActive()).toBe(false)
      sidebarState.userSubmit('创建客户张三')
      expect(sidebarState.isActive()).toBe(true)
    })
  })

  describe('状态转换历史', () => {
    it('应记录状态转换历史', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      const history = sidebarState.getRecentTransitions(2)
      expect(history.length).toBe(2)
      expect(history[0].reason).toBe('user_submit')
      expect(history[1].reason).toBe('ai_collecting_done')
    })

    it('resetToIdle 应清空历史', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.resetToIdle()
      expect(sidebarState.history.value.length).toBe(0)
    })
  })

  // ========== Phase 5: 性能测试 ==========

  describe('性能验收', () => {
    it('状态转换响应时间应 < 100ms', () => {
      const startTime = performance.now()

      // 执行完整的状态转换流程
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({ action: 'create_customer', params: {} })
      sidebarState.userConfirm()
      sidebarState.aiExecutionDone({ customerId: 123 })

      const endTime = performance.now()
      const duration = endTime - startTime

      // 状态转换应该在 100ms 内完成
      expect(duration).toBeLessThan(100)
    })

    it('批量状态转换应高效', () => {
      const startTime = performance.now()

      // 执行 100 次状态转换
      for (let i = 0; i < 100; i++) {
        sidebarState.userSubmit(`测试${i}`)
        sidebarState.resetToIdle()
      }

      const endTime = performance.now()
      const duration = endTime - startTime

      // 100 次转换应该在 50ms 内完成
      expect(duration).toBeLessThan(50)
    })

    it('uiConfig 计算属性应快速响应', () => {
      // 先转换状态
      sidebarState.userSubmit('创建客户张三')

      const startTime = performance.now()
      const config = sidebarState.uiConfig.value
      const endTime = performance.now()

      // 计算属性访问应该是即时响应
      expect(endTime - startTime).toBeLessThan(1)
      expect(config.showSidebar).toBe(true)
    })
  })

  // ========== Phase 5: UI 配置验收 ==========

  describe('UI 配置验收', () => {
    it('IDLE 状态：主输入框显示，Sidebar 隐藏', () => {
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
      expect(sidebarState.uiConfig.value.showInputBox).toBe(true)
      expect(sidebarState.uiConfig.value.showSidebar).toBe(false)
      expect(sidebarState.uiConfig.value.showStopButton).toBe(false)
      expect(sidebarState.uiConfig.value.showNewChatButton).toBe(false)
    })

    it('EXECUTING 状态：Sidebar 显示，停止按钮显示', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({ action: 'create_customer', params: {} })
      sidebarState.userConfirm()

      expect(sidebarState.state.value).toBe(SidebarState.EXECUTING)
      expect(sidebarState.uiConfig.value.showInputBox).toBe(false)
      expect(sidebarState.uiConfig.value.showSidebar).toBe(true)
      expect(sidebarState.uiConfig.value.showStopButton).toBe(true)
      expect(sidebarState.uiConfig.value.showNewChatButton).toBe(false)
    })

    it('COMPLETED 状态：Sidebar 显示，新对话按钮显示', () => {
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({ action: 'create_customer', params: {} })
      sidebarState.userConfirm()
      sidebarState.aiExecutionDone({ customerId: 123 })

      expect(sidebarState.state.value).toBe(SidebarState.COMPLETED)
      expect(sidebarState.uiConfig.value.showInputBox).toBe(false)
      expect(sidebarState.uiConfig.value.showSidebar).toBe(true)
      expect(sidebarState.uiConfig.value.showStopButton).toBe(false)
      expect(sidebarState.uiConfig.value.showNewChatButton).toBe(true)
    })

    it('点击新对话按钮返回 IDLE 状态', () => {
      // 先到达 COMPLETED 状态
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({ action: 'create_customer', params: {} })
      sidebarState.userConfirm()
      sidebarState.aiExecutionDone({ customerId: 123 })

      // 点击新对话
      sidebarState.userNewChat()

      // 应返回 IDLE
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
      expect(sidebarState.uiConfig.value.showInputBox).toBe(true)
      expect(sidebarState.uiConfig.value.showSidebar).toBe(false)
    })

    it('点击停止按钮返回 IDLE 状态', () => {
      // 先到达 EXECUTING 状态
      sidebarState.userSubmit('创建客户张三')
      sidebarState.aiCollectingDone({ intent: 'create_customer' })
      sidebarState.aiPreviewGenerated({ action: 'create_customer', params: {} })
      sidebarState.userConfirm()

      // 点击停止
      sidebarState.userStop()

      // 应返回 IDLE
      expect(sidebarState.state.value).toBe(SidebarState.IDLE)
      expect(sidebarState.uiConfig.value.showInputBox).toBe(true)
      expect(sidebarState.uiConfig.value.showSidebar).toBe(false)
    })
  })
})