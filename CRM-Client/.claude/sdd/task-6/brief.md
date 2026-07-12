# Task 6: FollowUpFormDialog 弹窗

**Files:**
- Create: `src/components/dialogs/FollowUpFormDialog.vue`

**Interfaces:**
- Consumes: `customerId: number`, `open: boolean`
- Produces: FollowUpFormDialog component

---

## Global Constraints

- **Design Tokens**: 必须使用 `variables-v2.scss` 和 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`
- **表单验证**: VeeValidate + Zod schema

---

## Requirements

Create a dialog for adding follow-up records with:
- 跟进方式 (RadioGroup: 电话/微信/拜访/邮件/其他)
- 跟进内容 (Textarea, required)
- 下次跟进时间 (Input type="date")
- 下一步动作 (Textarea)

---

## Key Implementation Details

1. Use VeeValidate + Zod for form validation
2. Set default next_follow_time to 3 days from now
3. Call `customerFollowUpApi.createFollowUp(customerId, data)`
4. Show toast on success
5. Emit 'update:open' and 'success' events

---

## Zod Schema

```typescript
const schema = toTypedSchema(
  z.object({
    method: z.string().min(1, '请选择跟进方式'),
    content: z.string().min(1, '请输入跟进内容').max(500, '内容不能超过500字'),
    next_follow_time: z.string().optional(),
    next_action: z.string().max(200, '动作不能超过200字').optional()
  })
)
```

---

## Verification

```bash
npm run type-check
```

Expected: No TypeScript errors