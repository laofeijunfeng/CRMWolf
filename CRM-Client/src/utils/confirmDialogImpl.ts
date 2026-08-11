/**
 * 确认对话框实现
 * 使用全局状态驱动确认对话框
 */

import { ref } from 'vue'
import type { Ref } from 'vue'

export interface ConfirmDialogOptions {
  message: string
  title: string
  confirmText: string
  cancelText: string
  variant: 'default' | 'destructive'
}

// 全局确认对话框状态
const confirmDialogState = ref<{
  visible: boolean
  options: ConfirmDialogOptions
  resolve: ((value: boolean) => void) | null
}>({
  visible: false,
  options: {
    message: '',
    title: '确认',
    confirmText: '确定',
    cancelText: '取消',
    variant: 'default',
  },
  resolve: null,
})

/**
 * 创建确认对话框
 * 通过 Promise 实现异步调用
 */
export function createConfirmDialog(options: ConfirmDialogOptions): Promise<boolean> {
  return new Promise((resolve) => {
    confirmDialogState.value = {
      visible: true,
      options,
      resolve,
    }
  })
}

/**
 * 确认对话框组件的状态管理
 */
export function useConfirmDialogState(): Ref<typeof confirmDialogState.value> {
  return confirmDialogState
}

/**
 * 处理确认
 */
export function handleConfirm(): void {
  confirmDialogState.value.resolve?.(true)
  confirmDialogState.value.visible = false
}

/**
 * 处理取消
 */
export function handleCancel(): void {
  confirmDialogState.value.resolve?.(false)
  confirmDialogState.value.visible = false
}
