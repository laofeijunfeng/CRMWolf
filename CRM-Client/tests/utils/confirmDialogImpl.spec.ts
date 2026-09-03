import { describe, expect, it } from 'vitest'
import {
  createConfirmDialog,
  handleCancel,
  handleConfirm,
  useConfirmDialogState,
} from '@/utils/confirmDialogImpl'

describe('confirmDialogImpl', () => {
  it('queues concurrent confirmations instead of overwriting the first resolver', async () => {
    const state = useConfirmDialogState()
    const first = createConfirmDialog({
      title: '第一个确认',
      message: '第一个操作',
      confirmText: '继续',
      cancelText: '取消',
      variant: 'default',
    })
    const second = createConfirmDialog({
      title: '第二个确认',
      message: '第二个操作',
      confirmText: '继续',
      cancelText: '取消',
      variant: 'destructive',
    })

    expect(state.value.visible).toBe(true)
    expect(state.value.options.title).toBe('第一个确认')

    handleConfirm()
    await expect(first).resolves.toBe(true)
    expect(state.value.visible).toBe(true)
    expect(state.value.options.title).toBe('第二个确认')

    handleCancel()
    await expect(second).resolves.toBe(false)
    expect(state.value.visible).toBe(false)
  })
})
