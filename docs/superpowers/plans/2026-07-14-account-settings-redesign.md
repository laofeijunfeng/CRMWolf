# 账户设置页面重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将个人账户能力迁移到全新的 `/settings/account` 页面，收拢用户菜单入口，并在桌面端和移动端提供一致、安全、可访问的账户设置与退出登录旅程。

**Architecture:** 账户信息页是由 `userStore` 驱动的独立、懒加载路由，使用现有 shadcn-vue/CRMWolf 原语渲染只读资料和密码修改 Dialog。`AppLayout` 负责桌面端的 `DropdownMenu` 用户菜单和统一退出编排；`BottomNav` 负责移动端的可达入口并把退出意图向上 emit 给 `AppLayout`，从而避免导航组件直接修改认证状态。

**Tech Stack:** Vue 3 Composition API、TypeScript、Vue Router、Pinia、Vitest、Vue Test Utils、shadcn-vue / Reka UI wrappers、VeeValidate + Zod、vue-sonner、SCSS V2 Design Tokens、lucide-vue-next。

## Global Constraints

- 不导入、嵌套或改造 `src/views/Settings.vue`；该页面的系统管理入口、操作记录和旧账户 UI 都不在本次范围内。
- 所有新增 UI 使用 `src/components/ui/` 已安装的 shadcn-vue 原语；禁止新增 Element Plus UI、自定义 Button/Dialog/Dropdown/Card。
- 新增 SCSS 必须 `@use '@/styles/variables-v2.scss' as *;`，并只使用 `-v2` token；禁止硬编码颜色、间距和圆角。
- 使用 `lucide-vue-next` 图标；禁止 emoji 和 Element Plus 图标。
- 组件与 store 禁止 `any`、`as any`、`@ts-ignore`、非空断言；Pinia state 使用带泛型的 `ref<T>()`，异步 store action 必须有返回类型和 try/catch。
- API 请求必须按项目规则经 Zod 校验；本次仅调用已有 `authApi.getUserInfo()` 和 `authApi.changePassword()`，不新增后端 API。
- 退出登录不发网络请求：清理 token、用户资料、权限和团队状态，然后 `router.replace('/login')`；失败时 `window.location.assign('/login')` 兜底。
- 桌面端账户菜单以 shadcn-vue `DropdownMenu` 实现，允许有限的 hover 打开适配，但不得重写其焦点、Esc、键盘导航或动画；触发器必须是可聚焦 button。
- 移动端不能将隐藏侧栏作为唯一入口：BottomNav 的“更多”中必须提供“账户设置”和“退出登录”。
- 密码字段使用关联 Label、password visibility toggle、`autocomplete`、失焦/提交校验、字段旁 `role="alert"` 错误和首个错误聚焦；新密码规则为 6–50 字符且确认值必须一致。
- 所有可交互控件在移动端最小点击区域为 44×44pt，保留可见 focus ring，支持 `prefers-reduced-motion`；亮色和暗色 token 均独立验证。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `CRM-Client/src/stores/user.ts` | 提供唯一的本地 `logout(): void`，协调 user、permission、team 状态清理。 |
| `CRM-Client/src/utils/confirmDialog.ts` | 定义与设计系统一致、具有 destructive 语义且说明需重新登录的 `confirmLogout()` 文案。 |
| `CRM-Client/src/router/index.ts` | 注册受认证保护、懒加载的 `AccountSettings` 路由。 |
| `CRM-Client/src/components/crmwolf/BottomNav.vue` | 公开移动端“账户设置”和 `logout` 意图；不直接操作 store。 |
| `CRM-Client/src/components/crmwolf/BottomNavOverflow.vue` | 将 overflow 条目渲染为 shadcn-vue 可访问菜单，并区分路由与退出 action。 |
| `CRM-Client/src/AppLayout.vue` | 用 `DropdownMenu` 替换自定义用户菜单，维护团队切换，编排统一确认后的登出，消费 BottomNav 的退出事件。 |
| `CRM-Client/src/views/AccountSettings.vue` | 新的账户设置页面、资料/详情卡片、加载和错误态、密码修改 Dialog。 |
| `CRM-Client/src/schemas/account-settings.ts` | 密码表单的 Zod schema 与推导类型，避免页面内重复手写校验。 |
| `CRM-Client/src/stores/__tests__/user.spec.ts` | 验证统一退出时所有本地状态都会清空。 |
| `CRM-Client/tests/components/BottomNav.spec.ts` | 验证移动端“更多”提供账户设置和退出操作。 |
| `CRM-Client/tests/components/AppLayout.spec.ts` | 验证桌面用户菜单、账户路由、统一退出确认和焦点可达性。 |
| `CRM-Client/tests/views/AccountSettings.spec.ts` | 验证账户资料、空态、加载/重试、密码表单和密码 API 交互。 |

## Interfaces

```ts
// src/stores/user.ts
logout(): void

// src/components/crmwolf/BottomNav.vue
// emitted by BottomNav and consumed by AppLayout
emit('logout'): void

// src/schemas/account-settings.ts
export const changePasswordSchema: z.ZodObject<{
  oldPassword: z.ZodString
  newPassword: z.ZodString
  confirmPassword: z.ZodString
}>
export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>
```

---

### Task 1: Make local logout complete and independently testable

**Files:**
- Modify: `CRM-Client/src/stores/user.ts`
- Modify: `CRM-Client/src/utils/confirmDialog.ts`
- Create: `CRM-Client/src/stores/__tests__/user.spec.ts`
- Create: `CRM-Client/tests/utils/confirmDialog.spec.ts`

**Consumes:** `usePermissionStore().clearPermissions(): void`, `useTeamStore().clearTeam(): void`, and the global `ConfirmDialog` host already mounted in `App.vue`.

**Produces:** `useUserStore().logout(): void`, which clears token, user profile, persisted token, permissions and teams before any caller changes route; `confirmLogout(): Promise<boolean>`, whose destructive confirmation explicitly states the re-login consequence.

- [ ] **Step 1: Write the failing store and logout-confirmation tests**

```ts
// src/stores/__tests__/user.spec.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const permissionStore = vi.hoisted(() => ({ clearPermissions: vi.fn() }))
const teamStore = vi.hoisted(() => ({ clearTeam: vi.fn() }))

vi.mock('@/stores/permissions', () => ({
  usePermissionStore: () => permissionStore,
}))
vi.mock('@/stores/team', () => ({
  useTeamStore: () => teamStore,
}))

import { useUserStore } from '@/stores/user'

describe('useUserStore.logout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    permissionStore.clearPermissions.mockClear()
    teamStore.clearTeam.mockClear()
  })

  it('clears user, permission, team, and persisted authentication state', () => {
    const store = useUserStore()
    store.setToken('access-token')
    store.setUserInfo({
      id: 1, name: '王小明', email: 'wang@example.com', status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
    })

    store.logout()

    expect(store.token).toBe('')
    expect(store.userInfo).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(permissionStore.clearPermissions).toHaveBeenCalledOnce()
    expect(teamStore.clearTeam).toHaveBeenCalledOnce()
  })
})
```

Add the following focused helper test:

```ts
// tests/utils/confirmDialog.spec.ts
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
```

- [ ] **Step 2: Run the tests and verify the cleanup assertions fail**

Run: `cd CRM-Client && npm run test:unit -- src/stores/__tests__/user.spec.ts tests/utils/confirmDialog.spec.ts`

Expected: FAIL because `logout()` currently does not call `clearPermissions()` or `clearTeam()`, and `confirmLogout()` currently uses generic, non-destructive confirmation copy.

- [ ] **Step 3: Implement the single logout boundary and design-system confirmation**

Update imports and replace the logout action in `src/stores/user.ts` with typed functions matching store rules:

```ts
import { usePermissionStore } from './permissions'
import { useTeamStore } from './team'

const logout = (): void => {
  const permissionStore = usePermissionStore()
  const teamStore = useTeamStore()

  token.value = ''
  userInfo.value = null
  localStorage.removeItem('token')
  permissionStore.clearPermissions()
  teamStore.clearTeam()
}
```

Do not call `router`, `toast`, or any UI confirmation API from this store.

Replace `confirmLogout()` in `src/utils/confirmDialog.ts` with the exact shared destructive contract:

```ts
export async function confirmLogout(): Promise<boolean> {
  return confirmDialog(
    '退出后需要重新登录才能继续使用系统。',
    '退出登录',
    { variant: 'destructive', confirmText: '退出登录', cancelText: '取消' },
  )
}
```

The existing global `ConfirmDialog` component in `App.vue` already renders this helper through shadcn-vue `AlertDialog`; do not introduce a second confirmation host or direct Element Plus confirmation.

- [ ] **Step 4: Run the targeted tests and static check**

Run: `cd CRM-Client && npm run test:unit -- src/stores/__tests__/user.spec.ts tests/utils/confirmDialog.spec.ts && npm run type-check`

Expected: PASS; no TypeScript errors.

- [ ] **Step 5: Commit the state boundary**

```bash
git add CRM-Client/src/stores/user.ts CRM-Client/src/utils/confirmDialog.ts CRM-Client/src/stores/__tests__/user.spec.ts CRM-Client/tests/utils/confirmDialog.spec.ts
git commit -m "feat(auth): clear all local state on logout"
```

### Task 2: Add an account route and a reachable mobile account/logout path

**Files:**
- Modify: `CRM-Client/src/router/index.ts`
- Modify: `CRM-Client/src/components/crmwolf/BottomNav.vue`
- Modify: `CRM-Client/src/components/crmwolf/BottomNavOverflow.vue`
- Create: `CRM-Client/tests/components/BottomNav.spec.ts`

**Consumes:** `AccountSettings.vue` route component (introduced as a lazy import and created in Task 3) and the existing `BottomNav` placement in `AppLayout`.

**Produces:** `/settings/account`, plus `BottomNav` events `navigate(route: string)` and `logout()` that the layout can handle in Task 4.

- [ ] **Step 1: Write failing route and mobile-navigation tests**

```ts
// tests/components/BottomNav.spec.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const router = vi.hoisted(() => ({ push: vi.fn() }))
const route = vi.hoisted(() => ({ path: '/customers' }))
vi.mock('vue-router', () => ({ useRouter: () => router, useRoute: () => route }))

import BottomNav from '@/components/crmwolf/BottomNav.vue'

describe('BottomNav account affordances', () => {
  beforeEach(() => router.push.mockReset())

  it('offers account settings in More and navigates to its dedicated route', async () => {
    const wrapper = mount(BottomNav)
    await wrapper.get('button[aria-label="更多"]').trigger('click')
    const accountItem = document.body.querySelector('[role="menuitem"][aria-label="账户设置"]') as HTMLElement
    expect(accountItem).not.toBeNull()
    accountItem.click()
    expect(router.push).toHaveBeenCalledWith('/settings/account')
  })

  it('emits logout rather than mutating authentication state itself', async () => {
    const wrapper = mount(BottomNav)
    await wrapper.get('button[aria-label="更多"]').trigger('click')
    const logoutItem = document.body.querySelector('[role="menuitem"][aria-label="退出登录"]') as HTMLElement
    logoutItem.click()
    expect(wrapper.emitted('logout')).toEqual([[]])
  })
})
```

Add a route test in the same file or a focused router test that asserts the `/settings/account` record has `meta.requiresAuth === true` and `meta.title === '账户设置'`.

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd CRM-Client && npm run test:unit -- tests/components/BottomNav.spec.ts`

Expected: FAIL because the More menu currently links only to `/settings` and has no logout item/event.

- [ ] **Step 3: Add the route and discriminated mobile overflow actions**

Add this route after the legacy `settings` route in `src/router/index.ts`:

```ts
{
  path: 'settings/account',
  name: 'AccountSettings',
  component: () => import('@/views/AccountSettings.vue'),
  meta: { requiresAuth: true, title: '账户设置' },
},
```

In `BottomNav.vue`, replace the single navigation-only item contract with a local discriminated union and emit declaration:

```ts
interface RouteNavItem { kind: 'route'; route: string; icon: Component; label: string }
interface ActionNavItem { kind: 'action'; action: 'logout'; icon: Component; label: string }
type NavItem = RouteNavItem | ActionNavItem

const emit = defineEmits<{
  logout: []
}>()

const overflowItems: NavItem[] = [
  { kind: 'route', route: '/leads', icon: Flag, label: '线索' },
  { kind: 'route', route: '/invoices', icon: Tickets, label: '发票' },
  { kind: 'route', route: '/approvals', icon: Bell, label: '审批' },
  { kind: 'route', route: '/settings/account', icon: Settings, label: '账户设置' },
  { kind: 'action', action: 'logout', icon: LogOut, label: '退出登录' },
]

const handleOverflowSelect = (item: NavItem): void => {
  if (item.kind === 'route') router.push(item.route)
  else emit('logout')
}
```

Use Lucide `Settings`, `LogOut`, and `More` icons rather than Element Plus icons in the changed navigation components. Update `BottomNavOverflow.vue` props/emits to receive `NavItem`, emit the selected `NavItem`, expose `aria-label` from the item label, and calculate active state only for `item.kind === 'route'`. Replace `el-popover` and role-bearing `div` menu items with the existing `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`, and `DropdownMenuItem` primitives. Each item selection must close the menu through the primitive’s native select behavior.

- [ ] **Step 4: Run the targeted tests and type check**

Run: `cd CRM-Client && npm run test:unit -- tests/components/BottomNav.spec.ts && npm run type-check`

Expected: PASS; `/settings/account` is the only mobile account destination and the navigation component emits, but does not execute, logout.

- [ ] **Step 5: Commit the route and mobile navigation change**

```bash
git add CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/BottomNav.vue CRM-Client/src/components/crmwolf/BottomNavOverflow.vue CRM-Client/tests/components/BottomNav.spec.ts
git commit -m "feat(navigation): add mobile account settings access"
```

### Task 3: Build the new account settings page with test-first password behavior

**Files:**
- Create: `CRM-Client/src/schemas/account-settings.ts`
- Create: `CRM-Client/src/views/AccountSettings.vue`
- Create: `CRM-Client/tests/views/AccountSettings.spec.ts`

**Consumes:** `authApi.getUserInfo(): Promise<UserResponse>`, `authApi.changePassword(data: ChangePasswordRequest)`, `useUserStore().userInfo`, `useUserStore().fetchUserInfo()`, `handleApiError(error, context)`, shadcn-vue primitives exported by `@/components/crmwolf`.

**Produces:** A standalone account page that never imports `Settings.vue`, shows load/error/empty-field states, and contains a validated password Dialog.

- [ ] **Step 1: Write failing page tests**

Mock `@/api/auth`, `@/stores/user`, `@/utils/errorHandler`, `vue-sonner`, and `vue-router`; use a user fixture with `created_at`, `updated_at`, optional avatar, and multiple roles. Include these executable assertions:

```ts
it('renders account information and locale dates without the legacy created_time field', () => {
  const wrapper = mountAccountPage({ userInfo: userFixture })
  expect(wrapper.get('h1').text()).toBe('账户设置')
  expect(wrapper.text()).toContain('wang@example.com')
  expect(wrapper.text()).toContain('产品部')
  expect(wrapper.text()).toContain('销售经理')
  expect(wrapper.text()).toContain(new Intl.DateTimeFormat().format(new Date(userFixture.created_at)))
})

it('loads profile data when the store is empty, and retries from an actionable error state', async () => {
  const { wrapper, userStore } = mountAccountPage({ userInfo: null })
  expect(userStore.fetchUserInfo).toHaveBeenCalledOnce()
  await userStore.fetchUserInfo.mockRejectedValueOnce(new Error('network'))
  await flushPromises()
  await wrapper.get('button').filter('[data-testid="account-retry"]').trigger('click')
  expect(userStore.fetchUserInfo).toHaveBeenCalledTimes(2)
})

it('validates password fields and submits only valid values', async () => {
  const wrapper = mountAccountPage({ userInfo: userFixture })
  await wrapper.get('[data-testid="change-password-trigger"]').trigger('click')
  await wrapper.get('input[name="oldPassword"]').setValue('old-password')
  await wrapper.get('input[name="newPassword"]').setValue('12345')
  await wrapper.get('form').trigger('submit')
  expect(authApi.changePassword).not.toHaveBeenCalled()
  expect(wrapper.get('[role="alert"]').text()).toContain('6–50')

  await wrapper.get('input[name="newPassword"]').setValue('new-password')
  await wrapper.get('input[name="confirmPassword"]').setValue('new-password')
  await wrapper.get('form').trigger('submit')
  expect(authApi.changePassword).toHaveBeenCalledWith({
    old_password: 'old-password', new_password: 'new-password',
  })
})
```

Also test `avatar` image error fallback, every absent field rendering “未设置”, successful password submission clears fields and closes the Dialog, failed submission calls `handleApiError(error, '修改密码')`, and a populated password Dialog requires confirmation before dismissal.

- [ ] **Step 2: Run the page test and verify it fails**

Run: `cd CRM-Client && npm run test:unit -- tests/views/AccountSettings.spec.ts`

Expected: FAIL because the schema and `AccountSettings.vue` do not yet exist.

- [ ] **Step 3: Add the typed password schema**

Create `src/schemas/account-settings.ts`:

```ts
import { z } from 'zod'

export const changePasswordSchema = z.object({
  oldPassword: z.string().min(1, '请输入当前密码'),
  newPassword: z.string().min(6, '新密码长度为 6–50 个字符').max(50, '新密码长度为 6–50 个字符'),
  confirmPassword: z.string().min(1, '请确认新密码'),
}).refine((values) => values.newPassword === values.confirmPassword, {
  message: '两次输入的密码不一致',
  path: ['confirmPassword'],
})

export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>
```

- [ ] **Step 4: Implement the independent `AccountSettings.vue` page**

Build the page from `Card`, `CardHeader`, `CardContent`, `Avatar`, `AvatarImage`, `AvatarFallback`, `Badge`, `Skeleton`, `Alert`, `AlertTitle`, `AlertDescription`, `Button`, `Dialog`, `DialogContent`, `DialogHeader`, `DialogFooter`, `DialogTitle`, `Label`, `Input`, `Tooltip`, `TooltipTrigger`, and `TooltipContent` imported from `@/components/crmwolf`. Use the existing `Form`, `FormField`, `FormItem`, `FormControl`, `FormLabel`, `FormMessage` wrappers from `@/components/ui/form`, together with `useForm<ChangePasswordFormValues>({ validationSchema: toTypedSchema(changePasswordSchema) })` from VeeValidate and `@vee-validate/zod`, rather than handwritten per-field validation.

Implement these concrete functions:

```ts
const isInitialLoad = ref<boolean>(false)
const loadError = ref<boolean>(false)
const avatarFailed = ref<boolean>(false)
const passwordDialogOpen = ref<boolean>(false)
const passwordVisible = reactive<Record<'oldPassword' | 'newPassword' | 'confirmPassword', boolean>>({
  oldPassword: false, newPassword: false, confirmPassword: false,
})

const displayValue = (value?: string | null): string => value?.trim() || '未设置'
const formatDateTime = (value?: string): string => {
  if (!value || Number.isNaN(Date.parse(value))) return '未设置'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

const loadUser = async (): Promise<void> => {
  isInitialLoad.value = true
  loadError.value = false
  try {
    await userStore.fetchUserInfo()
  } catch (error: unknown) {
    loadError.value = true
    handleApiError(error, '获取账户信息')
  } finally {
    isInitialLoad.value = false
  }
}

const submitPassword = handleSubmit(async (values): Promise<void> => {
  try {
    await authApi.changePassword({ old_password: values.oldPassword, new_password: values.newPassword })
    resetForm()
    passwordDialogOpen.value = false
    toast.success('密码修改成功')
  } catch (error: unknown) {
    handleApiError(error, '修改密码')
  }
})
```

On mount, call `loadUser()` only if `userStore.userInfo` is null. Render three Cards in the required order: personal information, account details, then security. Use `created_at` / `updated_at`; do not reference `created_time`. Render account status as textual Badge content, use a tabular-number class for user ID, and provide a native copy action only if it can be implemented with an existing `Button`/`Tooltip` and browser `navigator.clipboard`; otherwise display it read-only (no custom UI primitive).

For each password field render an associated `FormLabel`, a `FormControl`-wrapped `Input` named with the schema key, `autocomplete="current-password"` or `autocomplete="new-password"`, and an accessible `Button` that toggles its `type` plus an `aria-label` such as “显示新密码”. Render the existing `FormMessage` under each field and extend its rendered error node with `role="alert"`; make the new-password 6–50 character helper text permanently visible with `FormDescription`. After invalid submit, focus the first invalid input. If the dialog has dirty password values, call `confirmDialog('当前输入尚未保存，确定放弃本次修改吗？', '放弃修改', { variant: 'destructive', confirmText: '放弃修改' })` before allowing cancel/close; otherwise close and `resetForm()` immediately.

Use a scoped SCSS block with V2 tokens for only page layout and data-description grid. At narrow widths use one column, mobile input/button sizing tokens, word-breaking/wrapping for long values, `min-height: 100dvh` only when necessary, and a `prefers-reduced-motion` override that suppresses nonessential transform transitions. Do not override shadcn primitive animations.

- [ ] **Step 5: Run page tests and quality checks**

Run: `cd CRM-Client && npm run test:unit -- tests/views/AccountSettings.spec.ts && npm run lint && npm run lint:style && npm run type-check`

Expected: PASS; no Element Plus imports in `AccountSettings.vue`; no stylelint violations.

- [ ] **Step 6: Commit the new account page**

```bash
git add CRM-Client/src/schemas/account-settings.ts CRM-Client/src/views/AccountSettings.vue CRM-Client/tests/views/AccountSettings.spec.ts
git commit -m "feat(account): add standalone account settings page"
```

### Task 4: Replace the desktop account control with an accessible shadcn dropdown and centralize logout UI

**Files:**
- Modify: `CRM-Client/src/AppLayout.vue`
- Create: `CRM-Client/tests/components/AppLayout.spec.ts`

**Consumes:** `useUserStore().logout(): void` from Task 1; `confirmLogout(): Promise<boolean`; `BottomNav` `logout` event from Task 2; `/settings/account` route from Task 2.

**Produces:** A single desktop account-settings entry and a shared `requestLogout(): Promise<void>` action consumed by both desktop and mobile UI.

- [ ] **Step 1: Write failing AppLayout behavior tests**

Mock router, `confirmLogout`, stores, header/page-title stores, `ApprovalIcon`, and `BottomNav`. Test visible behavior rather than internal ref names:

```ts
it('has exactly one desktop account entry and routes it to /settings/account', async () => {
  const wrapper = mountLayout()
  const trigger = wrapper.get('button[aria-label="用户设置"]')
  await trigger.trigger('mouseenter')
  await flushPromises()
  expect(document.body.textContent).toContain('账户设置')
  expect(document.body.textContent).not.toContain('个人资料')
  ;(document.body.querySelector('[role="menuitem"][aria-label="账户设置"]') as HTMLElement).click()
  expect(router.push).toHaveBeenCalledWith('/settings/account')
})

it('makes the user trigger keyboard accessible and returns focus after Escape', async () => {
  const wrapper = mountLayout()
  const trigger = wrapper.get('button[aria-label="用户设置"]')
  await trigger.trigger('keydown', { key: 'Enter' })
  await flushPromises()
  await document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  expect(document.activeElement).toBe(trigger.element)
})

it('confirms then logs out and replaces the current history entry', async () => {
  confirmLogout.mockResolvedValue(true)
  const wrapper = mountLayout()
  await wrapper.get('button[aria-label="用户设置"]').trigger('keydown', { key: 'Enter' })
  await flushPromises()
  ;(document.body.querySelector('[role="menuitem"][aria-label="退出登录"]') as HTMLElement).click()
  await flushPromises()
  expect(userStore.logout).toHaveBeenCalledOnce()
  expect(router.replace).toHaveBeenCalledWith('/login')
})

it('does nothing when logout confirmation is cancelled', async () => {
  confirmLogout.mockResolvedValue(false)
  const wrapper = mountLayout()
  await wrapper.get('button[aria-label="用户设置"]').trigger('keydown', { key: 'Enter' })
  await flushPromises()
  ;(document.body.querySelector('[role="menuitem"][aria-label="退出登录"]') as HTMLElement).click()
  await flushPromises()
  expect(userStore.logout).not.toHaveBeenCalled()
})
```

Include a test asserting the `BottomNav` `logout` event calls the same `requestLogout()` behavior by stubbing `BottomNav` with `<button data-testid="mobile-logout" @click="$emit('logout')" />`, clicking it, and asserting `confirmLogout`, `userStore.logout`, and `router.replace('/login')` receive the same calls. Mount teleported content in `document.body` and clean it in `afterEach`.

- [ ] **Step 2: Run the AppLayout test and verify it fails**

Run: `cd CRM-Client && npm run test:unit -- tests/components/AppLayout.spec.ts`

Expected: FAIL because the custom menu still includes “个人资料”, and logout currently pushes without confirmation or complete cleanup.

- [ ] **Step 3: Replace the custom user menu and implement the shared flow**

In `AppLayout.vue`:

1. Replace the user footer `div role="button"` and manually-transitioned menu with `DropdownMenu` and a `DropdownMenuTrigger as-child` containing:

```vue
<button
  type="button"
  class="user-info"
  aria-label="用户设置"
  :aria-expanded="showUserDropdown"
  @mouseenter="openUserDropdownOnHover"
  @focus="openUserDropdownOnHover"
>
  <!-- existing Avatar/user name/team/Chevron content -->
</button>
```

2. Use `DropdownMenuContent side="top" align="start"` with existing team items, `DropdownMenuSeparator`, exactly one `DropdownMenuItem` labelled “账户设置”, and a separate destructive `DropdownMenuItem` labelled “退出登录”. Delete the “个人资料” item and `handleUserProfile`.
3. Control `showUserDropdown` only through the root `v-model:open` and desktop-only hover handlers. Ensure moving pointer from trigger to content does not close prematurely (attach `mouseleave` to a containing footer and schedule/cancel close without altering DropdownMenu keyboard behavior). Do not create a custom Escape listener or focus loop.
4. Import `DropdownMenu`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuSeparator`, `DropdownMenuTrigger`, `Avatar`, `AvatarImage`, `AvatarFallback`, and Lucide icons from `@/components/crmwolf` / `lucide-vue-next`. Remove obsolete `User` icon and any manual menu `Transition` styling.
5. Implement and expose the single action:

```ts
const requestLogout = async (): Promise<void> => {
  showUserDropdown.value = false
  if (!await confirmLogout()) return

  userStore.logout()
  toast.success('已退出登录')
  try {
    await router.replace('/login')
  } catch {
    window.location.assign('/login')
  }
}
```

6. Bind `<BottomNav @logout="requestLogout" />`. On mobile it is the explicit visible account/logout route; do not duplicate authentication state logic inside `BottomNav`.
7. Preserve `handleSwitchTeam(teamId: number): Promise<void>` but change only its menu close statement to the DropdownMenu state; keep existing success/error handling and `router.go(0)` behavior unless a test exposes a regression.
8. Add a visually-hidden skip link before navigation, `<main id="main-content" tabindex="-1">`, and after `router.push('/settings/account')` call `await nextTick(); document.getElementById('main-content')?.focus()` so route navigation has a meaningful keyboard/reader destination. Do not add a second semantic page heading in TopBar.

- [ ] **Step 4: Run focused tests and full frontend checks**

Run: `cd CRM-Client && npm run test:unit -- tests/components/AppLayout.spec.ts tests/components/BottomNav.spec.ts src/stores/__tests__/user.spec.ts tests/views/AccountSettings.spec.ts && npm run lint && npm run lint:style && npm run type-check && npm run build`

Expected: PASS; no duplicate “个人资料” label, logout confirms then uses `replace`, and all account entry points use shadcn primitives.

- [ ] **Step 5: Commit the desktop/mobile integration**

```bash
git add CRM-Client/src/AppLayout.vue CRM-Client/tests/components/AppLayout.spec.ts
git commit -m "feat(navigation): unify account menu and logout flow"
```

### Task 5: End-to-end visual, responsive, and accessibility verification

**Files:**
- Modify only if defects are found by this verification: the owning source/test file from Tasks 1–4.

**Consumes:** Fully implemented account route, AppLayout menu, BottomNav affordances, and tests.

**Produces:** Evidence that the approved user journeys work outside mocked tests, with no unrelated code changes.

- [ ] **Step 1: Start the frontend application**

Run: `cd CRM-Client && npm run dev`

Expected: Vite prints a local development URL.

- [ ] **Step 2: Exercise the desktop user journey in a real browser**

At ≥1024px while authenticated:

1. Hover and keyboard-focus the bottom sidebar user trigger; verify it opens upward.
2. Tab through team switching, “账户设置”, and “退出登录”; press Esc and confirm focus returns to the trigger.
3. Verify only “账户设置” exists—no “个人资料”.
4. Navigate to account settings and verify the cards show profile, account details, and security only.
5. Open password Dialog: test empty, too-short, mismatched, API success, API failure, visibility toggle, and dirty-dismiss confirmation.
6. Cancel logout and verify state persists; confirm logout and verify `/login` replaces history (browser Back cannot restore protected content).

- [ ] **Step 3: Exercise the mobile responsive journey**

At 375px portrait and a small landscape viewport:

1. Verify the sidebar is hidden and BottomNav remains visible above the safe area.
2. Open “更多”; verify “账户设置” and “退出登录” are visible, have labels/icons, and are touch-sized.
3. Navigate to account settings; verify content is single-column, long email/role text does not overflow, and password inputs remain at least 44px/16px body text.
4. Test at 768px, 1024px, and 1440px to verify the hand-off between BottomNav and sidebar has no duplicate or missing account access.

- [ ] **Step 4: Verify preference and contrast behavior**

1. Enable light and dark themes if the application supports theme selection; verify text, Badge labels, card borders, focus rings, dropdown and Dialog surfaces remain distinguishable.
2. Enable `prefers-reduced-motion`; verify menus and Dialog remain usable without transform-dependent interactions.
3. Use browser accessibility inspection or axe-core to validate heading order, button labels, menu roles, dialog focus trapping, field labels, field error announcements, and contrast warnings.

- [ ] **Step 5: Run final repository checks and commit any defect fixes separately**

Run: `cd CRM-Client && npm run lint && npm run lint:style && npm run type-check && npm run test:unit && npm run build`

Expected: all commands exit 0. If verification uncovers a defect, first add a focused regression test, make the minimal fix in its owning task file, rerun this complete command set, then commit with a scoped `fix(account): ...` message. Do not commit unrelated pre-existing worktree changes.
