/**
 * pageTitle Store - 页面标题状态管理
 *
 * @description 统一管理 Header 显示的页面标题
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 页面标题 Store
 *
 * @example
 * // 在组件中使用
 * const pageTitleStore = usePageTitleStore()
 * const { title } = storeToRefs(pageTitleStore)
 * const { setTitle, reset } = pageTitleStore
 *
 * // 设置标题
 * setTitle('客户列表')
 *
 * // 重置为空
 * reset()
 */
export const usePageTitleStore = defineStore('pageTitle', () => {
  // ===== State（必须类型化） =====

  /** 页面标题 */
  const title = ref<string>('')

  // ===== Actions（必须参数和返回类型） =====

  /**
   * 设置页面标题
   *
   * @param val - 新的页面标题
   */
  const setTitle = (val: string): void => {
    title.value = val
  }

  /**
   * 重置页面标题为空字符串
   */
  const reset = (): void => {
    title.value = ''
  }

  // ===== 返回所有导出 =====
  return {
    // State
    title,
    // Actions
    setTitle,
    reset
  }
})