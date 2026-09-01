<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { ArrowLeft, Plus, Pencil, Trash2 } from 'lucide-vue-next'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Badge, Button, Card, CardContent, CardHeader, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Input, ListCard, Textarea } from '@/components/crmwolf'
import { CardDescription, CardTitle } from '@/components/ui/card'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import ErrorState from '@/components/ErrorState.vue'
import { Skeleton } from '@/components/ui/skeleton'
import procurementApi, { type ProcurementMethodWithStages, type ProcurementStageTemplate, type ProcurementStageTemplateCreate, type ProcurementStageTemplateUpdate } from '@/api/procurement'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete } from '@/utils/confirmDialog'
import { usePermissionStore } from '@/stores/permissions'

const route = useRoute()
const router = useRouter()
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
const loadError = ref(false)
const dialogOpen = ref(false)
const submitting = ref(false)
const editingStage = ref<ProcurementStageTemplate | null>(null)

const stageSchema = toTypedSchema(z.object({
  stage_code: z.string().trim().min(1, '请输入阶段编码').max(50, '编码不能超过50字符').regex(/^[A-Z0-9_]+$/, '编码只能包含大写字母、数字和下划线'),
  stage_name: z.string().trim().min(1, '请输入阶段名称').max(50, '阶段名称不能超过50字符'),
  win_probability: z.number().min(0, '赢率不能小于0').max(100, '赢率不能超过100'),
  sort_order: z.number().int('排序必须是整数').min(0, '排序不能小于0'),
  is_default: z.boolean(),
  can_skip: z.boolean(),
  description: z.string().max(200, '描述不能超过200字符').optional(),
}))
const { handleSubmit, resetForm } = useForm({
  validationSchema: stageSchema,
  initialValues: { stage_code: '', stage_name: '', win_probability: 0, sort_order: 0, is_default: false, can_skip: false, description: '' },
})

const loadMethod = async (): Promise<void> => {
  if (methodId.value === null) return
  loading.value = true
  loadError.value = false
  try {
    method.value = await procurementApi.getProcurementMethod(methodId.value)
  } catch (error: unknown) {
    loadError.value = true
    handleApiError(error, '获取采购阶段模板')
  } finally {
    loading.value = false
  }
}
const showCreate = (): void => {
  editingStage.value = null
  resetForm({ values: { stage_code: '', stage_name: '', win_probability: 0, sort_order: method.value?.stage_templates.length ?? 0, is_default: false, can_skip: false, description: '' } })
  dialogOpen.value = true
}
const showEdit = (stage: ProcurementStageTemplate): void => {
  editingStage.value = stage
  resetForm({ values: { stage_code: stage.stage_code, stage_name: stage.stage_name, win_probability: stage.win_probability, sort_order: stage.sort_order, is_default: stage.is_default === 1, can_skip: stage.can_skip === 1, description: stage.description ?? '' } })
  dialogOpen.value = true
}
const submit = handleSubmit(async (values) => {
  if (methodId.value === null) return
  submitting.value = true
  try {
    if (editingStage.value !== null) {
      const data: ProcurementStageTemplateUpdate = { stage_name: values.stage_name, win_probability: values.win_probability, sort_order: values.sort_order, is_default: values.is_default ? 1 : 0, can_skip: values.can_skip ? 1 : 0, description: values.description ?? '' }
      await procurementApi.updateStageTemplate(editingStage.value.id, data)
      toast.success('阶段模板已更新')
    } else {
      const data: ProcurementStageTemplateCreate = { procurement_method_id: methodId.value, stage_code: values.stage_code, stage_name: values.stage_name, win_probability: values.win_probability, sort_order: values.sort_order, is_default: values.is_default ? 1 : 0, can_skip: values.can_skip ? 1 : 0, description: values.description ?? '' }
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

onMounted(() => { void loadMethod() })
</script>

<template>
  <main class="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6" aria-label="采购阶段模板">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="space-y-1">
        <p class="text-sm font-medium text-primary">系统设置 / 采购方式管理</p>
        <h1 class="text-2xl font-semibold tracking-tight">采购阶段模板</h1>
        <p class="text-sm text-muted-foreground">配置采购方式“{{ method?.name ?? '未找到' }}”的阶段顺序、赢率和跳过规则。</p>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" @click="router.push('/settings/procurement-methods')"><ArrowLeft class="mr-2 size-4" />返回采购方式</Button>
        <Button v-if="hasAccess && canCreate && method !== null" @click="showCreate"><Plus class="mr-2 size-4" />新增阶段</Button>
      </div>
    </div>
    <ErrorState v-if="!hasAccess" variant="forbidden" title="暂无访问权限" description="你没有访问采购阶段模板的权限。" />
    <ErrorState v-else-if="methodId === null" variant="error" title="采购方式不存在" description="请从采购方式管理页面选择有效的采购方式。" />
    <div v-else-if="loading" class="space-y-3" aria-label="正在加载采购阶段模板"><Skeleton v-for="index in 3" :key="index" class="h-20 w-full" /></div>
    <ErrorState v-else-if="loadError" variant="error" title="采购阶段模板加载失败" description="请检查网络后重试。"><template #action><Button variant="outline" @click="loadMethod">重试</Button></template></ErrorState>
    <Card v-else-if="method !== null">
      <CardHeader><CardTitle>{{ method.name }} · 阶段模板</CardTitle><CardDescription>调整模板会影响后续新建或推进的商机，历史商机数据保持不变。</CardDescription></CardHeader>
      <CardContent>
        <ListCard :title="`阶段列表（${method.stage_templates.length}）`" :items="method.stage_templates.slice().sort((a, b) => a.sort_order - b.sort_order)" empty-text="暂无阶段模板">
          <template #itemMain="{ item }"><div class="font-medium text-wolf-text-primary">{{ item.stage_name }}</div><div class="mt-1 text-xs text-muted-foreground">{{ item.stage_code }} · 赢率 {{ item.win_probability }}% · 排序 {{ item.sort_order }}</div><div v-if="item.description" class="mt-1 text-sm text-muted-foreground">{{ item.description }}</div></template>
          <template #itemBadges="{ item }"><Badge v-if="item.is_default === 1" variant="outline">默认起点</Badge><Badge v-if="item.can_skip === 1" variant="secondary">可跳过</Badge><Badge :variant="item.is_active === 1 ? 'default' : 'secondary'">{{ item.is_active === 1 ? '启用' : '停用' }}</Badge></template>
          <template #itemActions="{ item }"><Button v-if="canUpdate" variant="ghost" size="icon" title="编辑" @click="showEdit(item)"><Pencil class="size-4" /></Button><Button v-if="canDelete" variant="ghost" size="icon" title="删除" class="text-destructive hover:text-destructive" @click="removeStage(item)"><Trash2 class="size-4" /></Button></template>
        </ListCard>
      </CardContent>
    </Card>
  </main>
  <Dialog v-model:open="dialogOpen"><DialogContent class="max-w-lg"><DialogHeader><DialogTitle>{{ editingStage === null ? '新增阶段模板' : '编辑阶段模板' }}</DialogTitle><DialogDescription>阶段编码创建后不可修改，避免影响已有商机引用。</DialogDescription></DialogHeader><form class="space-y-4" @submit="submit"><FormField v-slot="{ componentField }" name="stage_code"><FormItem><FormLabel>阶段编码</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" :disabled="editingStage !== null" placeholder="如：QUALIFICATION" /></FormControl><FormMessage /></FormItem></FormField><FormField v-slot="{ componentField }" name="stage_name"><FormItem><FormLabel>阶段名称</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" placeholder="请输入阶段名称" /></FormControl><FormMessage /></FormItem></FormField><div class="grid grid-cols-2 gap-4"><FormField v-slot="{ componentField }" name="win_probability"><FormItem><FormLabel>赢率（%）</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" type="number" /></FormControl><FormMessage /></FormItem></FormField><FormField v-slot="{ componentField }" name="sort_order"><FormItem><FormLabel>排序</FormLabel><FormControl><Input v-bind="componentField as unknown as Record<string, unknown>" type="number" /></FormControl><FormMessage /></FormItem></FormField></div><FormField v-slot="{ value, handleChange }" name="is_default"><FormItem class="flex items-center justify-between rounded-lg border p-3"><FormLabel>默认起点</FormLabel><FormControl><Switch :model-value="value" @update:model-value="handleChange" /></FormControl></FormItem></FormField><FormField v-slot="{ value, handleChange }" name="can_skip"><FormItem class="flex items-center justify-between rounded-lg border p-3"><FormLabel>允许跳过</FormLabel><FormControl><Switch :model-value="value" @update:model-value="handleChange" /></FormControl></FormItem></FormField><FormField v-slot="{ componentField }" name="description"><FormItem><FormLabel>描述</FormLabel><FormControl><Textarea v-bind="componentField as unknown as Record<string, unknown>" :rows="3" placeholder="可选" /></FormControl><FormMessage /></FormItem></FormField><DialogFooter><Button type="button" variant="outline" @click="dialogOpen = false">取消</Button><Button type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '保存' }}</Button></DialogFooter></form></DialogContent></Dialog>
</template>
