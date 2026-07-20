import { describe, it, expect } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import HoverPreviewTooltip from '../HoverPreviewTooltip.vue'

describe('HoverPreviewTooltip.vue', () => {
  const mockRows = [
    { label: '客户ID', value: '16' },
    { label: '行业', value: '金融服务业' },
    { label: '状态', value: '活跃' }
  ]

  const mountTooltip = (props: { rows: typeof mockRows; minWidth?: number }, slot = '<span>Trigger</span>'): VueWrapper => {
    return mount(HoverPreviewTooltip, {
      props,
      slots: { default: slot },
      global: {
        stubs: {
          HoverInfo: {
            template: `
              <div class="hover-info-stub">
                <div class="hover-info-trigger"><slot name="trigger" /></div>
                <div class="hover-info-content"><slot /></div>
              </div>
            `
          }
        }
      }
    }) as VueWrapper
  }

  it('renders tooltip rows correctly', () => {
    const wrapper = mountTooltip({ rows: mockRows }, '<span class="trigger">Hover me</span>')

    expect(wrapper.findAll('.tooltip-row')).toHaveLength(3)
    expect(wrapper.find('.tooltip-label').text()).toBe('客户ID:')
    expect(wrapper.find('.tooltip-value').text()).toBe('16')
  })

  it('renders tooltip content through HoverInfo', () => {
    const wrapper = mountTooltip({ rows: mockRows })
    const tooltip = wrapper.find('.hover-preview-tooltip')

    expect(tooltip.exists()).toBe(true)
    expect(wrapper.find('.hover-info-trigger .hover-preview').exists()).toBe(true)
  })

  it('has correct min-width 200px by default', () => {
    const wrapper = mountTooltip({ rows: mockRows })

    expect(wrapper.find('.hover-preview-tooltip').attributes('style')).toContain('min-width: 200px')
  })

  it('accepts custom minWidth prop', () => {
    const wrapper = mountTooltip({ rows: mockRows, minWidth: 300 })

    const tooltip = wrapper.find('.hover-preview-tooltip')
    expect(tooltip.exists()).toBe(true)
    expect(tooltip.attributes('style')).toContain('min-width: 300px')
  })

  it('renders slot content', () => {
    const wrapper = mountTooltip({ rows: mockRows }, '<span class="trigger">Custom Trigger</span>')

    expect(wrapper.find('.trigger').text()).toBe('Custom Trigger')
  })

  it('displays all rows in correct order', () => {
    const wrapper = mountTooltip({ rows: mockRows })

    const rows = wrapper.findAll('.tooltip-row')
    expect(rows).toHaveLength(3)
    expect(rows.map((row) => row.text())).toEqual([
      '客户ID:16',
      '行业:金融服务业',
      '状态:活跃'
    ])
  })

  it('handles empty rows array', () => {
    const wrapper = mountTooltip({ rows: [] })

    expect(wrapper.findAll('.tooltip-row')).toHaveLength(0)
  })
})
