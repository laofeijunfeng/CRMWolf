# Task 4: FollowUpList 迁移到 shadcn-vue

**Files:**
- Modify: `src/components/FollowUpList.vue`

**Interfaces:**
- Consumes: `followUps` prop, `loading` prop, `currentUserId` prop
- Produces: shadcn-vue 版本的跟进记录列表

---

## Global Constraints

- **Design Tokens**: 必须使用 `variables-v2.scss` 和 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`，禁止 Element Plus
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`
- **Lucide Icons**: 使用 Lucide Icons，禁止 Emoji

---

## Requirements

1. Replace all Element Plus components with shadcn-vue:
   - `el-skeleton` → `Skeleton`
   - `el-empty` → `Empty` (with EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription)
   - `el-icon` → Lucide Icons
   - `el-button` → `Button`
   - `ElMessageBox.confirm` → `Dialog` confirmation

2. Update styles to use Design Tokens (`$wolf-xxx-v2`)

3. Add delete confirmation dialog with shadcn-vue Dialog

---

## Key Changes

- Import `Delete, User, Phone, MessageSquare` from `lucide-vue-next`
- Import `Button, Skeleton, Empty components, Dialog components`
- Replace Element Plus icons with Lucide Icons
- Update all styles to use `$wolf-xxx-v2` tokens

---

## Verification

```bash
npm run type-check
```

Expected: No TypeScript errors, no Element Plus imports remaining