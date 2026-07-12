# Task 5: FollowUpPanel 面板

**Files:**
- Create: `src/components/panels/FollowUpPanel.vue`

**Interfaces:**
- Consumes: `customerId: number`, `followUps: CustomerFollowUpResponse[]`
- Produces: FollowUpPanel component

---

## Global Constraints

- **Design Tokens**: 必须使用 `variables-v2.scss` 和 `$wolf-xxx-v2` 变量名
- **shadcn-vue**: 所有 UI 组件必须来自 `src/components/ui/`
- **TypeScript**: 禁用 `any` `as any` `@ts-ignore` `!`

---

## Requirements

Create a panel component that wraps FollowUpList with:
- Card header with title "跟进记录"
- "添加跟进" button
- FollowUpList component in CardContent

---

## Component Structure

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { Plus } from 'lucide-vue-next'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import FollowUpList from '@/components/FollowUpList.vue'
import type { CustomerFollowUpResponse } from '@/api/customerFollowUp'

interface Props {
  customerId: number
  followUps: CustomerFollowUpResponse[]
  currentUserId?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'add': []
  'delete': [followUp: CustomerFollowUpResponse]
}>()
</script>

<template>
  <Card>
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">跟进记录</h3>
      <Button size="sm" @click="$emit('add')">
        <Plus class="w-4 h-4 mr-1" />
        添加跟进
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <FollowUpList
        :follow-ups="followUps"
        :loading="false"
        :current-user-id="currentUserId"
        @delete="$emit('delete', $event)"
      />
    </CardContent>
  </Card>
</template>
```

---

## Verification

```bash
npm run type-check
```

Expected: No TypeScript errors