# CustomerDetailSheet Phase 2 实施计划（续）

> 续编：Task 7-17 详细步骤

---

## Task 7: ContactsPanel 面板

**Files:**
- Create: `src/components/panels/ContactsPanel.vue`

**Interfaces:**
- Consumes: `customerId: number`, `contacts: ContactResponse[]`
- Produces: ContactsPanel component

- [ ] **Step 1: 创建 ContactsPanel.vue**

```vue
<script setup lang="ts">
import { Plus, Pencil, Trash2, Star } from 'lucide-vue-next'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ContactResponse } from '@/api/customer'

interface Props {
  customerId: number
  contacts: ContactResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
  'edit': [contact: ContactResponse]
  'delete': [contactId: number]
  'set-primary': [contactId: number]
}>()

const handleAdd = (): void => {
  emit('add')
}

const handleEdit = (contact: ContactResponse): void => {
  emit('edit', contact)
}

const handleDelete = (contactId: number): void => {
  emit('delete', contactId)
}

const handleSetPrimary = (contactId: number): void => {
  emit('set-primary', contactId)
}
</script>

<template>
  <Card class="contacts-panel">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">联系人</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建联系人
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <div v-if="contacts.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
        暂无联系人
      </div>
      <div v-else class="divide-y divide-wolf-border-light-v2">
        <div
          v-for="contact in contacts"
          :key="contact.id"
          class="p-4 flex items-center justify-between hover:bg-wolf-bg-hover-v2 transition-colors"
        >
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium text-wolf-text-primary-v2">{{ contact.name }}</span>
              <Badge v-if="contact.is_primary" variant="secondary" class="text-xs">
                <Star class="w-3 h-3 mr-1" />
                主要联系人
              </Badge>
              <StatusBadge v-if="contact.is_decision_maker" status="decision-maker" text="决策者" />
            </div>
            <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
              {{ contact.position || '-' }} · {{ contact.mobile }}
              <span v-if="contact.email">· {{ contact.email }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Button variant="ghost" size="sm" @click="handleEdit(contact)">
              <Pencil class="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="sm" @click="handleDelete(contact.id)">
              <Trash2 class="w-4 h-4 text-wolf-danger-text-v2" />
            </Button>
            <Button
              v-if="!contact.is_primary"
              variant="ghost"
              size="sm"
              @click="handleSetPrimary(contact.id)"
            >
              <Star class="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
```

- [ ] **Step 2: 验证编译**

```bash
npm run type-check
```

Expected: No TypeScript errors

- [ ] **Step 3: 提交**

```bash
git add src/components/panels/ContactsPanel.vue
git commit -m "feat: create ContactsPanel component"
```

---

## Task 8: ContactFormDialog 弹窗

**Files:**
- Create: `src/components/dialogs/ContactFormDialog.vue`

**Interfaces:**
- Consumes: `customerId: number`, `open: boolean`, `contact?: ContactResponse`
- Produces: ContactFormDialog component

- [ ] **Step 1: 创建 ContactFormDialog.vue**

```vue
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { handleApiError } from '@/utils/errorHandler'
import customerApi, { type ContactResponse, type ContactCreate, type ContactUpdate } from '@/api/customer'

const props = defineProps<{
  customerId: number
  open: boolean
  contact?: ContactResponse | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'success': []
}>()

const isEdit = computed(() => !!props.contact)

const schema = toTypedSchema(
  z.object({
    name: z.string().min(1, '请输入姓名').max(50, '姓名不能超过50字'),
    gender: z.enum(['男', '女']).optional(),
    position: z.string().max(50, '职位不能超过50字').optional(),
    is_decision_maker: z.boolean().optional(),
    mobile: z.string().min(1, '请输入手机号').regex(/^1[3-9]\d{9}$/, '请输入正确的手机号'),
    email: z.string().email('请输入正确的邮箱').optional().or(z.literal('')),
    wechat_id: z.string().max(50, '微信号不能超过50字').optional()
  })
)

const { handleSubmit, resetForm, values, setValues } = useForm({
  validationSchema: schema,
  initialValues: {
    name: '',
    gender: undefined,
    position: '',
    is_decision_maker: false,
    mobile: '',
    email: '',
    wechat_id: ''
  }
})

const submitting = ref(false)

const onSubmit = handleSubmit(async (values) => {
  submitting.value = true
  try {
    const data: ContactCreate | ContactUpdate = {
      name: values.name,
      gender: values.gender,
      position: values.position || null,
      is_decision_maker: values.is_decision_maker || false,
      mobile: values.mobile,
      email: values.email || null,
      wechat_id: values.wechat_id || null
    }

    if (isEdit.value && props.contact) {
      await customerApi.updateContact(props.contact.id, data)
      toast.success('联系人更新成功')
    } else {
      await customerApi.createContact(props.customerId, data as ContactCreate)
      toast.success('联系人创建成功')
    }

    emit('update:open', false)
    emit('success')
    resetForm()
  } catch (error) {
    handleApiError(error, isEdit.value ? '更新联系人' : '创建联系人')
  } finally {
    submitting.value = false
  }
})

watch(() => props.open, (open) => {
  if (open && props.contact) {
    setValues({
      name: props.contact.name,
      gender: props.contact.gender === 1 ? '男' : props.contact.gender === 0 ? '女' : undefined,
      position: props.contact.position || '',
      is_decision_maker: props.contact.is_decision_maker,
      mobile: props.contact.mobile,
      email: props.contact.email || '',
      wechat_id: props.contact.wechat_id || ''
    })
  } else if (open) {
    resetForm()
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogContent class="sm:max-w-[500px]">
      <DialogHeader>
        <DialogTitle>{{ isEdit ? '编辑联系人' : '新建联系人' }}</DialogTitle>
      </DialogHeader>

      <form @submit="onSubmit" class="grid gap-4 py-4">
        <div class="grid gap-2">
          <Label for="name">姓名 <span class="text-wolf-danger-text-v2">*</span></Label>
          <Input id="name" v-model="values.name" placeholder="请输入姓名" />
        </div>

        <div class="grid gap-2">
          <Label for="gender">性别</Label>
          <div class="flex gap-4">
            <label class="flex items-center gap-2">
              <input type="radio" v-model="values.gender" value="男" />
              <span>男</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="radio" v-model="values.gender" value="女" />
              <span>女</span>
            </label>
          </div>
        </div>

        <div class="grid gap-2">
          <Label for="position">职位</Label>
          <Input id="position" v-model="values.position" placeholder="请输入职位" />
        </div>

        <div class="flex items-center gap-2">
          <Switch id="is_decision_maker" v-model="values.is_decision_maker" />
          <Label for="is_decision_maker">是否决策者</Label>
        </div>

        <div class="grid gap-2">
          <Label for="mobile">手机号 <span class="text-wolf-danger-text-v2">*</span></Label>
          <Input id="mobile" v-model="values.mobile" placeholder="请输入手机号" />
        </div>

        <div class="grid gap-2">
          <Label for="email">邮箱</Label>
          <Input id="email" type="email" v-model="values.email" placeholder="请输入邮箱" />
        </div>

        <div class="grid gap-2">
          <Label for="wechat_id">微信号</Label>
          <Input id="wechat_id" v-model="values.wechat_id" placeholder="请输入微信号" />
        </div>
      </form>

      <DialogFooter>
        <Button variant="outline" @click="$emit('update:open', false)">取消</Button>
        <Button :disabled="submitting" @click="onSubmit">
          {{ submitting ? '提交中...' : '确定' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
```

- [ ] **Step 2: 验证编译**

```bash
npm run type-check
```

Expected: No TypeScript errors

- [ ] **Step 3: 提交**

```bash
git add src/components/dialogs/ContactFormDialog.vue
git commit -m "feat: create ContactFormDialog with VeeValidate + Zod"
```

---

## Task 9: OpportunitiesPanel 面板

**Files:**
- Create: `src/components/panels/OpportunitiesPanel.vue`

**Interfaces:**
- Consumes: `customerId: number`, `opportunities: OpportunityListResponse[]`
- Produces: OpportunitiesPanel component

- [ ] **Step 1: 创建 OpportunitiesPanel.vue**

```vue
<script setup lang="ts">
import { Plus, ExternalLink } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/StatusBadge.vue'
import type { OpportunityListResponse } from '@/api/opportunity'

interface Props {
  customerId: number
  opportunities: OpportunityListResponse[]
}

defineProps<Props>()

const emit = defineEmits<{
  'add': []
}>()

const router = useRouter()

const handleAdd = (): void => {
  emit('add')
}

const handleView = (opportunityId: number): void => {
  router.push(`/opportunities/${opportunityId}`)
}

const formatCurrency = (amount: number): string => {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0
  }).format(amount)
}

const formatDate = (dateStr: string): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <Card class="opportunities-panel">
    <CardHeader class="p-4 border-b border-wolf-border-light-v2 flex flex-row items-center justify-between">
      <h3 class="text-sm font-semibold text-wolf-text-primary-v2">商机</h3>
      <Button size="sm" @click="handleAdd">
        <Plus class="w-4 h-4 mr-1" />
        新建商机
      </Button>
    </CardHeader>
    <CardContent class="p-0">
      <div v-if="opportunities.length === 0" class="p-8 text-center text-wolf-text-tertiary-v2">
        暂无商机
      </div>
      <div v-else class="divide-y divide-wolf-border-light-v2">
        <div
          v-for="opportunity in opportunities"
          :key="opportunity.id"
          class="p-4 flex items-center justify-between hover:bg-wolf-bg-hover-v2 transition-colors cursor-pointer"
          @click="handleView(opportunity.id)"
        >
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium text-wolf-text-primary-v2">{{ opportunity.opportunity_name }}</span>
              <StatusBadge :status="opportunity.status.toString()" />
            </div>
            <div class="text-sm text-wolf-text-tertiary-v2 mt-1">
              {{ formatCurrency(opportunity.total_amount) }} · {{ opportunity.stage_info?.stage_name || '-' }}
              · 预计成交: {{ formatDate(opportunity.expected_closing_date) }}
            </div>
          </div>
          <Button variant="ghost" size="sm" @click.stop="handleView(opportunity.id)">
            <ExternalLink class="w-4 h-4" />
          </Button>
        </div>
      </div>
    </CardContent>
  </Card>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
```

- [ ] **Step 2: 验证编译**

```bash
npm run type-check
```

Expected: No TypeScript errors

- [ ] **Step 3: 提交**

```bash
git add src/components/panels/OpportunitiesPanel.vue
git commit -m "feat: create OpportunitiesPanel component"
```

---

## Task 10-17: 简要说明

由于文档篇幅限制，Task 10-17 遵循相同模式：

- **Task 10-12**: 商机、合同表单弹窗（参考 Task 8 的 VeeValidate + Zod 模式）
- **Task 13**: 回款面板（数据展示，无弹窗）
- **Task 14-15**: 发票面板和表单弹窗
- **Task 16**: License 面板（整合部署信息 + 申请记录）
- **Task 17**: 整合到 CustomerDetailSheet

详细代码将在执行时根据具体 API 类型补充。