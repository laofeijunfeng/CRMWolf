<script setup lang="ts">
import { ref, computed, watch } from 'vue'
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
import ErrorState from '@/components/ErrorState.vue'
import { handleApiError } from '@/utils/errorHandler'

import roleApi from '@/api/role'
import type { RoleResponse, RoleWithPermissions, PermissionResponse } from '@/api/role'
import permissionApi from '@/api/permissions'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'

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
import {
  getPermissionActionName,
  getPermissionResourceName,
  isAssignablePermission,
  mergePermissionIdsPreservingDeprecated,
} from '@/constants/permissions'

usePageTitle()

const route = useRoute()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { isOwner, canAccess, permissionsUnavailable, permissionsPending } = useSettingsAccess()
const rolesSettings = getSettingsNavigationItem('roles')
const hasAccess = computed(() => rolesSettings !== undefined && canAccess(rolesSettings))
const retryingPermissions = computed(() => permissionStore.loadState === 'loading')
const teamId = computed(() => teamStore.currentTeam?.id)


const retryPermissions = async (): Promise<void> => {
  await teamStore.retryPermissionSync()
}


const submittedSearch = ref('')
const roles = ref<RoleResponse[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)

const roleDialogOpen = ref(false)
const roleDialogSubmitting = ref(false)
const isEditMode = ref(false)
const selectedRole = ref<RoleResponse | null>(null)

const permissionsDialogOpen = ref(false)
const permissionsDialogSubmitting = ref(false)
const currentRole = ref<RoleWithPermissions | null>(null)
const allPermissions = ref<PermissionResponse[]>([])
const selectedPermissionIds = ref<number[]>([])

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

const { handleSubmit, resetForm } = useForm({
  validationSchema: roleSchema,
  initialValues: {
    code: '',
    name: '',
    description: ''
  }
})

const getResourceName = getPermissionResourceName
const getActionName = getPermissionActionName

const canManageRoles = computed(() => isOwner.value || permissionStore.hasPermission('role:manage'))
const canManageRolePermissions = computed(() => isOwner.value || permissionStore.hasAnyPermission(['permission:manage', 'role:manage']))

const displayedRoles = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  if (query.length === 0) return roles.value
  return roles.value.filter((role) => {
    const name = role.name.toLowerCase()
    const code = role.code.toLowerCase()
    return name.includes(query) || code.includes(query)
  })
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'name', label: '角色', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'code', label: '代码', column: true }),
  settingsListColumn({ key: 'updated_at', label: '更新时间', column: true }),
])

const permissionGroups = computed(() => {
  const groups: Record<string, PermissionResponse[]> = {}
  allPermissions.value.filter(isAssignablePermission).forEach(permission => {
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

const loadRoles = async (): Promise<void> => {
  if (!hasAccess.value) return
  const requestId = ++listRequestId.value

  loading.value = true
  loadError.value = null
  try {
    const response = await roleApi.getRoles()
    if (requestId !== listRequestId.value) return
    roles.value = response
  } catch (error) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(error, '角色列表')
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
  }
}

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
    void loadRoles()
  } catch (error) {
    handleApiError(error, isEditMode.value ? '更新角色' : '创建角色')
  } finally {
    roleDialogSubmitting.value = false
  }
})

const handleDelete = async (record: RoleResponse): Promise<void> => {
  if (!confirm(`确定要删除角色"${record.name}"吗？删除后不可恢复。`)) {
    return
  }

  try {
    await roleApi.deleteRole(record.id)
    toast.success('角色删除成功')
    void loadRoles()
  } catch (error) {
    handleApiError(error, '删除角色')
  }
}

const handleConfigPermissions = async (record: RoleResponse): Promise<void> => {
  try {
    const roleData = await roleApi.getRole(record.id)
    currentRole.value = roleData

    const permsData = await permissionApi.getAllPermissions()
    allPermissions.value = permsData

    selectedPermissionIds.value = roleData.permissions?.map((p: PermissionResponse) => p.id) ?? []

    permissionsDialogOpen.value = true
  } catch (error) {
    handleApiError(error, '获取角色权限')
  }
}

const isGroupAllSelected = (resource: string): boolean => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return false
  return group.permissions.every(p => selectedPermissionIds.value.includes(p.id))
}

const isGroupIndeterminate = (resource: string): boolean => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return false
  const selectedCount = group.permissions.filter(p => selectedPermissionIds.value.includes(p.id)).length
  return selectedCount > 0 && selectedCount < group.permissions.length
}

const handleGroupSelect = (resource: string, checked: boolean): void => {
  const group = permissionGroups.value.find(g => g.resource === resource)
  if (!group) return

  if (checked) {
    const newIds = group.permissions.map(p => p.id)
    selectedPermissionIds.value = [...new Set([...selectedPermissionIds.value, ...newIds])]
  } else {
    const groupIds = group.permissions.map(p => p.id)
    selectedPermissionIds.value = selectedPermissionIds.value.filter(id => !groupIds.includes(id))
  }
}

const handlePermissionSelect = (permissionId: number, checked: boolean): void => {
  if (checked) {
    selectedPermissionIds.value = [...selectedPermissionIds.value, permissionId]
  } else {
    selectedPermissionIds.value = selectedPermissionIds.value.filter(id => id !== permissionId)
  }
}

const handleSavePermissions = async (): Promise<void> => {
  if (!currentRole.value) return

  permissionsDialogSubmitting.value = true
  try {
    const permissionIds = mergePermissionIdsPreservingDeprecated(
      selectedPermissionIds.value,
      currentRole.value.permissions,
    )
    await roleApi.updateRolePermissions(currentRole.value.id, permissionIds)
    toast.success('权限配置保存成功')
    permissionsDialogOpen.value = false
  } catch (error) {
    handleApiError(error, '保存权限配置')
  } finally {
    permissionsDialogSubmitting.value = false
  }
}

const asRoleHandler = (handler: (row: RoleResponse) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as RoleResponse) }
}

const getRowActions = (_row: RoleResponse): TableRowActionSet => {
  return {
    primaryActions: [{
      label: '配置权限',
      desktopPrimary: true,
      visible: canManageRolePermissions.value,
      handler: asRoleHandler((role) => { void handleConfigPermissions(role) }),
    }],
    secondaryActions: [
      { id: 'edit', label: '编辑', visible: canManageRoles.value, handler: asRoleHandler(handleEdit) },
      { id: 'delete', label: '删除', destructive: true, risk: 'destructive', visible: canManageRoles.value, handler: asRoleHandler((role) => { void handleDelete(role) }) },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canManageRoles],
  actions: () => [{
    id: 'create-role',
    label: '新建角色',
    type: 'primary',
    icon: Plus,
    visible: canManageRoles.value,
    handler: showCreateDialog,
  }],
})

const handleSearchApply = (value: string): void => {
  submittedSearch.value = value.trim()
}

const handleSearchClear = (): void => {
  submittedSearch.value = ''
}

function formatDate(dateStr: string): string {
  if (dateStr.length === 0) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

watch([hasAccess, teamId], (): void => {
  if (!hasAccess.value) return
  void loadRoles()
}, { immediate: true })




watch(() => route.query['action'], (action) => {
  if (action === 'create' && canManageRoles.value) showCreateDialog()
}, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="角色管理" description="配置角色、权限集合和角色成员。短任务继续用对话框。">
    <ErrorState
      v-if="permissionsUnavailable"
      variant="error"
      title="权限信息暂不可用"
      description="暂时无法确认你的团队设置权限。请重试权限同步，避免在权限不明确时继续操作。"
    >
      <template #action>
        <Button :loading="retryingPermissions" @click="retryPermissions">
          {{ retryingPermissions ? '同步中…' : '重试权限同步' }}
        </Button>
      </template>
    </ErrorState>
    <ErrorState
      v-else-if="permissionsPending"
      variant="error"
      title="正在同步权限"
      description="正在确认你的访问权限，请稍候。"
    />
    <ErrorState
      v-else-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问角色管理的权限，请联系团队所有者或管理员。"
    />
    <DataTable
      v-else

      :fields="fields"
      :data="displayedRoles"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedRoles.length, 1)"
      :total="displayedRoles.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无角色数据"
      :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
      :get-row-actions="getRowActions"
      mobile-title-key="name"
      :mobile-meta-keys="['code']"
      search-enabled
      :search="submittedSearch"
      search-placeholder="搜索角色代码、名称"
      :search-loading="loading"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @retry="loadRoles"
    >
      <template #cell-name="{ row }">
        <div class="font-medium text-wolf-text-primary">{{ row.name }}</div>
        <div v-if="row.description" class="mt-1 text-sm text-muted-foreground">
          {{ row.description }}
        </div>
      </template>
      <template #cell-code="{ row }">
        <Badge variant="outline">{{ row.code }}</Badge>
      </template>
      <template #cell-updated_at="{ row }">
        {{ formatDate(row.updated_at) }}
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>

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
                    {{ getActionName(permission.action) }}
                  </Badge>
                  <span class="text-sm">{{ permission.name }}</span>
                  <code class="text-xs text-muted-foreground">{{ permission.code }}</code>
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
