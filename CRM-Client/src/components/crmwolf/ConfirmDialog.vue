<script setup lang="ts">
/**
 * ConfirmDialog - 全局确认对话框组件
 * UI/UX Pro Max §8: confirmation-dialogs
 *
 * 特性：
 * - 函数式调用（通过 confirmDialog）
 * - 支持键盘操作（Enter 确认，Escape 取消）
 * - Focus 自动聚焦到确认按钮
 * - 点击遮罩层关闭
 */
import { useConfirmDialogState, handleConfirm, handleCancel } from '@/utils/confirmDialogImpl'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog'

const state = useConfirmDialogState()
</script>

<template>
  <AlertDialog :open="state.visible">
    <AlertDialogContent>
      <AlertDialogTitle>{{ state.options.title }}</AlertDialogTitle>
      <AlertDialogDescription>
        {{ state.options.message }}
      </AlertDialogDescription>

      <div class="flex justify-end gap-wolf-sm mt-wolf-lg">
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
      </div>
    </AlertDialogContent>
  </AlertDialog>
</template>