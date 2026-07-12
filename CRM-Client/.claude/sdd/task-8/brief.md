# Task 8: ContactFormDialog 弹窗

**Files:**
- Create: `src/components/dialogs/ContactFormDialog.vue`

**Interfaces:**
- Consumes: `customerId: number`, `open: boolean`, `contact?: ContactResponse` (edit mode)
- Produces: ContactFormDialog component

## Global Constraints

- **Design Tokens**: 使用 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`
- **表单验证**: VeeValidate + Zod schema

## Form Fields

- 姓名（必填）
- 性别（男/女）
- 职位
- 是否决策者（Switch）
- 手机号（必填，手机号格式验证）
- 邮箱（邮箱格式验证）
- 微信号

参见续编文档：`.claude/plans/2026-07-11-customer-detail-sheet-phase2-implementation-part2.md`