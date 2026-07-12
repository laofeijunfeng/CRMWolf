# Task 9: OpportunitiesPanel 面板

**Files:**
- Create: `src/components/panels/OpportunitiesPanel.vue`

**Interfaces:**
- Consumes: `customerId: number`, `opportunities: OpportunityListResponse[]`
- Produces: OpportunitiesPanel component

## Global Constraints

- **Design Tokens**: 使用 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`
- **Lucide Icons**: 使用 Lucide Icons

## Implementation

参见续编文档：`.claude/plans/2026-07-11-customer-detail-sheet-phase2-implementation-part2.md`

关键点：
- 商机列表展示（商机名称、金额、阶段、预计成交日期）
- StatusBadge 显示状态
- 点击跳转商机详情
- 新建商机按钮