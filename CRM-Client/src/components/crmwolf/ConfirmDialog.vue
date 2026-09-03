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
  if (!open) handleCancel()
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
