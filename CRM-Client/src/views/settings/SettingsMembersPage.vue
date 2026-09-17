<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Search, Loader2, Plus } from 'lucide-vue-next'
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
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete } from '@/utils/confirmDialog'
import { teamApi } from '@/api/team'
import type { TeamMemberResponse } from '@/api/team'
import userApi from '@/api/user'
import type { UserSearchResult } from '@/api/user'
import roleApi from '@/api/role'
import type { RoleResponse } from '@/api/role'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
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

const userStore = useUserStore()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { isOwner } = useSettingsAccess()

const submittedSearch = ref('')
const members = ref<TeamMemberResponse[]>([])
const loading = ref(false)
const loadError = ref<FeedbackError | null>(null)
const listRequestId = ref(0)
const searchLoading = ref(false)

const inviteDialogOpen = ref(false)
const inviteEmail = ref('')
const searchResults = ref<UserSearchResult[]>([])
const hasSearched = ref(false)

const roleDialogOpen = ref(false)
const selectedMember = ref<TeamMemberResponse | null>(null)
const selectedRoleIds = ref<number[]>([])
const availableRoles = ref<RoleResponse[]>([])
const saveRolesLoading = ref(false)

const resetPasswordDialogOpen = ref(false)
const resetPasswordTargetUser = ref<TeamMemberResponse | null>(null)
const resetPasswordSubmitting = ref(false)

const updateNameDialogOpen = ref(false)
const updateNameTargetUser = ref<TeamMemberResponse | null>(null)
const updateNameSubmitting = ref(false)
const updateNameValue = ref('')
const updateNameError = ref('')

const updateNameSchema = z.string()
  .trim()
  .min(1, '用户名不能为空')
  .max(100, '用户名不能超过100个字符')

const resetPasswordSchema = toTypedSchema(
  z.object({
    newPassword: z.string()
      .min(6, '密码长度为6-50个字符')
      .max(50, '密码长度为6-50个字符'),
    confirmPassword: z.string()
  }).refine((data) => data.newPassword === data.confirmPassword, {
    message: '两次输入的密码不一致',
    path: ['confirmPassword']
  })
)

const { handleSubmit: handleResetPasswordSubmit, resetForm: resetPasswordResetForm } = useForm({
  validationSchema: resetPasswordSchema,
  initialValues: {
    newPassword: '',
    confirmPassword: ''
  }
})

const currentUserId = computed(() => String(userStore.userInfo?.id ?? ''))
const teamId = computed(() => teamStore.currentTeam?.id)

const canManageMembers = computed(() => {
  if (isOwner.value) return true
  return permissionStore.hasAnyPermission([
    'team:member:invite',
    'team:member:update',
    'team:member:password_reset',
    'team:member:remove',
    'role:manage',
  ])
})
const canInviteMembers = computed(() => isOwner.value || permissionStore.hasAnyPermission(['team:member:invite', 'role:manage']))
const canUpdateMembers = computed(() => isOwner.value || permissionStore.hasAnyPermission(['team:member:update', 'role:manage']))
const canResetMemberPasswords = computed(() => isOwner.value || permissionStore.hasAnyPermission(['team:member:password_reset', 'role:manage']))
const canRemoveMembers = computed(() => isOwner.value || permissionStore.hasAnyPermission(['team:member:remove', 'role:manage']))

const displayedMembers = computed(() => {
  const query = submittedSearch.value.trim().toLowerCase()
  if (query.length === 0) return members.value
  return members.value.filter((member) => {
    const name = member.name.toLowerCase()
    const email = member.email.toLowerCase()
    return name.includes(query) || email.includes(query)
  })
})

const fields: ListFieldDefinition[] = defineListFields([
  settingsListColumn({ key: 'member', label: '成员', column: { fixed: 'left' } }),
  settingsListColumn({ key: 'roles', label: '角色', column: true }),
  settingsListColumn({ key: 'joined_at', label: '加入时间', column: true }),
])

const currentTeamId = (): number | null => teamId.value ?? null

const loadMembers = async (): Promise<void> => {
  const id = currentTeamId()
  if (id === null) return
  const requestId = ++listRequestId.value
  loading.value = true
  loadError.value = null
  try {
    const response = await teamApi.getTeamMembers(id)
    if (requestId !== listRequestId.value) return
    members.value = response
  } catch (error) {
    if (requestId !== listRequestId.value) return
    loadError.value = toFeedbackError(error, '团队成员')
  } finally {
    if (requestId === listRequestId.value) {
      loading.value = false
    }
  }
}

const fetchAvailableRoles = async (): Promise<void> => {
  try {
    const response = await roleApi.getRoles()
    availableRoles.value = response
  } catch (error) {
    handleApiError(error, '获取角色列表')
  }
}

const showInviteDialog = (): void => {
  inviteEmail.value = ''
  searchResults.value = []
  hasSearched.value = false
  inviteDialogOpen.value = true
}

const handleSearchEmail = async (): Promise<void> => {
  const email = inviteEmail.value.trim()
  if (email.length === 0) {
    toast.warning('请输入邮箱')
    return
  }

  searchLoading.value = true
  hasSearched.value = false
  try {
    const response = await userApi.searchUsers(email)
    searchResults.value = response
    hasSearched.value = true
  } catch (error) {
    handleApiError(error, '搜索用户')
    hasSearched.value = true
  } finally {
    searchLoading.value = false
  }
}

const isInTeam = (userId: number): boolean => {
  return members.value.some(m => Number(m.id) === userId)
}

const handleInviteUser = async (user: UserSearchResult): Promise<void> => {
  const id = currentTeamId()
  if (id === null) return

  try {
    await teamApi.addMemberDirect(id, user.id)
    toast.success(`${user.name} 已加入团队`)
    inviteDialogOpen.value = false
    void loadMembers()
  } catch (error) {
    handleApiError(error, '邀请成员')
  }
}

const handleAssignRoles = (member: TeamMemberResponse): void => {
  selectedMember.value = member
  selectedRoleIds.value = member.roles?.map(r => r.id) ?? []
  roleDialogOpen.value = true
}

const handleSaveRoles = async (): Promise<void> => {
  const id = currentTeamId()
  if (id === null || selectedMember.value === null) return

  saveRolesLoading.value = true
  try {
    await teamApi.assignMemberRoles(id, selectedMember.value.id, selectedRoleIds.value)
    toast.success('角色已分配')
    roleDialogOpen.value = false
    void loadMembers()
  } catch (error) {
    handleApiError(error, '分配角色')
  } finally {
    saveRolesLoading.value = false
  }
}

const showUpdateNameDialog = (member: TeamMemberResponse): void => {
  updateNameTargetUser.value = member
  updateNameValue.value = member.name
  updateNameError.value = ''
  updateNameDialogOpen.value = true
}

const onUpdateNameSubmit = async (event?: Event): Promise<void> => {
  event?.preventDefault()
  if (teamId.value === undefined || updateNameTargetUser.value === null) return

  const parsedName = updateNameSchema.safeParse(updateNameValue.value)
  if (!parsedName.success) {
    updateNameError.value = parsedName.error.issues[0]?.message ?? '用户名格式不正确'
    return
  }

  updateNameError.value = ''
  updateNameSubmitting.value = true
  try {
    const response = await teamApi.updateMemberName(
      teamId.value,
      updateNameTargetUser.value.id,
      { name: parsedName.data }
    )
    toast.success(`已将用户名修改为 ${response.name}`)
    updateNameDialogOpen.value = false
    await loadMembers()
  } catch (error) {
    handleApiError(error, '修改用户名')
  } finally {
    updateNameSubmitting.value = false
  }
}

const showResetPasswordDialog = (member: TeamMemberResponse): void => {
  resetPasswordTargetUser.value = member
  resetPasswordResetForm({
    values: {
      newPassword: '',
      confirmPassword: ''
    }
  })
  resetPasswordDialogOpen.value = true
}

const onResetPasswordSubmit = handleResetPasswordSubmit(async (formValues) => {
  const id = currentTeamId()
  if (id === null || resetPasswordTargetUser.value === null) return

  resetPasswordSubmitting.value = true
  try {
    await teamApi.resetMemberPassword(
      id,
      resetPasswordTargetUser.value.id,
      { new_password: formValues.newPassword }
    )
    toast.success(`已重置 ${resetPasswordTargetUser.value.name} 的密码`)
    resetPasswordDialogOpen.value = false
  } catch (error) {
    handleApiError(error, '重置密码')
  } finally {
    resetPasswordSubmitting.value = false
  }
})

const handleRemoveMember = async (member: TeamMemberResponse): Promise<void> => {
  const confirmed = await confirmDelete(`成员"${member.name}"`)
  const id = currentTeamId()
  if (!confirmed || id === null) return

  try {
    await teamApi.removeMember(id, member.id.toString())
    toast.success('成员已移除')
    void loadMembers()
  } catch (error) {
    handleApiError(error, '移除成员')
  }
}

const asMemberHandler = (handler: (row: TeamMemberResponse) => void): ActionConfig['handler'] => {
  return (row) => { handler(row as TeamMemberResponse) }
}

const getRowActions = (row: TeamMemberResponse): TableRowActionSet => {
  const isSelf = row.id === currentUserId.value
  return {
    primaryActions: [{
      id: 'assign',
      label: '分配角色',
      desktopPrimary: true,
      visible: !isSelf && canManageMembers.value,
      handler: asMemberHandler(handleAssignRoles),
    }],
    secondaryActions: [
      { label: '修改用户名', visible: !isSelf && canUpdateMembers.value, handler: asMemberHandler(showUpdateNameDialog) },
      { label: '重置密码', visible: !isSelf && canResetMemberPasswords.value, handler: asMemberHandler(showResetPasswordDialog) },
      { id: 'delete', label: '移除', destructive: true, risk: 'destructive', visible: !isSelf && canRemoveMembers.value, handler: asMemberHandler((member) => { void handleRemoveMember(member) }) },
    ],
  }
}

useTopBarRegistration({
  actionDeps: [canInviteMembers],
  actions: () => [{
    id: 'invite-member',
    label: '邀请成员',
    type: 'primary',
    icon: Plus,
    visible: canInviteMembers.value,
    handler: showInviteDialog,
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

function handleRoleChange(roleId: number, checked: boolean): void {
  if (checked) {
    if (!selectedRoleIds.value.includes(roleId)) {
      selectedRoleIds.value.push(roleId)
    }
  } else {
    selectedRoleIds.value = selectedRoleIds.value.filter(id => id !== roleId)
  }
}

watch(() => teamStore.currentTeam?.id, () => {
  void loadMembers()
  void fetchAvailableRoles()
}, { immediate: true })
</script>

<template>
  <SettingsContent ariaLabel="团队成员" description="管理当前团队成员、邀请和角色。邀请、改名、重置密码等短任务继续用对话框。">
    <DataTable
      :fields="fields"
      :data="displayedMembers"
      :loading="loading"
      :load-error="loadError"
      :page="1"
      :page-size="Math.max(displayedMembers.length, 1)"
      :total="displayedMembers.length"
      height-strategy="page"
      scroll-mode="page"
      compact-pagination
      empty-title="暂无团队成员"
      :empty-reason="submittedSearch.trim() !== '' ? 'filtered' : 'not-created'"
      :get-row-actions="getRowActions"
      mobile-title-key="name"
      :mobile-meta-keys="['email']"
      search-enabled
      :search="submittedSearch"
      search-placeholder="搜索姓名、邮箱"
      :search-loading="loading"
      @search-apply="handleSearchApply"
      @search-clear="handleSearchClear"
      @retry="loadMembers"
    >
      <template #cell-member="{ row }">
        <div class="flex items-center gap-3">
          <div v-if="row.avatar_url" class="h-9 w-9 overflow-hidden rounded-full">
            <img :src="row.avatar_url" alt="头像" class="h-full w-full object-cover" />
          </div>
          <div v-else class="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
            {{ row.name?.charAt(0) || 'U' }}
          </div>
          <div class="min-w-0">
            <div class="font-medium text-wolf-text-primary">{{ row.name }}</div>
            <div class="mt-1 text-xs text-muted-foreground">
              {{ row.email }}
            </div>
          </div>
        </div>
      </template>
      <template #cell-roles="{ row }">
        <Badge v-for="role in row.roles" :key="role.id" variant="outline">{{ role.name }}</Badge>
        <Badge v-if="row.roles.length === 0" variant="secondary">暂无角色</Badge>
      </template>
      <template #cell-joined_at="{ row }">
        {{ formatDate(row.joined_at) }}
      </template>
      <template #mobile-actions="{ row }">
        <TableRowActions :row="row" v-bind="getRowActions(row)" size="lg" />
      </template>
    </DataTable>
  </SettingsContent>

  <!-- 邀请成员 Dialog (z-[1000]) -->
  <Dialog v-model:open="inviteDialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>邀请成员</DialogTitle>
        <DialogDescription>
          通过邮箱搜索用户并邀请加入团队
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <div class="flex gap-2">
          <Input
            v-model="inviteEmail"
            placeholder="输入用户邮箱"
            class="flex-1"
          />
          <Button :loading="searchLoading" @click="handleSearchEmail">
            <Search class="w-4 h-4 mr-2" />
            搜索
          </Button>
        </div>

        <!-- 搜索加载 -->
        <div v-if="searchLoading" class="flex items-center justify-center py-8">
          <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
          <span class="ml-2 text-muted-foreground">搜索中...</span>
        </div>

        <!-- 搜索结果 -->
        <div v-else-if="hasSearched && searchResults.length > 0" class="space-y-2">
          <div class="text-sm text-muted-foreground">找到以下用户:</div>
          <div
            v-for="user in searchResults"
            :key="user.id"
            class="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
          >
            <div class="flex items-center gap-3">
              <div v-if="user.avatar_url" class="w-10 h-10 rounded-full overflow-hidden">
                <img :src="user.avatar_url" alt="头像" class="w-full h-full object-cover" />
              </div>
              <div v-else class="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold">
                {{ user.name?.charAt(0) || 'U' }}
              </div>
              <div>
                <div class="font-medium">{{ user.name }}</div>
                <div class="text-sm text-muted-foreground">{{ user.email }}</div>
              </div>
            </div>
            <Badge v-if="isInTeam(user.id)" variant="secondary">已在团队中</Badge>
            <Button v-else size="sm" @click="handleInviteUser(user)">邀请</Button>
          </div>
        </div>

        <!-- 无结果 -->
        <div v-else-if="hasSearched && searchResults.length === 0" class="text-center py-8 text-muted-foreground">
          未找到该用户
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="inviteDialogOpen = false">关闭</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 分配角色 Dialog (z-[1000]) -->
  <Dialog v-model:open="roleDialogOpen">
    <DialogContent class="max-w-lg z-[1000]">
      <DialogHeader>
        <DialogTitle>分配角色</DialogTitle>
        <DialogDescription>
          为成员分配团队角色
        </DialogDescription>
      </DialogHeader>

      <div v-if="selectedMember" class="space-y-4">
        <!-- 成员信息 -->
        <div class="flex items-center gap-3 pb-4 border-b">
          <div v-if="selectedMember.avatar_url" class="w-12 h-12 rounded-full overflow-hidden">
            <img :src="selectedMember.avatar_url" alt="头像" class="w-full h-full object-cover" />
          </div>
          <div v-else class="w-12 h-12 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold">
            {{ selectedMember.name?.charAt(0) || 'U' }}
          </div>
          <div>
            <div class="font-medium">{{ selectedMember.name }}</div>
            <div class="text-sm text-muted-foreground">{{ selectedMember.email }}</div>
          </div>
        </div>

        <!-- 角色选择 -->
        <div class="space-y-3">
          <div
            v-for="role in availableRoles"
            :key="role.id"
            class="flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
          >
            <Checkbox
              :id="`role-${role.id}`"
              :checked="selectedRoleIds.includes(role.id)"
              @update:checked="handleRoleChange(role.id, $event)"
            />
            <Label :for="`role-${role.id}`" class="flex-1 cursor-pointer">
              <div class="font-medium">{{ role.name }}</div>
              <div class="text-xs text-muted-foreground">{{ role.code }}</div>
            </Label>
          </div>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="roleDialogOpen = false">取消</Button>
        <Button :loading="saveRolesLoading" @click="handleSaveRoles">
          {{ saveRolesLoading ? '保存中...' : '保存' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 修改用户名 Dialog (z-[1000]) -->
  <Dialog v-model:open="updateNameDialogOpen">
    <DialogContent class="max-w-md z-[1000]">
      <DialogHeader>
        <DialogTitle>修改用户名 - {{ updateNameTargetUser?.name }}</DialogTitle>
        <DialogDescription>
          修改该成员在系统中的显示名称
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onUpdateNameSubmit">
        <div class="space-y-2">
          <Label for="member-name">用户名 <span class="text-destructive">*</span></Label>
          <Input
            id="member-name"
            v-model="updateNameValue"
            placeholder="请输入用户名"
            :aria-invalid="updateNameError ? 'true' : 'false'"
            @input="updateNameError = ''"
          />
          <p v-if="updateNameError" class="text-sm font-medium text-destructive">{{ updateNameError }}</p>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" @click="updateNameDialogOpen = false">取消</Button>
          <Button type="submit" :loading="updateNameSubmitting">
            {{ updateNameSubmitting ? '保存中...' : '保存' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- 重置密码 Dialog (z-[1000]) -->
  <Dialog v-model:open="resetPasswordDialogOpen">
    <DialogContent class="max-w-md z-[1000]">
      <DialogHeader>
        <DialogTitle>重置密码 - {{ resetPasswordTargetUser?.name }}</DialogTitle>
        <DialogDescription>
          为成员设置新密码
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit="onResetPasswordSubmit">
        <FormField v-slot="{ componentField }" name="newPassword">
          <FormItem>
            <FormLabel>新密码 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                type="password"
                placeholder="请输入新密码（6-50位）"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormField v-slot="{ componentField }" name="confirmPassword">
          <FormItem>
            <FormLabel>确认密码 <span class="text-destructive">*</span></FormLabel>
            <FormControl>
              <Input
                v-bind="componentField as unknown as Record<string, unknown>"
                type="password"
                placeholder="请再次输入新密码"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <DialogFooter>
          <Button type="button" variant="outline" @click="resetPasswordDialogOpen = false">取消</Button>
          <Button type="submit" :loading="resetPasswordSubmitting">
            {{ resetPasswordSubmitting ? '提交中...' : '确认重置' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
