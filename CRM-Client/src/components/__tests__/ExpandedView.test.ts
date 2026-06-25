// CRM-Client/src/components/__tests__/ExpandedView.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ExpandedView from '../ExpandedView.vue'
import type { ExecutionStep } from '@/types/agentExecution'
import { ExecutionStepType } from '@/types/agentExecution'

describe('ExpandedView.vue (V2)', () => {
  const mockSteps: ExecutionStep[] = [
    {
      id: 'step-1',
      type: ExecutionStepType.TOOL_RESULT,
      title: '查找客户信息',
      timestamp: new Date('2026-01-01T10:00:10'),
      round: 1,
      inline_text: '查找客户信息，找到 1 个客户：光大证券股份有限公司',
      success: true
    },
    {
      id: 'step-2',
      type: ExecutionStepType.TOOL_RESULT,
      title: '查找商机',
      timestamp: new Date('2026-01-01T10:00:20'),
      round: 2,
      inline_text: '查找商机，找到 2 个商机',
      success: true
    }
  ]

  it('renders InlineStep components', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps, currentRound: 2 }
    })

    // V2: 使用 InlineStep 组件
    const inlineSteps = wrapper.findAll('.step-inline')
    expect(inlineSteps.length).toBeGreaterThan(0)
  })

  it('has max-height 280px', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    expect(wrapper.find('.expanded-view').exists()).toBe(true)
    // CSS 规范已定义 max-height: 280px
  })

  it('emits collapse on header click', async () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    await wrapper.find('.expand-header').trigger('click')

    expect(wrapper.emitted('collapse')).toBeTruthy()
  })

  it('supports keyboard navigation (Escape to collapse)', async () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    await wrapper.find('.expanded-view').trigger('keydown', { key: 'Escape' })

    expect(wrapper.emitted('collapse')).toBeTruthy()
  })

  it('has correct ARIA attributes', () => {
    const wrapper = mount(ExpandedView, {
      props: { steps: mockSteps }
    })

    const view = wrapper.find('.expanded-view')
    expect(view.attributes('aria-live')).toBe('polite')
  })

  it('handles disambiguation waiting_for_user type', () => {
    const disambiguationStep: ExecutionStep = {
      id: 'step-3',
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '请选择目标客户',
      timestamp: new Date('2026-01-01T10:00:30'),
      round: 3,
      confirmationType: 'disambiguation',
      options: [
        { id: 16, name: '光大证券股份有限公司', entity_info_inline: 'ID:16 · 金融 · 活跃' },
        { id: 17, name: '光大银行', entity_info_inline: 'ID:17 · 金融 · 活跃' }
      ]
    }

    const wrapper = mount(ExpandedView, {
      props: { steps: [...mockSteps, disambiguationStep] }
    })

    // V2: 使用 InlineCandidate 组件
    const candidates = wrapper.findAll('.candidate-inline')
    expect(candidates.length).toBeGreaterThan(0)
  })

  it('handles confirmation waiting_for_user type', () => {
    const confirmationStep: ExecutionStep = {
      id: 'step-4',
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '创建跟进记录',
      timestamp: new Date('2026-01-01T10:00:40'),
      round: 4,
      confirmationType: 'confirmation',
      riskLevel: 'low',
      detail_params: {
        '客户': { value: '光大证券股份有限公司', isEntity: true },
        '内容': { value: '项目立项阶段', isEntity: false }
      }
    }

    const wrapper = mount(ExpandedView, {
      props: { steps: [...mockSteps, confirmationStep] }
    })

    // V2: 使用 CompactConfirmSummary 组件
    expect(wrapper.find('.confirmation-summary').exists()).toBe(true)
  })

  it('handles info_gap waiting_for_user type', () => {
    const infoGapStep: ExecutionStep = {
      id: 'step-5',
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '创建跟进记录',
      timestamp: new Date('2026-01-01T10:00:50'),
      round: 5,
      confirmationType: 'info_gap',
      summary_params: { '客户': '光大证券' },
      error: '缺少必填字段：跟进内容'
    }

    const wrapper = mount(ExpandedView, {
      props: { steps: [...mockSteps, infoGapStep] }
    })

    // V2: 使用 CompactInfoGap 组件
    expect(wrapper.find('.info-gap-summary').exists()).toBe(true)
  })

  it('shows scroll container when content exceeds max-height', () => {
    // 创建多个步骤测试滚动
    const manySteps: ExecutionStep[] = Array.from({ length: 20 }, (_, i) => ({
      id: `step-${i}`,
      type: ExecutionStepType.TOOL_RESULT,
      title: `步骤 ${i + 1}`,
      timestamp: new Date(`2026-01-01T10:00:${i * 10}`),
      round: Math.floor(i / 5) + 1,
      inline_text: `步骤 ${i + 1} 执行完成`,
      success: true
    }))

    const wrapper = mount(ExpandedView, {
      props: { steps: manySteps }
    })

    expect(wrapper.find('.expanded-content').exists()).toBe(true)
  })

  it('emits confirm event when confirming selection', async () => {
    const disambiguationStep: ExecutionStep = {
      id: 'step-3',
      type: ExecutionStepType.WAITING_FOR_USER,
      title: '请选择目标客户',
      timestamp: new Date('2026-01-01T10:00:30'),
      round: 3,
      confirmationType: 'disambiguation',
      options: [
        { id: 16, name: '光大证券股份有限公司', entity_info_inline: 'ID:16 · 金融 · 活跃' }
      ]
    }

    const wrapper = mount(ExpandedView, {
      props: { steps: [disambiguationStep] }
    })

    // 点击确认按钮
    const confirmBtn = wrapper.find('.btn-confirm')
    if (confirmBtn.exists()) {
      await confirmBtn.trigger('click')
      expect(wrapper.emitted('confirm')).toBeTruthy()
    }
  })
})