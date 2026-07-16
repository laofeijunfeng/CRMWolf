# Task 2: 创建团队加入表单 Schema

**Files:**
- Create: `CRM-Client/src/schemas/team-join.schema.ts`

**Interfaces:**
- Produces: `teamJoinSchema` (Zod schema), `TeamJoinFormValues` (TypeScript 类型)

## Global Constraints

- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`
- **表单验证**：使用 VeeValidate + Zod（`@vee-validate/zod`, `vee-validate`）

## Implementation

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