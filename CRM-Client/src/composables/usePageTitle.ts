/**
 * usePageTitle Composable - 页面标题管理
 *
 * @description 封装页面标题设置逻辑，自动从 route.meta.title 设置静态标题
 */

import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePageTitleStore } from '@/stores/pageTitle'

/**
 * 页面标题管理 Composable
 *
 * 功能：
 * 1. 自动从 route.meta.title 设置静态标题
 * 2. 提供 setTitle() 设置动态标题（详情页使用）
 * 3. 页面卸载时自动 reset 标题
 *
 * @example
 * // 静态标题（route.meta.title）
 * usePageTitle()
 *
 * @example
 * // 动态标题
 * const { setTitle } = usePageTitle()
 * setTitle(customerDetail?.account_name || '客户详情')
 */
export function usePageTitle(): {
  setTitle: (val: string) => void
  resetTitle: () => void
} {
  const route = useRoute()
  const store = usePageTitleStore()

  // 自动设置 route.meta.title（静态标题）
  onMounted(() => {
    const title = route.meta?.title
    if (title !== undefined && title !== null && typeof title === 'string') {
      store.setTitle(title)
    }
  })

  // 页面卸载时重置标题
  onUnmounted(() => {
    store.reset()
  })

  return {
    setTitle: (val: string): void => store.setTitle(val),
    resetTitle: (): void => store.reset()
  }
}