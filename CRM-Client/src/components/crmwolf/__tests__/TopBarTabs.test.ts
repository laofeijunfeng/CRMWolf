import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TopBarTabs from '../TopBarTabs.vue'

const tabs = [
  { key: 'all', label: '全部客户', viewKind: 'built-in' as const },
  { key: 'public', label: '公海客户', viewKind: 'built-in' as const },
  {
    key: 'custom-view:1',
    label: '重点客户',
    viewKind: 'custom' as const,
    isCustomView: true,
    onRename: vi.fn(),
    onMoveToFirst: vi.fn(),
    onDelete: vi.fn(),
  },
]

describe('TopBarTabs', () => {
  it('keeps the existing tab presentation and does not add view-group labels', () => {
    const wrapper = mount(TopBarTabs, {
      props: {
        tabs,
        activeTab: 'all',
      },
    })

    expect(wrapper.find('[aria-label="系统视图：全部客户"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="系统视图：公海客户"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="我的视图：重点客户"]').exists()).toBe(false)
    expect(wrapper.find('[role="separator"]').exists()).toBe(false)
    expect(wrapper.find('.tabs-item--group-start').exists()).toBe(false)
  })

  it('keeps view actions only on personal views', () => {
    const wrapper = mount(TopBarTabs, {
      props: {
        tabs,
        activeTab: 'all',
      },
    })

    expect(wrapper.findAll('[aria-label="视图操作"]')).toHaveLength(1)
  })
})
