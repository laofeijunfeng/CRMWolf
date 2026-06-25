/**
 * HistoryList.vue 单元测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HistoryList from '../HistoryList.vue'
import type { ConversationGroup } from '@/api/aiConversation'

describe('HistoryList', () => {
  const mockGroups: ConversationGroup = {
    today: [
      { id: 1, title: '创建客户张三', entityType: 'customer', entityId: 100, createdAt: '2024-01-15T14:30:00', actionType: 'create' }
    ],
    yesterday: [
      { id: 2, title: '商机赢单', entityType: 'opportunity', entityId: 200, createdAt: '2024-01-14T10:15:00', actionType: 'update' }
    ],
    earlier: [
      { id: 3, title: '跟进记录', entityType: 'lead', entityId: 300, createdAt: '2024-01-10T09:00:00', actionType: 'create' }
    ]
  }

  it('renders today group correctly', () => {
    const wrapper = mount(HistoryList, {
      props: {
        groups: mockGroups
      }
    })

    expect(wrapper.find('.history-list__group-title').text()).toBe('今天')
  })

  it('renders all groups', () => {
    const wrapper = mount(HistoryList, {
      props: {
        groups: mockGroups
      }
    })

    const groupTitles = wrapper.findAll('.history-list__group-title')
    expect(groupTitles.length).toBe(3)
    expect(groupTitles[0]?.text()).toBe('今天')
    expect(groupTitles[1]?.text()).toBe('昨天')
    expect(groupTitles[2]?.text()).toBe('更早')
  })

  it('shows empty state when no conversations', () => {
    const emptyGroups: ConversationGroup = {
      today: [],
      yesterday: [],
      earlier: []
    }

    const wrapper = mount(HistoryList, {
      props: {
        groups: emptyGroups
      },
      global: {
        stubs: {
          HistoryItem: true
        }
      }
    })

    expect(wrapper.find('.history-list__empty').exists()).toBe(true)
    // Updated selector to match actual component structure
    expect(wrapper.find('.history-list__empty-title').text()).toBe('开始你的第一个对话')
  })

  it('shows loading state', () => {
    const wrapper = mount(HistoryList, {
      props: {
        groups: mockGroups,
        loading: true
      }
    })

    expect(wrapper.find('.history-list__loading').exists()).toBe(true)
  })

  it('emits select event when item is clicked', async () => {
    const wrapper = mount(HistoryList, {
      props: {
        groups: mockGroups
      }
    })

    const firstItem = wrapper.findComponent({ name: 'HistoryItem' })
    await firstItem.vm.$emit('select', 1)

    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')?.[0]).toEqual([1])
  })
})