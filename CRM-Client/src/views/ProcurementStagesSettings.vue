<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import { Plus } from 'lucide-vue-next'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Button, DataTable, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Input, TableRowActions, Textarea } from '@/components/crmwolf'
import { Badge } from '@/components/ui/badge'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import ErrorState from '@/components/ErrorState.vue'
import procurementApi, { type ProcurementMethodWithStages, type ProcurementStageTemplate, type ProcurementStageTemplateCreate, type ProcurementStageTemplateUpdate } from '@/api/procurement'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete } from '@/utils/confirmDialog'
import { usePermissionStore } from '@/stores/permissions'
import { useTopBarRegistration } from '@/composables/useTopBarRegistration'
import { useHeaderStore } from '@/stores/header'
import type { ActionConfig, TableRowActionSet } from '@/components/crmwolf'
import { defineListFields } from '@/components/crmwolf/listFieldCatalog'
import type { ListFieldDefinition } from '@/components/crmwolf/listFieldCatalog'
import { settingsListColumn } from '@/views/settings/settingsListCatalog'
import { toFeedbackError } from '@/types/feedback'
import type { FeedbackError } from '@/types/feedback'
import SettingsContent from '@/views/settings/SettingsContent.vue'

const route = useRoute()
const headerStore = useHeaderStore()
headerStore.setBack(true, '/settings/procurement-methods')
const permissionStore = usePermissionStore()
const { canAccess } = useSettingsAccess()
const procurementSettings = getSettingsNavigationItem('procurement')
const methodId = computed(() => {
  const raw = route.params['methodId']
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
})
const hasAccess = computed(() => procurementSettings !== undefined && canAccess(procurementSettings))
const canCreate = computed(() => permissionStore.hasPermission('procurement_stage:create'))
const canUpdate = computed(() => permissionStore.hasPermission('procurement_stage:update'))
const canDelete = computed(() => permissionStore.hasPermission('procurement_stage:delete'))
const method = ref<ProcurementMethodWithStages | null>(null)
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const dialogOpen = ref(false)
const submitting = ref(false)
const editingStage = ref<ProcurementStageTemplate | null>(null)

const stageSchema = toTypedSchema(z.object({
  template_code: z.string().trim().min(1, '请输入阶段编码').max(50, '编码不能超过50字符').regex(/^[A-Z0-9_]+$/, '编码只能包含大写字母、数字和下划线'),
  stage_name: z.string().trim().min(1, '请输入阶段名称').max(50, '阶段名称不能超过50字符'),
  win_probability: z.number().min(0, '赢率不能小于0').max(100, '赢率不能超过100'),
  sort_order: z.number().int('排序必须是整数').min(0, '排序不能小于0'),
  is_default_start: z.boolean(),
  can_skip: z.boolean(),
  description: z.string().max(200, '描述不能超过200字符').optional(),
}))
const { handleSubmit, resetForm } = useForm({
  validationSchema: stageSchema,
  initialValues: { template_code: '', stage_name: '', win_probability: 0, sort_order: 0, is_default_start: false, can_skip: false, description: '' },
})

const displayedStages = computed(() => {
  if (method.value === null) return []
  return method.value.stage_templates.slice().sort((left, right) => left.sort_order - right.sort_order)
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'stage_name', label: '阶段', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'template_code', label: '编码', column: true }),
  settingsListColumn({ key: 'win_probability', label: '赢率', column: true }),
  settingsListColumn({ key: 'sort_order', label: '排序', column: true }),
  settingsListColumn({ key: 'is_default_start', label: '默认起点', column: true }),
  settingsListColumn({ key: 'can_skip', label: '可跳过', column: true }),
])

const loadMethod = async (): Promise<void> => {
  if (methodId.value === null) return
  loading.value = true
  loadError.value = null
  try {
    method.value = await procurementApi.getProcurementMethod(methodId.value)
  } catch (error: unknown) {
    loadError.value = toFeedbackError(error, '采购阶段模板')
    handleApiError(error, '获取采购阶段模板')
  } finally {
    loading.value = false
  }
}

const showCreate = (): void => {
  editingStage.value = null
  resetForm({ values: { template_code: '', stage_name: '', win_probability: 0, sort_order: method.value?.stage_templates.length ?? 0, is_default_start: false, can_skip: false, description: '' } })
  dialogOpen.value = true
}

const showEdit = (stage: ProcurementStageTemplate): void => {
  editingStage.value = stage
  resetForm({ values: { template_code: stage.template_code, stage_name: stage.stage_name, win_probability: stage.win_probability, sort_order: stage.sort_order, is_default_start: stage.is_default_start === 1, can_skip: stage.can_skip === 1, description: stage.description ?? '' } })
  dialogOpen.value = true
}

const submit = handleSubmit(async (values) => {
  if (methodId.value === null) return
  submitting.value = true
  try {
    if (editingStage.value !== null) {
      const data: ProcurementStageTemplateUpdate = { template_code: values.template_code, stage_name: values.stage_name, win_probability: values.win_probability, sort_order: values.sort_order, is_default_start: values.is_default_start ? 1 : 0, can_skip: values.can_skip ? 1 : 0, description: values.description ?? '' }
      await procurementApi.updateStageTemplate(editingStage.value.id, data)
      toast.success('阶段模板已更新')
    } else {
      const data: ProcurementStageTemplateCreate = { procurement_method_id: methodId.value, template_code: values.template_code, stage_name: values.stage_name, win_probability: values.win_probability, sort_order: values.sort_order, is_default_start: values.is_default_start ? 1 : 0, can_skip: values.can_skip ? 1 : 0, description: values.description ?? '' }
      await procurementApi.createStageTemplate(data)
      toast.success('阶段模板已创建')
    }
    dialogOpen.value = false
    await loadMethod()
  } catch (error: unknown) {
    handleApiError(error, editingStage.value === null ? '创建阶段模板' : '更新阶段模板')
  } finally {
    submitting.value = false
  }
})

const removeStage = async (stage: ProcurementStageTemplate): Promise<void> => {
  if (!(await confirmDelete(`阶段模板“${stage.stage_name}”`))) return
  try {
    await procurementApi.deleteStageTemplate(stage.id)
    toast.success('阶段模板已删除')
    await loadMethod()
  } catch (error: unknown) {
    handleApiError(error, '删除阶段模板')
  }
}

const asStageHandler = (handler: (row: ProcurementStageTemplate) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as ProcurementStageTemplate) }
}

const getRowActions = (_row: ProcurementStageTemplate): TableRowActionSet => {
  return {
    primaryActions: [{
      id: 'edit',
      label: '编辑',
      desktopPrimary: true,
      visible: canUpdate.value,
      handler: asStageHandler(showEdit),
    }],
    secondaryActions: [
      { id: 'delete', label: '删除', destructive: true, risk: 'destructive', visible: canDelete.value, handler: asStageHandler((stage) => { void removeStage(stage) }) },
    ],
  }
}

onMounted(() => { void loadMethod() })

useTopBarRegistration({
  actionDeps: [hasAccess, canCreate, method],
  actions: () => [{
    id: 'create-stage',
    label: '新增阶段',
    type: 'primary',
    icon: Plus,
    visible: hasAccess.value && canCreate.value && method.value !== null,
    handler: showCreate,
  }],
})
</script>

<template>
  <SettingsContent ariaLabel="采购阶段模板" :description="`配置采购方式“${method?.name ?? '未找到'}”的阶段顺序、赢率和跳过规则。`">
    <ErrorState v-if="!hasAccess" variant="forbidden" title="暂无访问权限" description="你没有访问采购阶段模板的权限。" />
    <ErrorState v-else-if="methodId === null" variant="error" title="采购方式不存在" description="请从采购方式管理页面选择有效的采购方式。" />
    <DataTable
      v-else
      :fields="fields"
      :data="displayedStages"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedStages.length, 1)"
      :total="displayedStages.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无阶段模板"
      empty-reason="not-created"
      :get-row-actions="getRowActions"
      mobile-title-key="stage_name"
      :mobile-meta-keys="['template_code']"
      @retry="loadMethod"
    >
      <template #cell-stage_name="{ row }">
        <div class="font-medium text-wolf-text-primary">{{ row.stage_name }}</div>
        <div v-if="row.description" class="mt-1 text-sm text-muted-foreground">{{ row.description }}</div>
      </template>
      <template #cell-template_code="{ row }">
        <Badge variant="outline">{{ row.template_code }}</Badge>
      </template>
      <template #cell-win_probability="{ row }">
        {{ row.win_probability }}%
      </template>
      <template #cell-sort_order="{ row }">
        {{ row.sort_order }}
      </template>
      <template #cell-is_default_start="{ row }">
        <Badge v-if="row.is_default_start === 1" variant="outline">默认起点</Badge>
        <span v-else class="text-muted-foreground">否</span>
      </template>
      <template #cell-can_skip="{ row }">
        <Badge v-if="row.can_skip === 1" variant="secondary">可跳过</Badge>
        <span v-else class="text-muted-foreground">否</span>
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>
  <Dialog v-model:open="dialogOpen">
    <DialogContent class="max-w-lg">
      <DialogHeader><DialogTitle>{{ editingStage === null ? '新增阶段模板' : '编辑阶段模板' }}</DialogTitle><DialogDescription>阶段编码创建后不可修改，避免影响已有商机引用。</DialogDescription></DialogHeader>
      <form class="space-y-4" @submit="submit">
        <FormField v-slot="{ componentField }" name="template_code"><FormItem><FormLabel>阶段编码</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" :disabled="editingStage !== null" placeholder="如：QUALIFICATION" /></FormControl><FormMessage /></FormItem></FormField>
        <FormField v-slot="{ componentField }" name="stage_name"><FormItem><FormLabel>阶段名称</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" placeholder="请输入阶段名称" /></FormControl><FormMessage /></FormItem></FormField>
        <div class="grid grid-cols-2 gap-4"><FormField v-slot="{ componentField }" name="win_probability"><FormItem><FormLabel>赢率（%）</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" type="number" /></FormControl><FormMessage /></FormItem></FormField><FormField v-slot="{ componentField }" name="sort_order"><FormItem><FormLabel>排序</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" type="number" /></FormControl><FormMessage /></FormItem></FormField></div>
        <FormField v-slot="{ value, handleChange }" name="is_default_start"><FormItem class="flex items-center justify-between rounded-lg border p-3"><FormLabel>默认起点</FormLabel><FormControl><Switch :model-value="value" @update:model-value="handleChange" /></FormControl></FormItem></FormField>
        <FormField v-slot="{ value, handleChange }" name="can_skip"><FormItem class="flex items-center justify-between rounded-lg border p-3"><FormLabel>允许跳过</FormLabel><FormControl><Switch :model-value="value" @update:model-value="handleChange" /></FormControl></FormItem></FormField>
        <FormField v-slot="{ componentField }" name="description"><FormItem><FormLabel>描述</FormLabel><FormControl><Textarea v-bind="componentField as unknown as Record<string, unknown>" :rows="3" placeholder="可选" /></FormControl><FormMessage /></FormItem></FormField>
        <DialogFooter><Button type="button" variant="outline" @click="dialogOpen = false">取消</Button><Button type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '保存' }}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
