import { describe, expect, it, vi } from 'vitest'

const createConfirmDialog = vi.hoisted(() => vi.fn())
vi.mock('@/utils/confirmDialogImpl', () => ({ createConfirmDialog }))

import { confirmLogout } from '@/utils/confirmDialog'

describe('confirmLogout', () => {
  it('uses destructive confirmation text that explains re-login is required', async () => {
    createConfirmDialog.mockResolvedValueOnce(true)

    await confirmLogout()

    expect(createConfirmDialog).toHaveBeenCalledWith({
      title: '退出登录',
      message: '退出后需要重新登录才能继续使用系统。',
      confirmText: '退出登录',
      cancelText: '取消',
      variant: 'destructive',
    })
  })
})
