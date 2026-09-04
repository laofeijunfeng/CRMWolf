<script setup lang="ts">
/**
 * ConfirmDialog - 全局确认对话框组件
 * UI/UX Pro Max §8: confirmation-dialogs
 *
 * 特性：
 * - 函数式调用（通过 confirmDialog）
 * - 支持键盘操作（Enter 确认，Escape 取消）
 * - Focus 自动聚焦到确认按钮
 * - 通过取消按钮或 Escape 取消，避免误触遮罩层
 */
import { useConfirmDialogState, handleConfirm, handleCancel } from '@/utils/confirmDialogImpl'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogFooter,
} from '@/components/ui/alert-dialog'

const state = useConfirmDialogState()

const handleDialogOpenChange = (open: boolean): void => {
  if (open) return

  // AlertDialogAction/Cancel 先触发底层 DialogClose，再触发按钮自身的 click
  // 监听器。如果这里同步按“关闭”处理，会把“确定”误判成“取消”，导致
  // confirmDialog() 得到 false，调用方自然不会继续执行后续 API。
  // 延迟到当前 click 事件完成后再兜底处理 Escape 等无按钮关闭场景；如果
  // 确定/取消按钮已经结算，visible 会变为 false，此处不会重复结算。
  Promise.resolve().then(() => {
    if (state.value.visible) handleCancel()
  })
}
</script>

<template>
  <AlertDialog :open="state.visible" @update:open="handleDialogOpenChange">
    <AlertDialogContent>
      <AlertDialogTitle>{{ state.options.title }}</AlertDialogTitle>
      <AlertDialogDescription>
        {{ state.options.message }}
      </AlertDialogDescription>

      <AlertDialogFooter>
        <AlertDialogCancel @click="handleCancel">
          {{ state.options.cancelText }}
        </AlertDialogCancel>
        <AlertDialogAction
          :class="{
            'bg-wolf-danger hover:bg-wolf-danger/90': state.options.variant === 'destructive',
          }"
          @click="handleConfirm"
        >
          {{ state.options.confirmText }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
