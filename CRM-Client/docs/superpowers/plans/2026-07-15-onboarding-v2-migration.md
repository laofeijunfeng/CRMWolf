# Onboarding V2 设计迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Onboarding 流程的三个页面（Onboarding.vue、TeamCreate.vue、TeamJoin.vue）从 Element Plus 组件和 V1 设计变量迁移到 shadcn-vue 组件和 V2 设计系统。

**Architecture:** 采用分页面渐进式迁移策略，先迁移主入口 Onboarding.vue（无表单），再迁移两个表单页面 TeamCreate.vue 和 TeamJoin.vue。每个页面独立可测试，迁移后保持功能不变。

**Tech Stack:** Vue 3 + TypeScript + shadcn-vue + VeeValidate + Zod + vue-sonner + lucide-vue-next

## Global Constraints

- **设计令牌来源**：`CRM-Client/src/styles/variables-v2.scss`（必须使用 `-v2` 后缀变量）
- **组件导入**：从 `@/components/crmwolf` 统一导入（Button, Input, Card 等）
- **表单验证**：使用 VeeValidate + Zod（`@vee-validate/zod`, `vee-validate`）
- **消息提示**：使用 `toast` from `vue-sonner`（替代 ElMessage）
- **图标来源**：使用 `lucide-vue-next`（替代 @element-plus/icons-vue）
- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`
- **组件 Props/Emits**：必须类型化
- **保持路由不变**：`/onboarding`, `/onboarding/create-team`, `/onboarding/join-team`

### UI/UX Pro Max 规范（CRITICAL）

- **Accessibility**：表单错误使用 `aria-live` 或 `role="alert"` 通知屏幕阅读器
- **Accessibility**：表单验证失败后自动聚焦第一个无效字段
- **Accessibility**：Logo 图片使用描述性 alt 文本
- **Layout**：移动端使用 `min(100vh, 100dvh)` 替代 `100vh`（避免 iOS Safari 地址栏问题）
- **Layout**：使用 safe-area insets 避开 notch/Dynamic Island
- **Forms**：使用 `FormDescription` 提供字段帮助文本
- **Forms**：使用 `ErrorMessage` 组件显示验证错误
- **Navigation**：退出登录为危险操作，需确认对话框

---

## 文件结构

```
CRM-Client/src/
├── views/
│   ├── Onboarding.vue          # 修改：迁移到 V2
│   ├── TeamCreate.vue          # 修改：迁移到 V2 + VeeValidate
│   └── TeamJoin.vue            # 修改：迁移到 V2 + VeeValidate
├── schemas/
│   ├── team-create.schema.ts   # 创建：团队创建表单 Zod schema
│   └── team-join.schema.ts     # 创建：团队加入表单 Zod schema
├── components/
│   └── ui/form/                # 已存在：FormField, FormItem, FormLabel, FormDescription, ErrorMessage
└── styles/
    └── variables-v2.scss       # 已存在：V2 设计令牌
```

---

### Task 1: 创建团队创建表单 Schema

**Files:**
- Create: `CRM-Client/src/schemas/team-create.schema.ts`

**Interfaces:**
- Produces: `teamCreateSchema` (Zod schema), `TeamCreateFormValues` (TypeScript 类型)

- [ ] **Step 1: 创建 Zod schema 文件**

```typescript
// CRM-Client/src/schemas/team-create.schema.ts
import { z } from 'zod'

export const teamCreateSchema = z.object({
  name: z
    .string()
    .min(2, { message: '团队名称长度为2-50个字符' })
    .max(50, { message: '团队名称长度为2-50个字符' }),
})

export type TeamCreateFormValues = z.infer<typeof teamCreateSchema>
```

- [ ] **Step 2: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS（无新增错误）

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/schemas/team-create.schema.ts
git commit -m "feat(schemas): add team create form schema"
```

---

### Task 2: 创建团队加入表单 Schema

**Files:**
- Create: `CRM-Client/src/schemas/team-join.schema.ts`

**Interfaces:**
- Produces: `teamJoinSchema` (Zod schema), `TeamJoinFormValues` (TypeScript 类型)

- [ ] **Step 1: 创建 Zod schema 文件**

```typescript
// CRM-Client/src/schemas/team-join.schema.ts
import { z } from 'zod'

export const teamJoinSchema = z.object({
  code: z
    .string()
    .min(4, { message: '邀请码长度为4-20个字符' })
    .max(20, { message: '邀请码长度为4-20个字符' }),
})

export type TeamJoinFormValues = z.infer<typeof teamJoinSchema>
```

- [ ] **Step 2: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add CRM-Client/src/schemas/team-join.schema.ts
git commit -m "feat(schemas): add team join form schema"
```

---

### Task 3: 迁移 Onboarding.vue 主入口页面

**Files:**
- Modify: `CRM-Client/src/views/Onboarding.vue`

**Interfaces:**
- Consumes: `Button`, `Card`, `CardContent` from `@/components/crmwolf`
- Consumes: 图标 `Plus`, `Link`, `LogOut` from `lucide-vue-next`

**业务逻辑（保持不变）：**
- 点击"创建新团队" → 导航到 `/onboarding/create-team`
- 点击"加入已有团队" → 导航到 `/onboarding/join-team`
- 点击"退出登录" → 显示确认对话框后调用 `userStore.logout()` 并导航到 `/login`

**UI/UX Pro Max 要求：**
- Logo 使用描述性 alt 文本
- 移动端使用动态视口高度
- 使用 safe-area insets
- 退出登录需要确认对话框

- [ ] **Step 1: 更新 script 部分 - 替换导入**

将原导入：
```typescript
import { Plus, Link, SwitchButton } from '@element-plus/icons-vue'
```

替换为：
```typescript
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Link, LogOut } from 'lucide-vue-next'
import { Button, Card, CardContent } from '@/components/crmwolf'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const showLogoutDialog = ref(false)

const goToCreateTeam = (): void => {
  router.push('/onboarding/create-team')
}

const goToJoinTeam = (): void => {
  router.push('/onboarding/join-team')
}

const handleLogout = (): void => {
  showLogoutDialog.value = true
}

const confirmLogout = (): void => {
  userStore.logout()
  router.push('/login')
}
```

- [ ] **Step 2: 更新 template - 替换组件**

将原 template 替换为：
```vue
<template>
  <main class="onboarding-container" role="main" aria-label="团队设置引导页面">
    <Button 
      variant="ghost" 
      size="sm" 
      class="logout-btn" 
      aria-label="退出登录"
      @click="handleLogout"
    >
      <LogOut class="mr-2 h-4 w-4" aria-hidden="true" />
      退出登录
    </Button>

    <Card class="onboarding-card">
      <CardContent class="card-body">
        <div class="logo">
          <img 
            src="/logo.png" 
            alt="CRMWolf 智能客户关系管理系统 Logo" 
            width="64" 
            height="64" 
          />
          <p>智能客户关系管理系统</p>
        </div>

        <div class="welcome-text">
          <h1 class="text-2xl font-semibold">欢迎使用 CRMWolf</h1>
          <p>开始使用前，您需要先创建或加入一个团队</p>
        </div>

        <div class="action-buttons" role="group" aria-label="团队操作选项">
          <Button size="lg" class="action-btn" @click="goToCreateTeam">
            <Plus class="mr-2 h-5 w-5" aria-hidden="true" />
            创建新团队
          </Button>

          <Button variant="outline" size="lg" class="action-btn" @click="goToJoinTeam">
            <Link class="mr-2 h-5 w-5" aria-hidden="true" />
            加入已有团队
          </Button>
        </div>

        <p class="tip-text">创建团队后，您将成为团队管理员，可以邀请团队成员</p>
      </CardContent>
    </Card>

    <!-- 退出登录确认对话框 -->
    <AlertDialog v-model:open="showLogoutDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认退出</AlertDialogTitle>
          <AlertDialogDescription>
            确定要退出登录吗？退出后需要重新登录才能继续使用系统。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="confirmLogout">确认退出</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>
```

- [ ] **Step 3: 更新 style 部分 - 迁移到 V2 变量 + 移动端适配**

将原样式替换为：
```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度，避免 iOS Safari 地址栏问题
  min-height: $wolf-viewport-height-mobile-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page-v2;
  padding: $wolf-space-lg-v2;
  // UI/UX Pro Max: Safe area 支持
  padding-top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  padding-bottom: calc($wolf-space-lg-v2 + $wolf-safe-area-bottom-v2);
  position: relative;
}

.logout-btn {
  position: absolute;
  top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  right: $wolf-space-lg-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  // UI/UX Pro Max: Touch target ≥44px
  min-height: $wolf-touch-target-min-v2;
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
}

.card-body {
  padding: $wolf-space-2xl-v2 $wolf-space-lg-v2;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;
}

.logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
  margin-bottom: $wolf-space-md-v2;
}

.logo p {
  font-size: $wolf-font-size-title-v2;
  color: $wolf-text-primary-v2;
  margin: 0;
  font-weight: $wolf-font-weight-semibold-v2;
}

.welcome-text {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;

  h1 {
    color: $wolf-text-primary-v2;
    margin: 0 0 $wolf-space-sm-v2 0;
  }

  p {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    margin: 0;
  }
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md-v2;
  width: 100%;
}

.action-btn {
  width: 100%;
  height: $wolf-button-height-lg-v2; // 48px - UI/UX Pro Max touch target
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.tip-text {
  text-align: center;
  margin-top: $wolf-space-2xl-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

// UI/UX Pro Max: Mobile breakpoint
@media (max-width: $wolf-breakpoint-xs-v2) {
  .onboarding-container {
    padding: $wolf-page-padding-mobile-v2;
    padding-top: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-top-v2);
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .logout-btn {
    top: calc($wolf-space-md-v2 + $wolf-safe-area-top-v2);
    right: $wolf-space-md-v2;
  }

  .card-body {
    padding: $wolf-space-xl-v2 $wolf-card-padding-mobile-v2;
  }

  .welcome-text h1 {
    font-size: $wolf-font-size-title-mobile-v2;
  }
}
</style>
```

- [ ] **Step 4: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS

- [ ] **Step 5: 手动测试 - 验证页面渲染**

Run: `cd CRM-Client && npm run dev`
验证：
1. 访问 `/onboarding` 页面正常渲染
2. 两个按钮样式正确（主按钮蓝色，次要按钮 outline）
3. 点击"创建新团队"跳转到 `/onboarding/create-team`
4. 点击"加入已有团队"跳转到 `/onboarding/join-team`
5. 点击"退出登录"显示确认对话框
6. 确认对话框点击"取消"关闭对话框
7. 确认对话框点击"确认退出"执行登出并跳转到 `/login`
8. 移动端 (375px) 页面布局正确，按钮可点击

- [ ] **Step 6: 提交**

```bash
git add CRM-Client/src/views/Onboarding.vue
git commit -m "feat(onboarding): migrate Onboarding.vue to V2 design system with accessibility and mobile optimization"
```

---

### Task 4: 迁移 TeamCreate.vue 表单页面

**Files:**
- Modify: `CRM-Client/src/views/TeamCreate.vue`

**Interfaces:**
- Consumes: `teamCreateSchema`, `TeamCreateFormValues` from `@/schemas/team-create.schema`
- Consumes: `Button`, `Card`, `CardContent`, `Input` from `@/components/crmwolf`
- Consumes: `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormDescription`, `ErrorMessage` from `@/components/ui/form`
- Consumes: 图标 `ArrowLeft`, `LogOut` from `lucide-vue-next`
- Consumes: `toast` from `vue-sonner`

**业务逻辑（保持不变）：**
- 表单验证：团队名称 2-50 字符
- 提交成功后调用 `teamStore.createTeam()` 并导航到 `/leads`
- 返回按钮导航到 `/onboarding`

**UI/UX Pro Max 要求：**
- 使用 `FormDescription` 提供帮助文本
- 使用 `ErrorMessage` 显示验证错误（aria-live 自动支持）
- 表单验证失败后自动聚焦第一个无效字段
- 退出登录需要确认对话框

- [ ] **Step 1: 更新 script 部分 - 替换导入和表单逻辑**

将原 script 替换为：
```typescript
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { ArrowLeft, LogOut } from 'lucide-vue-next'
import { Button, Card, CardContent, Input } from '@/components/crmwolf'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormDescription,
} from '@/components/ui/form'
import ErrorMessage from '@/components/ui/form/ErrorMessage.vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { teamCreateSchema, type TeamCreateFormValues } from '@/schemas/team-create.schema'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const teamStore = useTeamStore()
const userStore = useUserStore()

const loading = ref(false)
const showLogoutDialog = ref(false)

const { handleSubmit } = useForm<TeamCreateFormValues>({
  validationSchema: toTypedSchema(teamCreateSchema),
  initialValues: {
    name: '',
  },
})

// UI/UX Pro Max: 验证失败后聚焦第一个无效字段
const focusFirstInvalidField = async (): Promise<void> => {
  await nextTick()
  const firstInvalid = document.querySelector<HTMLInputElement>('input[aria-invalid="true"]')
  firstInvalid?.focus()
}

const onSubmit = handleSubmit(async (values): Promise<void> => {
  loading.value = true
  try {
    await teamStore.createTeam(values.name)
    toast.success('团队创建成功')
    router.push('/leads')
  } catch (error: unknown) {
    handleApiError(error, '创建团队')
  } finally {
    loading.value = false
  }
}, focusFirstInvalidField) // 验证失败时聚焦

const goBack = (): void => {
  router.push('/onboarding')
}

const handleLogout = (): void => {
  showLogoutDialog.value = true
}

const confirmLogout = (): void => {
  userStore.logout()
  router.push('/login')
}
</script>
```

- [ ] **Step 2: 更新 template - 使用 FormField 组件**

将原 template 替换为：
```vue
<template>
  <main class="onboarding-container" role="main" aria-label="创建新团队">
    <Button 
      variant="ghost" 
      size="sm" 
      class="logout-btn" 
      aria-label="退出登录"
      @click="handleLogout"
    >
      <LogOut class="mr-2 h-4 w-4" aria-hidden="true" />
      退出登录
    </Button>

    <Card class="onboarding-card">
      <CardContent class="card-body">
        <div class="logo">
          <img 
            src="/logo.png" 
            alt="CRMWolf 智能客户关系管理系统 Logo" 
            width="64" 
            height="64" 
          />
          <p>智能客户关系管理系统</p>
        </div>

        <header class="header">
          <h1 class="text-2xl font-semibold">创建新团队</h1>
          <p>创建团队后，您将成为团队管理员</p>
        </header>

        <form class="create-form" @submit.prevent="onSubmit" novalidate>
          <FormField v-slot="{ componentField, errorMessage }" name="name">
            <FormItem>
              <FormLabel for="team-name">团队名称</FormLabel>
              <FormControl>
                <Input
                  id="team-name"
                  type="text"
                  placeholder="请输入团队名称"
                  maxlength="50"
                  :aria-invalid="!!errorMessage"
                  :aria-describedby="errorMessage ? 'team-name-error team-name-hint' : 'team-name-hint'"
                  v-bind="componentField"
                />
              </FormControl>
              <!-- UI/UX Pro Max: 帮助文本 -->
              <FormDescription id="team-name-hint">
                团队名称长度为 2-50 个字符
              </FormDescription>
              <!-- UI/UX Pro Max: 错误消息使用 ErrorMessage（自动 aria-live） -->
              <ErrorMessage id="team-name-error" :message="errorMessage" />
            </FormItem>
          </FormField>

          <Button 
            type="submit" 
            size="lg" 
            class="submit-btn" 
            :disabled="loading"
            :aria-busy="loading"
          >
            <span v-if="loading">创建中...</span>
            <span v-else>创建团队</span>
          </Button>
        </form>

        <Button variant="ghost" size="sm" class="back-link" @click="goBack">
          <ArrowLeft class="mr-2 h-4 w-4" aria-hidden="true" />
          返回上一步
        </Button>
      </CardContent>
    </Card>

    <!-- 退出登录确认对话框 -->
    <AlertDialog v-model:open="showLogoutDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认退出</AlertDialogTitle>
          <AlertDialogDescription>
            确定要退出登录吗？退出后需要重新登录才能继续使用系统。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="confirmLogout">确认退出</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>
```

- [ ] **Step 3: 更新 style 部分 - 迁移到 V2 变量 + 移动端适配**

将原样式替换为：
```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度
  min-height: $wolf-viewport-height-mobile-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page-v2;
  padding: $wolf-space-lg-v2;
  // UI/UX Pro Max: Safe area 支持
  padding-top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  padding-bottom: calc($wolf-space-lg-v2 + $wolf-safe-area-bottom-v2);
  position: relative;
}

.logout-btn {
  position: absolute;
  top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  right: $wolf-space-lg-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  min-height: $wolf-touch-target-min-v2;
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
}

.card-body {
  padding: $wolf-space-2xl-v2 $wolf-space-lg-v2;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;
}

.logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
  margin-bottom: $wolf-space-md-v2;
}

.logo p {
  font-size: $wolf-font-size-title-v2;
  color: $wolf-text-primary-v2;
  margin: 0;
  font-weight: $wolf-font-weight-semibold-v2;
}

.header {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;

  h1 {
    color: $wolf-text-primary-v2;
    margin: 0 0 $wolf-space-sm-v2 0;
  }

  p {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    margin: 0;
  }
}

.create-form {
  width: 100%;
  margin-bottom: $wolf-space-lg-v2;
}

.submit-btn {
  width: 100%;
  height: $wolf-button-height-lg-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  margin-top: $wolf-space-md-v2;
}

.back-link {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  min-height: $wolf-touch-target-min-v2;
}

// UI/UX Pro Max: Mobile breakpoint
@media (max-width: $wolf-breakpoint-xs-v2) {
  .onboarding-container {
    padding: $wolf-page-padding-mobile-v2;
    padding-top: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-top-v2);
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .logout-btn {
    top: calc($wolf-space-md-v2 + $wolf-safe-area-top-v2);
    right: $wolf-space-md-v2;
  }

  .card-body {
    padding: $wolf-space-xl-v2 $wolf-card-padding-mobile-v2;
  }

  .header h1 {
    font-size: $wolf-font-size-title-mobile-v2;
  }
}
</style>
```

- [ ] **Step 4: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS

- [ ] **Step 5: 手动测试 - 验证表单功能**

Run: `cd CRM-Client && npm run dev`
验证：
1. 访问 `/onboarding/create-team` 页面正常渲染
2. 输入框样式正确，帮助文本显示
3. 提交空表单显示验证错误，焦点自动移至无效字段
4. 输入少于2字符显示验证错误
5. 正常提交表单（mock 或实际 API）
6. 返回按钮跳转到 `/onboarding`
7. 退出登录显示确认对话框
8. 移动端 (375px) 布局正确

- [ ] **Step 6: 提交**

```bash
git add CRM-Client/src/views/TeamCreate.vue
git commit -m "feat(onboarding): migrate TeamCreate.vue to V2 design system with accessibility and form UX optimization"
```

---

### Task 5: 迁移 TeamJoin.vue 表单页面

**Files:**
- Modify: `CRM-Client/src/views/TeamJoin.vue`

**Interfaces:**
- Consumes: `teamJoinSchema`, `TeamJoinFormValues` from `@/schemas/team-join.schema`
- Consumes: `Button`, `Card`, `CardContent`, `Input` from `@/components/crmwolf`
- Consumes: `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormDescription`, `ErrorMessage` from `@/components/ui/form`
- Consumes: 图标 `ArrowLeft`, `LogOut` from `lucide-vue-next`
- Consumes: `toast` from `vue-sonner`

**业务逻辑（保持不变）：**
- 表单验证：邀请码 4-20 字符
- 提交成功后调用 `teamStore.joinTeam()` 并导航到 `/leads`
- 返回按钮导航到 `/onboarding`

**UI/UX Pro Max 要求：**
- 使用 `FormDescription` 提供帮助文本
- 使用 `ErrorMessage` 显示验证错误（aria-live 自动支持）
- 表单验证失败后自动聚焦第一个无效字段
- 退出登录需要确认对话框

- [ ] **Step 1: 更新 script 部分 - 替换导入和表单逻辑**

将原 script 替换为：
```typescript
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { ArrowLeft, LogOut } from 'lucide-vue-next'
import { Button, Card, CardContent, Input } from '@/components/crmwolf'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormDescription,
} from '@/components/ui/form'
import ErrorMessage from '@/components/ui/form/ErrorMessage.vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { teamJoinSchema, type TeamJoinFormValues } from '@/schemas/team-join.schema'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const teamStore = useTeamStore()
const userStore = useUserStore()

const loading = ref(false)
const showLogoutDialog = ref(false)

const { handleSubmit } = useForm<TeamJoinFormValues>({
  validationSchema: toTypedSchema(teamJoinSchema),
  initialValues: {
    code: '',
  },
})

// UI/UX Pro Max: 验证失败后聚焦第一个无效字段
const focusFirstInvalidField = async (): Promise<void> => {
  await nextTick()
  const firstInvalid = document.querySelector<HTMLInputElement>('input[aria-invalid="true"]')
  firstInvalid?.focus()
}

const onSubmit = handleSubmit(async (values): Promise<void> => {
  loading.value = true
  try {
    await teamStore.joinTeam(values.code)
    toast.success('加入团队成功')
    router.push('/leads')
  } catch (error: unknown) {
    handleApiError(error, '加入团队')
  } finally {
    loading.value = false
  }
}, focusFirstInvalidField)

const goBack = (): void => {
  router.push('/onboarding')
}

const handleLogout = (): void => {
  showLogoutDialog.value = true
}

const confirmLogout = (): void => {
  userStore.logout()
  router.push('/login')
}
</script>
```

- [ ] **Step 2: 更新 template - 使用 FormField 组件**

将原 template 替换为：
```vue
<template>
  <main class="onboarding-container" role="main" aria-label="加入已有团队">
    <Button 
      variant="ghost" 
      size="sm" 
      class="logout-btn" 
      aria-label="退出登录"
      @click="handleLogout"
    >
      <LogOut class="mr-2 h-4 w-4" aria-hidden="true" />
      退出登录
    </Button>

    <Card class="onboarding-card">
      <CardContent class="card-body">
        <div class="logo">
          <img 
            src="/logo.png" 
            alt="CRMWolf 智能客户关系管理系统 Logo" 
            width="64" 
            height="64" 
          />
          <p>智能客户关系管理系统</p>
        </div>

        <header class="header">
          <h1 class="text-2xl font-semibold">加入已有团队</h1>
          <p>请输入团队邀请码，加入您的团队</p>
        </header>

        <form class="join-form" @submit.prevent="onSubmit" novalidate>
          <FormField v-slot="{ componentField, errorMessage }" name="code">
            <FormItem>
              <FormLabel for="invite-code">邀请码</FormLabel>
              <FormControl>
                <Input
                  id="invite-code"
                  type="text"
                  placeholder="请输入邀请码"
                  maxlength="20"
                  :aria-invalid="!!errorMessage"
                  :aria-describedby="errorMessage ? 'invite-code-error invite-code-hint' : 'invite-code-hint'"
                  v-bind="componentField"
                />
              </FormControl>
              <!-- UI/UX Pro Max: 帮助文本 -->
              <FormDescription id="invite-code-hint">
                邀请码长度为 4-20 个字符
              </FormDescription>
              <!-- UI/UX Pro Max: 错误消息 -->
              <ErrorMessage id="invite-code-error" :message="errorMessage" />
            </FormItem>
          </FormField>

          <Button 
            type="submit" 
            size="lg" 
            class="submit-btn" 
            :disabled="loading"
            :aria-busy="loading"
          >
            <span v-if="loading">加入中...</span>
            <span v-else>加入团队</span>
          </Button>
        </form>

        <p class="tip-text">邀请码由团队管理员提供，通常为6-8位字母数字组合</p>

        <Button variant="ghost" size="sm" class="back-link" @click="goBack">
          <ArrowLeft class="mr-2 h-4 w-4" aria-hidden="true" />
          返回上一步
        </Button>
      </CardContent>
    </Card>

    <!-- 退出登录确认对话框 -->
    <AlertDialog v-model:open="showLogoutDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认退出</AlertDialogTitle>
          <AlertDialogDescription>
            确定要退出登录吗？退出后需要重新登录才能继续使用系统。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="confirmLogout">确认退出</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>
```

- [ ] **Step 3: 更新 style 部分 - 迁移到 V2 变量 + 移动端适配**

将原样式替换为：
```scss
<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度
  min-height: $wolf-viewport-height-mobile-v2;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page-v2;
  padding: $wolf-space-lg-v2;
  // UI/UX Pro Max: Safe area 支持
  padding-top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  padding-bottom: calc($wolf-space-lg-v2 + $wolf-safe-area-bottom-v2);
  position: relative;
}

.logout-btn {
  position: absolute;
  top: calc($wolf-space-lg-v2 + $wolf-safe-area-top-v2);
  right: $wolf-space-lg-v2;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  min-height: $wolf-touch-target-min-v2;
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
}

.card-body {
  padding: $wolf-space-2xl-v2 $wolf-space-lg-v2;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;
}

.logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
  margin-bottom: $wolf-space-md-v2;
}

.logo p {
  font-size: $wolf-font-size-title-v2;
  color: $wolf-text-primary-v2;
  margin: 0;
  font-weight: $wolf-font-weight-semibold-v2;
}

.header {
  text-align: center;
  margin-bottom: $wolf-space-2xl-v2;

  h1 {
    color: $wolf-text-primary-v2;
    margin: 0 0 $wolf-space-sm-v2 0;
  }

  p {
    font-size: $wolf-font-size-body-v2;
    color: $wolf-text-secondary-v2;
    margin: 0;
  }
}

.join-form {
  width: 100%;
  margin-bottom: $wolf-space-md-v2;
}

.submit-btn {
  width: 100%;
  height: $wolf-button-height-lg-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-medium-v2;
  margin-top: $wolf-space-md-v2;
}

.tip-text {
  text-align: center;
  margin-bottom: $wolf-space-lg-v2;
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
}

.back-link {
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-caption-v2;
  min-height: $wolf-touch-target-min-v2;
}

// UI/UX Pro Max: Mobile breakpoint
@media (max-width: $wolf-breakpoint-xs-v2) {
  .onboarding-container {
    padding: $wolf-page-padding-mobile-v2;
    padding-top: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-top-v2);
    padding-bottom: calc($wolf-page-padding-mobile-v2 + $wolf-safe-area-bottom-v2);
  }

  .logout-btn {
    top: calc($wolf-space-md-v2 + $wolf-safe-area-top-v2);
    right: $wolf-space-md-v2;
  }

  .card-body {
    padding: $wolf-space-xl-v2 $wolf-card-padding-mobile-v2;
  }

  .header h1 {
    font-size: $wolf-font-size-title-mobile-v2;
  }
}
</style>
```

- [ ] **Step 4: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS

- [ ] **Step 5: 手动测试 - 验证表单功能**

Run: `cd CRM-Client && npm run dev`
验证：
1. 访问 `/onboarding/join-team` 页面正常渲染
2. 输入框样式正确，帮助文本显示
3. 提交空表单显示验证错误，焦点自动移至无效字段
4. 输入少于4字符显示验证错误
5. 正常提交表单（mock 或实际 API）
6. 返回按钮跳转到 `/onboarding`
7. 退出登录显示确认对话框
8. 移动端 (375px) 布局正确

- [ ] **Step 6: 提交**

```bash
git add CRM-Client/src/views/TeamJoin.vue
git commit -m "feat(onboarding): migrate TeamJoin.vue to V2 design system with accessibility and form UX optimization"
```

---

### Task 6: 创建 ErrorMessage 组件（如不存在）

**Files:**
- Create: `CRM-Client/src/components/ui/form/ErrorMessage.vue`

**Interfaces:**
- Consumes: `role="alert"` 属性用于屏幕阅读器通知
- Produces: 带有 aria-live 支持的错误消息组件

**UI/UX Pro Max 要求：**
- 使用 `role="alert"` 实现自动 aria-live
- 错误消息必须可被屏幕阅读器感知

- [ ] **Step 1: 检查 ErrorMessage 组件是否存在**

Run: `ls CRM-Client/src/components/ui/form/`
Expected: 如果没有 ErrorMessage.vue 则创建

- [ ] **Step 2: 创建 ErrorMessage 组件（如不存在）**

```vue
<!-- CRM-Client/src/components/ui/form/ErrorMessage.vue -->
<script setup lang="ts">
import { cn } from '@/lib/utils'

interface Props {
  message?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: undefined,
  class: undefined,
})
</script>

<template>
  <p
    v-if="message"
    role="alert"
    :class="cn('text-sm font-medium text-destructive', props.class)"
    aria-live="polite"
  >
    {{ message }}
  </p>
</template>
```

- [ ] **Step 3: 导出 ErrorMessage（更新 index.ts）**

在 `CRM-Client/src/components/ui/form/index.ts` 中添加导出：
```typescript
export { default as ErrorMessage } from './ErrorMessage.vue'
```

- [ ] **Step 4: 运行类型检查**

Run: `cd CRM-Client && npm run type-check`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add CRM-Client/src/components/ui/form/ErrorMessage.vue
git add CRM-Client/src/components/ui/form/index.ts
git commit -m "feat(form): add ErrorMessage component with aria-live support for accessibility"
```

---

### Task 7: 端到端集成测试

**Files:**
- 无新增文件，验证现有流程

- [ ] **Step 1: 运行开发服务器**

Run: `cd CRM-Client && npm run dev`

- [ ] **Step 2: 验证完整 onboarding 流程**

在浏览器中执行以下测试用例：

**测试路径 1：创建团队**
1. 访问 `/onboarding`
2. 验证页面布局正确（Logo、标题、两个按钮）
3. 点击"创建新团队"
4. 验证跳转到 `/onboarding/create-team`
5. 验证表单验证（空提交、短名称）- 焦点自动移至无效字段
6. 输入有效团队名称并提交
7. 验证跳转到 `/leads`

**测试路径 2：加入团队**
1. 访问 `/onboarding`
2. 点击"加入已有团队"
3. 验证跳转到 `/onboarding/join-team`
4. 验证表单验证（空提交、短邀请码）- 焦点自动移至无效字段
5. 输入有效邀请码并提交
6. 验证跳转到 `/leads`

**测试路径 3：退出登录确认**
1. 在任意 onboarding 页面点击"退出登录"
2. 验证显示确认对话框
3. 点击"取消"关闭对话框，留在当前页
4. 再次点击"退出登录"
5. 点击"确认退出"验证跳转到 `/login`

**测试路径 4：移动端适配**
1. Chrome DevTools 切换到 iPhone SE (375px)
2. 验证所有页面布局正确
3. 验证按钮高度符合 touch target (≥44px)
4. 验证 safe-area 正常工作

**测试路径 5：无障碍测试**
1. 使用键盘 Tab 导航，验证焦点顺序正确
2. 验证所有交互元素有可见焦点环
3. 使用屏幕阅读器验证 Logo alt 文本正确
4. 验证表单验证错误能被屏幕阅读器朗读

- [ ] **Step 3: 运行 lint 和类型检查**

Run: `cd CRM-Client && npm run lint && npm run type-check`
Expected: PASS

- [ ] **Step 4: 最终提交（如有遗漏修复）**

```bash
git status
# 如有未提交的修改
git add -A
git commit -m "fix(onboarding): final cleanup for V2 migration"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] Onboarding.vue - 迁移到 shadcn-vue Button, Card + V2 变量 + 无障碍 + 移动端适配
- [x] TeamCreate.vue - 迁移到 VeeValidate + Zod + shadcn-vue + V2 变量 + 表单 UX 优化
- [x] TeamJoin.vue - 迁移到 VeeValidate + Zod + shadcn-vue + V2 变量 + 表单 UX 优化
- [x] 创建 team-create.schema.ts
- [x] 创建 team-join.schema.ts
- [x] 创建 ErrorMessage.vue（带 aria-live 支持）
- [x] 所有 Element Plus 组件已替换
- [x] 所有 V1 变量已替换为 V2

**2. UI/UX Pro Max CRITICAL 检查:**
- [x] **Accessibility**: 表单错误使用 `role="alert"` 实现 aria-live
- [x] **Accessibility**: 验证失败后自动聚焦第一个无效字段
- [x] **Accessibility**: Logo 使用描述性 alt 文本
- [x] **Touch Target**: 所有按钮高度 ≥44px
- [x] **Layout**: 使用动态视口高度 `$wolf-viewport-height-mobile-v2`
- [x] **Layout**: 使用 safe-area insets
- [x] **Forms**: 使用 `FormDescription` 提供帮助文本
- [x] **Forms**: 使用 `ErrorMessage` 组件显示验证错误
- [x] **Navigation**: 退出登录显示确认对话框

**3. Placeholder scan:**
- [x] 无 TBD/TODO 占位符
- [x] 所有代码步骤包含完整实现
- [x] 所有命令包含预期输出

**4. Type consistency:**
- [x] `TeamCreateFormValues` 在 Task 1 定义，Task 4 使用 - 一致
- [x] `TeamJoinFormValues` 在 Task 2 定义，Task 5 使用 - 一致
- [x] `handleSubmit` 来自 VeeValidate，与 schema 类型一致

**5. Design System V2 合规:**
- [x] 所有变量使用 `-v2` 后缀
- [x] 移动端断点使用 `$wolf-breakpoint-xs-v2`
- [x] 移动端字体使用 `$wolf-font-size-*-mobile-v2`
- [x] Safe area 使用 `$wolf-safe-area-*-v2`
- [x] 触摸目标使用 `$wolf-touch-target-min-v2`
- [x] 按钮高度使用 `$wolf-button-height-lg-v2`