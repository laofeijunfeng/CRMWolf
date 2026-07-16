# Task 1: 创建团队创建表单 Schema

**Files:**
- Create: `CRM-Client/src/schemas/team-create.schema.ts`

**Interfaces:**
- Produces: `teamCreateSchema` (Zod schema), `TeamCreateFormValues` (TypeScript 类型)

## Global Constraints

- **设计令牌来源**：`CRM-Client/src/styles/variables-v2.scss`（必须使用 `-v2` 后缀变量）
- **组件导入**：从 `@/components/crmwolf` 统一导入（Button, Input, Card 等）
- **表单验证**：使用 VeeValidate + Zod（`@vee-validate/zod`, `vee-validate`）
- **消息提示**：使用 `toast` from `vue-sonner`（替代 ElMessage）
- **图标来源**：使用 `lucide-vue-next`（替代 @element-plus/icons-vue）
- **TypeScript 四禁令**：禁用 `any` `as any` `@ts-ignore` `!`

## Implementation

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