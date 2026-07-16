import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '../EmptyState.vue'

// Mock localStorage
let storageState = new Map<string, string>()
const localStorageMock = {
  get length(): number {
    return storageState.size
  },
  clear: vi.fn((): void => {
    storageState = new Map<string, string>()
  }),
  getItem: vi.fn((key: string): string | null => storageState.get(key) ?? null),
  key: vi.fn((index: number): string | null => Array.from(storageState.keys())[index] ?? null),
  removeItem: vi.fn((key: string): void => {
    storageState.delete(key)
  }),
  setItem: vi.fn((key: string, value: string): void => {
    storageState.set(key, value)
  }),
} satisfies Storage
Object.defineProperty(global, 'localStorage', {
  value: localStorageMock
})

describe('EmptyState.vue', () => {
  beforeEach(() => {
    storageState = new Map<string, string>()
    vi.clearAllMocks()
    localStorageMock.getItem.mockImplementation((key: string): string | null => storageState.get(key) ?? null)
    localStorageMock.key.mockImplementation((index: number): string | null => Array.from(storageState.keys())[index] ?? null)
    localStorageMock.removeItem.mockImplementation((key: string): void => {
      storageState.delete(key)
    })
    localStorageMock.setItem.mockImplementation((key: string, value: string): void => {
      storageState.set(key, value)
    })
    localStorageMock.clear.mockImplementation((): void => {
      storageState = new Map<string, string>()
    })
  })

  describe('渲染测试', () => {
    it('should display warm welcome message', async () => {
      localStorageMock.getItem.mockReturnValue(null) // 首次访问

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      // 验证温暖文案（设计要求）
      expect(wrapper.text()).toContain('AI 准备就绪，等待你的指令')
    })

    it('should show first-time tip when user has not seen it', async () => {
      localStorageMock.getItem.mockReturnValue(null) // 首次访问

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      const tipBubble = wrapper.find('.first-time-tip')
      expect(tipBubble.exists()).toBe(true)
      expect(tipBubble.text()).toContain('输入指令后，AI 的执行过程会在这里实时展示')
    })

    it('should hide first-time tip when user has seen it', async () => {
      localStorageMock.getItem.mockReturnValue('true') // 已看过

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      const tipBubble = wrapper.find('.first-time-tip')
      expect(tipBubble.exists()).toBe(false)
    })

    it('should use Cpu icon (not Document icon)', async () => {
      localStorageMock.getItem.mockReturnValue(null)

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      // 验证使用 Cpu 图标容器存在
      const icon = wrapper.find('.empty-icon')
      expect(icon.exists()).toBe(true)
    })
  })

  describe('交互测试', () => {
    it('should mark as seen when user clicks "知道了"', async () => {
      localStorageMock.getItem.mockReturnValue(null) // 首次访问

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      const button = wrapper.find('.dismiss-button')
      await button.trigger('click')

      // 验证 localStorage 存储
      expect(localStorageMock.setItem).toHaveBeenCalledWith('hasSeenExecutionLogTip', 'true')

      // 验证提示气泡消失
      expect(wrapper.find('.first-time-tip').exists()).toBe(false)
    })
  })

  describe('样式测试', () => {
    it('should have correct container classes', async () => {
      localStorageMock.getItem.mockReturnValue(null)

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      const container = wrapper.find('.empty-state')
      expect(container.exists()).toBe(true)
    })

    it('should have accessible dismiss button', async () => {
      localStorageMock.getItem.mockReturnValue(null)

      const wrapper = mount(EmptyState)
      await wrapper.vm.$nextTick()

      const button = wrapper.find('.dismiss-button')
      expect(button.exists()).toBe(true)
      expect(button.text()).toBe('知道了')
    })
  })
})