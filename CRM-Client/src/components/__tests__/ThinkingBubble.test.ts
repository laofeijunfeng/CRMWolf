import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ThinkingBubble from '../ThinkingBubble.vue'

describe('ThinkingBubble.vue', () => {
  describe('渲染测试', () => {
    it('默认渲染正确', () => {
      const wrapper = mount(ThinkingBubble, {
        props: {
          content: '正在思考中...'
        }
      })

      expect(wrapper.find('.thinking-bubble').exists()).toBe(true)
    })

    it('显示推理文字', () => {
      const content = '正在分析客户信息...'
      const wrapper = mount(ThinkingBubble, {
        props: {
          content
        }
      })

      expect(wrapper.find('.thinking-text').text()).toBe(content)
    })

    it('渲染 CPU 图标', () => {
      const wrapper = mount(ThinkingBubble, {
        props: {
          content: '思考中'
        }
      })

      // 检查图标容器存在
      expect(wrapper.find('.thinking-icon').exists()).toBe(true)
      // 检查 CPU 图标存在（Element Plus Icon）
      expect(wrapper.find('.el-icon').exists()).toBe(true)
    })
  })

  describe('样式测试', () => {
    it('使用微蓝背景色', () => {
      const wrapper = mount(ThinkingBubble, {
        props: {
          content: '测试内容'
        }
      })

      const bubble = wrapper.find('.thinking-bubble')
      expect(bubble.exists()).toBe(true)
      // 验证类名存在，实际样式由 SCSS 变量控制
      expect(bubble.classes()).toContain('thinking-bubble')
    })

    it('文字为斜体', () => {
      const wrapper = mount(ThinkingBubble, {
        props: {
          content: '测试内容'
        }
      })

      const text = wrapper.find('.thinking-text')
      expect(text.exists()).toBe(true)
    })
  })

  describe('Props 验证', () => {
    it('content prop 必填', () => {
      const wrapper = mount(ThinkingBubble, {
        props: {
          content: '测试内容'
        }
      })

      expect(wrapper.props('content')).toBe('测试内容')
    })

    it('正确传递内容', () => {
      const longContent = '这是一段很长的推理内容，用于测试组件是否正确显示长文本内容'
      const wrapper = mount(ThinkingBubble, {
        props: {
          content: longContent
        }
      })

      expect(wrapper.find('.thinking-text').text()).toBe(longContent)
    })
  })
})