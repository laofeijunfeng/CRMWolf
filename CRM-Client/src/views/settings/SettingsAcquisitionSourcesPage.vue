<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Plus } from 'lucide-vue-next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
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
import acquisitionSourceApi, {
  type AcquisitionSource,
  type AcquisitionSourceCreate,
  type AcquisitionSourceUpdate,
} from '@/api/acquisition-source'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog } from '@/utils/confirmDialog'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { usePageTitle } from '@/composables/usePageTitle'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { DataTable, TableRowActions } from '@/components/crmwolf'
import type { ActionConfig, TableRowActionSet } from '@/components/crmwolf'
import { defineListFields } from '@/components/crmwolf/listFieldCatalog'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import { settingsListColumn } from '@/views/settings/settingsListCatalog'
import { toFeedbackError } from '@/types/feedback'
import type { FeedbackError } from '@/types/feedback'
import SettingsContent from '@/views/settings/SettingsContent.vue'

usePageTitle()

const route = useRoute()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { isOwner } = useSettingsAccess()

const submittedSearch = ref('')
const sources = ref<AcquisitionSource[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)

const dialogOpen = ref(false)
const dialogSubmitting = ref(false)
const isEditMode = ref(false)
const selectedSource = ref<AcquisitionSource | null>(null)

const canCreate = computed(() => isOwner.value || permissionStore.hasPermission('acquisition_source:create'))
const canUpdate = computed(() => isOwner.value || permissionStore.hasPermission('acquisition_source:update'))

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

const displayedSources = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  const sorted = sources.value.slice().sort((left, right) => left.sort_order - right.sort_order)
  if (query.length === 0) return sorted
  return sorted.filter((source) => source.name.toLowerCase().includes(query))
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'name', label: '来源', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'reference_count', label: '引用', column: true }),
  settingsListColumn({ key: 'is_active', label: '状态', column: true }),
  settingsListColumn({ key: 'sort_order', label: '排序', column: true }),
])

const queryParam = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}

const loadSources = async (): Promise<void> => {
  const requestId = ++listRequestId.value
  loading.value = true
  loadError.value = null
  try {
    const data = await acquisitionSourceApi.list()
    if (requestId !== listRequestId.value) return
    sources.value = Array.isArray(data) ? data : []
  } catch (error) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(error, '获客来源')
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
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

const handleEdit = (record: AcquisitionSource): void => {
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
    void loadSources()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新获客来源' : '创建获客来源')
  } finally {
    dialogSubmitting.value = false
  }
})

const handleToggleActive = async (record: AcquisitionSource): Promise<void> => {
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
    void loadSources()
  } catch (error) {
    handleApiError(error, nextActive === 1 ? '启用获客来源' : '停用获客来源')
  }
}

const asSourceHandler = (handler: (row: AcquisitionSource) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as AcquisitionSource) }
}

const getRowActions = (row: AcquisitionSource): TableRowActionSet => {
  return {
    primaryActions: [{
      label: row.is_active ? '停用' : '启用',
      desktopPrimary: true,
      visible: canUpdate.value,
      handler: asSourceHandler((source) => { void handleToggleActive(source) }),
    }],
    secondaryActions: [
      { id: 'edit', label: '编辑', visible: canUpdate.value, handler: asSourceHandler(handleEdit) },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canCreate],
  actions: () => [{
    id: 'create-source',
    label: '新建来源',
    type: 'primary',
    icon: Plus,
    visible: canCreate.value,
    handler: showCreateDialog,
  }],
})

const handleSearchApply = (value: string): void => {
  submittedSearch.value = value.trim()
}

const handleSearchClear = (): void => {
  submittedSearch.value = ''
}

watch(() => [route.query['action'], canCreate.value] as const, ([action]) => {
  if (queryParam(action) === 'create' && canCreate.value) {
    showCreateDialog()
  }
}, { immediate: true })

watch(() => [route.query['action'], route.query['id'], sources.value.length, canUpdate.value] as const, ([action, id]) => {
  const actionValue = queryParam(action)
  const idValue = queryParam(id)
  if (actionValue === 'edit' && idValue !== '' && canUpdate.value) {
    const source = sources.value.find(item => item.public_id === idValue)
    if (source !== undefined) handleEdit(source)
  }
}, { immediate: true })

watch(() => teamStore.currentTeam?.id, () => {
  void loadSources()
}, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="获客来源" description="维护线索与客户共用的获客来源。短任务继续用对话框。">
    <DataTable
      :fields="fields"
      :data="displayedSources"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedSources.length, 1)"
      :total="displayedSources.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无获客来源"
      :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
      :get-row-actions="getRowActions"
      mobile-title-key="name"
      :mobile-meta-keys="['sort_order']"
      search-enabled
      :search="submittedSearch"
      search-placeholder="搜索来源名称"
      :search-loading="loading"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @retry="loadSources"
    >
      <template #cell-name="{ row }">
        <div class="font-medium text-wolf-text-primary">{{ row.name }}</div>
        <div v-if="row.is_system" class="mt-1">
          <Badge variant="outline">系统</Badge>
        </div>
      </template>
      <template #cell-reference_count="{ row }">
        {{ row.lead_count + row.customer_count }}
      </template>
      <template #cell-is_active="{ row }">
        <Badge :variant="row.is_active ? 'default' : 'secondary'">
          {{ row.is_active ? '启用' : '停用' }}
        </Badge>
      </template>
      <template #cell-sort_order="{ row }">
        {{ row.sort_order }}
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>

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
