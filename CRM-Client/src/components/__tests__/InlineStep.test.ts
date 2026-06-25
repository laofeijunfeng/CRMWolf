import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InlineStep from '../InlineStep.vue'
import type { ExecutionStep } from '@/types/agentExecution'

describe('InlineStep.vue', () => {
  const createMockStep = (overrides?: Partial<ExecutionStep>): ExecutionStep => ({
    id: 's1',
    type: 'tool_result' as any,
    title: '查找客户信息',
    description: '找到 1 个客户',
    timestamp: new Date(),
    ...overrides
  })

  it('renders Round Badge with correct format', () => {
    const wrapper = mount(InlineStep, {
      props: {
        round: 1,
        step: createMockStep()
      }
    })

    expect(wrapper.find('.round-badge').text()).toBe('R1')
  })

  it('renders Round Badge with progress format R2/5', () => {
    const wrapper = mount(InlineStep, {
      props: {
        round: 2,
        totalRounds: 5,
        step: createMockStep()
      }
    })

    expect(wrapper.find('.round-badge').text()).toBe('R2/5')
  })

  it('applies success color when status is success', () => {
    const wrapper = mount(InlineStep, {
      props: {
        status: 'success',
        step: createMockStep({ inline_text: '查找成功' })
      }
    })

    expect(wrapper.find('.step-inline.success').exists()).toBe(true)
    expect(wrapper.find('.step-text').classes()).toContain('success')
  })

  it('applies error color when status is error', () => {
    const wrapper = mount(InlineStep, {
      props: {
        status: 'error',
        step: createMockStep({ inline_text: '查找失败' })
      }
    })

    expect(wrapper.find('.step-inline.error').exists()).toBe(true)
  })

  it('merges inline_text from backend', () => {
    const wrapper = mount(InlineStep, {
      props: {
        step: createMockStep({
          inline_text: '查找客户信息，找到 1 个客户：光大证券股份有限公司'
        })
      }
    })

    expect(wrapper.find('.step-text').text()).toBe('查找客户信息，找到 1 个客户：光大证券股份有限公司')
  })

  it('falls back to title + description merge when inline_text not provided', () => {
    const wrapper = mount(InlineStep, {
      props: {
        step: createMockStep({
          title: '查找客户信息',
          description: '找到 1 个客户'
        })
      }
    })

    expect(wrapper.find('.step-text').text()).toBe('查找客户信息，找到 1 个客户')
  })

  it('uses summary as fallback when description is missing', () => {
    const wrapper = mount(InlineStep, {
      props: {
        step: createMockStep({
          title: '查找客户',
          description: undefined,  // Clear description
          summary: '找到光大证券'
        })
      }
    })

    expect(wrapper.find('.step-text').text()).toBe('查找客户，找到光大证券')
  })

  it('has correct padding 3px 16px', () => {
    const wrapper = mount(InlineStep, {
      props: {
        step: createMockStep({ inline_text: 'test' })
      }
    })

    expect(wrapper.find('.step-inline').exists()).toBe(true)
  })

  it('applies current class when isCurrent is true', () => {
    const wrapper = mount(InlineStep, {
      props: {
        round: 1,
        isCurrent: true,
        step: createMockStep()
      }
    })

    expect(wrapper.find('.round-badge.current').exists()).toBe(true)
  })

  it('applies warning color when status is warning', () => {
    const wrapper = mount(InlineStep, {
      props: {
        status: 'warning',
        step: createMockStep()
      }
    })

    expect(wrapper.find('.step-inline.warning').exists()).toBe(true)
  })

  it('applies loading animation when status is loading', () => {
    const wrapper = mount(InlineStep, {
      props: {
        status: 'loading',
        step: createMockStep()
      }
    })

    expect(wrapper.find('.status-icon.loading').exists()).toBe(true)
  })
})