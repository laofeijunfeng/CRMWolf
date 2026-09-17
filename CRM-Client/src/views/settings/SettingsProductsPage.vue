<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { toTypedSchema } from '@vee-validate/zod'
import type { GenericObject } from 'vee-validate'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Plus } from 'lucide-vue-next'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { usePermissionStore } from '@/stores/permissions'
import { useTeamStore } from '@/stores/team'
import productApi from '@/api/product'
import type {
  ProductCreate,
  ProductModuleCreate,
  ProductModuleResponse,
  ProductResponse,
  ProductUpdate,
} from '@/schemas/product'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog, confirmDelete } from '@/utils/confirmDialog'
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

const submittedSearch = ref('')
const products = ref<ProductResponse[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)

const dialogOpen = ref(false)
const moduleDialogOpen = ref(false)
const dialogSubmitting = ref(false)
const moduleDialogSubmitting = ref(false)
const isEditMode = ref(false)
const isModuleEditMode = ref(false)
const selectedProduct = ref<ProductResponse | null>(null)
const selectedModule = ref<ProductModuleResponse | null>(null)

const canCreate = computed<boolean>(() => permissionStore.hasPermission('product:create'))
const canEdit = computed<boolean>(() => permissionStore.hasPermission('product:edit'))
const canDelete = computed<boolean>(() => permissionStore.hasPermission('product:delete'))

const productFormZodSchema = z.object({
  name: z.string().trim().min(1, '请输入产品名称').max(100),
  description: z.string().max(2000).optional(),
})

type ProductFormValues = z.infer<typeof productFormZodSchema>

const moduleFormZodSchema = z.object({
  name: z.string().trim().min(1, '请输入模块名称').max(100),
  description: z.string().max(2000).optional(),
})

type ModuleFormValues = z.infer<typeof moduleFormZodSchema>

const productFormSchema = toTypedSchema(productFormZodSchema)
const moduleFormSchema = toTypedSchema(moduleFormZodSchema)
const productFormValues = ref<ProductFormValues>({ name: '', description: '' })
const moduleFormValues = ref<ModuleFormValues>({ name: '', description: '' })

const displayedProducts = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  if (query.length === 0) return products.value
  return products.value.filter((item) => item.name.toLowerCase().includes(query))
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'name', label: '产品', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'status', label: '状态', column: true }),
  settingsListColumn({ key: 'modules', label: '模块', column: true }),
])

const queryParam = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return ''
}

const loadProducts = async (): Promise<void> => {
  const requestId = ++listRequestId.value
  loading.value = true
  loadError.value = null
  try {
    const data = await productApi.list()
    if (requestId !== listRequestId.value) return
    products.value = Array.isArray(data) ? data : []
  } catch (error) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(error, '产品')
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
  }
}

const showCreateDialog = (): void => {
  if (!canCreate.value) return
  isEditMode.value = false
  selectedProduct.value = null
  productFormValues.value = { name: '', description: '' }
  dialogOpen.value = true
}

const showEditDialog = (product: ProductResponse): void => {
  if (!canEdit.value) return
  isEditMode.value = true
  selectedProduct.value = product
  productFormValues.value = {
    name: product.name,
    description: product.description ?? '',
  }
  dialogOpen.value = true
}

const onSubmit = async (values: GenericObject): Promise<void> => {
  if (isEditMode.value ? !canEdit.value : !canCreate.value) return

  const parsed = productFormZodSchema.parse(values)
  dialogSubmitting.value = true
  try {
    if (isEditMode.value && selectedProduct.value) {
      const data: ProductUpdate = {
        name: parsed.name,
        description: parsed.description ?? null,
      }
      await productApi.update(selectedProduct.value.public_id, data)
      toast.success('产品更新成功')
    } else {
      const data: ProductCreate = {
        name: parsed.name,
        description: parsed.description ?? null,
      }
      await productApi.create(data)
      toast.success('产品创建成功')
    }

    dialogOpen.value = false
    await loadProducts()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新产品' : '创建产品')
  } finally {
    dialogSubmitting.value = false
  }
}

const toggleProduct = async (product: ProductResponse): Promise<void> => {
  if (!canEdit.value) return

  const next = !product.is_active
  if (!next) {
    const confirmed = await confirmDialog(
      `停用后产品及模块将不再用于业务配置。确定停用「${product.name}」吗？`,
      '停用产品',
    )
    if (!confirmed) return
  }

  try {
    await productApi.update(product.public_id, { is_active: next })
    toast.success(next ? '产品已启用' : '产品已停用')
    await loadProducts()
  } catch (error) {
    handleApiError(error, '更新产品状态')
  }
}

const deleteProduct = async (product: ProductResponse): Promise<void> => {
  if (!canDelete.value || !(await confirmDelete(`产品「${product.name}」`))) return

  try {
    await productApi.delete(product.public_id)
    toast.success('产品删除成功')
    await loadProducts()
  } catch (error) {
    handleApiError(error, '删除产品')
  }
}

const showCreateModuleDialog = (product: ProductResponse): void => {
  selectedProduct.value = product
  isModuleEditMode.value = false
  selectedModule.value = null
  moduleFormValues.value = { name: '', description: '' }
  moduleDialogOpen.value = true
}

const onModuleSubmit = async (values: GenericObject): Promise<void> => {
  if (!canEdit.value || !selectedProduct.value) return

  const parsed = moduleFormZodSchema.parse(values)
  moduleDialogSubmitting.value = true
  try {
    if (isModuleEditMode.value && selectedModule.value) {
      await productApi.updateModule(
        selectedProduct.value.public_id,
        selectedModule.value.public_id,
        { name: parsed.name, description: parsed.description ?? null },
      )
      toast.success('模块更新成功')
    } else {
      const data: ProductModuleCreate = {
        name: parsed.name,
        description: parsed.description ?? null,
        module_role: 'ADD_ON',
        is_active: true,
        sort_order: 0,
      }
      await productApi.createModule(selectedProduct.value.public_id, data)
      toast.success('模块创建成功')
    }

    moduleDialogOpen.value = false
    await loadProducts()
  } catch (error) {
    handleApiError(error, isModuleEditMode.value ? '更新模块' : '创建模块')
  } finally {
    moduleDialogSubmitting.value = false
  }
}

const deleteModule = async (
  product: ProductResponse,
  module: ProductModuleResponse,
): Promise<void> => {
  if (
    !canEdit.value
    || module.module_role === 'BASE'
    || !(await confirmDelete(`模块「${module.name}」`))
  ) return

  try {
    await productApi.deleteModule(product.public_id, module.public_id)
    toast.success('模块删除成功')
    await loadProducts()
  } catch (error) {
    handleApiError(error, '删除模块')
  }
}

const asProductHandler = (handler: (row: ProductResponse) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as ProductResponse) }
}

const getRowActions = (row: ProductResponse): TableRowActionSet => {
  const addOnModules = row.modules.filter((module) => module.module_role !== 'BASE')
  return {
    primaryActions: [{
      id: 'edit',
      label: '编辑',
      desktopPrimary: true,
      visible: canEdit.value,
      handler: asProductHandler(showEditDialog),
    }],
    secondaryActions: [
      {
        label: '新增模块',
        visible: canEdit.value,
        handler: asProductHandler(showCreateModuleDialog),
      },
      ...addOnModules.map((module) => ({
        label: '删除模块',
        visible: canEdit.value,
        handler: asProductHandler((product) => { void deleteModule(product, module) }),
      })),
      {
        label: row.is_active ? '停用' : '启用',
        visible: canEdit.value,
        handler: asProductHandler((product) => { void toggleProduct(product) }),
      },
      {
        id: 'delete' as const,
        label: '删除',
        visible: canDelete.value,
        destructive: true,
        risk: 'destructive' as const,
        handler: asProductHandler((product) => { void deleteProduct(product) }),
      },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canCreate],
  actions: () => [{
    id: 'create-product',
    label: '新建产品',
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

watch(() => [route.query['action'], route.query['id'], products.value.length, canEdit.value] as const, ([action, id]) => {
  const actionValue = queryParam(action)
  const idValue = queryParam(id)
  if (actionValue === 'edit' && idValue !== '' && canEdit.value) {
    const product = products.value.find((item) => item.public_id === idValue || item.id === idValue)
    if (product !== undefined) showEditDialog(product)
  }
}, { immediate: true })

watch(() => teamStore.currentTeam?.id, () => {
  void loadProducts()
}, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="产品管理" description="维护产品及其基础模块、增强模块和启用状态。短任务继续用对话框。">
    <DataTable
      :fields="fields"
      :data="displayedProducts"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedProducts.length, 1)"
      :total="displayedProducts.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无产品"
      :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
      :empty-description="canCreate ? '' : '你没有创建产品的权限，请联系团队管理员'"
      :get-row-actions="getRowActions"
      mobile-title-key="name"
      :mobile-meta-keys="['status']"
      search-enabled
      :search="submittedSearch"
      search-placeholder="搜索产品名称"
      :search-loading="loading"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @retry="loadProducts"
    >
      <template #cell-name="{ row }">
        <div class="font-medium text-wolf-text-primary">{{ row.name }}</div>
        <div class="mt-1 text-xs text-muted-foreground">{{ row.description || '暂无描述' }}</div>
      </template>
      <template #cell-status="{ row }">
        <Badge :variant="row.is_active ? 'default' : 'secondary'">
          {{ row.is_active ? '启用' : '停用' }}
        </Badge>
      </template>
      <template #cell-modules="{ row }">
        <div class="text-sm">
          模块：{{ row.modules.length }} 个
          <span v-if="row.modules.find((module) => module.module_role === 'BASE')">
            ；基础模块：{{ row.modules.find((module) => module.module_role === 'BASE')?.name }}
          </span>
        </div>
        <div class="mt-1 space-y-1">
          <div
            v-for="module in row.modules"
            :key="module.public_id"
            class="text-sm text-muted-foreground"
          >
            {{ module.name }}
          </div>
        </div>
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>

  <Dialog v-model:open="dialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ isEditMode ? '编辑产品' : '新建产品' }}</DialogTitle>
        <DialogDescription>维护产品名称和描述。</DialogDescription>
      </DialogHeader>
      <Form
        v-if="dialogOpen"
        :validation-schema="productFormSchema"
        :initial-values="productFormValues"
        class="space-y-4"
        @submit="onSubmit"
      >
        <FormField v-slot="{ componentField }" name="name">
          <FormItem>
            <FormLabel>名称</FormLabel>
            <FormControl>
              <Input v-bind="componentField as unknown as Record<string, unknown>" />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>
        <FormField v-slot="{ componentField }" name="description">
          <FormItem>
            <FormLabel>描述</FormLabel>
            <FormControl>
              <Textarea v-bind="componentField as unknown as Record<string, unknown>" />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>
        <DialogFooter>
          <Button type="submit" :disabled="dialogSubmitting">保存</Button>
        </DialogFooter>
      </Form>
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="moduleDialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ isModuleEditMode ? '编辑模块' : '新增模块' }}</DialogTitle>
        <DialogDescription>
          增强模块用于扩展产品能力；基础模块不可修改状态或删除。
        </DialogDescription>
      </DialogHeader>
      <Form
        v-if="moduleDialogOpen"
        :validation-schema="moduleFormSchema"
        :initial-values="moduleFormValues"
        class="space-y-4"
        @submit="onModuleSubmit"
      >
        <FormField v-slot="{ componentField }" name="name">
          <FormItem>
            <FormLabel>名称</FormLabel>
            <FormControl>
              <Input v-bind="componentField as unknown as Record<string, unknown>" />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>
        <FormField v-slot="{ componentField }" name="description">
          <FormItem>
            <FormLabel>描述</FormLabel>
            <FormControl>
              <Textarea v-bind="componentField as unknown as Record<string, unknown>" />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>
        <DialogFooter>
          <Button type="submit" :disabled="moduleDialogSubmitting">保存</Button>
        </DialogFooter>
      </Form>
    </DialogContent>
  </Dialog>
</template>
