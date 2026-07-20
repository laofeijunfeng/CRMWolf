/**
 * 统一确认对话框工具
 * UI/UX Pro Max §8: confirmation-dialogs
 *
 * 职责：
 * - 提供统一确认交互
 * - 提供函数式调用方式
 * - 符合 UI/UX Pro Max 规范
 *
 * @example
 * // 基本用法
 * const confirmed = await confirmDialog('确定删除该客户？', '删除确认')
 * if (confirmed) {
 *   // 执行删除
 * }
 *
 * @example
 * // 危险操作
 * const confirmed = await confirmDialog('此操作不可恢复，确定删除？', '删除确认', {
 *   variant: 'destructive'
 * })
 */

import { createConfirmDialog } from './confirmDialogImpl'

export interface ConfirmOptions {
  /** 标题 */
  title?: string
  /** 确认按钮文字 */
  confirmText?: string
  /** 取消按钮文字 */
  cancelText?: string
  /** 是否为危险操作（红色确认按钮） */
  variant?: 'default' | 'destructive'
}

/**
 * 显示确认对话框
 *
 * @param message - 确认消息
 * @param title - 标题（可选）
 * @param options - 其他选项（可选）
 * @returns Promise<boolean> - true 表示确认，false 表示取消
 */
export async function confirmDialog(
  message: string,
  title?: string,
  options?: ConfirmOptions
): Promise<boolean> {
  return createConfirmDialog({
    message,
    title: title ?? '确认',
    confirmText: options?.confirmText ?? '确定',
    cancelText: options?.cancelText ?? '取消',
    variant: options?.variant ?? 'default',
  })
}

/**
 * 删除确认快捷方法
 */
export async function confirmDelete(itemName = '该项'): Promise<boolean> {
  return confirmDialog(
    `确定删除${itemName}？此操作不可恢复。`,
    '删除确认',
    { variant: 'destructive', confirmText: '删除' }
  )
}

/**
 * 退出登录确认快捷方法
 */
export async function confirmLogout(): Promise<boolean> {
  return confirmDialog(
    '退出后需要重新登录才能继续使用系统。',
    '退出登录',
    { variant: 'destructive', confirmText: '退出登录', cancelText: '取消' },
  )
}

/**
 * 提交确认快捷方法
 */
export async function confirmSubmit(actionName = '提交'): Promise<boolean> {
  return confirmDialog(
    `确定${actionName}吗？`,
    `${actionName}确认`
  )
}
