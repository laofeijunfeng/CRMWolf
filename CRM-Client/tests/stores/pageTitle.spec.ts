/**
 * Task 1: pageTitle Store 测试
 *
 * 验证 store 管理页面标题状态：初始状态、设置标题、重置标题、多次更新
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { usePageTitleStore } from '@/stores/pageTitle'

describe('usePageTitleStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('初始状态', () => {
    it('初始标题为空字符串', () => {
      const store = usePageTitleStore()
      const { title } = storeToRefs(store)

      expect(title.value).toBe('')
    })
  })

  describe('setTitle', () => {
    it('设置标题为指定值', () => {
      const store = usePageTitleStore()
      const { title } = storeToRefs(store)

      store.setTitle('客户列表')

      expect(title.value).toBe('客户列表')
    })

    it('多次设置标题，保留最后一次', () => {
      const store = usePageTitleStore()
      const { title } = storeToRefs(store)

      store.setTitle('客户列表')
      expect(title.value).toBe('客户列表')

      store.setTitle('商机详情')
      expect(title.value).toBe('商机详情')

      store.setTitle('审批中心')
      expect(title.value).toBe('审批中心')
    })
  })

  describe('reset', () => {
    it('重置标题为空字符串', () => {
      const store = usePageTitleStore()
      const { title } = storeToRefs(store)

      store.setTitle('客户详情')
      expect(title.value).toBe('客户详情')

      store.reset()

      expect(title.value).toBe('')
    })

    it('多次调用 reset 仍保持空字符串', () => {
      const store = usePageTitleStore()
      const { title } = storeToRefs(store)

      store.setTitle('测试标题')
      store.reset()
      expect(title.value).toBe('')

      store.reset()
      expect(title.value).toBe('')
    })
  })
})