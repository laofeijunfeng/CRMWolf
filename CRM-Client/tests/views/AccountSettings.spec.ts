import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref, type Ref } from 'vue'

interface UserFixture {
  id: number
  name: string
  email: string
  mobile?: string
  avatar_url?: string
  employee_no?: string
  region?: string
  status: string
  created_at: string
  updated_at: string
  roles?: Array<{ id: number, name: string, code: string, created_at: string, updated_at: string }>
}

interface UserStoreMock {
  userInfo?: Ref<UserFixture | null>
  fetchUserInfo: ReturnType<typeof vi.fn>
}

const authApi = vi.hoisted(() => ({ getUserInfo: vi.fn(), changePassword: vi.fn() }))
// vi.hoisted runs before static imports, so it must not call ref(). The reactive ref
// is assigned after imports and before every component mount; storeToRefs then receives
// a real Vue ref and preserves reactivity.
const userStore = vi.hoisted<UserStoreMock>(() => ({ userInfo: undefined, fetchUserInfo: vi.fn() }))
const handleApiError = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn() }))
const confirmDialog = vi.hoisted(() => vi.fn())
const headerStore = vi.hoisted(() => ({ clear: vi.fn() }))

vi.mock('@/api/auth', () => ({ authApi }))
vi.mock('@/stores/user', () => ({ useUserStore: () => userStore }))
vi.mock('@/stores/header', () => ({ useHeaderStore: () => headerStore }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('@/utils/confirmDialog', () => ({ confirmDialog }))
vi.mock('vue-sonner', () => ({ toast }))
vi.mock('vue-router', () => ({ useRouter: vi.fn(), useRoute: vi.fn() }))

vi.mock('@/components/crmwolf', async () => {
  const { defineComponent, h } = await import('vue')
  const passthrough = (name: string) => defineComponent({ name, template: '<div><slot /></div>' })
  const button = defineComponent({ name: 'Button', inheritAttrs: false, template: '<button v-bind="$attrs"><slot /></button>' })
  const { Input } = await import('@/components/ui/input')
  const avatarImage = defineComponent({ name: 'AvatarImage', inheritAttrs: false, template: '<img v-bind="$attrs" />' })

  return {
    Alert: passthrough('Alert'), AlertDescription: passthrough('AlertDescription'), AlertTitle: passthrough('AlertTitle'),
    Avatar: passthrough('Avatar'), AvatarFallback: passthrough('AvatarFallback'), AvatarImage: avatarImage,
    Badge: passthrough('Badge'), Button: button, Card: passthrough('Card'), CardContent: passthrough('CardContent'),
    CardHeader: passthrough('CardHeader'), Dialog: defineComponent({
      name: 'Dialog', props: { open: Boolean }, setup: (props, { slots }) => () => props.open ? h('div', { role: 'dialog' }, slots.default?.()) : null,
    }),
    DialogContent: passthrough('DialogContent'), DialogFooter: passthrough('DialogFooter'), DialogHeader: passthrough('DialogHeader'),
    DialogTitle: passthrough('DialogTitle'), Input, Label: passthrough('Label'), Skeleton: passthrough('Skeleton'),
    Tooltip: passthrough('Tooltip'), TooltipContent: passthrough('TooltipContent'), TooltipTrigger: passthrough('TooltipTrigger'),
  }
})

import AccountSettings from '@/views/AccountSettings.vue'

const userFixture: UserFixture = {
  id: 7,
  name: '王晓明',
  email: 'wang@example.com',
  mobile: '13800000000',
  avatar_url: 'https://example.com/avatar.png',
  employee_no: 'E-001',
  region: '产品部',
  status: '启用',
  created_at: '2026-07-14T08:00:00.000Z',
  updated_at: '2026-07-14T09:00:00.000Z',
  roles: [
    { id: 1, name: '销售经理', code: 'sales_manager', created_at: '2026-01-01T00:00:00.000Z', updated_at: '2026-01-01T00:00:00.000Z' },
    { id: 2, name: '产品专员', code: 'product_manager', created_at: '2026-01-01T00:00:00.000Z', updated_at: '2026-01-01T00:00:00.000Z' },
  ],
}

const mountAccountPage = (options: { userInfo: UserFixture | null }) => {
  userStore.userInfo = ref(options.userInfo)
  return { wrapper: mount(AccountSettings), userStore }
}

describe('AccountSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    userStore.userInfo = ref(null)
    userStore.fetchUserInfo.mockResolvedValue(userFixture)
    authApi.changePassword.mockResolvedValue({ message: 'ok' })
    confirmDialog.mockResolvedValue(true)
  })

  it('clears inherited top-bar state and renders account information without a duplicate page heading', () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    expect(headerStore.clear).toHaveBeenCalledOnce()
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('查看账户资料并管理登录安全。')
    expect(wrapper.text()).toContain('wang@example.com')
    expect(wrapper.text()).toContain('产品部')
    expect(wrapper.text()).toContain('销售经理')
    expect(wrapper.text()).toContain(new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(userFixture.created_at)))
    expect(wrapper.text()).not.toContain('created_time')
  })

  it('marks account content to inherit the application typography system', () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    expect(wrapper.classes()).toContain('account-settings--system')
  })

  it('loads profile data when the store is empty, and retries from an actionable error state', async () => {
    userStore.fetchUserInfo.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(userFixture)
    const { wrapper } = mountAccountPage({ userInfo: null })
    await flushPromises()
    expect(userStore.fetchUserInfo).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="account-retry"]').text()).toBe('重试')
    await wrapper.get('[data-testid="account-retry"]').trigger('click')
    expect(userStore.fetchUserInfo).toHaveBeenCalledTimes(2)
  })

  it('validates password fields and submits only valid values', async () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
    await wrapper.get('input[name="oldPassword"]').setValue('old-password')
    await wrapper.get('input[name="newPassword"]').setValue('12345')
    // Supplying a matching confirmation isolates the new-password length error.
    await wrapper.get('input[name="confirmPassword"]').setValue('12345')
    await nextTick()
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(authApi.changePassword).not.toHaveBeenCalled()
      expect(wrapper.findAll('[role="alert"]').some(node => node.text().includes('6–50'))).toBe(true)
    })

    await wrapper.get('input[name="newPassword"]').setValue('new-password')
    await wrapper.get('input[name="confirmPassword"]').setValue('new-password')
    await nextTick()
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(authApi.changePassword).toHaveBeenCalledWith({ old_password: 'old-password', new_password: 'new-password' })
    })
  })

  it('falls back to initials when the avatar image fails', async () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    await wrapper.get('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('王')
  })

  it('renders 未设置 for each absent optional field', () => {
    const { wrapper } = mountAccountPage({
      userInfo: { ...userFixture, name: '', email: '', mobile: undefined, avatar_url: undefined, employee_no: undefined, region: undefined, status: '', roles: [] },
    })
    expect(wrapper.text().match(/未设置/g)?.length).toBeGreaterThanOrEqual(6)
  })

  it('clears password values and closes the dialog after a successful submission', async () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
    await wrapper.get('input[name="oldPassword"]').setValue('old-password')
    await wrapper.get('input[name="newPassword"]').setValue('new-password')
    await wrapper.get('input[name="confirmPassword"]').setValue('new-password')
    await nextTick()
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(authApi.changePassword).toHaveBeenCalledWith({ old_password: 'old-password', new_password: 'new-password' })
      expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
      expect(toast.success).toHaveBeenCalledWith('密码修改成功')
    })
    expect(wrapper.find('input[name="oldPassword"]').exists()).toBe(false)
  })

  it('reports a failed password submission', async () => {
    const error = new Error('network')
    authApi.changePassword.mockRejectedValueOnce(error)
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
    await wrapper.get('input[name="oldPassword"]').setValue('old-password')
    await wrapper.get('input[name="newPassword"]').setValue('new-password')
    await wrapper.get('input[name="confirmPassword"]').setValue('new-password')
    await nextTick()
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => {
      expect(handleApiError).toHaveBeenCalledWith(error, '修改密码')
    })
  })

  it('closes a populated password dialog directly and can open it again', async () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
    await wrapper.get('input[name="oldPassword"]').setValue('old-password')
    const cancelButton = wrapper.findAll('button[type="button"]').find((node) => node.text() === '取消')
    expect(cancelButton).toBeDefined()
    if (!cancelButton) throw new Error('未找到取消修改按钮')

    await cancelButton.trigger('click')
    await flushPromises()
    expect(confirmDialog).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  })

  it('routes close requests through the same direct dialog-close path', async () => {
    const { wrapper } = mountAccountPage({ userInfo: userFixture })
    await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
    const dialog = wrapper.getComponent({ name: 'Dialog' })
    dialog.vm.$emit('update:open', false)
    await flushPromises()
    expect(confirmDialog).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
})
