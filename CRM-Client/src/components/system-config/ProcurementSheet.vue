<script setup lang="ts">
/**
 * ProcurementSheet.vue - 采购配置管理 Sheet
 *
 * 功能：
 * - 展示采购方式列表（ListCard）
 * - 搜索采购方式
 * - 新建/编辑采购方式（Dialog）
 * - 删除采购方式
 * - AI 创建采购方式
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件
 * - V2 Design Tokens
 * - z-index: Sheet z-[200], Dialog z-[1000]
 */
import { ref, computed, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Search, Plus, Pencil, Trash2, Wand2 } from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ListCard } from '@/components/crmwolf'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete } from '@/utils/confirmDialog'
import procurementApi, {
  type ProcurementMethod,
  type ProcurementMethodCreate,
  type ProcurementMethodUpdate
} from '@/api/procurement'

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== State ====================
const loading = ref(false)
const procurementMethods = ref<ProcurementMethod[]>([])
const searchText = ref('')
const filterStatus = ref('all')
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 新建/编辑 Dialog
const dialogOpen = ref(false)
const dialogSubmitting = ref(false)
const isEditMode = ref(false)
const selectedMethod = ref<ProcurementMethod | null>(null)

// ==================== Zod Schema ====================
const procurementSchema = toTypedSchema(
  z.object({
    code: z.string()
      .min(1, '请输入编码')
      .max(50, '编码不能超过50字符')
      .regex(/^[A-Z_]+$/, '编码只能包含大写字母和下划线'),
    name: z.string()
      .min(1, '请输入名称')
      .max(50, '名称不能超过50字符'),
    sort_order: z.number()
      .min(0, '排序序号不能小于0')
      .default(0),
    description: z.string()
      .max(200, '描述不能超过200字符')
      .optional()
      .nullable()
  })
)

// VeeValidate form setup
const { handleSubmit, resetForm } = useForm({
  validationSchema: procurementSchema,
  initialValues: {
    code: '',
    name: '',
    sort_order: 0,
    description: ''
  }
})

// ==================== Computed ====================
const filteredMethods = computed(() => {
  let filtered = procurementMethods.value

  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    filtered = filtered.filter(method =>
      method.name.toLowerCase().includes(search) ||
      method.code.toLowerCase().includes(search)
    )
  }

  if (filterStatus.value !== 'all') {
    filtered = filtered.filter(method =>
      filterStatus.value === 'true' ? method.is_active : !method.is_active
    )
  }

  return filtered.sort((a, b) => a.sort_order - b.sort_order)
})

const listTitle = computed(() => `采购方式列表（${filteredMethods.value.length}）`)

// ==================== API Methods ====================
const fetchProcurementMethods = async (): Promise<void> => {
  loading.value = true
  try {
    const data = await procurementApi.getProcurementMethods()
    procurementMethods.value = data || []
    pagination.value.total = procurementMethods.value.length
  } catch (error) {
    handleApiError(error, '获取采购方式')
  } finally {
    loading.value = false
  }
}

// ==================== CRUD Actions ====================
const showCreateDialog = (): void => {
  isEditMode.value = false
  selectedMethod.value = null
  resetForm({
    values: {
      code: '',
      name: '',
      sort_order: 0,
      description: ''
    }
  })
  dialogOpen.value = true
}

const handleEdit = (record: ProcurementMethod): void => {
  isEditMode.value = true
  selectedMethod.value = record
  resetForm({
    values: {
      code: record.code,
      name: record.name,
      sort_order: record.sort_order,
      description: record.description ?? ''
    }
  })
  dialogOpen.value = true
}

const onSubmit = handleSubmit(async (formValues) => {
  dialogSubmitting.value = true
  try {
    if (isEditMode.value && selectedMethod.value) {
      const updateData: ProcurementMethodUpdate = {
        name: formValues.name,
        sort_order: formValues.sort_order
      }
      if (formValues.description) updateData.description = formValues.description
      await procurementApi.updateProcurementMethod(selectedMethod.value.id, updateData)
      toast.success('采购方式更新成功')
    } else {
      const createData: ProcurementMethodCreate = {
        code: formValues.code,
        name: formValues.name,
        sort_order: formValues.sort_order
      }
      if (formValues.description) createData.description = formValues.description
      await procurementApi.createProcurementMethod(createData)
      toast.success('采购方式创建成功')
    }

    dialogOpen.value = false
    fetchProcurementMethods()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新采购方式' : '创建采购方式')
  } finally {
    dialogSubmitting.value = false
  }
})

const handleDelete = async (record: ProcurementMethod): Promise<void> => {
  const confirmed = await confirmDelete(`采购方式"${record.name}"`)
  if (!confirmed) return

  try {
    await procurementApi.deleteProcurementMethod(record.id)
    toast.success('采购方式删除成功')
    fetchProcurementMethods()
  } catch (error) {
    handleApiError(error, '删除采购方式')
  }
}

const handleAICreate = (): void => {
  // TODO: Open AI creation dialog
  toast.info('AI 创建采购方式功能开发中')
}

// ==================== Lifecycle ====================
watch(() => props.open, (open) => {
  if (open) {
    fetchProcurementMethods()
  }
})

// ==================== Helper Functions ====================
function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent>
      <SheetHeader class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">采购方式管理</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">配置采购方式与阶段模板</SheetDescription>
      </SheetHeader>
      <ScrollArea class="h-full">
        <!-- 搜索/操作栏 -->
        <div class="p-4 border-b space-y-4">
          <div class="flex items-center gap-4">
            <div class="relative flex-1">
              <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                v-model="searchText"
                placeholder="搜索方式名称、编码"
                class="pl-10"
              />
            </div>
            <Button @click="handleAICreate">
              <Wand2 class="w-4 h-4 mr-2" />
              AI 创建
            </Button>
            <Button @click="showCreateDialog">
              <Plus class="w-4 h-4 mr-2" />
              新增采购方式
            </Button>
          </div>

          <!-- 筛选栏 -->
          <div class="flex items-center gap-4">
            <Select v-model="filterStatus">
              <SelectTrigger class="w-[120px]">
                <SelectValue placeholder="筛选状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="true">启用</SelectItem>
                <SelectItem value="false">停用</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <!-- 列表区域 -->
        <div class="p-4">
          <ListCard
            :title="listTitle"
            :items="filteredMethods"
            :loading="loading"
            empty-text="暂无采购方式"
          >
            <template #itemMain="{ item }">
              <div class="font-medium text-wolf-text-primary">{{ item.name }}</div>
              <div class="mt-1 text-xs text-muted-foreground">
                {{ item.code }} · 排序 {{ item.sort_order }} · {{ formatDate(item.created_time) }}
              </div>
              <div v-if="item.description" class="mt-1 text-sm text-muted-foreground">
                {{ item.description }}
              </div>
            </template>

            <template #itemBadges="{ item }">
              <Badge :variant="item.is_active ? 'default' : 'secondary'">
                {{ item.is_active ? '启用' : '停用' }}
              </Badge>
            </template>

            <template #itemActions="{ item }">
              <Button variant="ghost" size="icon" title="编辑" @click="handleEdit(item)">
                <Pencil class="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="删除"
                class="text-destructive hover:text-destructive"
                @click="handleDelete(item)"
              >
                <Trash2 class="h-4 w-4" />
              </Button>
            </template>
          </ListCard>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>

  <!-- 新建采购方式 Dialog (z-[1000]) -->
  <Dialog v-model:open="dialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ isEditMode ? '编辑采购方式' : '新增采购方式' }}</DialogTitle>
        <DialogDescription>
          {{ isEditMode ? '修改采购方式信息' : '创建新的采购方式' }}
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- 编码 -->
        <FormField v-slot="{ componentField }" name="code">
          <FormItem>
            <FormLabel>编码 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                placeholder="如：PUBLIC_BIDDING"
                :disabled="isEditMode"
                class="uppercase"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- 名称 -->
        <FormField v-slot="{ componentField }" name="name">
          <FormItem>
            <FormLabel>名称 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                placeholder="请输入采购方式名称"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- 排序序号 -->
        <FormField v-slot="{ componentField }" name="sort_order">
          <FormItem>
            <FormLabel>排序序号 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                type="number"
                placeholder="请输入排序序号"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- 描述 -->
        <FormField v-slot="{ componentField }" name="description">
          <FormItem>
            <FormLabel>描述</FormLabel>
            <FormControl>
              <Textarea
                v-bind="componentField as unknown as Record<string, unknown>"
                placeholder="请输入描述"
                :rows="3"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <DialogFooter class="pt-4 border-t">
          <Button
            type="button"
            variant="outline"
            @click="dialogOpen = false"
          >
            取消
          </Button>
          <Button type="submit" :loading="dialogSubmitting">
            {{ dialogSubmitting ? '提交中...' : '确定' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
}
</style>
