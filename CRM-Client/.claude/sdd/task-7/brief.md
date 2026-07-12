# Task 7: ContactsPanel 面板

**Files:**
- Create: `src/components/panels/ContactsPanel.vue`

**Interfaces:**
- Consumes: `customerId: number`, `contacts: ContactResponse[]`
- Produces: ContactsPanel component with add/edit/delete/set-primary operations

## Global Constraints

- **Design Tokens**: 使用 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`
- **Lucide Icons**: 使用 Lucide Icons

## Implementation

参见续编文档：`.claude/plans/2026-07-11-customer-detail-sheet-phase2-implementation-part2.md`

关键点：
- 联系人列表展示（姓名、职位、电话、邮箱、决策者标记）
- 主要联系人 Badge 显示
- 编辑/删除/设为主要联系人操作
- StatusBadge 显示决策者标记