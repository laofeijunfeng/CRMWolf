import { ref } from 'vue'

export interface RenameDialogOptions {
  title?: string
  description?: string
  initialName: string
  confirmText?: string
  cancelText?: string
  maxLength?: number
}

const renameDialogState = ref<{
  visible: boolean
  options: Required<RenameDialogOptions>
  resolve: ((value: string | null) => void) | null
}>({
  visible: false,
  options: {
    title: '重命名',
    description: '',
    initialName: '',
    confirmText: '保存',
    cancelText: '取消',
    maxLength: 100,
  },
  resolve: null,
})

export function renameDialog(options: RenameDialogOptions): Promise<string | null> {
  return new Promise((resolve) => {
    renameDialogState.value = {
      visible: true,
      options: {
        title: options.title ?? '重命名',
        description: options.description ?? '',
        initialName: options.initialName,
        confirmText: options.confirmText ?? '保存',
        cancelText: options.cancelText ?? '取消',
        maxLength: options.maxLength ?? 100,
      },
      resolve,
    }
  })
}

export function useRenameDialogState(): typeof renameDialogState {
  return renameDialogState
}

export function confirmRenameDialog(value: string): void {
  renameDialogState.value.resolve?.(value)
  renameDialogState.value.visible = false
  renameDialogState.value.resolve = null
}

export function cancelRenameDialog(): void {
  renameDialogState.value.resolve?.(null)
  renameDialogState.value.visible = false
  renameDialogState.value.resolve = null
}
