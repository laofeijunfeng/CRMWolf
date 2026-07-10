# 线索表单迁移到 Dialog 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将线索创建/编辑从独立页面迁移到 Dialog 弹窗，使用 shadcn-vue Form 套件，符合 UI/UX Pro Max 最佳实践

**Architecture:** 创建统一的 LeadFormDialog 组件支持创建和编辑模式，使用 VeeValidate + Zod 进行表单验证，在 Leads.vue 中通过弹窗调用替代路由跳转

**Tech Stack:** Vue 3 + shadcn-vue + VeeValidate + Zod + TypeScript

## Global Constraints

- 必须使用 shadcn-vue 组件
- 必须使用 VeeValidate + Zod 进行表单验证
- Dialog 宽度：sm+: 600px（两列布局）
- Input 高度：xs: 44px（符合触摸目标），sm+: 32px
- 遵循 CRMWolf 设计系统规范（README.md §8.5）
- 使用 Design Tokens（variables-v2.scss）
- **UX CRITICAL**: Escape Route（未保存更改确认）
- **UX CRITICAL**: Focus Management（错误后自动聚焦）
- **UX HIGH**: Input Types（语义化输入类型）
- **UX HIGH**: Autofill Support（自动填充属性）

---

## File Structure

| 文件 | 类型 | 职责 |
|------|------|------|
| `src/schemas/lead-form.ts` | 创建 | Zod schema 定义 |
| `src/components/LeadFormDialog.vue` | 创建 | 线索表单弹窗组件（含 UX 优化） |
| `src/views/Leads.vue` | 修改 | 添加弹窗调用逻辑 |
| `src/views/LeadDetailSheet.vue` | 修改 | 使用新弹窗组件 |
| `src/router/index.ts` | 修改 | 删除旧路由 |
| `src/views/LeadForm.vue` | 删除 | 旧的页面组件 |

---

### Task 1: 安装 shadcn-vue Form 套件

**Files:**
- N/A（使用 CLI 工具）

**Interfaces:**
- Produces: FormField, FormItem, FormLabel, FormControl, FormMessage, FormDescription 组件

- [ ] **Step 1: 检查 shadcn-vue CLI 可用性**

Run: `cd CRM-Client && npx shadcn-vue@latest --help`
Expected: 显示 CLI 帮助信息

- [ ] **Step 2: 安装 Form 套件**

Run: `cd CRM-Client && npx shadcn-vue@latest add form`
Expected: 安装 FormField、FormItem、FormLabel、FormControl、FormMessage、FormDescription 组件

- [ ] **Step 3: 验证组件安装**

Run: `ls -la CRM-Client/src/components/ui/form/`
Expected: 看到 Form.vue, FormField.vue, FormItem.vue, FormLabel.vue, FormControl.vue, FormMessage.vue, FormDescription.vue

- [ ] **Step 4: 安装 AlertDialog（Escape Route 需要）**

Run: `cd CRM-Client && npx shadcn-vue@latest add alert-dialog`
Expected: 安装 AlertDialog 组件

- [ ] **Step 5: 提交**

```bash
cd CRM-Client && git add src/components/ui/form/ src/components/ui/alert-dialog/
git commit -m "feat: install shadcn-vue form and alert-dialog components"
```

---

### Task 2: 创建 Zod Schema

**Files:**
- Create: `CRM-Client/src/schemas/lead-form.ts`

**Interfaces:**
- Produces: `leadSchema` (Zod schema), `LeadForm` (TypeScript type)

- [ ] **Step 1: 创建 schema 文件**

```typescript
// CRM-Client/src/schemas/lead-form.ts
import { z } from 'zod'

export const leadSchema = z.object({
  lead_name: z.string()
    .min(2, '线索名称至少 2 个字符')
    .max(100, '线索名称最多 100 个字符'),

  source: z.enum([
    '线上注册', '市场活动', '客户推荐',
    '电话营销', '网站咨询', '展会', '其他'
  ], {
    required_error: '请选择线索来源'
  }),

  city: z.string()
    .min(2, '城市名称至少 2 个字符')
    .max(50, '城市名称最多 50 个字符'),

  company_scale: z.enum([
    '1-50人', '51-200人', '201-500人',
    '501-1000人', '1000人以上'
  ]).optional(),

  contact_name: z.string()
    .min(2, '联系人姓名至少 2 个字符')
    .max(50, '联系人姓名最多 50 个字符'),

  contact_phone: z.string()
    .regex(/^1[3-9]\d{9}$/, '请输入正确的手机号码'),

  remark: z.string()
    .max(500, '备注最多 500 个字符')
    .optional()
})

export type LeadForm = z.infer<typeof leadSchema>
```

- [ ] **Step 2: 提交**

```bash
cd CRM-Client && git add src/schemas/lead-form.ts
git commit -m "feat: add lead form Zod schema"
```

---

### Task 3: 创建 LeadFormDialog 组件（含 UX 优化）

**Files:**
- Create: `CRM-Client/src/components/LeadFormDialog.vue`

**Interfaces:**
- Consumes: `leadSchema` from Task 2
- Consumes: `leadApi` from `src/api/lead.ts`
- Produces: `LeadFormDialog` Vue component with props: `open`, `mode`, `leadId?`

**UX Requirements:**
- ✅ Escape Route: Confirm before dismissing with unsaved changes
- ✅ Focus Management: Auto-focus first invalid field on submit error
- ✅ Input Types: Use `type="tel"` for phone number
- ✅ Autofill Support: Add `autocomplete` attributes

- [ ] **Step 1: 创建组件文件（含完整 UX 优化）**

```vue
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { leadApi } from '@/api/lead'
import { leadSchema, type LeadForm } from '@/schemas/lead-form'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  leadId?: number
}

interface Emits {
  (e: 'update:open', value: boolean): void
  (e: 'success'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 状态
const submitting = ref(false)
const loading = ref(false)
const initialValues = ref<Partial<LeadForm>>({})
const isDirty = ref(false)
const showConfirmDialog = ref(false)

// VeeValidate 表单管理
const { setFocus, errors } = useForm()

// 计算属性
const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
})

// 选项配置
const sourceOptions = [
  { value: '线上注册', label: '线上注册' },
  { value: '市场活动', label: '市场活动' },
  { value: '客户推荐', label: '客户推荐' },
  { value: '电话营销', label: '电话营销' },
  { value: '网站咨询', label: '网站咨询' },
  { value: '展会', label: '展会' },
  { value: '其他', label: '其他' }
]

const companyScaleOptions = [
  { value: '1-50人', label: '1-50人' },
  { value: '51-200人', label: '51-200人' },
  { value: '201-500人', label: '201-500人' },
  { value: '501-1000人', label: '501-1000人' },
  { value: '1000人以上', label: '1000人以上' }
]

// 监听表单变化（UX 优化：Escape Route）
watch(initialValues, () => {
  isDirty.value = true
}, { deep: true })

// 编辑模式：加载线索详情
watch([() => props.open, () => props.leadId], async ([open, leadId]) => {
  if (open && props.mode === 'edit' && leadId) {
    loading.value = true
    try {
      const lead = await leadApi.getLeadDetail(leadId)
      initialValues.value = {
        lead_name: lead.lead_name,
        source: lead.source,
        city: lead.city,
        company_scale: lead.company_scale || undefined,
        contact_name: lead.contact_name,
        contact_phone: lead.contact_phone,
        remark: lead.remark || undefined
      }
      // 重置 dirty 状态
      setTimeout(() => {
        isDirty.value = false
      }, 100)
    } catch (error) {
      toast.error('加载线索详情失败')
      visible.value = false
    } finally {
      loading.value = false
    }
  }
}, { immediate: true })

// 表单提交处理
const handleSubmit = async (values: LeadForm) => {
  submitting.value = true
  try {
    if (props.mode === 'create') {
      await leadApi.createLead(values)
      toast.success('线索创建成功')
    } else {
      await leadApi.updateLead(props.leadId!, values)
      toast.success('线索更新成功')
    }
    
    isDirty.value = false
    visible.value = false
    emit('success')
  } catch (error) {
    toast.error(props.mode === 'create' ? '创建线索失败' : '更新线索失败')
    
    // UX 优化：Focus Management - 提交失败后自动聚焦第一个错误字段
    const firstErrorField = Object.keys(errors.value)[0]
    if (firstErrorField) {
      setFocus(firstErrorField)
    }
  } finally {
    submitting.value = false
  }
}

// 取消操作（UX 优化：Escape Route）
const handleCancel = () => {
  if (isDirty.value) {
    showConfirmDialog.value = true
  } else {
    visible.value = false
  }
}

// 确认放弃更改
const confirmCancel = () => {
  showConfirmDialog.value = false
  visible.value = false
}

// 继续编辑
const continueEditing = () => {
  showConfirmDialog.value = false
}
</script>

<template>
  <Dialog v-model:open="visible">
    <DialogContent class="sm:max-w-[600px]">
      <DialogHeader>
        <DialogTitle>{{ mode === 'create' ? '新建线索' : '编辑线索' }}</DialogTitle>
      </DialogHeader>

      <div v-if="loading" class="flex justify-center py-8">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>

      <Form
        v-else
        :schema="leadSchema"
        :initial-values="initialValues"
        @submit="handleSubmit"
      >
        <!-- 基本信息 Section -->
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- 线索名称 -->
            <FormField v-slot="{ componentField }" name="lead_name">
              <FormItem>
                <FormLabel>线索名称 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="organization"
                    class="h-11 sm:h-8"
                    placeholder="请输入线索名称"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 线索来源 -->
            <FormField v-slot="{ componentField }" name="source">
              <FormItem>
                <FormLabel>线索来源 *</FormLabel>
                <Select v-bind="componentField">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择来源" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in sourceOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 所在城市 -->
            <FormField v-slot="{ componentField }" name="city">
              <FormItem>
                <FormLabel>所在城市 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="address-level2"
                    class="h-11 sm:h-8"
                    placeholder="请输入城市"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 公司规模 -->
            <FormField v-slot="{ componentField }" name="company_scale">
              <FormItem>
                <FormLabel>公司规模</FormLabel>
                <Select v-bind="componentField">
                  <FormControl>
                    <SelectTrigger class="h-11 sm:h-8">
                      <SelectValue placeholder="请选择规模" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem
                      v-for="option in companyScaleOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 联系人姓名 -->
            <FormField v-slot="{ componentField }" name="contact_name">
              <FormItem>
                <FormLabel>联系人姓名 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    autocomplete="name"
                    class="h-11 sm:h-8"
                    placeholder="请输入联系人姓名"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>

            <!-- 联系电话（UX 优化：Input Types） -->
            <FormField v-slot="{ componentField }" name="contact_phone">
              <FormItem>
                <FormLabel>联系电话 *</FormLabel>
                <FormControl>
                  <Input
                    v-bind="componentField"
                    type="tel"
                    autocomplete="tel"
                    class="h-11 sm:h-8"
                    placeholder="请输入联系电话"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            </FormField>
          </div>

          <!-- 备注（全宽） -->
          <FormField v-slot="{ componentField }" name="remark">
            <FormItem>
              <FormLabel>备注</FormLabel>
              <FormControl>
                <Textarea
                  v-bind="componentField"
                  :rows="4"
                  placeholder="请输入备注信息（可选）"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>
        </div>

        <!-- DialogFooter 在 Form 内部 -->
        <DialogFooter class="mt-6 pt-4 border-t">
          <Button variant="outline" type="button" @click="handleCancel">
            取消
          </Button>
          <Button type="submit" :loading="submitting">
            {{ mode === 'create' ? '创建' : '保存' }}
          </Button>
        </DialogFooter>
      </Form>
    </DialogContent>
  </Dialog>

  <!-- UX 优化：Escape Route - 未保存更改确认对话框 -->
  <AlertDialog v-model:open="showConfirmDialog">
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>放弃更改？</AlertDialogTitle>
        <AlertDialogDescription>
          您有未保存的更改，确定要关闭吗？
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="continueEditing">
          继续编辑
        </AlertDialogCancel>
        <AlertDialogAction @click="confirmCancel">
          放弃更改
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
```

- [ ] **Step 2: 提交**

```bash
cd CRM-Client && git add src/components/LeadFormDialog.vue
git commit -m "feat: create LeadFormDialog component with UX optimizations (escape route, focus management, input types, autofill)"
```

---

### Task 4: 修改 Leads.vue（添加弹窗调用）

**Files:**
- Modify: `CRM-Client/src/views/Leads.vue`

**Interfaces:**
- Consumes: `LeadFormDialog` from Task 3
- Produces: 弹窗状态管理，TopBar 按钮改为打开弹窗

- [ ] **Step 1: 导入组件**

在 `<script setup>` 顶部添加：

```typescript
// 在第 168 行后添加
import LeadFormDialog from '@/components/LeadFormDialog.vue'
```

- [ ] **Step 2: 添加弹窗状态**

在第 193 行后添加：

```typescript
// 手动创建/编辑弹窗
const showLeadCreateDialog = ref(false)
const showLeadEditDialog = ref(false)
const selectedLeadId = ref<number | null>(null)
```

- [ ] **Step 3: 修改 TopBar 按钮逻辑**

将第 580-602 行替换为：

```typescript
// Phase 2: TopBar 按钮配置（使用 watchEffect 响应权限变化）
watchEffect(() => {
  headerStore.setActions([
    {
      id: 'ai-create',
      label: 'AI 创建线索',
      icon: WandSparkles,
      type: 'primary',
      handler: () => showAILeadCreate.value = true,
      visible: canCreateLead.value,
      ariaLabel: '使用 AI 智能创建新线索'
    },
    {
      id: 'manual-create',
      label: '手动创建',
      icon: Edit,
      type: 'default',
      handler: () => showLeadCreateDialog.value = true,  // ✅ 改为打开弹窗
      visible: canCreateLead.value,
      ariaLabel: '手动填写表单创建新线索'
    }
  ])
})
```

- [ ] **Step 4: 添加成功回调**

在第 455 行后添加：

```typescript
// 创建线索成功回调
const handleLeadCreated = () => {
  fetchLeadList()
}

// 编辑线索成功回调
const handleLeadUpdated = () => {
  fetchLeadList()
  sheetVisible.value = false
}

// 从详情抽屉打开编辑弹窗
const handleEditFromSheet = (leadId: number) => {
  selectedLeadId.value = leadId
  showLeadEditDialog.value = true
}
```

- [ ] **Step 5: 添加弹窗组件到模板**

在 `<template>` 中第 141 行前添加：

```vue
<!-- 手动创建线索弹窗 -->
<LeadFormDialog
  v-model:open="showLeadCreateDialog"
  mode="create"
  @success="handleLeadCreated"
/>

<!-- 编辑线索弹窗 -->
<LeadFormDialog
  v-model:open="showLeadEditDialog"
  mode="edit"
  :lead-id="selectedLeadId"
  @success="handleLeadUpdated"
/>
```

- [ ] **Step 6: 删除旧代码**

删除第 441 行：
```typescript
// ❌ 删除这一行
const showCreateModal = () => router.push('/leads/create')
```

- [ ] **Step 7: 提交**

```bash
cd CRM-Client && git add src/views/Leads.vue
git commit -m "feat: integrate LeadFormDialog in Leads.vue"
```

---

### Task 5: 修改 LeadDetailSheet.vue（使用新弹窗）

**Files:**
- Modify: `CRM-Client/src/views/LeadDetailSheet.vue`

**Interfaces:**
- Consumes: `LeadFormDialog` from Task 3

- [ ] **Step 1: 导入组件**

在第 23 行后添加：

```typescript
import LeadFormDialog from '@/components/LeadFormDialog.vue'
```

- [ ] **Step 2: 替换现有编辑 Dialog**

删除第 38-44 行的 Dialog 导入，只保留：

```typescript
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
```

在第 38 行后添加：

```typescript
import LeadFormDialog from '@/components/LeadFormDialog.vue'
```

- [ ] **Step 3: 修改编辑逻辑**

找到编辑相关的代码（约第 200-300 行），删除内部的编辑表单逻辑，改为：

```typescript
// 编辑线索弹窗
const showEditDialog = ref(false)

const handleEditSuccess = () => {
  emit('refresh')
}
```

- [ ] **Step 4: 修改模板**

在 `<template>` 中找到编辑 Dialog（约第 800-900 行），替换为：

```vue
<!-- 编辑线索弹窗 -->
<LeadFormDialog
  v-model:open="showEditDialog"
  mode="edit"
  :lead-id="leadId"
  @success="handleEditSuccess"
/>
```

- [ ] **Step 5: 提交**

```bash
cd CRM-Client && git add src/views/LeadDetailSheet.vue
git commit -m "feat: use LeadFormDialog in LeadDetailSheet"
```

---

### Task 6: 删除旧路由

**Files:**
- Modify: `CRM-Client/src/router/index.ts`

**Interfaces:**
- N/A

- [ ] **Step 1: 找到并删除线索创建路由**

删除类似以下代码：

```typescript
// ❌ 删除这两个路由定义
{
  path: '/leads/create',
  name: 'LeadCreate',
  component: () => import('@/views/LeadForm.vue')
},
{
  path: '/leads/:id/edit',
  name: 'LeadEdit',
  component: () => import('@/views/LeadForm.vue')
}
```

- [ ] **Step 2: 提交**

```bash
cd CRM-Client && git add src/router/index.ts
git commit -m "feat: remove LeadForm routes"
```

---

### Task 7: 删除 LeadForm.vue

**Files:**
- Delete: `CRM-Client/src/views/LeadForm.vue`

**Interfaces:**
- N/A

- [ ] **Step 1: 删除文件**

```bash
rm CRM-Client/src/views/LeadForm.vue
```

- [ ] **Step 2: 提交**

```bash
cd CRM-Client && git add -A
git commit -m "feat: remove deprecated LeadForm.vue"
```

---

### Task 8: 功能测试（含 UX 验证）

**Files:**
- N/A

**Interfaces:**
- 测试所有创建/编辑流程，验证 UX 优化

- [ ] **Step 1: 启动开发服务器**

Run: `cd CRM-Client && npm run dev`
Expected: 服务启动成功

- [ ] **Step 2: 测试手动创建线索**

1. 访问 `/leads` 页面
2. 点击 TopBar 的"手动创建"按钮
3. 验证弹窗打开，标题为"新建线索"
4. 填写表单并提交
5. 验证线索创建成功，弹窗关闭，列表刷新

- [ ] **Step 3: 测试编辑线索**

1. 点击某个线索的"查看详情"
2. 在详情抽屉中点击"编辑"按钮
3. 验证弹窗打开，标题为"编辑线索"
4. 修改表单并提交
5. 验证线索更新成功，弹窗关闭，列表刷新

- [ ] **Step 4: 测试表单验证**

1. 打开创建弹窗
2. 点击"创建"按钮（不填写任何内容）
3. 验证显示必填字段错误提示
4. 输入错误的手机号码
5. 验证显示手机号格式错误提示

- [ ] **Step 5: 测试 UX 优化 - Escape Route**

1. 打开创建弹窗
2. 填写部分字段（例如：线索名称）
3. 点击"取消"按钮
4. **验证显示确认对话框："放弃更改？"**
5. 点击"继续编辑"
6. 验证弹窗仍然打开
7. 点击"放弃更改"
8. 验证弹窗关闭

- [ ] **Step 6: 测试 UX 优化 - Focus Management**

1. 打开创建弹窗
2. 不填写任何字段，点击"创建"
3. 验证显示错误提示
4. **验证光标自动聚焦到第一个错误字段（线索名称）**

- [ ] **Step 7: 测试 UX 优化 - Input Types**

1. 打开创建弹窗
2. 点击"联系电话"字段
3. **验证移动端键盘显示数字键盘（`type="tel"` 生效）**

- [ ] **Step 8: 测试响应式布局**

1. 在 Chrome DevTools 中切换到移动端视图（375px）
2. 验证弹窗全宽显示
3. 验证 Input 高度为 44px
4. 验证布局为单列

5. 切换到桌面端视图（1024px）
6. 验证弹窗宽度为 600px
7. 验证 Input 高度为 32px
8. 验证布局为两列

- [ ] **Step 9: 提交最终版本**

```bash
cd CRM-Client && git add -A
git commit -m "feat: complete lead form migration to Dialog with UX optimizations"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ 创建线索：Task 3, Task 4
- ✅ 编辑线索：Task 3, Task 5
- ✅ 表单验证：Task 2（Zod schema）
- ✅ Dialog 宽度：Task 3（sm:max-w-[600px]）
- ✅ Input 高度：Task 3（h-11 sm:h-8）
- ✅ 路由删除：Task 6
- ✅ 旧文件删除：Task 7
- ✅ 测试：Task 8
- ✅ UX 优化 - Escape Route：Task 3（AlertDialog）
- ✅ UX 优化 - Focus Management：Task 3（setFocus）
- ✅ UX 优化 - Input Types：Task 3（type="tel"）
- ✅ UX 优化 - Autofill：Task 3（autocomplete）

**2. Placeholder scan:**
- ✅ 无 "TBD"、"TODO" 等占位符
- ✅ 所有代码步骤都有完整实现
- ✅ 所有测试步骤都有具体命令

**3. Type consistency:**
- ✅ `LeadForm` 类型在 Task 2 定义，Task 3 使用
- ✅ Props 接口在 Task 3 定义，Task 4、Task 5 使用
- ✅ API 调用使用现有的 `leadApi`

---

Plan complete and saved to `docs/superpowers/plans/2026-07-10-lead-form-dialog-migration.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 我为每个任务派发新的子代理，任务间审查，快速迭代

**2. Inline Execution** - 在当前会话中执行任务，批量执行带检查点

选择哪种方式？