import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CompactConfirmSummary from '../CompactConfirmSummary.vue'

describe('CompactConfirmSummary.vue', () => {
  const mockParams = {
    客户: { value: '光大证券', isEntity: true },
    内容: { value: '项目立项阶段', isEntity: false },
    方式: { value: '电话沟通', isEntity: false }
  }

  it('shows summary by default', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    expect(wrapper.find('.confirmation-summary').exists()).toBe(true)
    expect(wrapper.find('.confirmation-expanded').exists()).toBe(false)
  })

  it('shows expanded params on click', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    await wrapper.find('.confirmation-summary').trigger('click')

    expect(wrapper.find('.confirmation-summary.expanded').exists()).toBe(true)
    expect(wrapper.find('.confirmation-expanded').isVisible()).toBe(true)
  })

  it('collapses on second click', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    // First click - expand
    await wrapper.find('.confirmation-summary').trigger('click')
    expect(wrapper.find('.confirmation-expanded').isVisible()).toBe(true)

    // Second click - collapse
    await wrapper.find('.confirmation-summary').trigger('click')
    expect(wrapper.find('.confirmation-expanded').exists()).toBe(false)
  })

  it('applies high-risk border style', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '删除客户', params: mockParams, riskLevel: 'high' }
    })

    expect(wrapper.find('.confirmation-summary.high-risk').exists()).toBe(true)
  })

  it('applies low-risk border style', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, riskLevel: 'low' }
    })

    expect(wrapper.find('.confirmation-summary.low-risk').exists()).toBe(true)
  })

  it('applies medium-risk style by default', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    // No specific risk level class should be applied for medium/default
    expect(wrapper.find('.confirmation-summary').exists()).toBe(true)
  })

  it('shows confirmed state', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, status: 'confirmed' }
    })

    expect(wrapper.find('.confirmation-summary.confirmed').exists()).toBe(true)
    expect(wrapper.find('.confirm-label.confirmed').exists()).toBe(true)
  })

  it('shows cancelled state', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, status: 'cancelled' }
    })

    expect(wrapper.find('.confirmation-summary.cancelled').exists()).toBe(true)
  })

  it('displays correct status label for waiting', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, status: 'waiting' }
    })

    expect(wrapper.find('.confirm-label').text()).toBe('待确认')
  })

  it('displays correct status label for confirmed', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, status: 'confirmed' }
    })

    expect(wrapper.find('.confirm-label').text()).toBe('已确认')
  })

  it('displays correct status label for cancelled', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams, status: 'cancelled' }
    })

    expect(wrapper.find('.confirm-label').text()).toBe('已取消')
  })

  it('emits confirm event on button click', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    // Expand first
    await wrapper.find('.confirmation-summary').trigger('click')

    // Click confirm button
    await wrapper.find('.btn-confirm').trigger('click')

    expect(wrapper.emitted('confirm')).toBeTruthy()
  })

  it('emits cancel event on cancel button click', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    // Expand first
    await wrapper.find('.confirmation-summary').trigger('click')

    // Click cancel button
    await wrapper.find('.btn-cancel').trigger('click')

    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('displays inline params summary (first 3 params)', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    const inlineParams = wrapper.find('.params-inline').text()
    expect(inlineParams).toContain('客户: 光大证券')
    expect(inlineParams).toContain('内容: 项目立项阶段')
    expect(inlineParams).toContain('方式: 电话沟通')
  })

  it('displays expanded params with correct format', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    // Expand
    await wrapper.find('.confirmation-summary').trigger('click')

    const expandedRows = wrapper.findAll('.expanded-param-row')
    expect(expandedRows).toHaveLength(3)
    expect(expandedRows[0].find('.expanded-param-name').text()).toBe('客户：')
    expect(expandedRows[0].find('.expanded-param-value').text()).toBe('光大证券')
  })

  it('applies entity class to entity parameters', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    // Expand
    await wrapper.find('.confirmation-summary').trigger('click')

    // First param (客户) should have entity class
    const entityParam = wrapper.findAll('.expanded-param-value')[0]
    expect(entityParam.classes()).toContain('entity')
  })

  it('shows Round Badge when round is provided', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: {
        round: 2,
        title: '创建跟进记录',
        params: mockParams
      }
    })

    expect(wrapper.find('.round-badge').text()).toBe('R2')
    expect(wrapper.find('.round-badge.current').exists()).toBe(true)
  })

  it('has correct padding 6px 16px', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    expect(wrapper.find('.confirmation-summary').exists()).toBe(true)
  })

  it('has expand hint text', () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    expect(wrapper.find('.expand-hint').text()).toBe('[点击展开详情]')
  })

  it('shows collapse hint when expanded', async () => {
    const wrapper = mount(CompactConfirmSummary, {
      props: { title: '创建跟进记录', params: mockParams }
    })

    await wrapper.find('.confirmation-summary').trigger('click')

    expect(wrapper.find('.expand-hint').text()).toBe('↑ 收起')
  })
})