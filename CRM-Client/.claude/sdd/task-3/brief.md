# Task 3: 客户档案卡片（Accordion）

**Files:**
- Modify: `src/views/CustomerDetailSheet.vue`

**Interfaces:**
- Consumes: `customer` ref from Task 1
- Produces: 可折叠的客户档案卡片 UI

---

## Global Constraints

- **Design Tokens**: 必须使用 `variables-v2.scss` 和 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`，禁止 Element Plus 新代码
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`

---

## Step 1: 导入 Accordion 组件

```typescript
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent
} from '@/components/ui/accordion'
import { RefreshCw, Loader2 } from 'lucide-vue-next'
```

---

## Step 2: 添加档案状态和函数

```typescript
const regeneratingProfile = ref(false)

const handleRegenerateProfile = async (): Promise<void> => {
  if (!props.customerId) return
  regeneratingProfile.value = true
  try {
    await customerApi.regenerateProfile(props.customerId)
    toast.success('档案生成中，请稍后刷新')
  } catch (error) {
    handleApiError(error, '生成档案')
  } finally {
    regeneratingProfile.value = false
  }
}
```

---

## Step 3: 在模板中添加客户档案卡片

在热力值卡片后添加完整模板（见计划文件）。

---

## Step 4: 添加样式

```scss
.profile-item {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-xs-v2;
}

.profile-label {
  font-size: $wolf-font-size-caption-v2;
  color: $wolf-text-tertiary-v2;
  font-weight: $wolf-font-weight-medium-v2;
}

.profile-value {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-secondary-v2;
  line-height: $wolf-line-height-body-v2;
}

.profile-link {
  font-size: $wolf-font-size-body-v2;
  color: $wolf-text-link-v2;
  text-decoration: underline;

  &:hover {
    color: $wolf-text-link-hover-v2;
  }
}
```

---

## Step 5-6: 验证编译 + 提交

```bash
npm run type-check
git add src/views/CustomerDetailSheet.vue
git commit -m "feat(CustomerDetailSheet): add customer profile card with Accordion"
```