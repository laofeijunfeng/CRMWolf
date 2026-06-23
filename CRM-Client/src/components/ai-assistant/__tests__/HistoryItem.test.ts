/**
 * HistoryItem.vue 单元测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HistoryItem from '../HistoryItem.vue'

describe('HistoryItem', () => {
  it('renders title correctly', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '创建客户张三',
        createdAt: '2024-01-15T14:30:00',
        entityType: 'customer'
      }
    })

    expect(wrapper.find('.history-item__title').text()).toBe('创建客户张三')
  })

  it('renders entity tag for customer', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '创建客户张三',
        createdAt: '2024-01-15T14:30:00',
        entityType: 'customer'
      }
    })

    const tag = wrapper.find('.history-item__tag')
    expect(tag.exists()).toBe(true)
    expect(tag.text()).toBe('客户')
    expect(tag.classes()).toContain('history-item__tag--customer')
  })

  it('renders entity tag for opportunity', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '商机赢单',
        createdAt: '2024-01-15T14:30:00',
        entityType: 'opportunity'
      }
    })

    const tag = wrapper.find('.history-item__tag')
    expect(tag.exists()).toBe(true)
    expect(tag.text()).toBe('商机')
    expect(tag.classes()).toContain('history-item__tag--opportunity')
  })

  it('does not render tag when entityType is null', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '普通对话',
        createdAt: '2024-01-15T14:30:00',
        entityType: null
      }
    })

    expect(wrapper.find('.history-item__tag').exists()).toBe(false)
  })

  it('formats time correctly', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '创建客户张三',
        createdAt: '2024-01-15T14:30:00'
      }
    })

    expect(wrapper.find('.history-item__time').text()).toBe('14:30')
  })

  it('emits select event on click', async () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '创建客户张三',
        createdAt: '2024-01-15T14:30:00'
      }
    })

    await wrapper.find('.history-item').trigger('click')

    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')?.[0]).toEqual([1])
  })

  it('applies active class when active prop is true', () => {
    const wrapper = mount(HistoryItem, {
      props: {
        id: 1,
        title: '创建客户张三',
        createdAt: '2024-01-15T14:30:00',
        active: true
      }
    })

    expect(wrapper.find('.history-item').classes()).toContain('active')
  })
})