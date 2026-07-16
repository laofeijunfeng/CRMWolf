# Task 3: 迁移 Onboarding.vue 主入口页面

**Files:**
- Modify: `CRM-Client/src/views/Onboarding.vue`

**Interfaces:**
- Consumes: `Button`, `Card`, `CardContent` from `@/components/crmwolf`
- Consumes: 图标 `Plus`, `Link`, `LogOut` from `lucide-vue-next`
- Consumes: `AlertDialog` components from `@/components/ui/alert-dialog`

**业务逻辑（保持不变）：**
- 点击"创建新团队" → 导航到 `/onboarding/create-team`
- 点击"加入已有团队" → 导航到 `/onboarding/join-team`
- 点击"退出登录" → 显示确认对话框后调用 `userStore.logout()` 并导航到 `/login`

## UI/UX Pro Max 要求

- Logo 使用描述性 alt 文本: `"CRMWolf 智能客户关系管理系统 Logo"`
- 移动端使用动态视口高度: `$wolf-viewport-height-mobile-v2`
- 使用 safe-area insets: `$wolf-safe-area-top-v2`, `$wolf-safe-area-bottom-v2`
- 退出登录需要确认对话框 (AlertDialog)
- 所有按钮高度 ≥44px: `$wolf-button-height-lg-v2`

## Global Constraints

- **设计令牌来源**：`CRM-Client/src/styles/variables-v2.scss`（必须使用 `-v2` 后缀变量）
- **组件导入**：从 `@/components/crmwolf` 统一导入
- **图标来源**：使用 `lucide-vue-next`
- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`

## Implementation Steps

See full implementation in plan: CRM-Client/docs/superpowers/plans/2026-07-15-onboarding-v2-migration.md (lines 150-413)

Key changes:
1. Replace Element Plus imports with shadcn-vue and lucide-vue-next
2. Add AlertDialog for logout confirmation
3. Update template with semantic HTML (role="main", aria-label, aria-hidden)
4. Update styles to use V2 variables with mobile breakpoint support