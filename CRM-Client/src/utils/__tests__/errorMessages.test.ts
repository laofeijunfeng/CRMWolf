import { describe, expect, it, vi } from 'vitest'

const toastError = vi.fn()
const toastSuccess = vi.fn()

vi.mock('vue-sonner', () => ({
  toast: {
    error: toastError,
    success: toastSuccess,
  },
}))

describe('errorMessages', () => {
  it('exports stable message helpers used by existing pages', async () => {
    const messages = await import('../errorMessages')

    expect(messages.getErrorMessage(new Error('HTTP error: 401'), '获取合同')).toBe('登录已过期，请重新登录')
    expect(messages.getSuccessMessage('创建', '回款计划')).toBe('回款计划已创建，可以继续下一步操作')
    expect(messages.getEmptyStateMessage('合同列表')).toEqual({
      title: '创建合同',
      description: '点击新建合同，管理合同签署',
    })
  })

  it('uses vue-sonner for accessible error and success notifications', async () => {
    const { showError, showSuccess } = await import('../errorMessages')

    showError(new Error('Network Error'), '获取合同')
    showSuccess('提交', '合同')

    expect(toastError).toHaveBeenCalledWith('网络连接中断，请检查网络后刷新页面')
    expect(toastSuccess).toHaveBeenCalledWith('合同已提交，可以继续下一步操作')
  })
})
