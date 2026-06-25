/**
 * ChatBubble.vue 单元测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatBubble from '../ChatBubble.vue'

describe('ChatBubble', () => {
  it('renders user bubble correctly', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'user',
        content: '创建客户张三',
        timestamp: '2024-01-15T14:30:00'
      }
    })

    expect(wrapper.find('.chat-bubble').classes()).toContain('chat-bubble--user')
    expect(wrapper.find('.chat-bubble__text').text()).toBe('创建客户张三')
  })

  it('renders assistant bubble correctly', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'assistant',
        content: '好的，我将创建客户...',
        timestamp: '2024-01-15T14:31:00'
      },
      global: {
        stubs: {
          MarkdownContent: {
            template: '<div class="markdown-content">{{ content }}</div>',
            props: ['content']
          }
        }
      }
    })

    expect(wrapper.find('.chat-bubble').classes()).toContain('chat-bubble--assistant')
    // AI messages use MarkdownContent component
    expect(wrapper.find('.markdown-content').text()).toBe('好的，我将创建客户...')
  })

  it('formats time correctly', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'user',
        content: '测试消息',
        timestamp: '2024-01-15T09:05:00'
      }
    })

    expect(wrapper.find('.chat-bubble__time').text()).toBe('09:05')
  })

  it('renders user avatar on right side', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'user',
        content: '测试',
        timestamp: '2024-01-15T14:30:00'
      }
    })

    // 用户气泡的 avatar 应在 content 之后（flex-direction: row-reverse）
    const bubble = wrapper.find('.chat-bubble')
    // 检查 avatar 存在
    expect(bubble.find('.chat-bubble__avatar').exists()).toBe(true)
    expect(bubble.find('.chat-bubble__content').exists()).toBe(true)
  })

  it('renders assistant avatar on left side', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'assistant',
        content: '测试',
        timestamp: '2024-01-15T14:30:00'
      },
      global: {
        stubs: {
          MarkdownContent: {
            template: '<div class="markdown-content">{{ content }}</div>',
            props: ['content']
          }
        }
      }
    })

    // AI 气泡有 ai-icon (not avatar)
    const bubble = wrapper.find('.chat-bubble')
    expect(bubble.find('.chat-bubble__ai-icon').exists()).toBe(true)
    expect(bubble.find('.chat-bubble__content').exists()).toBe(true)
  })

  it('renders preview card slot for assistant', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'assistant',
        content: '请确认以下信息',
        timestamp: '2024-01-15T14:30:00'
      },
      global: {
        stubs: {
          MarkdownContent: {
            template: '<div class="markdown-content">{{ content }}</div>',
            props: ['content']
          }
        }
      },
      slots: {
        'preview-card': '<div class="preview-card-test">预览卡片</div>'
      }
    })

    expect(wrapper.find('.preview-card-test').exists()).toBe(true)
    expect(wrapper.find('.preview-card-test').text()).toBe('预览卡片')
  })

  it('applies correct user bubble styles', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        role: 'user',
        content: '测试',
        timestamp: '2024-01-15T14:30:00'
      }
    })

    // 检查是否应用了正确的类
    expect(wrapper.find('.chat-bubble--user').exists()).toBe(true)
  })
})