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
})