<script setup lang="ts">
/**
 * RoleSheet.vue - 角色管理 Sheet
 *
 * 功能：
 * - 展示角色列表（DataTable）
 * - 搜索角色
 * - 新建/编辑角色（Dialog）
 * - 配置权限（Dialog）
 * - 删除角色
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
import { Search, Plus, Pencil, Settings, Trash2 } from 'lucide-vue-next'
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
import { DataTable } from '@/components/crmwolf'
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
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { handleApiError } from '@/utils/errorHandler'
import roleApi, {
  type RoleResponse,
  type RoleWithPermissions,
  type PermissionResponse
} from '@/api/role'
import permissionApi from '@/api/permissions'

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== State ====================
const loading = ref(false)
const roles = ref<RoleResponse[]>([])
const searchText = ref('')
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 新建/编辑 Dialog
const roleDialogOpen = ref(false)
const roleDialogSubmitting = ref(false)
const isEditMode = ref(false)
const selectedRole = ref<RoleResponse | null>(null)

// 配置权限 Dialog
const permissionsDialogOpen = ref(false)
const permissionsDialogSubmitting = ref(false)
const currentRole = ref<RoleWithPermissions | null>(null)
const allPermissions = ref<PermissionResponse[]>([])
const selectedPermissionIds = ref<number[]>([])

// ==================== Zod Schema ====================
const roleSchema = toTypedSchema(
  z.object({
    code: z.string()
      .min(1, '请输入角色代码')
      .max(50, '角色代码不能超过50字符')
      .regex(/^[A-Z_]+$/, '角色代码只能包含大写字母和下划线'),
    name: z.string()
      .min(1, '请输入角色名称')
      .max(50, '角色名称不能超过50字符'),
    description: z.string()
      .max(200, '描述不能超过200字符')
      .optional()
      .nullable()
  })
)

// VeeValidate form setup
const { handleSubmit, resetForm } = useForm({
  validationSchema: roleSchema,
  initialValues: {
    code: '',
    name: '',
    description: ''
  }
})

// ==================== Types ====================
interface Column {
  key: string
  title: string
  width?: string
  align?: 'left' | 'center' | 'right'
  fixed?: 'left' | 'right'
}

// ==================== Resource Name Mapping ====================
const resourceNames: Record<string, string> = {
  lead: '线索',
  customer: '客户',
  opportunity: '商机',
  contract: '合同',
  invoice: '发票',
  product: '产品',
  user: '用户',
  role: '角色',
  permission: '权限',
  system: '系统'
}

function getResourceName(resource: string): string {
  return resourceNames[resource] ?? resource
}

// ==================== Table Columns ====================
const columns: Column[] = [
  {
    key: 'code',
    title: '角色代码',
    width: '150px',
    fixed: 'left'
  },
  {
    key: 'name',
    title: '角色名称',
    width: '150px'
  },
  {
    key: 'description',
    title: '描述'
  },
  {
    key: 'created_at',
    title: '创建时间',
    width: '160px'
  },
  {
    key: 'actions',
    title: '操作',
    width: '220px',
    fixed: 'right',
    align: 'center'
  }
]

// ==================== Computed ====================
const filteredRoles = computed(() => {
  if (!searchText.value) return roles.value
  const search = searchText.value.toLowerCase()
  return roles.value.filter(role =>
    role.code.toLowerCase().includes(search) ||
    role.name.toLowerCase().includes(search)
  )
})

// 权限分组（按资源分组）
const permissionGroups = computed(() => {
  const groups: Record<string, PermissionResponse[]> = {}
  allPermissions.value.forEach(permission => {
    const resource = permission.resource
    if (!groups[resource]) {
      groups[resource] = []
    }
    groups[resource].push(permission)
  })
  return Object.entries(groups).map(([resource, permissions]) => ({
    resource,
    permissions
  }))
})

// ==================== API Methods ====================
const fetchRoles = async (): Promise<void> => {
  loading.value = true
  try {
    const params = {
      skip: (pagination.value.page - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    }
    const data = await roleApi.getRoles(params)
    roles.value = data
    pagination.value.total = data.length
  } catch (error) {
    handleApiError(error, '获取角色列表')
  } finally {
    loading.value = false
  }
}

// ==================== Role CRUD ====================
const showCreateDialog = (): void => {
  isEditMode.value = false
  selectedRole.value = null
  resetForm({
    values: {
      code: '',
      name: '',
      description: ''
    }
  })
  roleDialogOpen.value = true
}

const handleEdit = (record: RoleResponse): void => {
  isEditMode.value = true
  selectedRole.value = record
  resetForm({
    values: {
      code: record.code,
      name: record.name,
      description: record.description ?? ''
    }
  })
  roleDialogOpen.value = true
}

const onSubmit = handleSubmit(async (formValues) => {
  roleDialogSubmitting.value = true
  try {
    if (isEditMode.value && selectedRole.value) {
      const updateData = {
        role_name: formValues.name,
        description: formValues.description ?? null
      }
      await roleApi.updateRole(selectedRole.value.id, updateData)
      toast.success('角色更新成功')
    } else {
      const createData = {
        code: formValues.code,
        name: formValues.name,
        description: formValues.description ?? null
      }
      await roleApi.createRole(createData)
      toast.success('角色创建成功')
    }

    roleDialogOpen.value = false
    fetchRoles()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新角色' : '创建角色')
  } finally {
    roleDialogSubmitting.value = false
  }
})

const handleDelete = async (record: RoleResponse): Promise<void> => {
  // 使用 confirm 代替 ElMessageBox
  if (!confirm(`确定要删除角色"${record.name}"吗？删除后不可恢复。`)) {
    return
  }

  try {
    await roleApi.deleteRole(record.id)
    toast.success('角色删除成功')
    fetchRoles()
  } catch (error) {
    handleApiError(error, '删除角色')
  }
}

// ==================== Permissions Configuration ====================
const handleConfigPermissions = async (record: RoleResponse): Promise<void> => {
  try {
    // 获取角色详情（包含当前权限）
    const roleData = await roleApi.getRole(record.id)
    currentRole.value = roleData

    // 获取所有权限列表
    const permsData = await permissionApi.getAllPermissions()
    allPermissions.value = permsData

    // 设置当前已选权限
    selectedPermissionIds.value = roleData.permissions?.map((p: PermissionResponse) => p.id) ?? []

    permissionsDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取角色权限')
  }
}

// 检查分组是否全选
const isGroupAllSelected = (resource: string): boolean => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return false
  return group.permissions.every(p => selectedPermissionIds.value.includes(p.id))
}

// 检查分组是否部分选中
const isGroupIndeterminate = (resource: string): boolean => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return false
  const selectedCount = group.permissions.filter(p => selectedPermissionIds.value.includes(p.id)).length
  return selectedCount > 0 && selectedCount < group.permissions.length
}

// 处理分组全选
const handleGroupSelect = (resource: string, checked: boolean): void => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return

  if (checked) {
    // 添加该分组所有权限
    const newIds = group.permissions.map(p => p.id)
    selectedPermissionIds.value = [...new Set([...selectedPermissionIds.value, ...newIds])]
  } else {
    // 移除该分组所有权限
    const groupIds = group.permissions.map(p => p.id)
    selectedPermissionIds.value = selectedPermissionIds.value.filter(id => !groupIds.includes(id))
  }
}

// 处理单个权限选择
const handlePermissionSelect = (permissionId: number, checked: boolean): void => {
  if (checked) {
    selectedPermissionIds.value = [...selectedPermissionIds.value, permissionId]
  } else {
    selectedPermissionIds.value = selectedPermissionIds.value.filter(id => id !== permissionId)
  }
}

// 保存权限配置
const handleSavePermissions = async (): Promise<void> => {
  if (!currentRole.value) return

  permissionsDialogSubmitting.value = true
  try {
    await roleApi.updateRolePermissions(currentRole.value.id, selectedPermissionIds.value)
    toast.success('权限配置保存成功')
    permissionsDialogOpen.value = false
  } catch (error) {
    handleApiError(error, '保存权限配置')
  } finally {
    permissionsDialogSubmitting.value = false
  }
}

// ==================== Lifecycle ====================
watch(() => props.open, (open) => {
  if (open) {
    fetchRoles()
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
    <SheetHeader>
      <SheetTitle class="text-base font-semibold text-wolf-text-primary">角色管理</SheetTitle>
      <SheetDescription class="text-sm text-wolf-text-secondary">配置系统角色与权限</SheetDescription>
    </SheetHeader>
    <DetailSheetContent>
      <ScrollArea class="h-full">
        <!-- 搜索/操作栏 -->
        <div class="p-4 border-b flex items-center gap-4">
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              v-model="searchText"
              placeholder="搜索角色代码、名称"
              class="pl-10"
            />
          </div>
          <Button @click="showCreateDialog">
            <Plus class="w-4 h-4 mr-2" />
            新建角色
          </Button>
        </div>

        <!-- 表格区域 -->
        <div class="p-4">
          <DataTable
            :columns="columns"
            :data="filteredRoles"
            :loading="loading"
            :total="pagination.total"
            :page="pagination.page"
            :page-size="pagination.pageSize"
            height="calc(100vh - 350px)"
            empty-title="暂无角色数据"
          >
            <!-- 角色代码列 -->
            <template #cell-code="{ row }">
              <span class="text-primary font-medium cursor-pointer hover:underline">
                {{ row.code }}
              </span>
            </template>

            <!-- 创建时间列 -->
            <template #cell-created_at="{ row }">
              {{ formatDate(row.created_at) }}
            </template>

            <!-- 操作列 -->
            <template #cell-actions="{ row }">
              <div class="flex items-center justify-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  @click="handleEdit(row)"
                >
                  <Pencil class="w-3.5 h-3.5 mr-1" />
                  编辑
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  @click="handleConfigPermissions(row)"
                >
                  <Settings class="w-3.5 h-3.5 mr-1" />
                  权限
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2 text-destructive hover:text-destructive"
                  @click="handleDelete(row)"
                >
                  <Trash2 class="w-3.5 h-3.5 mr-1" />
                  删除
                </Button>
              </div>
            </template>
          </DataTable>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>

  <!-- 新建/编辑角色 Dialog (z-[1000]) -->
  <Dialog v-model:open="roleDialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>{{ isEditMode ? '编辑角色' : '新建角色' }}</DialogTitle>
        <DialogDescription>
          {{ isEditMode ? '修改角色信息' : '创建新的系统角色' }}
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onSubmit">
        <!-- 角色代码 -->
        <FormField v-slot="{ componentField }" name="code">
          <FormItem>
            <FormLabel>角色代码 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                placeholder="如：SALES_DIRECTOR"
                :disabled="isEditMode"
                class="uppercase"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <!-- 角色名称 -->
        <FormField v-slot="{ componentField }" name="name">
          <FormItem>
            <FormLabel>角色名称 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                placeholder="如：销售总监"
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
                placeholder="请输入角色描述"
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
            @click="roleDialogOpen = false"
          >
            取消
          </Button>
          <Button type="submit" :loading="roleDialogSubmitting">
            {{ roleDialogSubmitting ? '提交中...' : '确定' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- 配置权限 Dialog (z-[1000]) -->
  <Dialog v-model:open="permissionsDialogOpen">
    <DialogContent class="max-w-2xl max-h-[90vh] overflow-y-auto z-[1000]">
      <DialogHeader>
        <DialogTitle>配置角色权限</DialogTitle>
        <DialogDescription>
          为角色分配系统操作权限
        </DialogDescription>
      </DialogHeader>

      <div v-if="currentRole" class="space-y-4">
        <!-- 角色信息卡片 -->
        <div class="p-4 rounded-lg bg-muted/50 border">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-semibold text-lg">
              {{ currentRole.name?.charAt(0) || '角' }}
            </div>
            <div class="flex-1">
              <div class="font-semibold text-base">{{ currentRole.name }}</div>
              <div class="flex items-center gap-2 mt-1">
                <Badge variant="outline" class="text-xs">
                  {{ currentRole.code }}
                </Badge>
                <span v-if="currentRole.description" class="text-muted-foreground text-sm">
                  {{ currentRole.description }}
                </span>
              </div>
              <div class="text-muted-foreground text-sm mt-1">
                已选择 {{ selectedPermissionIds.length }} 项权限
              </div>
            </div>
          </div>
        </div>

        <!-- 权限列表 -->
        <div class="space-y-3">
          <div
            v-for="group in permissionGroups"
            :key="group.resource"
            class="p-4 rounded-lg border bg-card"
          >
            <!-- 分组标题 -->
            <div class="flex items-center justify-between pb-3 border-b mb-3">
              <span class="font-semibold">{{ getResourceName(group.resource) }}</span>
              <div class="flex items-center gap-2">
                <Checkbox
                  :id="`group-${group.resource}`"
                  :checked="isGroupAllSelected(group.resource)"
                  :indeterminate="isGroupIndeterminate(group.resource)"
                  @update:checked="handleGroupSelect(group.resource, $event)"
                />
                <Label
                  :for="`group-${group.resource}`"
                  class="text-sm text-muted-foreground cursor-pointer"
                >
                  全选
                </Label>
              </div>
            </div>

            <!-- 权限项 -->
            <div class="flex flex-wrap gap-3">
              <div
                v-for="permission in group.permissions"
                :key="permission.id"
                class="flex items-center gap-2"
              >
                <Checkbox
                  :id="`permission-${permission.id}`"
                  :checked="selectedPermissionIds.includes(permission.id)"
                  @update:checked="handlePermissionSelect(permission.id, $event)"
                />
                <Label
                  :for="`permission-${permission.id}`"
                  class="flex items-center gap-2 cursor-pointer"
                >
                  <Badge variant="outline" class="text-xs">
                    {{ permission.action }}
                  </Badge>
                  <span class="text-sm">{{ permission.name }}</span>
                </Label>
              </div>
            </div>
          </div>
        </div>
      </div>

      <DialogFooter class="pt-4 border-t">
        <Button
          type="button"
          variant="outline"
          @click="permissionsDialogOpen = false"
        >
          取消
        </Button>
        <Button
          type="button"
          :loading="permissionsDialogSubmitting"
          @click="handleSavePermissions"
        >
          {{ permissionsDialogSubmitting ? '保存中...' : '保存' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
