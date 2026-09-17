<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import procurementApi, {
  type ProcurementMethod,
  type ProcurementMethodCreate,
  type ProcurementMethodUpdate,
} from '@/api/procurement'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete, confirmDialog } from '@/utils/confirmDialog'
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

type ProcurementMethodRow = ProcurementMethod & {
  stage_templates?: readonly unknown[]
}

usePageTitle()

const route = useRoute()
const router = useRouter()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { isOwner } = useSettingsAccess()

const submittedSearch = ref('')
const methods = ref<ProcurementMethodRow[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)

const dialogOpen = ref(false)
const dialogSubmitting = ref(false)
const isEditMode = ref(false)
const selectedMethod = ref<ProcurementMethodRow | null>(null)

const canCreate = computed(() => isOwner.value || permissionStore.hasPermission('procurement_method:create'))
const canUpdate = computed(() => isOwner.value || permissionStore.hasPermission('procurement_method:update'))
const canDelete = computed(() => isOwner.value || permissionStore.hasPermission('procurement_method:delete'))

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
      .nullable(),
  }),
)

const { handleSubmit, resetForm } = useForm({
  validationSchema: procurementSchema,
  initialValues: {
    code: '',
    name: '',
    sort_order: 0,
    description: '',
  },
})

const displayedMethods = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  const sorted = methods.value.slice().sort((left, right) => left.sort_order - right.sort_order)
  if (query.length === 0) return sorted
  return sorted.filter((method) =>
    method.name.toLowerCase().includes(query) || method.code.toLowerCase().includes(query),
  )
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'name', label: '采购方式', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'stage_count', label: '阶段', column: true }),
  settingsListColumn({ key: 'is_active', label: '状态', column: true }),
])

const queryParam = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}

const loadMethods = async (): Promise<void> => {
  const requestId = ++listRequestId.value
  loading.value = true
  loadError.value = null
  try {
    const data = await procurementApi.getProcurementMethods()
    if (requestId !== listRequestId.value) return
    methods.value = Array.isArray(data) ? data : []
  } catch (error) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(error, '采购方式')
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
  }
}

const showCreateDialog = (): void => {
  isEditMode.value = false
  selectedMethod.value = null
  resetForm({
    values: {
      code: '',
      name: '',
      sort_order: 0,
      description: '',
    },
  })
  dialogOpen.value = true
}

const handleEdit = (record: ProcurementMethodRow): void => {
  isEditMode.value = true
  selectedMethod.value = record
  resetForm({
    values: {
      code: record.code,
      name: record.name,
      sort_order: record.sort_order,
      description: record.description ?? '',
    },
  })
  dialogOpen.value = true
}

const onSubmit = handleSubmit(async (formValues) => {
  dialogSubmitting.value = true
  try {
    if (isEditMode.value && selectedMethod.value) {
      const updateData: ProcurementMethodUpdate = {
        name: formValues.name,
        sort_order: formValues.sort_order,
      }
      if (formValues.description !== undefined && formValues.description !== null && formValues.description.length > 0) {
        updateData.description = formValues.description
      }
      await procurementApi.updateProcurementMethod(selectedMethod.value.id, updateData)
      toast.success('采购方式更新成功')
    } else {
      const createData: ProcurementMethodCreate = {
        code: formValues.code,
        name: formValues.name,
        sort_order: formValues.sort_order,
      }
      if (formValues.description !== undefined && formValues.description !== null && formValues.description.length > 0) {
        createData.description = formValues.description
      }
      await procurementApi.createProcurementMethod(createData)
      toast.success('采购方式创建成功')
    }

    dialogOpen.value = false
    void loadMethods()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新采购方式' : '创建采购方式')
  } finally {
    dialogSubmitting.value = false
  }
})

const handleDelete = async (record: ProcurementMethodRow): Promise<void> => {
  const confirmed = await confirmDelete(`采购方式"${record.name}"`)
  if (!confirmed) return

  try {
    await procurementApi.deleteProcurementMethod(record.id)
    toast.success('采购方式删除成功')
    void loadMethods()
  } catch (error) {
    handleApiError(error, '删除采购方式')
  }
}

const handleToggleActive = async (record: ProcurementMethodRow): Promise<void> => {
  const nextActive = record.is_active ? 0 : 1
  const action = nextActive === 1 ? '启用' : '停用'
  const confirmed = await confirmDialog(
    `确定要${action}采购方式"${record.name}"吗？`,
    `确认${action}`,
  )
  if (!confirmed) return

  try {
    await procurementApi.updateProcurementMethod(record.id, { is_active: nextActive })
    toast.success(`采购方式已${action}`)
    void loadMethods()
  } catch (error) {
    handleApiError(error, `${action}采购方式`)
  }
}

const openStageTemplates = (record: ProcurementMethodRow): void => {
  void router.push('/settings/procurement-methods/' + record.id + '/stages')
}

const asMethodHandler = (handler: (row: ProcurementMethodRow) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as ProcurementMethodRow) }
}

const getRowActions = (row: ProcurementMethodRow): TableRowActionSet => {
  return {
    primaryActions: [{
      label: '阶段模板',
      desktopPrimary: true,
      visible: true,
      handler: asMethodHandler(openStageTemplates),
    }],
    secondaryActions: [
      { id: 'edit', label: '编辑', visible: canUpdate.value, handler: asMethodHandler(handleEdit) },
      {
        label: row.is_active ? '停用' : '启用',
        visible: canUpdate.value,
        handler: asMethodHandler((method) => { void handleToggleActive(method) }),
      },
      {
        id: 'delete',
        label: '删除',
        visible: canDelete.value,
        destructive: true,
        risk: 'destructive',
        handler: asMethodHandler((method) => { void handleDelete(method) }),
      },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canCreate],
  actions: () => [{
    id: 'create-method',
    label: '新建采购方式',
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

watch(() => [route.query['action'], route.query['id'], methods.value.length, canUpdate.value] as const, ([action, id]) => {
  const actionValue = queryParam(action)
  const idValue = queryParam(id)
  if (actionValue === 'edit' && idValue !== '' && canUpdate.value) {
    const method = methods.value.find(item => String(item.id) === idValue)
    if (method !== undefined) handleEdit(method)
  }
}, { immediate: true })

watch(() => teamStore.currentTeam?.id, () => {
  void loadMethods()
}, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="采购方式管理" description="维护采购方式和阶段模板。短任务继续用对话框。">
    <DataTable
      :fields="fields"
      :data="displayedMethods"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedMethods.length, 1)"
      :total="displayedMethods.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无采购方式"
      :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
      :get-row-actions="getRowActions"
      mobile-title-key="name"
      :mobile-meta-keys="['code']"
      search-enabled
      :search="submittedSearch"
      search-placeholder="搜索方式名称、编码"
      :search-loading="loading"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @retry="loadMethods"
    >
      <template #cell-name="{ row }">
        <div class="font-medium text-wolf-text-primary">{{ row.name }}</div>
        <div class="mt-1 text-xs text-muted-foreground">{{ row.code }}</div>
      </template>
      <template #cell-stage_count="{ row }">
        {{ Array.isArray(row.stage_templates) ? row.stage_templates.length : 0 }}
      </template>
      <template #cell-is_active="{ row }">
        <Badge :variant="row.is_active ? 'default' : 'secondary'">
          {{ row.is_active ? '启用' : '停用' }}
        </Badge>
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>

  <Dialog v-model:open="dialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ isEditMode ? '编辑采购方式' : '新增采购方式' }}</DialogTitle>
        <DialogDescription>
          {{ isEditMode ? '修改采购方式信息' : '创建新的采购方式' }}
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
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
