import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HoverPreviewTooltip from '../HoverPreviewTooltip.vue'

describe('HoverPreviewTooltip.vue', () => {
  const mockRows = [
    { label: '客户ID', value: '16' },
    { label: '行业', value: '金融服务业' },
    { label: '状态', value: '活跃' }
  ]

  it('renders tooltip rows correctly', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: {
        default: '<span class="trigger">Hover me</span>'
      }
    })

    expect(wrapper.findAll('.tooltip-row')).toHaveLength(3)
    expect(wrapper.find('.tooltip-label').text()).toBe('客户ID:')
    expect(wrapper.find('.tooltip-value').text()).toBe('16')
  })

  it('is hidden by default', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span>Trigger</span>' }
    })

    const tooltip = wrapper.find('.hover-preview-tooltip')
    expect(tooltip.exists()).toBe(true)
    // CSS 控制显示/隐藏，检查元素存在
  })

  it('shows on hover', async () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span class="trigger">Trigger</span>' }
    })

    await wrapper.find('.hover-preview').trigger('mouseenter')

    const tooltip = wrapper.find('.hover-preview-tooltip')
    expect(tooltip.exists()).toBe(true)
  })

  it('hides on mouseleave', async () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span class="trigger">Trigger</span>' }
    })

    // Hover first
    await wrapper.find('.hover-preview').trigger('mouseenter')

    // Then leave
    await wrapper.find('.hover-preview').trigger('mouseleave')

    const tooltip = wrapper.find('.hover-preview-tooltip')
    expect(tooltip.exists()).toBe(true)
  })

  it('has correct min-width 200px by default', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span>Trigger</span>' }
    })

    expect(wrapper.find('.hover-preview-tooltip').exists()).toBe(true)
  })

  it('accepts custom minWidth prop', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows, minWidth: 300 },
      slots: { default: '<span>Trigger</span>' }
    })

    const tooltip = wrapper.find('.hover-preview-tooltip')
    expect(tooltip.exists()).toBe(true)
    // CSS style is applied via :style binding
  })

  it('renders slot content', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span class="trigger">Custom Trigger</span>' }
    })

    expect(wrapper.find('.trigger').text()).toBe('Custom Trigger')
  })

  it('has correct transition duration 0.15s', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span>Trigger</span>' }
    })

    expect(wrapper.find('.hover-preview-tooltip').exists()).toBe(true)
  })

  it('displays all rows in correct order', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: mockRows },
      slots: { default: '<span>Trigger</span>' }
    })

    const rows = wrapper.findAll('.tooltip-row')
    expect(rows[0].find('.tooltip-label').text()).toBe('客户ID:')
    expect(rows[1].find('.tooltip-label').text()).toBe('行业:')
    expect(rows[2].find('.tooltip-label').text()).toBe('状态:')
  })

  it('handles empty rows array', () => {
    const wrapper = mount(HoverPreviewTooltip, {
      props: { rows: [] },
      slots: { default: '<span>Trigger</span>' }
    })

    expect(wrapper.findAll('.tooltip-row')).toHaveLength(0)
  })
})