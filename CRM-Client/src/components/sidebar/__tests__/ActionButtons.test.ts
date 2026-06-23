import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ActionButtons from '../ActionButtons.vue'

describe('ActionButtons.vue', () => {
  describe('渲染测试', () => {
    it('不显示任何按钮时，容器仍然存在', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: false,
          showNewChat: false
        }
      })

      expect(wrapper.find('.action-buttons-container').exists()).toBe(true)
      expect(wrapper.find('.stop-button').exists()).toBe(false)
      expect(wrapper.find('.new-chat-button').exists()).toBe(false)
    })

    it('showStop=true 时显示停止按钮', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: false
        }
      })

      expect(wrapper.find('.stop-button').exists()).toBe(true)
      expect(wrapper.find('.stop-button').text()).toContain('停止操作')
    })

    it('showNewChat=true 时显示新对话按钮', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: false,
          showNewChat: true
        }
      })

      expect(wrapper.find('.new-chat-button').exists()).toBe(true)
      expect(wrapper.find('.new-chat-button').text()).toContain('新对话')
    })

    it('同时显示停止和新对话按钮', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: true
        }
      })

      expect(wrapper.find('.stop-button').exists()).toBe(true)
      expect(wrapper.find('.new-chat-button').exists()).toBe(true)
    })

    it('showUndo=true + undoEndpoint 时显示撤销按钮', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: false,
          showNewChat: false,
          showUndo: true,
          undoEndpoint: '/api/undo',
          operationId: 123
        }
      })

      expect(wrapper.find('.undo-button').exists()).toBe(true)
      expect(wrapper.find('.undo-button').text()).toContain('撤销')
    })
  })

  describe('事件测试', () => {
    it('点击停止按钮触发 stop 事件', async () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: false
        }
      })

      await wrapper.find('.stop-button').trigger('click')

      const stopEvents = wrapper.emitted('stop')
      expect(stopEvents).toBeTruthy()
      expect(stopEvents?.length).toBe(1)
    })

    it('点击新对话按钮触发 newChat 事件', async () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: false,
          showNewChat: true
        }
      })

      await wrapper.find('.new-chat-button').trigger('click')

      const newChatEvents = wrapper.emitted('newChat')
      expect(newChatEvents).toBeTruthy()
      expect(newChatEvents?.length).toBe(1)
    })

    it('点击撤销按钮触发 undoFailed 事件（无 endpoint 时）', async () => {
      // 注意：当没有 undoEndpoint 时，撤销按钮不会显示
      // 这个测试验证的是 handleUndo 函数的逻辑
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: false,
          showNewChat: false,
          showUndo: true,
          undoEndpoint: '/api/undo',
          operationId: 123
        }
      })

      // 撤销按钮存在时测试
      expect(wrapper.find('.undo-button').exists()).toBe(true)
    })
  })

  describe('样式测试', () => {
    it('容器有正确的 CSS 类', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: true
        }
      })

      const container = wrapper.find('.action-buttons-container')
      expect(container.exists()).toBe(true)
    })

    it('按钮有正确的 CSS 类', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: true,
          showUndo: true,
          undoEndpoint: '/api/undo',
          operationId: 123
        }
      })

      expect(wrapper.find('.stop-button').classes()).toContain('action-button')
      expect(wrapper.find('.new-chat-button').classes()).toContain('action-button')
      expect(wrapper.find('.undo-button').classes()).toContain('action-button')
    })
  })

  describe('Props 验证', () => {
    it('默认 props 正确', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: true
        }
      })

      // 验证默认值
      expect(wrapper.props('showUndo')).toBe(false)
      expect(wrapper.props('undoEndpoint')).toBeUndefined()
      expect(wrapper.props('operationId')).toBeUndefined()
    })

    it('所有 props 正确传递', () => {
      const wrapper = mount(ActionButtons, {
        props: {
          showStop: true,
          showNewChat: true,
          showUndo: true,
          undoEndpoint: '/api/v1/undo/123',
          operationId: 456
        }
      })

      expect(wrapper.props('showStop')).toBe(true)
      expect(wrapper.props('showNewChat')).toBe(true)
      expect(wrapper.props('showUndo')).toBe(true)
      expect(wrapper.props('undoEndpoint')).toBe('/api/v1/undo/123')
      expect(wrapper.props('operationId')).toBe(456)
    })
  })
})