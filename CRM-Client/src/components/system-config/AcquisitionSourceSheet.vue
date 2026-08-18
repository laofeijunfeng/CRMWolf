<script setup lang="ts">
/**
 * AcquisitionSourceSheet.vue - 获客来源配置 Sheet
 *
 * 功能：
 * - 展示获客来源列表（ListCard）
 * - 搜索 / 按启用态筛选
 * - 新建 / 改名 / 排序
 * - 启用 / 停用（不提供删除）
 */
import { computed, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Pencil, Plus, Power, Search } from 'lucide-vue-next'
import {
  Sheet,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ListCard } from '@/components/crmwolf'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import acquisitionSourceApi, {
  type AcquisitionSource,
  type AcquisitionSourceCreate,
  type AcquisitionSourceUpdate,
} from '@/api/acquisition-source'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import { usePermissionStore } from '@/stores/permissions'

interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

interface AcquisitionSourceListItem extends AcquisitionSource {
  id: string
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const permissionStore = usePermissionStore()

const loading = ref(false)
const sources = ref<AcquisitionSource[]>([])
const searchText = ref('')
const filterStatus = ref('all')

const dialogOpen = ref(false)
const dialogSubmitting = ref(false)
const isEditMode = ref(false)
const selectedSource = ref<AcquisitionSource | null>(null)

const canCreate = computed(() => permissionStore.hasPermission('acquisition_source:create'))
const canUpdate = computed(() => permissionStore.hasPermission('acquisition_source:update'))

const sourceFormSchema = toTypedSchema(
  z.object({
    name: z.string()
      .trim()
      .min(1, '请输入获客来源名称')
      .max(50, '名称不能超过50个字符'),
    sort_order: z.number()
      .int('排序序号必须是整数')
      .min(0, '排序序号不能小于0')
      .optional(),
  }),
)

const { handleSubmit, resetForm } = useForm({
  validationSchema: sourceFormSchema,
  initialValues: {
    name: '',
    sort_order: undefined,
  },
})

const filteredSources = computed<AcquisitionSourceListItem[]>(() => {
  let filtered = sources.value

  if (searchText.value) {
    const search = searchText.value.toLowerCase()
    filtered = filtered.filter((source) => source.name.toLowerCase().includes(search))
  }

  if (filterStatus.value !== 'all') {
    filtered = filtered.filter((source) =>
      filterStatus.value === 'true' ? source.is_active : !source.is_active,
    )
  }

  return filtered
    .slice()
    .sort((left, right) => left.sort_order - right.sort_order)
    .map((source) => ({
      ...source,
      id: source.public_id,
    }))
})

const listTitle = computed(() => `获客来源列表（${filteredSources.value.length}）`)

const fetchSources = async (): Promise<void> => {
  loading.value = true
  try {
    sources.value = await acquisitionSourceApi.list()
  } catch (error) {
    handleApiError(error, '获取获客来源')
  } finally {
    loading.value = false
  }
}

const showCreateDialog = (): void => {
  isEditMode.value = false
  selectedSource.value = null
  resetForm({
    values: {
      name: '',
      sort_order: undefined,
    },
  })
  dialogOpen.value = true
}

const handleEdit = (record: AcquisitionSourceListItem): void => {
  isEditMode.value = true
  selectedSource.value = record
  resetForm({
    values: {
      name: record.name,
      sort_order: record.sort_order,
    },
  })
  dialogOpen.value = true
}

const onSubmit = handleSubmit(async (formValues) => {
  dialogSubmitting.value = true
  try {
    if (isEditMode.value && selectedSource.value) {
      const updateData: AcquisitionSourceUpdate = {
        name: formValues.name,
      }
      if (formValues.sort_order !== undefined) {
        updateData.sort_order = formValues.sort_order
      }
      await acquisitionSourceApi.update(selectedSource.value.public_id, updateData)
      toast.success('获客来源更新成功')
    } else {
      const createData: AcquisitionSourceCreate = {
        name: formValues.name,
      }
      if (formValues.sort_order !== undefined) {
        createData.sort_order = formValues.sort_order
      }
      await acquisitionSourceApi.create(createData)
      toast.success('获客来源创建成功')
    }

    dialogOpen.value = false
    await fetchSources()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新获客来源' : '创建获客来源')
  } finally {
    dialogSubmitting.value = false
  }
})

const handleToggleActive = async (record: AcquisitionSourceListItem): Promise<void> => {
  const nextActive = record.is_active ? 0 : 1
  if (nextActive === 0) {
    const confirmed = await confirmDialog(
      `停用后，新建线索和客户时将不再显示「${record.name}」。已有记录不受影响。`,
      '停用获客来源',
    )
    if (!confirmed) return
  }

  try {
    await acquisitionSourceApi.update(record.public_id, { is_active: nextActive })
    toast.success(nextActive === 1 ? '已启用' : '已停用')
    await fetchSources()
  } catch (error) {
    handleApiError(error, nextActive === 1 ? '启用获客来源' : '停用获客来源')
  }
}

watch(() => props.open, (open) => {
  if (open) {
    void fetchSources()
  }
})
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent>
      <SheetHeader class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">获客来源</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">
          配置线索与客户共用的获客渠道。来源只支持启用 / 停用，不支持删除。
        </SheetDescription>
      </SheetHeader>
      <ScrollArea class="h-full">
        <div class="p-4 border-b space-y-4">
          <div class="flex items-center gap-4">
            <div class="relative flex-1">
              <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                v-model="searchText"
                placeholder="搜索来源名称"
                class="pl-10"
              />
            </div>
            <Button v-if="canCreate" @click="showCreateDialog">
              <Plus class="w-4 h-4 mr-2" />
              新增获客来源
            </Button>
          </div>

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

        <div class="p-4">
          <ListCard
            :title="listTitle"
            :items="filteredSources"
            :loading="loading"
            empty-text="暂无获客来源"
          >
            <template #itemMain="{ item }">
              <div class="font-medium text-wolf-text-primary">{{ item.name }}</div>
              <div class="mt-1 text-xs text-muted-foreground">
                线索 {{ item.lead_count }} · 客户 {{ item.customer_count }} · 排序 {{ item.sort_order }}
              </div>
            </template>

            <template #itemBadges="{ item }">
              <Badge v-if="item.is_system" variant="outline">系统</Badge>
              <Badge :variant="item.is_active ? 'default' : 'secondary'">
                {{ item.is_active ? '启用' : '停用' }}
              </Badge>
            </template>

            <template #itemActions="{ item }">
              <Button
                v-if="canUpdate"
                variant="ghost"
                size="icon"
                title="编辑"
                @click="handleEdit(item)"
              >
                <Pencil class="h-4 w-4" />
              </Button>
              <Button
                v-if="canUpdate"
                variant="ghost"
                size="icon"
                :title="item.is_active ? '停用' : '启用'"
                @click="handleToggleActive(item)"
              >
                <Power class="h-4 w-4" />
              </Button>
            </template>
          </ListCard>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>

  <Dialog v-model:open="dialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ isEditMode ? '编辑获客来源' : '新增获客来源' }}</DialogTitle>
        <DialogDescription>
          {{ isEditMode ? '修改名称或排序，历史记录会跟读最新名称。' : '创建后会生成对外 ID，编码由系统分配。' }}
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <FormField v-slot="{ componentField }" name="name">
          <FormItem>
            <FormLabel>名称 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                placeholder="请输入获客来源名称"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField v-slot="{ componentField }" name="sort_order">
          <FormItem>
            <FormLabel>排序序号</FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                type="number"
                placeholder="可选，留空由系统分配"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <DialogFooter class="pt-4 border-t">
          <Button type="button" variant="outline" @click="dialogOpen = false">
            取消
          </Button>
          <Button type="submit" :disabled="dialogSubmitting">
            {{ isEditMode ? '保存' : '创建' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
