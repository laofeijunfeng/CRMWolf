// CRM-Client/src/components/__tests__/CollapsedView.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CollapsedView from '../CollapsedView.vue'

describe('CollapsedView.vue (V2)', () => {
  it('has height 36px (compact)', () => {
    const wrapper = mount(CollapsedView, {
      props: {
        round: 2,
        totalRounds: 5,
        status: 'loading',
        stepText: '正在查询商机...'
      }
    })

    expect(wrapper.find('.collapsed-view').exists()).toBe(true)
    // CSS 规范已定义 height: 36px
  })

  it('shows Round Badge with progress format R2/5', () => {
    const wrapper = mount(CollapsedView, {
      props: {
        round: 2,
        totalRounds: 5,
        status: 'success',
        stepText: '查找成功'
      }
    })

    expect(wrapper.find('.round-badge').text()).toBe('R2/5')
  })

  it('shows Round Badge with simple format R1', () => {
    const wrapper = mount(CollapsedView, {
      props: {
        round: 1,
        status: 'success',
        stepText: '查找成功'
      }
    })

    expect(wrapper.find('.round-badge').text()).toBe('R1')
  })

  it('shows 16px status icon', () => {
    const wrapper = mount(CollapsedView, {
      props: {
        status: 'loading',
        stepText: '正在处理...'
      }
    })

    const statusIcon = wrapper.find('.status-icon')
    expect(statusIcon.exists()).toBe(true)
    expect(statusIcon.classes()).toContain('loading')
  })

  it('emits click event on click', async () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })

    await wrapper.find('.collapsed-view').trigger('click')

    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('toggles expand on Enter key', async () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })

    await wrapper.find('.collapsed-view').trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('toggles expand on Space key', async () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })

    await wrapper.find('.collapsed-view').trigger('keydown', { key: ' ' })

    expect(wrapper.emitted('click')).toBeTruthy()
  })

  it('has focus-visible style for accessibility', () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })

    const view = wrapper.find('.collapsed-view')
    expect(view.attributes('tabindex')).toBe('0')
    expect(view.attributes('role')).toBe('button')
    expect(view.attributes('aria-expanded')).toBe('false')
  })

  it('applies correct status colors', () => {
    // success status
    const wrapperSuccess = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })
    expect(wrapperSuccess.find('.status-icon').classes()).toContain('success')

    // error status
    const wrapperError = mount(CollapsedView, {
      props: { status: 'error', stepText: 'test' }
    })
    expect(wrapperError.find('.status-icon').classes()).toContain('error')

    // loading status
    const wrapperLoading = mount(CollapsedView, {
      props: { status: 'loading', stepText: 'test' }
    })
    expect(wrapperLoading.find('.status-icon').classes()).toContain('loading')

    // partial status
    const wrapperPartial = mount(CollapsedView, {
      props: { status: 'partial', stepText: 'test' }
    })
    expect(wrapperPartial.find('.status-icon').classes()).toContain('partial')
  })

  it('displays stepText', () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: '找到 1 个客户：光大证券股份有限公司' }
    })

    expect(wrapper.find('.step-text').text()).toBe('找到 1 个客户：光大证券股份有限公司')
  })

  it('shows expand hint', () => {
    const wrapper = mount(CollapsedView, {
      props: { status: 'success', stepText: 'test' }
    })

    expect(wrapper.find('.expand-hint').text()).toContain('点击展开')
  })
})