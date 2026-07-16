# Task 5: 迁移 TeamJoin.vue 表单页面

**Files:**
- Modify: `CRM-Client/src/views/TeamJoin.vue`

**Interfaces:**
- Consumes: `teamJoinSchema`, `TeamJoinFormValues` from `@/schemas/team-join.schema` (Task 2)
- Consumes: `Button`, `Card`, `CardContent`, `Input` from `@/components/crmwolf`
- Consumes: `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormDescription` from `@/components/ui/form`
- Consumes: `ErrorMessage` from `@/components/ui/form/ErrorMessage.vue` (Task 6)
- Consumes: 图标 `ArrowLeft`, `LogOut` from `lucide-vue-next`
- Consumes: `toast` from `vue-sonner`

**业务逻辑（保持不变）：**
- 表单验证：邀请码 4-20 字符
- 提交成功后调用 `teamStore.joinTeam()` 并导航到 `/leads`
- 返回按钮导航到 `/onboarding`

## UI/UX Pro Max 要求

- 使用 `FormDescription` 提供帮助文本
- 使用 `ErrorMessage` 显示验证错误（aria-live 自动支持）
- 表单验证失败后自动聚焦第一个无效字段
- 退出登录需要确认对话框

## Global Constraints

- **设计令牌来源**：`CRM-Client/src/styles/variables-v2.scss`（必须使用 `-v2` 后缀变量）
- **表单验证**：使用 VeeValidate + Zod
- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`

## Implementation Steps

See full implementation in plan: CRM-Client/docs/superpowers/plans/2026-07-15-onboarding-v2-migration.md (lines 767-1122)

Key changes:
1. Replace Element Plus form with VeeValidate + FormField
2. Add focusFirstInvalidField for validation error focus
3. Add AlertDialog for logout confirmation
4. Use FormDescription and ErrorMessage components