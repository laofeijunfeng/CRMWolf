<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Pencil, Plus, Power, Search, Trash2 } from 'lucide-vue-next'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ListCard } from '@/components/crmwolf'
import ErrorState from '@/components/ErrorState.vue'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { usePermissionStore } from '@/stores/permissions'
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

interface Props {
  active?: boolean
  embedded?: boolean
  action?: 'create' | 'edit' | undefined
  recordId?: string | undefined
}

interface ProductListItem extends ProductResponse {
  id: string
}

const productFormZodSchema = z.object({
  code: z.string().trim().min(1, '请输入产品编码').max(50),
  name: z.string().trim().min(1, '请输入产品名称').max(100),
  description: z.string().max(2000).optional(),
})

type ProductFormValues = z.infer<typeof productFormZodSchema>

const moduleFormZodSchema = z.object({
  code: z.string().trim().min(1, '请输入模块编码').max(50),
  name: z.string().trim().min(1, '请输入模块名称').max(100),
  description: z.string().max(2000).optional(),
})

type ModuleFormValues = z.infer<typeof moduleFormZodSchema>

const props = withDefaults(defineProps<Props>(), {
  active: true,
  embedded: true,
  action: undefined,
  recordId: undefined,
})
const permissionStore = usePermissionStore()

const products = ref<ProductResponse[]>([])
const loading = ref(false)
const loadError = ref<unknown | null>(null)
const searchText = ref('')
const filterStatus = ref('all')
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

const filteredProducts = computed<ProductListItem[]>(() => {
  const query = searchText.value.trim().toLowerCase()
  return products.value
    .filter((item) => {
      const matchesQuery = query.length === 0
        || item.name.toLowerCase().includes(query)
        || item.code.toLowerCase().includes(query)
      const matchesStatus = filterStatus.value === 'all'
        || (filterStatus.value === 'true' ? item.is_active : !item.is_active)
      return matchesQuery && matchesStatus
    })
    .map((item) => ({ ...item, id: item.public_id }))
})

const productFormSchema = toTypedSchema(productFormZodSchema)
const moduleFormSchema = toTypedSchema(moduleFormZodSchema)
const { handleSubmit, resetForm } = useForm({
  validationSchema: productFormSchema,
  initialValues: { code: '', name: '', description: '' },
})
const {
  handleSubmit: handleModuleSubmit,
  resetForm: resetModuleForm,
} = useForm({
  validationSchema: moduleFormSchema,
  initialValues: { code: '', name: '', description: '' },
})

const fetchProducts = async (): Promise<void> => {
  loading.value = true
  loadError.value = null
  try {
    products.value = await productApi.list()
  } catch (error) {
    loadError.value = error
    handleApiError(error, '获取产品')
  } finally {
    loading.value = false
  }
}

const showCreateDialog = (): void => {
  if (!canCreate.value) return
  isEditMode.value = false
  selectedProduct.value = null
  resetForm({ values: { code: '', name: '', description: '' } })
  dialogOpen.value = true
}

const showEditDialog = (product: ProductResponse): void => {
  if (!canEdit.value) return
  isEditMode.value = true
  selectedProduct.value = product
  resetForm({
    values: {
      code: product.code,
      name: product.name,
      description: product.description ?? '',
    },
  })
  dialogOpen.value = true
}

const onSubmit = handleSubmit(async (values: ProductFormValues) => {
  if (isEditMode.value ? !canEdit.value : !canCreate.value) return

  dialogSubmitting.value = true
  try {
    if (isEditMode.value && selectedProduct.value) {
      const data: ProductUpdate = {
        name: values.name,
        description: values.description ?? null,
      }
      await productApi.update(selectedProduct.value.public_id, data)
      toast.success('产品更新成功')
    } else {
      const data: ProductCreate = {
        code: values.code,
        name: values.name,
        description: values.description ?? null,
      }
      await productApi.create(data)
      toast.success('产品创建成功')
    }

    dialogOpen.value = false
    await fetchProducts()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新产品' : '创建产品')
  } finally {
    dialogSubmitting.value = false
  }
})

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
    await fetchProducts()
  } catch (error) {
    handleApiError(error, '更新产品状态')
  }
}

const deleteProduct = async (product: ProductResponse): Promise<void> => {
  if (!canDelete.value || !(await confirmDelete(`产品「${product.name}」`))) return

  try {
    await productApi.delete(product.public_id)
    toast.success('产品删除成功')
    await fetchProducts()
  } catch (error) {
    handleApiError(error, '删除产品')
  }
}

const showCreateModuleDialog = (product: ProductResponse): void => {
  selectedProduct.value = product
  isModuleEditMode.value = false
  selectedModule.value = null
  resetModuleForm({ values: { code: '', name: '', description: '' } })
  moduleDialogOpen.value = true
}

const showEditModuleDialog = (
  product: ProductResponse,
  module: ProductModuleResponse,
): void => {
  if (module.module_role === 'BASE' || !canEdit.value) return

  selectedProduct.value = product
  selectedModule.value = module
  isModuleEditMode.value = true
  resetModuleForm({
    values: {
      code: module.code,
      name: module.name,
      description: module.description ?? '',
    },
  })
  moduleDialogOpen.value = true
}
const onModuleSubmit = handleModuleSubmit(async (values: ModuleFormValues) => {
  if (!canEdit.value || !selectedProduct.value) return

  moduleDialogSubmitting.value = true
  try {
    if (isModuleEditMode.value && selectedModule.value) {
      await productApi.updateModule(
        selectedProduct.value.public_id,
        selectedModule.value.public_id,
        { name: values.name, description: values.description ?? null },
      )
      toast.success('模块更新成功')
    } else {
      const data: ProductModuleCreate = {
        code: values.code,
        name: values.name,
        description: values.description ?? null,
        module_role: 'ADD_ON',
        is_active: true,
        sort_order: 0,
      }
      await productApi.createModule(selectedProduct.value.public_id, data)
      toast.success('模块创建成功')
    }

    moduleDialogOpen.value = false
    await fetchProducts()
  } catch (error) {
    handleApiError(error, isModuleEditMode.value ? '更新模块' : '创建模块')
  } finally {
    moduleDialogSubmitting.value = false
  }
})

const toggleModule = async (
  product: ProductResponse,
  module: ProductModuleResponse,
): Promise<void> => {
  if (!canEdit.value || module.module_role === 'BASE') return

  try {
    await productApi.updateModule(product.public_id, module.public_id, {
      is_active: !module.is_active,
    })
    toast.success(module.is_active ? '模块已停用' : '模块已启用')
    await fetchProducts()
  } catch (error) {
    handleApiError(error, '更新模块状态')
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
    await fetchProducts()
  } catch (error) {
    handleApiError(error, '删除模块')
  }
}

const lastDeepLinkKey = ref<string | null>(null)

watch(() => props.active, (active) => {
  if (active) void fetchProducts()
})

onMounted(() => {
  if (props.active) void fetchProducts()
})

watch(
  () => [props.active, props.action, props.recordId, products.value.length, canCreate.value, canEdit.value] as const,
  ([active, action, recordId]) => {
    if (!active) return

    if (action === undefined) {
      lastDeepLinkKey.value = null
      return
    }

    const key = `${action}:${recordId ?? ''}`
    if (lastDeepLinkKey.value === key) return

    if (action === 'create' && canCreate.value) {
      lastDeepLinkKey.value = key
      showCreateDialog()
      return
    }

    if (action === 'edit' && recordId !== undefined && canEdit.value) {
      const found = products.value.find(item => item.public_id === recordId)
      if (found) {
        lastDeepLinkKey.value = key
        showEditDialog(found)
      }
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="settings-module-panel">
    <ScrollArea class="h-full">
      <div class="space-y-4 p-4">
        <div class="flex flex-wrap items-center gap-3">
          <div class="relative min-w-48 flex-1">
            <Search class="absolute left-2 top-2.5 h-4 w-4" />
            <Input
              v-model="searchText"
              class="pl-8"
              placeholder="搜索产品名称或编码"
              aria-label="搜索产品名称或编码"
            />
          </div>
          <Button v-if="canCreate" type="button" @click="showCreateDialog">
            <Plus class="mr-1 h-4 w-4" />
            新建产品
          </Button>
        </div>

        <div class="flex items-center gap-3">
          <Select v-model="filterStatus">
            <SelectTrigger class="w-32" aria-label="产品状态">
              <SelectValue placeholder="状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="true">启用</SelectItem>
              <SelectItem value="false">停用</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <ErrorState
          v-if="loadError !== null"
          title="产品加载失败"
          description="请检查网络连接后重试。"
        >
          <template #action>
            <Button
              type="button"
              data-testid="product-list-retry"
              :disabled="loading"
              @click="void fetchProducts()"
            >
              {{ loading ? '加载中...' : '重新加载' }}
            </Button>
          </template>
        </ErrorState>
        <ListCard
          v-if="loadError === null || products.length > 0"
          :title="`产品列表（${filteredProducts.length}）`"
          :items="filteredProducts"
          :loading="loading"
          empty-text="暂无产品"
        >
          <template #itemMain="{ item }">
            <div>
              <div class="font-medium">
                {{ item.name }}
                <span class="text-muted-foreground">({{ item.code }})</span>
              </div>
              <div class="text-sm text-muted-foreground">
                {{ item.description || '暂无描述' }}
              </div>
              <div class="mt-2 text-sm">
                模块：{{ item.modules.length }} 个
                <span v-if="item.modules.find(module => module.module_role === 'BASE')">
                  ；基础模块：{{ item.modules.find(module => module.module_role === 'BASE')?.name }}
                </span>
              </div>
            </div>
          </template>
          <template #itemBadges="{ item }">
            <Badge>{{ item.is_active ? '启用' : '停用' }}</Badge>
          </template>
          <template #itemActions="{ item }">
            <div class="flex flex-wrap gap-2">
              <Button
                v-if="canEdit"
                type="button"
                size="sm"
                variant="outline"
                @click="showEditDialog(item)"
              >
                <Pencil class="mr-1 h-3 w-3" />
                编辑
              </Button>
              <Button
                v-if="canEdit"
                type="button"
                size="sm"
                variant="outline"
                @click="toggleProduct(item)"
              >
                <Power class="mr-1 h-3 w-3" />
                {{ item.is_active ? '停用' : '启用' }}
              </Button>
              <Button
                v-if="canDelete"
                type="button"
                size="sm"
                variant="outline"
                @click="deleteProduct(item)"
              >
                <Trash2 class="mr-1 h-3 w-3" />
                删除
              </Button>
              <Button
                v-if="canEdit"
                type="button"
                size="sm"
                @click="showCreateModuleDialog(item)"
              >
                <Plus class="mr-1 h-3 w-3" />
                新增模块
              </Button>
            </div>
            <div class="mt-2 space-y-1 border-l pl-3">
              <div
                v-for="module in item.modules"
                :key="module.public_id"
                class="flex flex-wrap items-center gap-2 text-sm"
              >
                <span>{{ module.name }} ({{ module.code }})</span>
                <Badge>
                  {{ module.module_role === 'BASE'
                    ? '基础模块（受保护）'
                    : module.is_active ? '启用' : '停用' }}
                </Badge>
                <template v-if="module.module_role !== 'BASE'">
                  <Button
                    v-if="canEdit"
                    type="button"
                    size="sm"
                    variant="ghost"
                    @click="showEditModuleDialog(item, module)"
                  >
                    编辑
                  </Button>
                  <Button
                    v-if="canEdit"
                    type="button"
                    size="sm"
                    variant="ghost"
                    @click="toggleModule(item, module)"
                  >
                    {{ module.is_active ? '停用' : '启用' }}
                  </Button>
                  <Button
                    v-if="canEdit"
                    type="button"
                    size="sm"
                    variant="ghost"
                    @click="deleteModule(item, module)"
                  >
                    删除模块
                  </Button>
                </template>
              </div>
            </div>
          </template>
        </ListCard>
      </div>
    </ScrollArea>
  </section>

  <Dialog v-model:open="dialogOpen">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ isEditMode ? '编辑产品' : '新建产品' }}</DialogTitle>
        <DialogDescription>维护产品编码、名称和描述。</DialogDescription>
      </DialogHeader>
      <form class="space-y-4" @submit="onSubmit">
        <FormField v-slot="{ componentField }" name="code">
          <FormItem>
            <FormLabel>编码</FormLabel>
            <FormControl>
              <Input v-bind="componentField as unknown as Record<string, unknown>" :disabled="isEditMode" />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>
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
      </form>
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="moduleDialogOpen">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ isModuleEditMode ? '编辑模块' : '新增模块' }}</DialogTitle>
        <DialogDescription>
          增强模块用于扩展产品能力；基础模块不可修改状态或删除。
        </DialogDescription>
      </DialogHeader>
      <form class="space-y-4" @submit="onModuleSubmit">
        <FormField v-slot="{ componentField }" name="code">
          <FormItem>
            <FormLabel>编码</FormLabel>
            <FormControl>
              <Input v-bind="componentField as unknown as Record<string, unknown>" :disabled="isModuleEditMode" />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>
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
      </form>
    </DialogContent>
  </Dialog>
</template>
