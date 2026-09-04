import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DataViewStatePanel from '@/components/crmwolf/DataViewStatePanel.vue'

describe('DataViewStatePanel', () => {
  it('renders loading as a stable live region', () => {
    const wrapper = mount(DataViewStatePanel, {
      props: { state: 'loading', loadingType: 'card', loadingRows: 2 },
    })

    const region = wrapper.find('[role="status"]')
    expect(region.exists()).toBe(true)
    expect(region.attributes('aria-busy')).toBe('true')
    expect(region.attributes('aria-live')).toBe('polite')
    expect(wrapper.findAll('[role="status"]').length).toBe(1)
    expect(wrapper.findComponent({ name: 'LoadingSkeleton' }).attributes('aria-hidden')).toBe('true')
  })

  it('renders error and emits retry from the default recovery action', async () => {
    const wrapper = mount(DataViewStatePanel, {
      props: {
        state: 'error',
        errorTitle: '回款计划加载失败',
        errorDescription: '请稍后重试。',
      },
    })

    expect(wrapper.text()).toContain('回款计划加载失败')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('keeps empty and ready states separate', () => {
    const empty = mount(DataViewStatePanel, {
      props: { state: 'empty', emptyTitle: '暂无回款计划' },
    })
    expect(empty.text()).toContain('暂无回款计划')

    const ready = mount(DataViewStatePanel, {
      props: { state: 'ready' },
      slots: { default: '<div data-testid="ready-content">详情内容</div>' },
    })
    expect(ready.find('[data-testid="ready-content"]').exists()).toBe(true)
  })
})
