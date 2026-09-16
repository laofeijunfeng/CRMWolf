# 系统设置工作区视觉与操作统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/settings/**` 收成两种页面：列表走 DataTable，表单走全宽分组 Card，操作位置和业务页一致。

**Architecture:** 先加一层很薄的 `SettingsContent` 外壳（padding、一句说明、表单网格 class）。账户/团队/AI/通知/集成改成全宽分组表单；成员/角色/审批/来源/采购/产品/阶段改成真页面 + `defineListFields` + DataTable。最后删掉 `SettingsModulePage` 对 Sheet 的嵌入。业务逻辑、权限码、Dialog 短任务、脱敏规则不动。

**Tech Stack:** Vue 3 + TypeScript + Pinia + Vitest + 现有 shadcn-vue Card/Form + `DataTable` / `defineListFields` / `useTopBarRegistration`。

## Global Constraints

- 合同：`docs/superpowers/specs/2026-09-17-settings-workspace-unification-design.md`（已确认）。
- 不改权限码、所有者兜底、`settingsNavigation.ts` 的 path/id/权限语义。
- 不引入新 UI 库，不另做设置色板。
- 不新增 `SettingsPageHeader` / `SettingsListPage` / `SettingsSection`。
- 不为设置列表升级后端 list-query；业务列必须 `filter: false` + `sort: false` 并写 `filterDisabledReason` / `sortDisabledReason`，文案固定为 `本期仍全量读取当前团队数据，未接入服务端 list-query`。
- DataTable 调用方必须满足 `listFieldCatalog.test.ts`：`:fields="fields"`、`ListFieldDefinition`、`:get-row-actions="getRowActions"`、`#mobile-actions`，禁止 `:columns` / `key: 'actions'`。
- 列表主操作进 TopBar（`HeaderAction.type: 'primary'`）；表单保存只放底部 `.settings-form-actions`，TopBar 不挂保存。
- 搜索必须走 `DataTableSearch` 提交，禁止 `v-model` 跟输入即时过滤。
- 禁止 `any` / `as any` / `@ts-ignore`。
- 不提交 `/tmp` 效果样例，不碰无关 dirty 文件。
- 中间任务只跑步骤里的聚焦测试。
- 不改审批画布产品、不合并两套审批页、不做所有权转移。
- `SystemConfig.vue` 本计划不删（`/system-config` 已重定向）；不要为了干净去改 `AppLayout.spec.ts` 对它的源码扫描。

## File map

- Create: `CRM-Client/src/views/settings/SettingsContent.vue`
- Create: `CRM-Client/src/views/settings/settingsListCatalog.ts`
- Create: `CRM-Client/src/views/settings/SettingsMembersPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsRolesPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsApprovalFlowsPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsAcquisitionSourcesPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsProcurementMethodsPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsProductsPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsAIPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsNotificationsPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsIntegrationsPage.vue`
- Create: `CRM-Client/src/composables/useSettingsUnsavedLeave.ts`
- Modify: `CRM-Client/src/views/AccountSettings.vue`
- Modify: `CRM-Client/src/views/TeamSettings.vue`
- Modify: `CRM-Client/src/views/ProcurementStagesSettings.vue`
- Modify: `CRM-Client/src/views/ApprovalFlowsNew.vue`
- Modify: `CRM-Client/src/router/index.ts`
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts`
- Modify: `CRM-Client/src/settingsNavigation.test.ts`
- Modify: `CRM-Client/tests/views/AccountSettings.spec.ts`
- Modify then delete: `CRM-Client/src/views/SettingsModulePage.vue`
- Tests migrate off: `CRM-Client/src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts`、`ProductPanel.test.ts`
- Keep Dialog/API inside existing system-config files until the corresponding page task copies the script and drops ListCard/Sheet chrome. After a page ships, that Sheet/Panel is no longer a settings route host.

---

### Task 1: SettingsContent shell

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsContent.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsContent.test.ts`

**Interfaces:**
- Consumes: 无。
- Produces: `SettingsContent` props `{ ariaLabel: string; description?: string }`；slot 内容；class `settings-content`；可选 `p.settings-content__description`；`:slotted` 工具 class：`settings-form-grid`、`settings-form-grid-full`、`settings-form-actions`、`settings-dl`、`settings-setting-row`。

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsContent from '../SettingsContent.vue'

describe('SettingsContent', () => {
  it('renders a full-width main landmark without a page heading or max-width shell', () => {
    const wrapper = mount(SettingsContent, {
      props: { ariaLabel: '账户设置', description: '个人资料和登录安全。' },
      slots: { default: '<div class="probe">body</div>' },
    })
    expect(wrapper.element.tagName).toBe('MAIN')
    expect(wrapper.attributes('aria-label')).toBe('账户设置')
    expect(wrapper.classes()).toContain('settings-content')
    expect(wrapper.classes().join(' ')).not.toContain('max-w-6xl')
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.get('p.settings-content__description').text()).toBe('个人资料和登录安全。')
    expect(wrapper.get('.probe').text()).toBe('body')
    wrapper.unmount()
  })

  it('omits the description paragraph when description is empty', () => {
    const wrapper = mount(SettingsContent, { props: { ariaLabel: '角色管理' } })
    expect(wrapper.find('p.settings-content__description').exists()).toBe(false)
    wrapper.unmount()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsContent.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement SettingsContent**

```vue
<script setup lang="ts">
interface Props {
  ariaLabel: string
  description?: string
}

withDefaults(defineProps<Props>(), {
  description: '',
})
</script>

<template>
  <main class="settings-content" :aria-label="ariaLabel">
    <p v-if="description.length > 0" class="settings-content__description">{{ description }}</p>
    <slot />
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.settings-content {
  min-height: 100%;
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-lg-v2;
}

.settings-content__description {
  margin: 0;
  font-size: $wolf-font-size-auxiliary-v2;
  color: $wolf-text-secondary-v2;
}

:slotted(.settings-form-grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: $wolf-form-item-gap-v2;
}

:slotted(.settings-form-grid-full) {
  grid-column: 1 / -1;
}

:slotted(.settings-form-actions) {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm-v2;
  background: $wolf-bg-card-v2;
  border-radius: $wolf-radius-surface-v2;
  padding: $wolf-card-padding-v2;
  box-shadow: $wolf-shadow-card-v2;
}

:slotted(.settings-dl) {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) 120px minmax(0, 1fr);
  gap: $wolf-space-md-v2 $wolf-space-xl-v2;
  margin: 0;
  font-size: $wolf-font-size-body-v2;
}

:slotted(.settings-dl dt) {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;
}

:slotted(.settings-dl dd) {
  margin: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

:slotted(.settings-setting-row) {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $wolf-space-lg-v2;
  padding: $wolf-space-md-v2 0;
  border-top: 1px solid $wolf-border-light-v2;
}

:slotted(.settings-setting-row:first-child) {
  border-top: 0;
  padding-top: 0;
}

@media (max-width: $wolf-breakpoint-sm-v2) {
  .settings-content {
    padding: $wolf-page-padding-mobile-v2;
  }

  :slotted(.settings-form-grid),
  :slotted(.settings-dl) {
    grid-template-columns: 1fr;
  }

  :slotted(.settings-setting-row) {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
```

- [ ] **Step 4: Re-run the test**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsContent.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsContent.vue CRM-Client/src/views/settings/__tests__/SettingsContent.test.ts
git commit -m "feat(settings): add full-width settings content shell"
```

---

### Task 2: Strip duplicate page chrome from existing settings hosts

**Files:**
- Modify: `CRM-Client/src/views/AccountSettings.vue`
- Modify: `CRM-Client/src/views/TeamSettings.vue`
- Modify: `CRM-Client/src/views/SettingsModulePage.vue`
- Modify: `CRM-Client/src/views/ProcurementStagesSettings.vue`
- Modify: `CRM-Client/tests/views/AccountSettings.spec.ts`
- Create: `CRM-Client/src/views/__tests__/TeamSettings.chrome.test.ts`
- Create: `CRM-Client/src/views/__tests__/SettingsModulePage.chrome.test.ts`

**Interfaces:**
- Consumes: `SettingsContent` from Task 1。
- Produces: 四个宿主都不再渲染「系统设置」眉题、`text-2xl` 页内 H1、`max-w-6xl`。账户页继续 `headerStore.clear()` 且没有 `h1`。

- [ ] **Step 1: Extend failing chrome assertions**

In `CRM-Client/tests/views/AccountSettings.spec.ts`，现有 `clears inherited top-bar state...` 已断言无 `h1`。追加：

```ts
it('wraps account content in the settings shell instead of a max-width page', () => {
  const { wrapper } = mountAccountPage({ userInfo: userFixture })
  expect(wrapper.findComponent({ name: 'SettingsContent' }).exists()).toBe(true)
  expect(wrapper.classes().join(' ')).not.toContain('max-w-6xl')
  expect(wrapper.text()).not.toContain('系统设置')
})
```

`CRM-Client/src/views/__tests__/TeamSettings.chrome.test.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TeamSettings from '@/views/TeamSettings.vue'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'

vi.mock('@/api/team', () => ({
  teamApi: { getTeamDetail: vi.fn(), updateTeam: vi.fn(), regenerateInviteCode: vi.fn() },
}))

describe('TeamSettings chrome', () => {
  it('does not render a duplicate settings heading or max-width shell', () => {
    setActivePinia(createPinia())
    const teamStore = useTeamStore()
    const permissionStore = usePermissionStore()
    permissionStore.loadState = 'ready'
    teamStore.currentTeam = { id: 1, name: '演示', code: 'DEMO', owner_id: '1', created_at: '2026-01-01T00:00:00Z' }
    const wrapper = mount(TeamSettings, { global: { stubs: { ErrorState: true, Card: { template: '<div><slot /></div>' }, CardHeader: true, CardTitle: true, CardDescription: true, CardContent: true, Button: true, Input: true, Label: true, Skeleton: true } } })
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('系统设置')
    expect(wrapper.html()).not.toContain('max-w-6xl')
    wrapper.unmount()
  })
})
```

`CRM-Client/src/views/__tests__/SettingsModulePage.chrome.test.ts` 用读源码，避免把整页权限树 mock 起来：

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('settings host chrome', () => {
  it.each([
    'src/views/SettingsModulePage.vue',
    'src/views/ProcurementStagesSettings.vue',
    'src/views/TeamSettings.vue',
  ])('stops %s from drawing a second page title', (relativePath) => {
    const source = readFileSync(resolve(process.cwd(), relativePath), 'utf8')
    expect(source).toContain('SettingsContent')
    expect(source).not.toContain('max-w-6xl')
    expect(source).not.toContain('text-2xl font-semibold tracking-tight')
    expect(source).not.toContain('系统设置 /')
  })
})
```

- [ ] **Step 2: Run tests and watch chrome cases fail**

```bash
cd CRM-Client && npm run test:unit -- tests/views/AccountSettings.spec.ts src/views/__tests__/TeamSettings.chrome.test.ts src/views/__tests__/SettingsModulePage.chrome.test.ts
```

Expected: FAIL（还没有 `SettingsContent` 包装 / 仍有 `max-w-6xl`）。

- [ ] **Step 3: Wrap the four hosts**

`AccountSettings.vue`：用 `SettingsContent` 替换外层 `<main class="account-settings account-settings--system">`。`aria-label="账户设置"`，`description` 先留空（Task 3 再写）。删掉 `.account-settings` 的 padding/background（改由外壳负责），保留 `__profile` / `__details` / `__password-input` 等到 Task 3。import：

```ts
import SettingsContent from '@/views/settings/SettingsContent.vue'
```

`TeamSettings.vue` 模板改成：

```vue
<SettingsContent aria-label="团队信息与安全" description="维护当前团队资料、邀请入口和团队安全边界。">
  <!-- 保留 ErrorState / loading / 现有两张 Card，先不要改成全宽网格 -->
</SettingsContent>
```

删掉眉题那块：

```html
<div class="space-y-1">
  <p class="text-sm font-medium text-primary">系统设置</p>
  <h1 ...>
```

`SettingsModulePage.vue`：外层改 `SettingsContent`，`:aria-label="moduleItem?.label ?? '系统设置'"`，`:description="moduleItem?.description ?? ''"`。删掉第 3–12 行那套标题 + 「进入配置」按钮（embedded 页本来就不显示它；非 embedded 的迁移卡也删，因为所有模块都有 `legacyComponentKey`）。保留权限 ErrorState 和 `<component :is="legacyComponent">`。

`ProcurementStagesSettings.vue`：同样包 `SettingsContent`，description 用现有那句阶段说明。删掉「系统设置 / 采购方式管理」眉题、页内 H1、页内「返回采购方式」和「新增阶段」按钮。改用：

```ts
import { ArrowLeft, Plus } from 'lucide-vue-next'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { useHeaderStore } from '@/stores/header'

const headerStore = useHeaderStore()
headerStore.setBack(true, '/settings/procurement-methods')
useTopBarRegistration({
  actionDeps: [hasAccess, canCreate, method],
  actions: () => [{
    id: 'create-stage',
    label: '新增阶段',
    type: 'primary',
    icon: Plus,
    visible: hasAccess.value && canCreate.value && method.value !== null,
    handler: showCreate,
  }],
})
```

`showCreate` 必须是已有函数。不要在 TopBar 再放返回按钮（`setBack` 已经提供）。

- [ ] **Step 4: Re-run chrome tests**

```bash
cd CRM-Client && npm run test:unit -- tests/views/AccountSettings.spec.ts src/views/__tests__/TeamSettings.chrome.test.ts src/views/__tests__/SettingsModulePage.chrome.test.ts
```

Expected: PASS。现有 AccountSettings 密码用例也必须过。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/AccountSettings.vue CRM-Client/src/views/TeamSettings.vue CRM-Client/src/views/SettingsModulePage.vue CRM-Client/src/views/ProcurementStagesSettings.vue CRM-Client/tests/views/AccountSettings.spec.ts CRM-Client/src/views/__tests__/TeamSettings.chrome.test.ts CRM-Client/src/views/__tests__/SettingsModulePage.chrome.test.ts
git commit -m "refactor(settings): drop duplicate page chrome"
```

---

### Task 3: Full-width account settings form

**Files:**
- Modify: `CRM-Client/src/views/AccountSettings.vue`
- Modify: `CRM-Client/tests/views/AccountSettings.spec.ts`

**Interfaces:**
- Consumes: `SettingsContent`、现有 `DataViewStatePanel`、密码 Dialog、飞书绑定 API。
- Produces: 两张全宽 Card：`个人信息`（头像 + `.settings-dl`）和 `安全与授权`（改密 + 飞书）。无页级保存。无「账户详情」第三张卡。

- [ ] **Step 1: Add layout assertions**

```ts
it('renders personal data in one full-width definition list and keeps security actions in a second card', () => {
  const { wrapper } = mountAccountPage({ userInfo: userFixture })
  expect(wrapper.findAll('.settings-dl').length).toBe(1)
  expect(wrapper.text()).toContain('安全与授权')
  expect(wrapper.text()).toContain('这是个人绑定，不是团队应用配置')
  expect(wrapper.find('[data-testid="change-password-trigger"]').exists()).toBe(true)
  expect(wrapper.findAll('h2').length).toBe(0)
})
```

Card 标题必须用 `CardTitle`（渲染 `h3`），不要 `h2`，以免和「无页内标题」冲突。

- [ ] **Step 2: Run the new test**

```bash
cd CRM-Client && npm run test:unit -- tests/views/AccountSettings.spec.ts
```

Expected: FAIL（还没有「安全与授权」/ `.settings-dl`）。

- [ ] **Step 3: Rebuild the ready-state markup**

保留 script 里的 load/password/oauth 逻辑。`description`：`个人资料和登录安全。飞书个人绑定与团队级飞书应用配置不是同一件事。`

Ready 槽只留两张 Card：

```vue
<Card>
  <CardHeader>
    <CardTitle>个人信息</CardTitle>
  </CardHeader>
  <CardContent>
    <div class="account-settings__profile">
      <Avatar class="h-16 w-16">...</Avatar>
      <div>
        <div class="font-medium">{{ displayValue(userInfo.name) }}</div>
        <p class="text-sm text-muted-foreground">{{ displayValue(userInfo.email) }}</p>
      </div>
    </div>
    <dl class="settings-dl">
      <dt>姓名</dt><dd>{{ displayValue(userInfo.name) }}</dd>
      <dt>邮箱</dt><dd>{{ displayValue(userInfo.email) }}</dd>
      <dt>手机号</dt><dd>{{ displayValue(userInfo.mobile) }}</dd>
      <dt>所属区域</dt><dd>{{ displayValue(userInfo.region) }}</dd>
      <dt>工号</dt><dd>{{ displayValue(userInfo.employee_no) }}</dd>
      <dt>账户状态</dt><dd><Badge>{{ displayValue(userInfo.status) }}</Badge></dd>
      <dt>用户 ID</dt>
      <dd class="flex items-center gap-2 tabular-nums">
        <span>{{ userInfo.id }}</span>
        <!-- 现有复制 Tooltip 按钮，aria-label="复制用户 ID" -->
      </dd>
      <dt>角色</dt>
      <dd class="flex flex-wrap gap-2">
        <Badge v-for="role in userRoles" :key="role.id" variant="secondary">{{ role.name }}</Badge>
        <span v-if="userRoles.length === 0">未设置</span>
      </dd>
      <dt>创建时间</dt><dd>{{ formatDateTime(userInfo.created_at) }}</dd>
      <dt>更新时间</dt><dd>{{ formatDateTime(userInfo.updated_at) }}</dd>
    </dl>
  </CardContent>
</Card>

<Card>
  <CardHeader>
    <CardTitle>安全与授权</CardTitle>
  </CardHeader>
  <CardContent>
    <div class="settings-setting-row">
      <div>
        <div class="font-medium">登录密码</div>
        <p class="text-sm text-muted-foreground">定期更新密码有助于保护账户安全。</p>
      </div>
      <Button data-testid="change-password-trigger" variant="outline" @click="passwordDialogOpen = true">修改密码</Button>
    </div>
    <div v-if="oauthLoading || feishuBinding?.enabled" class="settings-setting-row">
      <!-- 现有绑定文案；muted 追加：这是个人绑定，不是团队应用配置 -->
      <!-- 现有绑定/解绑按钮 -->
    </div>
  </CardContent>
</Card>
```

从 `@/components/ui/card` 增加 `CardTitle` / `CardDescription`（crmwolf 的 Card 再导出不含 Title）。删掉独立的「账户详情」「安全设置」「登录授权」三张卡。密码 Dialog 原样保留。

样式：删 `.account-settings` padding/background/font 复制；保留 `__profile`、`__password-input`。`__details` 可删。根 class 可留 `account-settings--system` 以免破坏现有 typography 测试，或把该测试改成断言 `settings-content`。优先改测试为：

```ts
expect(wrapper.find('.settings-content').exists()).toBe(true)
```

并删除对 `account-settings--system` 的断言。

- [ ] **Step 4: Re-run AccountSettings tests**

```bash
cd CRM-Client && npm run test:unit -- tests/views/AccountSettings.spec.ts
```

Expected: PASS，包括改密、头像 fallback、未设置、重试。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/AccountSettings.vue CRM-Client/tests/views/AccountSettings.spec.ts
git commit -m "feat(settings): restyle account page as full-width form"
```

---

### Task 4: Full-width team settings form

**Files:**
- Modify: `CRM-Client/src/views/TeamSettings.vue`
- Modify: `CRM-Client/src/views/__tests__/TeamSettings.chrome.test.ts`（扩成真正的页面测试，或另建 `TeamSettings.spec.ts`）

**Interfaces:**
- Consumes: `SettingsContent`、现有 `teamApi.getTeamDetail` / `updateTeam` / `regenerateInviteCode`、`confirmDialog`。
- Produces: 三张全宽 Card（团队信息 / 邀请 / 所有者）+ 底部 `.settings-form-actions` 保存团队名称。邀请码从成员页挪走的产品结果在本页已经具备；成员页 Task 6 再删重复入口。

- [ ] **Step 1: Write failing structure tests**

把 chrome 测试扩成：

```ts
it('keeps invite controls on the team page in a full-width stacked form', async () => {
  // mock getTeamDetail resolved team
  const wrapper = mount(TeamSettings, { /* stubs that pass through Card slots + Input + Button */ })
  await vi.waitFor(() => expect(wrapper.text()).toContain('邀请'))
  expect(wrapper.find('.settings-form-grid').exists()).toBe(true)
  expect(wrapper.find('.settings-form-actions').text()).toContain('保存团队信息')
  expect(wrapper.text()).toContain('复制邀请链接')
  expect(wrapper.text()).toContain('重置邀请码')
  expect(wrapper.find('.lg\\:grid-cols-2').exists()).toBe(false)
})
```

Input/Button 不要 stub 掉，否则保存按钮找不到。Card 系列用真实组件或透传 stub：`{ template: '<div><slot /></div>' }`。

- [ ] **Step 2: Run the test**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/TeamSettings.chrome.test.ts
```

Expected: FAIL（仍是 `lg:grid-cols-2`，保存按钮在第一张卡内）。

- [ ] **Step 3: Rebuild template**

```vue
<SettingsContent aria-label="团队信息与安全" description="维护当前团队资料和邀请入口。重置邀请码后，旧链接立即失效。">
  <!-- ErrorState 分支不变 -->
  <template v-else>
    <div v-if="loading" class="flex flex-col gap-4" aria-label="正在加载团队信息">
      <Card v-for="index in 3" :key="index">
        <CardHeader><Skeleton class="h-6 w-36" /></CardHeader>
        <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /></CardContent>
      </Card>
    </div>
    <ErrorState v-else-if="loadError" ... />
    <template v-else-if="team !== null">
      <Card>
        <CardHeader>
          <CardTitle>团队信息</CardTitle>
          <CardDescription>名称会显示在工作区和成员入口中。</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="settings-form-grid">
            <div class="space-y-2">
              <Label for="team-name">团队名称</Label>
              <Input id="team-name" v-model="teamName" :disabled="!canUpdateTeam || saving" maxlength="100" />
            </div>
            <div class="space-y-2">
              <Label for="team-created">创建时间</Label>
              <Input id="team-created" :model-value="team.created_at" disabled />
            </div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>邀请</CardTitle>
          <CardDescription>把链接发给同事即可加入当前团队。成员页不再重复放邀请码。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="settings-form-grid">
            <div class="space-y-2">
              <Label for="team-code">当前邀请码</Label>
              <Input id="team-code" :model-value="team.code" readonly />
            </div>
            <div class="space-y-2">
              <Label for="team-invite-link">邀请链接</Label>
              <Input id="team-invite-link" :model-value="inviteLink" readonly />
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" :disabled="inviteLink.length === 0" @click="copyInviteLink">复制邀请链接</Button>
            <Button variant="outline" :disabled="!canManageInvite || regenerating" @click="regenerateInviteCode">重置邀请码</Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>所有者</CardTitle>
          <CardDescription>所有权转移需要二次确认，本期只读展示。</CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-sm">{{ isOwner ? '当前用户（团队所有者）' : team.owner_id }}</p>
        </CardContent>
      </Card>
      <div class="settings-form-actions">
        <Button :disabled="!canUpdateTeam || saving || teamName.trim().length === 0" @click="saveTeamName">
          保存团队信息
        </Button>
      </div>
    </template>
  </template>
</SettingsContent>
```

`regenerateInviteCode` 继续先 `confirmDialog('确定要重置邀请码吗？重置后旧邀请码将失效。', '重置邀请码')`。若当前实现没有确认，补上。

创建时间若 `TeamResponse` 没有 `created_at`，就不要捏造字段，改成只读展示 `team.id` 不存在的话只保留团队名称一列（`settings-form-grid-full`）。以 `TeamResponse` 实际字段为准，禁止编造 API。

- [ ] **Step 4: Re-run team tests**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/TeamSettings.chrome.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/TeamSettings.vue CRM-Client/src/views/__tests__/TeamSettings.chrome.test.ts
git commit -m "feat(settings): restyle team page as full-width form"
```

---

### Task 5: Settings list catalog helper

**Files:**
- Create: `CRM-Client/src/views/settings/settingsListCatalog.ts`
- Create: `CRM-Client/src/views/settings/__tests__/settingsListCatalog.test.ts`

**Interfaces:**
- Consumes: `defineListFields` / `ListFieldDefinition` from `@/components/crmwolf/listFieldCatalog`。
- Produces:

```ts
export const SETTINGS_LIST_QUERY_DISABLED_REASON = '本期仍全量读取当前团队数据，未接入服务端 list-query'

export function settingsListColumn(
  field: Omit<ListFieldDefinition, 'filter' | 'sort' | 'filterDisabledReason' | 'sortDisabledReason'>,
): ListFieldDefinition
```

`settingsListColumn` 返回 `{ ...field, filter: false, sort: false, filterDisabledReason: SETTINGS_LIST_QUERY_DISABLED_REASON, sortDisabledReason: SETTINGS_LIST_QUERY_DISABLED_REASON }`。

- [ ] **Step 1: Write failing tests**

```ts
import { describe, expect, it } from 'vitest'
import { defineListFields, projectListFieldCatalog } from '@/components/crmwolf/listFieldCatalog'
import { SETTINGS_LIST_QUERY_DISABLED_REASON, settingsListColumn } from '../settingsListCatalog'

describe('settingsListColumn', () => {
  it('defines a business column that DataTable will not treat as filterable or sortable', () => {
    const fields = defineListFields([
      settingsListColumn({ key: 'name', label: '名称', column: true }),
    ])
    const projected = projectListFieldCatalog(fields)
    expect(projected.columns.map((column) => column.key)).toEqual(['name'])
    expect(projected.filterFields).toEqual([])
    expect(projected.sortFields).toEqual([])
    expect(fields[0]?.filterDisabledReason).toBe(SETTINGS_LIST_QUERY_DISABLED_REASON)
    expect(fields[0]?.sortDisabledReason).toBe(SETTINGS_LIST_QUERY_DISABLED_REASON)
  })
})
```

- [ ] **Step 2: Run the test**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/settingsListCatalog.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement the helper**

```ts
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'

export const SETTINGS_LIST_QUERY_DISABLED_REASON = '本期仍全量读取当前团队数据，未接入服务端 list-query'

export function settingsListColumn(
  field: Omit<ListFieldDefinition, 'filter' | 'sort' | 'filterDisabledReason' | 'sortDisabledReason'>,
): ListFieldDefinition {
  return {
    ...field,
    filter: false,
    sort: false,
    filterDisabledReason: SETTINGS_LIST_QUERY_DISABLED_REASON,
    sortDisabledReason: SETTINGS_LIST_QUERY_DISABLED_REASON,
  }
}
```

- [ ] **Step 4: Re-run**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/settingsListCatalog.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/settingsListCatalog.ts CRM-Client/src/views/settings/__tests__/settingsListCatalog.test.ts
git commit -m "feat(settings): add list catalog helper with query disabled"
```

---

### Task 6: Members list page

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsMembersPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsMembersPage.test.ts`
- Modify: `CRM-Client/src/router/index.ts`（`settings/members` 指向新页）
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts` 消费者名单加入 `views/settings/SettingsMembersPage.vue`
- Modify: `CRM-Client/src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts`：删除 members 用例（改由新测试覆盖）

**Interfaces:**
- Consumes: `teamApi.getTeamMembers`、邀请/改名/重置密码/分配角色/移除 Dialog 逻辑从 `TeamMemberSheet.vue` 原样搬迁（不要复制邀请码工具栏）。`settingsListColumn`。`useTopBarRegistration`。`DataTable` + `TableRowActions`。
- Produces: `/settings/members` 渲染 DataTable；TopBar「邀请成员」；行主操作「分配角色」；更多：修改用户名、重置密码、移除；无邀请码。

搬迁时把 `TeamMemberSheet.vue` 里除 Sheet/ListCard/搜索栏/团队信息条之外的 script 搬过来。Dialog 模板一起搬。不要再接受 `embedded`/`open`。

- [ ] **Step 1: Write failing page tests**

```ts
it('loads members into a DataTable and keeps invite code off this page', async () => {
  // pinia + team + owner + getTeamMembers mock 同 SettingsEmbeddedPanels
  const wrapper = mount(SettingsMembersPage, {
    global: {
      stubs: {
        DataTable: {
          props: ['data', 'fields'],
          template: '<div data-testid="members-table"><slot name="cell-member" v-for="row in data" :row="row" :index="0" /></div>',
        },
        TableRowActions: true,
        Dialog: { template: '<div><slot /></div>' },
        DialogContent: { template: '<div><slot /></div>' },
        DialogHeader: true, DialogTitle: true, DialogDescription: true, DialogFooter: true,
        FormField: { template: '<div><slot :componentField="{}" /></div>' },
        SettingsContent: { template: '<main><slot /></main>' },
      },
    },
  })
  await vi.waitFor(() => expect(getTeamMembers).toHaveBeenCalledWith(7))
  expect(wrapper.text()).toContain('成员一')
  expect(wrapper.text()).not.toContain('邀请码')
  expect(wrapper.text()).not.toContain('重置邀请码')
  expect(wrapper.html()).toContain('data-testid="members-table"')
})
```

同时改 `listFieldCatalog.test.ts` 的消费者数组，按字母序插入 `'views/settings/SettingsMembersPage.vue'`。这一步测试会失败，因为文件还不存在——先只写页面测试，catalog 名单放到 Step 3 一起改，避免 Step 2 被无关失败打断。

- [ ] **Step 2: Run members test**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsMembersPage.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement the page**

关键片段（完整页面必须能运行，Dialog 从 `TeamMemberSheet.vue` 拷）：

```ts
import { defineListFields } from '@/components/crmwolf/listFieldCatalog'
import { settingsListColumn } from '@/views/settings/settingsListCatalog'
import { DataTable, TableRowActions, type TableRowActionSet } from '@/components/crmwolf'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { Plus } from 'lucide-vue-next'
import { toFeedbackError, type FeedbackError } from '@/types/feedback'



const submittedSearch = ref('')
const members = ref<TeamMemberResponse[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)

const displayedMembers = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  if (query.length === 0) return members.value
  return members.value.filter((member) => {
    const name = member.name.toLowerCase()
    const email = member.email.toLowerCase()
    return name.includes(query) || email.includes(query)
  })
})

const fields = defineListFields([
  settingsListColumn({ key: 'member', label: '成员', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'roles', label: '角色', column: true }),
  settingsListColumn({ key: 'joined_at', label: '加入时间', column: true }),
])

const getRowActions = (row: TeamMemberResponse): TableRowActionSet => {
  const isSelf = row.id === currentUserId.value
  return {
    primaryActions: [{
      id: 'assign',
      label: '分配角色',
      desktopPrimary: true,
      visible: !isSelf && canManageMembers.value,
      handler: (raw) => { showAssignRoles(raw as TeamMemberResponse) },
    }],
    secondaryActions: [
      { label: '修改用户名', visible: !isSelf && canUpdateMembers.value, handler: (raw) => { showUpdateNameDialog(raw as TeamMemberResponse) } },
      { label: '重置密码', visible: !isSelf && canResetMemberPasswords.value, handler: (raw) => { showResetPasswordDialog(raw as TeamMemberResponse) } },
      { id: 'delete', label: '移除', destructive: true, risk: 'destructive', visible: !isSelf && canRemoveMembers.value, handler: (raw) => { void handleRemoveMember(raw as TeamMemberResponse) } },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canInviteMembers],
  actions: () => [{
    id: 'invite-member',
    label: '邀请成员',
    type: 'primary',
    icon: Plus,
    visible: canInviteMembers.value,
    handler: showInviteDialog,
  }],
})
```

`showAssignRoles` 等函数名跟 Sheet 里保持一致，避免漏改 Dialog。禁止 `as any`；若 handler 签名是 `Record<string, unknown>`，用局部函数：

```ts
const asMemberHandler = (handler: (row: TeamMemberResponse) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as TeamMemberResponse) }
}
```

模板：

```vue
<SettingsContent aria-label="团队成员" description="管理当前团队成员、邀请和角色。邀请、改名、重置密码等短任务继续用对话框。">
  <DataTable
    :fields="fields"
    :data="displayedMembers"
    :loading="loading"
    :load-error="loadError"
    :page="1"
    :page-size="Math.max(displayedMembers.length, 1)"
    :total="displayedMembers.length"
    height-strategy="page"
    scroll-mode="page"
    compact-pagination
    empty-title="暂无团队成员"
    :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
    :get-row-actions="getRowActions"
    mobile-title-key="name"
    :mobile-meta-keys="['email']"
    search-enabled
    :search="submittedSearch"
    search-placeholder="搜索姓名、邮箱"
    :search-loading="loading"
    @search-apply="handleSearchApply"
    @search-clear="handleSearchClear"
    @retry="loadMembers"
  >
    <template #cell-member="{ row }">
      <!-- 头像 + 姓名 + 邮箱，来自原 ListCard itemMain -->
    </template>
    <template #cell-roles="{ row }">
      <Badge v-for="role in row.roles" :key="role.id" variant="outline">{{ role.name }}</Badge>
      <Badge v-if="row.roles.length === 0" variant="secondary">暂无角色</Badge>
    </template>
    <template #mobile-actions="{ row }">
      <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
    </template>
  </DataTable>
</SettingsContent>
<!-- Dialogs: 邀请 / 分配角色 / 改名 / 重置密码 -->
```

```ts
const handleSearchApply = (value: string): void => {
  submittedSearch.value = value.trim()
}
const handleSearchClear = (): void => {
  submittedSearch.value = ''
}
```

`loadMembers` 用 `listRequestId` 取消过期响应，失败走 `toFeedbackError(error, '团队成员')`。不要传 skip/limit 去假装分页。不要请求团队详情，不要渲染邀请码。

Router：在 `settings/team` 之后加：

```ts
{
  path: 'settings/members',
  name: 'SettingsMembers',
  component: () => import('@/views/settings/SettingsMembersPage.vue'),
  meta: { requiresAuth: true, title: '团队成员', settingsKey: 'members' },
},
```

`settings/:module` 仍在，members 会被更具体的 path 抢先匹配（Vue Router 按注册顺序；**必须把 `settings/members` 写在 `settings/:module` 之前**）。

更新 `listFieldCatalog.test.ts` 消费者列表，按现有字母序插入新路径。

从 `SettingsEmbeddedPanels.test.ts` 删除 members 那个 it。

- [ ] **Step 4: Run tests**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsMembersPage.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts src/settingsNavigation.test.ts
```

Expected: PASS。`listFieldCatalog` 会扫到新页并要求 `ListFieldDefinition` / `#mobile-actions`。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsMembersPage.vue CRM-Client/src/views/settings/__tests__/SettingsMembersPage.test.ts CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts CRM-Client/src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts
git commit -m "feat(settings): move members to a DataTable page"
```

---

### Task 7: Roles list page

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsRolesPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsRolesPage.test.ts`
- Modify: `CRM-Client/src/router/index.ts`（`settings/roles` 写在 `settings/:module` 之前）
- Modify: `CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts` 消费者名单按字母序插入 `'views/settings/SettingsRolesPage.vue'`
- Modify: `CRM-Client/src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts` 删除 roles 用例

**Interfaces:**
- Consumes: `roleApi.getRoles` 以及 `RoleSheet.vue` 的创建/编辑/权限/删除 Dialog。
- Produces: DataTable；TopBar「新建角色」`type: 'primary'`；行主操作「配置权限」；更多：编辑、删除。`getRoles()` 不传 skip/limit。

- [ ] **Step 1: Write failing test**

```ts
it('loads roles into a DataTable without a sheet title', async () => {
  // pinia + getRoles mock 同 SettingsEmbeddedPanels roles 用例
  const wrapper = mount(SettingsRolesPage, {
    global: {
      stubs: {
        DataTable: {
          props: ['data'],
          template: '<div data-testid="roles-table"><div v-for="row in data" :key="row.id">{{ row.name }}</div></div>',
        },
        TableRowActions: true,
        SettingsContent: { template: '<main><slot /></main>' },
        Dialog: { template: '<div><slot /></div>' },
        DialogContent: { template: '<div><slot /></div>' },
      },
    },
  })
  await vi.waitFor(() => expect(getRoles).toHaveBeenCalled())
  expect(getRoles.mock.calls[0]?.[0]).toBeUndefined()
  expect(wrapper.text()).toContain('管理员')
  expect(wrapper.find('[data-testid="roles-table"]').exists()).toBe(true)
})
```

- [ ] **Step 2: Run it**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsRolesPage.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement the page**

从 `RoleSheet.vue` 拷 script 里的 fetch/Dialog/权限，丢掉 Sheet/ListCard/搜索栏。

```ts
const fields = defineListFields([
  settingsListColumn({ key: 'name', label: '角色', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'code', label: '代码', column: true }),
  settingsListColumn({ key: 'updated_at', label: '更新时间', column: true }),
])
```

`#cell-name` 显示 `item.name` + 描述。submittedSearch 过滤 `name`/`code`（trim + toLowerCase）。行操作：`desktopPrimary`「配置权限」；更多「编辑」「删除」（`id: 'delete'`）。内置角色删除沿用 Sheet 现有 visible/disabled。TopBar「新建角色」`visible: canManageRoles`。

```ts
watch(() => route.query['action'], (action) => {
  if (action === 'create' && canManageRoles.value) showCreateDialog()
}, { immediate: true })
```

Router：

```ts
{
  path: 'settings/roles',
  name: 'SettingsRoles',
  component: () => import('@/views/settings/SettingsRolesPage.vue'),
  meta: { requiresAuth: true, title: '角色管理', settingsKey: 'roles' },
},
```

DataTable 绑定：`:fields="fields"` `:data="displayedRoles"` `:loading` `:load-error` `:page="1"` `:page-size="Math.max(displayedRoles.length, 1)"` `:total="displayedRoles.length"` `height-strategy="page"` `scroll-mode="page"` `search-enabled` `:search="submittedSearch"` `@search-apply` `@search-clear` `#mobile-actions`。

- [ ] **Step 4: Run catalog + roles tests**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsRolesPage.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsRolesPage.vue CRM-Client/src/views/settings/__tests__/SettingsRolesPage.test.ts CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts CRM-Client/src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts
git commit -m "feat(settings): move roles to a DataTable page"
```

---

### Task 8: Approval flows list page

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsApprovalFlowsPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsApprovalFlowsPage.test.ts`
- Modify: `CRM-Client/src/router/index.ts`（`settings/approval-flows` 在 `:module` 前）
- Modify: catalog 消费者名单 `'views/settings/SettingsApprovalFlowsPage.vue'`
- Modify: `SettingsEmbeddedPanels.test.ts` 删除 approval SheetTitle 用例

**Interfaces:**
- Consumes: `approvalFlowApi.getApprovalFlows`、`ApprovalFlowFormDialog`、`ApprovalFlowAIDialog`。
- Produces: DataTable；TopBar「手动创建」`type: 'primary'`；AI 创建若保留则第二个 action `type: 'default'`。行主操作「编辑」；更多：查看、启用/停用。

- [ ] **Step 1: Write failing test**

```ts
it('loads approval flows into a DataTable without a sheet title', async () => {
  getApprovalFlows.mockResolvedValue([{ id: 1, flow_name: '合同审批', flow_code: 'CONTRACT_FLOW', business_type: 'CONTRACT', is_active: true, nodes: [] }])
  const wrapper = mount(SettingsApprovalFlowsPage, {
    global: { stubs: { DataTable: { props: ['data'], template: '<div data-testid="flows-table">{{ data[0]?.flow_name }}</div>' }, TableRowActions: true, SettingsContent: { template: '<main><slot /></main>' }, ApprovalFlowFormDialog: true, ApprovalFlowAIDialog: true } },
  })
  await vi.waitFor(() => expect(getApprovalFlows).toHaveBeenCalled())
  expect(wrapper.text()).toContain('合同审批')
  expect(wrapper.text()).not.toContain('审批流程管理')
})
```

- [ ] **Step 2: Run it**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsApprovalFlowsPage.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement**

从 `ApprovalFlowSheet.vue` 拷列表/Dialog/启停，丢掉 Sheet 头和即时搜索。

```ts
const fields = defineListFields([
  settingsListColumn({ key: 'flow_name', label: '流程', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'business_type', label: '单据', column: true }),
  settingsListColumn({ key: 'amount_range', label: '金额范围', column: true }),
  settingsListColumn({ key: 'node_count', label: '节点', column: true }),
  settingsListColumn({ key: 'is_active', label: '状态', column: true }),
])
```

`getApprovalFlows()` 不传 skip/limit。submittedSearch 过滤 `flow_name`/`flow_code`。不要 `row-interactive`。

```ts
useTopBarRegistration({
  actionDeps: [canCreate],
  actions: () => [
    { id: 'create-flow', label: '手动创建', type: 'primary', icon: Plus, visible: canCreate.value, handler: handleManualCreate },
    { id: 'ai-create-flow', label: 'AI 创建', type: 'default', visible: canCreate.value, handler: handleAICreate },
  ],
})
```

`watch` `route.query.action` + `route.query.id`：`create` 打开 FormDialog create；`edit` 且有 id 打开 edit。

Router meta `title: '审批流程管理', settingsKey: 'approval-flows'`。

- [ ] **Step 4:**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsApprovalFlowsPage.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsApprovalFlowsPage.vue CRM-Client/src/views/settings/__tests__/SettingsApprovalFlowsPage.test.ts CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts CRM-Client/src/components/system-config/__tests__/SettingsEmbeddedPanels.test.ts
git commit -m "feat(settings): move approval flows to a DataTable page"
```

---

### Task 9: Acquisition sources list page

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsAcquisitionSourcesPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsAcquisitionSourcesPage.test.ts`
- Modify: router `settings/acquisition-sources`（`:module` 前）
- Modify: catalog 消费者名单

**Interfaces:**
- Consumes: `AcquisitionSourcePanel.vue` 的 list/Dialog/启停/引用保护。
- Produces: DataTable；TopBar「新建来源」；行主操作按状态切换「停用」/「启用」；更多：编辑。

- [ ] **Step 1: Write failing test**

```ts
it('loads acquisition sources into a DataTable', async () => {
  listSources.mockResolvedValue([{ public_id: 'src_1', name: '官网咨询', is_active: true, reference_count: 24, sort_order: 1 }])
  const wrapper = mount(SettingsAcquisitionSourcesPage, {
    global: { stubs: { DataTable: { props: ['data'], template: '<div>{{ data[0]?.name }}</div>' }, TableRowActions: true, SettingsContent: { template: '<main><slot /></main>' }, Dialog: true } },
  })
  await vi.waitFor(() => expect(listSources).toHaveBeenCalled())
  expect(wrapper.text()).toContain('官网咨询')
})
```

API 函数名以 `AcquisitionSourcePanel.vue` 实际 import 为准（`acquisitionSourceApi.list` 或同等）。

- [ ] **Step 2: Run it — expect FAIL**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsAcquisitionSourcesPage.test.ts
```

- [ ] **Step 3: Implement**

```ts
const fields = defineListFields([
  settingsListColumn({ key: 'name', label: '来源', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'reference_count', label: '引用', column: true }),
  settingsListColumn({ key: 'is_active', label: '状态', column: true }),
  settingsListColumn({ key: 'sort_order', label: '排序', column: true }),
])
```

submittedSearch 过滤 `name`。被引用时删除按 Panel 现有规则禁用。`?action=create` 打开新建 Dialog。

DataTable 绑定：`:fields="fields"` `:data="displayedSources"` `:page="1"` `:page-size="Math.max(displayedSources.length, 1)"` `:total="displayedSources.length"` `height-strategy="page"` `scroll-mode="page"` `search-enabled` `:search="submittedSearch"` `#mobile-actions`。

- [ ] **Step 4:**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsAcquisitionSourcesPage.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsAcquisitionSourcesPage.vue CRM-Client/src/views/settings/__tests__/SettingsAcquisitionSourcesPage.test.ts CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts
git commit -m "feat(settings): move acquisition sources to a DataTable page"
```

---

### Task 10: Procurement methods list page

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsProcurementMethodsPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsProcurementMethodsPage.test.ts`
- Modify: `CRM-Client/src/router/index.ts` 把现有 `settings/procurement-methods` 从 `SettingsModulePage` 改到新页
- Modify: catalog 消费者名单

**Interfaces:**
- Consumes: `ProcurementMethodsPanel.vue` 的 CRUD Dialog。
- Produces: DataTable；TopBar「新建采购方式」；行主操作「阶段模板」`router.push('/settings/procurement-methods/' + methodId + '/stages')`；更多：编辑、删除/停用。

- [ ] **Step 1: Write failing test**

```ts
it('loads procurement methods into a DataTable', async () => {
  listMethods.mockResolvedValue([{ id: 'pm_1', name: '公开招标', code: 'OPEN_TENDER', is_active: true, stage_templates: [{}, {}] }])
  const wrapper = mount(SettingsProcurementMethodsPage, {
    global: { stubs: { DataTable: { props: ['data'], template: '<div>{{ data[0]?.name }}</div>' }, TableRowActions: true, SettingsContent: { template: '<main><slot /></main>' }, Dialog: true } },
  })
  await vi.waitFor(() => expect(listMethods).toHaveBeenCalled())
  expect(wrapper.text()).toContain('公开招标')
})
```

id 字段名以 Panel 的类型为准（`id` 或 `public_id`）。

- [ ] **Step 2: Run — expect FAIL**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsProcurementMethodsPage.test.ts
```

- [ ] **Step 3: Implement**

```ts
const fields = defineListFields([
  settingsListColumn({ key: 'name', label: '采购方式', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'stage_count', label: '阶段', column: true }),
  settingsListColumn({ key: 'is_active', label: '状态', column: true }),
])
```

`#cell-name` 显示名称 + 编码。阶段数列用 `stage_templates.length`（只读投影，不必进 API）。`?action=create|edit` 打开 Panel 现有 Dialog。

改 router 现有 `SettingsProcurementMethods` 的 `component` import，不要另留一条 `SettingsModulePage` 路由。

- [ ] **Step 4:**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsProcurementMethodsPage.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsProcurementMethodsPage.vue CRM-Client/src/views/settings/__tests__/SettingsProcurementMethodsPage.test.ts CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts
git commit -m "feat(settings): move procurement methods to a DataTable page"
```

---

### Task 11: Products list page

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsProductsPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsProductsPage.test.ts`
- Delete: `CRM-Client/src/components/system-config/__tests__/ProductPanel.test.ts`（用例迁到新文件后）
- Modify: router `settings/products`
- Modify: catalog 消费者名单

**Interfaces:**
- Consumes: `ProductPanel.vue` 的 list/模块 Dialog/权限。
- Produces: DataTable；TopBar「新建产品」`visible: canCreate`；行主操作「编辑」；更多：新增模块、删除模块、启停。只读用户没有维护按钮。

- [ ] **Step 1: Port failing tests**

把 `ProductPanel.test.ts` 里这些行为迁到 `SettingsProductsPage.test.ts`，mount 新页：

1. `product:view` 能看到产品名，看不到「新建产品」「编辑」「删除」
2. `product:edit` 能「删除模块」，不能删产品
3. 全权限能「新建产品」和「新增模块」
4. 只读 `action=edit` 不打开编辑 Dialog
5. `action=create` 在 create 权限就绪后打开「新建产品」Dialog
6. 空列表 + 无创建权限：文案含「你没有创建产品的权限」
7. list 失败显示「产品加载失败」且可 retry
8. 创建表单提交 `productApi.create`，不提交 `createModule`

DataTable stub 要透出 `empty-title` / `empty-description` 或把空态文案放在页面上，以便第 6 条仍能断言。

- [ ] **Step 2: Run — expect FAIL**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsProductsPage.test.ts
```

- [ ] **Step 3: Implement**

```ts
const fields = defineListFields([
  settingsListColumn({ key: 'name', label: '产品', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'status', label: '状态', column: true }),
  settingsListColumn({ key: 'modules', label: '模块', column: true }),
])
```

submittedSearch 过滤名称。`watch` query/`props` 不要再收 `action` prop；用 `route.query.action`。空列表权限说明用 DataTable `empty-description`。

实现后删除 `ProductPanel.test.ts`。

- [ ] **Step 4:**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsProductsPage.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

Expected: PASS，且不再收集 `ProductPanel.test.ts`。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/settings/SettingsProductsPage.vue CRM-Client/src/views/settings/__tests__/SettingsProductsPage.test.ts CRM-Client/src/router/index.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts
git add -u CRM-Client/src/components/system-config/__tests__/ProductPanel.test.ts
git commit -m "feat(settings): move products to a DataTable page"
```

---

### Task 12: Procurement stages as DataTable subpage

**Files:**
- Modify: `CRM-Client/src/views/ProcurementStagesSettings.vue`
- Create: `CRM-Client/src/views/__tests__/ProcurementStagesSettings.test.ts`
- Modify: catalog 消费者名单 `'views/ProcurementStagesSettings.vue'`

**Interfaces:**
- Consumes: Task 2 已接的 TopBar 返回 +「新增阶段」。
- Produces: ListCard 换成 DataTable；行主操作「编辑」；更多「删除」。

- [ ] **Step 1: Write failing test**

```ts
it('renders stages in a DataTable instead of ListCard', () => {
  const source = readFileSync(resolve(process.cwd(), 'src/views/ProcurementStagesSettings.vue'), 'utf8')
  expect(source).toContain('<DataTable')
  expect(source).toContain(':get-row-actions="getRowActions"')
  expect(source).toContain('#mobile-actions')
  expect(source).not.toContain('ListCard')
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/ProcurementStagesSettings.test.ts
```

- [ ] **Step 3: Replace ListCard**

```ts
const fields = defineListFields([
  settingsListColumn({ key: 'stage_name', label: '阶段', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'template_code', label: '编码', column: true }),
  settingsListColumn({ key: 'win_probability', label: '赢率', column: true }),
  settingsListColumn({ key: 'sort_order', label: '排序', column: true }),
  settingsListColumn({ key: 'is_default_start', label: '默认起点', column: true }),
  settingsListColumn({ key: 'can_skip', label: '可跳过', column: true }),
])
```

数据仍是 `method.stage_templates` 排序后的数组。`total` = 数组长度。Dialog 新增/编辑保持不变。

- [ ] **Step 4:**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/ProcurementStagesSettings.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/ProcurementStagesSettings.vue CRM-Client/src/views/__tests__/ProcurementStagesSettings.test.ts CRM-Client/src/components/crmwolf/__tests__/listFieldCatalog.test.ts
git commit -m "feat(settings): show procurement stages in a DataTable"
```

---

### Task 13: AI / notifications / integrations full-width form pages

**Files:**
- Create: `CRM-Client/src/views/settings/SettingsAIPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsNotificationsPage.vue`
- Create: `CRM-Client/src/views/settings/SettingsIntegrationsPage.vue`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsAIPage.test.ts`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsNotificationsPage.test.ts`
- Create: `CRM-Client/src/views/settings/__tests__/SettingsIntegrationsPage.test.ts`
- Modify: `CRM-Client/src/router/index.ts`（三条路由都写在 `settings/:module` 之前）

**Interfaces:**
- Consumes: `AIConfigSheet.vue` / `NotificationSheet.vue` / `LoginIntegrationSheet.vue` 的 load/save/test，不含 Sheet chrome。
- Produces: 全宽 Card + `.settings-form-grid` + 底部 `.settings-form-actions`「保存配置」。TopBar 不注册保存。密钥不明文。

- [ ] **Step 1: Write failing tests**

`SettingsAIPage.test.ts`：mount 后出现「服务配置」「连接测试」「保存配置」；没有「配置说明」；API Key input `type="password"`；保存按钮的父节点 class 含 `settings-form-actions`。

`SettingsNotificationsPage.test.ts`：有「飞书群通知」或「群名称」；有「发送测试」；「保存配置」在 `.settings-form-actions`；没有「配置说明」。

`SettingsIntegrationsPage.test.ts`：有「飞书应用」和「AI Agent 机器人」；有底部「保存配置」；文本不含「绑定飞书」。

- [ ] **Step 2: Run them**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsAIPage.test.ts src/views/settings/__tests__/SettingsNotificationsPage.test.ts src/views/settings/__tests__/SettingsIntegrationsPage.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: Implement three pages**

从对应 Sheet 拷 form/submit/test。包 `SettingsContent`。AI description：`配置当前团队使用的大模型接口。密钥不明文回显，空值保存表示保持原密钥。` 通知：`审批相关的团队通知通道。这里改的是怎么通知，不是审批流程本身。` 集成：`当前团队的飞书应用配置。和个人账户里的飞书绑定分开。`

AI 卡 1：`settings-form-grid` 里供应商、模型；接口地址和 API Key 加 `settings-form-grid-full`。卡 2：测试消息 + outline「测试连接」+ 结果 Alert。底部保存。

通知：一卡两列群名称 / Webhook；组内「发送测试」；底部保存。

集成：卡 1 启用开关 + App ID/Secret 两列 + 重定向 URL 整行；卡 2 机器人开关、只读回调、Token / Open ID；底部保存。

删掉 Sheet 的「配置说明」Card，改成 `FormDescription`。空密钥保存语义原样。

Router：

```ts
{ path: 'settings/ai', name: 'SettingsAI', component: () => import('@/views/settings/SettingsAIPage.vue'), meta: { requiresAuth: true, title: 'AI 配置', settingsKey: 'ai' } },
{ path: 'settings/notifications', name: 'SettingsNotifications', component: () => import('@/views/settings/SettingsNotificationsPage.vue'), meta: { requiresAuth: true, title: '通知配置', settingsKey: 'notifications' } },
{ path: 'settings/integrations', name: 'SettingsIntegrations', component: () => import('@/views/settings/SettingsIntegrationsPage.vue'), meta: { requiresAuth: true, title: '第三方集成', settingsKey: 'integrations' } },
```

- [ ] **Step 4: Re-run the three tests**

```bash
cd CRM-Client && npm run test:unit -- src/views/settings/__tests__/SettingsAIPage.test.ts src/views/settings/__tests__/SettingsNotificationsPage.test.ts src/views/settings/__tests__/SettingsIntegrationsPage.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit three times**

```bash
git add CRM-Client/src/views/settings/SettingsAIPage.vue CRM-Client/src/views/settings/__tests__/SettingsAIPage.test.ts CRM-Client/src/router/index.ts
git commit -m "feat(settings): restyle AI config as full-width form"
git add CRM-Client/src/views/settings/SettingsNotificationsPage.vue CRM-Client/src/views/settings/__tests__/SettingsNotificationsPage.test.ts CRM-Client/src/router/index.ts
git commit -m "feat(settings): restyle notification config as full-width form"
git add CRM-Client/src/views/settings/SettingsIntegrationsPage.vue CRM-Client/src/views/settings/__tests__/SettingsIntegrationsPage.test.ts CRM-Client/src/router/index.ts
git commit -m "feat(settings): restyle integrations as full-width form"
```

---

### Task 14: ApprovalFlowsNew chrome only

**Files:**
- Modify: `CRM-Client/src/views/ApprovalFlowsNew.vue`
- Modify: 现有 ApprovalFlowsNew 测试里对 `h1` / `data-testid="approval-flows-create"` 的选择器，如果测试是按页内按钮找的，改为断言 headerStore actions 或保留 `data-testid` 但按钮改挂 TopBar（TopBar 在 AppLayout，单测页面时 `useTopBarRegistration` 仍会 `setActions`，可 mock `useHeaderStore`）

**Interfaces:**
- Consumes: 现有 `canCreate` / `canCreateWorkflow` / `openCreate` / `openWorkflowEditor`。
- Produces: 无页内 `h1`、无页内主按钮；TopBar 注册创建动作。

- [ ] **Step 1: Write a source assertion test**

`CRM-Client/src/views/__tests__/ApprovalFlowsNew.chrome.test.ts`：

```ts
it('does not draw a second approval-flows heading', () => {
  const source = readFileSync(resolve(process.cwd(), 'src/views/ApprovalFlowsNew.vue'), 'utf8')
  expect(source).toContain('SettingsContent')
  expect(source).toContain('useTopBarRegistration')
  expect(source).not.toContain('text-2xl font-semibold tracking-tight')
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/ApprovalFlowsNew.chrome.test.ts
```

- [ ] **Step 3: Wrap chrome**

外层 `SettingsContent` `aria-label="审批流程管理"`。删掉第 168–177 行那套 h1 + 双按钮。

```ts
useTopBarRegistration({
  actionDeps: [canCreateWorkflow, canCreate, workflowEditorOpen],
  actions: () => workflowEditorOpen.value ? [] : [
    { id: 'create-workflow', label: '新建工作流', type: 'primary', visible: canCreateWorkflow.value, handler: () => { openWorkflowEditor(null) } },
    { id: 'create-approval-flow', label: '手动创建', type: 'default', visible: canCreate.value, handler: openCreate },
  ],
})
```

`data-testid` 若测试还要用，加在 HeaderAction 上做不到（TopBar 在 layout）。现有测试若 `get('[data-testid="approval-flows-create"]')`，改成 spy `useHeaderStore().setActions` 或继续在页面放 `display:none` 测试钩子——**禁止** hidden 按钮。改测试去读 headerStore mock。

画布打开时保持现有 `v-else` 编辑器全宽。

- [ ] **Step 4: Re-run chrome test + any existing ApprovalFlowsNew tests**

```bash
cd CRM-Client && npm run test:unit -- src/views/__tests__/ApprovalFlowsNew.chrome.test.ts
```

若有 `src/views/__tests__/ApprovalFlowsNew` 或类似文件，一并跑。

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/views/ApprovalFlowsNew.vue CRM-Client/src/views/__tests__/ApprovalFlowsNew.chrome.test.ts
git commit -m "refactor(settings): align new approval flows chrome"
```

---

### Task 15: Unsaved leave guard for settings forms

**Files:**
- Create: `CRM-Client/src/composables/useSettingsUnsavedLeave.ts`
- Create: `CRM-Client/src/composables/__tests__/useSettingsUnsavedLeave.test.ts`
- Modify: `CRM-Client/src/views/TeamSettings.vue`
- Modify: `CRM-Client/src/views/settings/SettingsAIPage.vue`
- Modify: `CRM-Client/src/views/settings/SettingsNotificationsPage.vue`
- Modify: `CRM-Client/src/views/settings/SettingsIntegrationsPage.vue`

**Interfaces:**

```ts
export function useSettingsUnsavedLeave(options: {
  isDirty: () => boolean
  isSubmitting: () => boolean
}): {
  showLeaveConfirm: Ref<boolean>
  pendingPath: Ref<string | null>
  confirmLeave: () => void
  cancelLeave: () => void
}
```

不要再提供返回 `void` 的重载。

- [ ] **Step 1: Write failing composable test**

用 `createMemoryHistory` + 一个 stub 页调用 composable。`isDirty` 返回 true 时 `router.push('/elsewhere')` 被拦住，`showLeaveConfirm` 为 true；`confirmLeave` 后到达目标路由。

- [ ] **Step 2: Run — expect FAIL**

```bash
cd CRM-Client && npm run test:unit -- src/composables/__tests__/useSettingsUnsavedLeave.test.ts
```

- [ ] **Step 3: Implement**

抄 `CustomerEdit.vue` 的 `onBeforeRouteLeave` + `beforeunload`。`isSubmitting()` 为 true 时不拦截。页面里渲染现有 `AlertDialog`：标题「放弃未保存的更改？」；确认走 `confirmLeave`。

接入：
- TeamSettings：`isDirty: () => teamName.value.trim() !== (team.value?.name ?? '')`
- AI/通知/集成：vee-validate `meta.dirty`（Sheet 迁过来时若没有，用一份 `initialSnapshot` JSON 对比当前表单值）

账户页不要调用。

- [ ] **Step 4: Re-run composable test + team chrome test**

```bash
cd CRM-Client && npm run test:unit -- src/composables/__tests__/useSettingsUnsavedLeave.test.ts src/views/__tests__/TeamSettings.chrome.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add CRM-Client/src/composables/useSettingsUnsavedLeave.ts CRM-Client/src/composables/__tests__/useSettingsUnsavedLeave.test.ts CRM-Client/src/views/TeamSettings.vue CRM-Client/src/views/settings/SettingsAIPage.vue CRM-Client/src/views/settings/SettingsNotificationsPage.vue CRM-Client/src/views/settings/SettingsIntegrationsPage.vue
git commit -m "feat(settings): guard unsaved settings forms"
```

---

### Task 16: Delete SettingsModulePage host

**Files:**
- Delete: `CRM-Client/src/views/SettingsModulePage.vue`
- Modify: `CRM-Client/src/router/index.ts` 删除 `settings/:module` catch-all，改为每个模块具名路由（若前序任务已加齐，这里只删 catch-all）
- Modify: `CRM-Client/src/settingsNavigation.test.ts`：删除「keeps separate AI and products legacy component mappings」；改成断言 router 源码含 `SettingsAIPage` 与 `SettingsProductsPage` 两个 import，或断言 `SETTINGS_NAVIGATION` 仍分开 `ai` / `products`
- Delete: `SettingsModulePage.chrome.test.ts`
- 可选：Sheet 文件若已无引用，不要在本任务删 SystemConfig 仍引用的 Sheet。`grep` 确认 `SettingsModulePage` 和 `legacyComponentKey` 无生产引用后再考虑删 `legacyComponentKey` 字段——**本任务不要删 `legacyComponentKey`**，以免导航类型大改；只删页面宿主。

- [ ] **Step 1: Write a failing grep test**

```ts
it('does not host settings modules through SettingsModulePage', () => {
  const routerSource = readFileSync(resolve(process.cwd(), 'src/router/index.ts'), 'utf8')
  expect(routerSource).not.toContain('SettingsModulePage')
  expect(routerSource).toContain('SettingsMembersPage')
  expect(routerSource).toContain('SettingsProductsPage')
  expect(routerSource).toContain('SettingsAIPage')
})
```

放进 `settingsNavigation.test.ts`。

- [ ] **Step 2: Run, expect FAIL if catch-all still exists**

- [ ] **Step 3: Remove the host and catch-all route.** 确认 `settings/procurement-methods` 已指向 Task 10 页面。未知模块 404 走现有 Router 行为即可，不要再渲染「设置模块不存在」卡。

- [ ] **Step 4:**

```bash
cd CRM-Client && npm run test:unit -- src/settingsNavigation.test.ts src/components/crmwolf/__tests__/listFieldCatalog.test.ts src/views/settings/__tests__/ src/views/__tests__/TeamSettings.chrome.test.ts tests/views/AccountSettings.spec.ts src/components/system-config/__tests__/ProductPanel.test.ts
```

Expected: PASS。`ProductPanel.test.ts` 若已迁移删除，从命令里拿掉。

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(settings): drop SettingsModulePage host"
```

---

## Self-Review Checklist

- [x] Spec §5 外壳 → Task 1–2
- [x] Spec §8 账户/团队全宽表单 → Task 3–4
- [x] Spec §7 DataTable 列表 + 显式关闭筛选排序 → Task 5–12
- [x] Spec 成员页去掉邀请码 → Task 4 保留、Task 6 删除
- [x] Spec 表单保存底部、TopBar 不挂保存 → Task 3/4/13
- [x] Spec 列表主操作 TopBar → Task 6–12
- [x] Spec AI/通知/集成全宽 + 说明改字段帮助 → Task 13
- [x] Spec ApprovalFlowsNew 只收口外壳 → Task 14
- [x] Spec dirty 离开保护 → Task 15
- [x] Spec 删除 SettingsModulePage 宿主 → Task 16
- [x] DataTable catalog 消费者名单随每个列表页更新
- [x] 不升级 list-query 后端
- [x] 不碰 SystemConfig.vue 删除
- [x] 无 TBD / “similar to Task N” 作为唯一说明（Task 7+ 仍写出本页字段和主操作）

## Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-17-settings-workspace-unification-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派一个新子代理，Task 之间做审查，迭代快。

**2. Inline Execution** — 本会话按 executing-plans 批量做，设检查点。

Which approach?
