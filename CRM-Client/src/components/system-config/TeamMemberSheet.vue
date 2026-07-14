<script setup lang="ts">
/**
 * TeamMemberSheet.vue - 团队成员管理 Sheet
 *
 * 功能：
 * - 展示团队成员列表（DataTable）
 * - 邀请成员（Dialog）
 * - 分配角色（Dialog）
 * - 重置成员密码（Dialog）
 * - 移除成员
 * - 重置邀请码
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
import { Search, Plus, RefreshCw, UserPlus, Key, Shield, Trash2, Loader2 } from 'lucide-vue-next'
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
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDialog, confirmDelete } from '@/utils/confirmDialog'
import teamApi, {
  type TeamMemberResponse,
  type TeamResponse,
  type RoleSimpleResponse
} from '@/api/team'
import userApi, { type UserSearchResult } from '@/api/user'
import roleApi, { type RoleResponse } from '@/api/role'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { authApi } from '@/api/auth'

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const userStore = useUserStore()
const teamStore = useTeamStore()

// ==================== State ====================
const loading = ref(false)
const codeLoading = ref(false)
const searchLoading = ref(false)
const members = ref<TeamMemberResponse[]>([])
const team = ref<TeamResponse | null>(null)
const searchText = ref('')
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 邀请成员 Dialog
const inviteDialogOpen = ref(false)
const inviteEmail = ref('')
const searchResults = ref<UserSearchResult[]>([])
const hasSearched = ref(false)

// 角色分配 Dialog
const roleDialogOpen = ref(false)
const selectedMember = ref<TeamMemberResponse | null>(null)
const selectedRoleIds = ref<number[]>([])
const availableRoles = ref<RoleResponse[]>([])
const saveRolesLoading = ref(false)

// 重置密码 Dialog
const resetPasswordDialogOpen = ref(false)
const resetPasswordTargetUser = ref<TeamMemberResponse | null>(null)
const resetPasswordSubmitting = ref(false)

// ==================== Zod Schema ====================
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

// ==================== Types ====================
interface Column {
  key: string
  title: string
  width?: string
  align?: 'left' | 'center' | 'right'
  fixed?: 'left' | 'right'
}

// ==================== Computed ====================
const currentUserId = computed(() => userStore.userInfo?.id)
const teamId = computed(() => teamStore.currentTeam?.id)

const isTeamAdmin = computed(() => {
  // TODO: Get current user roles in current team
  return true // For now, allow all operations
})

const filteredMembers = computed(() => {
  if (!searchText.value) return members.value
  const search = searchText.value.toLowerCase()
  return members.value.filter(member =>
    member.name.toLowerCase().includes(search) ||
    member.email.toLowerCase().includes(search)
  )
})

// ==================== Table Columns ====================
const columns: Column[] = [
  {
    key: 'name',
    title: '姓名',
    width: '150px',
    fixed: 'left'
  },
  {
    key: 'email',
    title: '邮箱',
    width: '200px'
  },
  {
    key: 'current_team',
    title: '当前团队',
    width: '100px',
    align: 'center'
  },
  {
    key: 'joined_at',
    title: '加入时间',
    width: '160px'
  },
  {
    key: 'roles',
    title: '角色',
    width: '200px'
  },
  {
    key: 'actions',
    title: '操作',
    width: '220px',
    fixed: 'right',
    align: 'center'
  }
]

// ==================== API Methods ====================
const fetchTeamInfo = async (): Promise<void> => {
  if (!teamId.value) return
  try {
    const response = await teamApi.getTeamDetail(teamId.value)
    team.value = response
  } catch (error) {
    handleApiError(error, '获取团队信息')
  }
}

const fetchMembers = async (): Promise<void> => {
  if (!teamId.value) return
  loading.value = true
  try {
    const response = await teamApi.getTeamMembers(teamId.value)
    members.value = response
    pagination.value.total = members.value.length
  } catch (error) {
    handleApiError(error, '获取成员列表')
  } finally {
    loading.value = false
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

// ==================== Invite Member ====================
const showInviteDialog = (): void => {
  inviteEmail.value = ''
  searchResults.value = []
  hasSearched.value = false
  inviteDialogOpen.value = true
}

const handleSearchEmail = async (): Promise<void> => {
  if (!inviteEmail.value || inviteEmail.value.trim().length === 0) {
    toast.warning('请输入邮箱')
    return
  }

  searchLoading.value = true
  hasSearched.value = false
  try {
    const response = await userApi.searchUsers(inviteEmail.value.trim())
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
  if (!teamId.value) return

  try {
    await teamApi.addMemberDirect(teamId.value, user.id)
    toast.success(`${user.name} 已加入团队`)
    inviteDialogOpen.value = false
    fetchMembers()
  } catch (error) {
    handleApiError(error, '邀请成员')
  }
}

// ==================== Role Assignment ====================
const handleAssignRoles = (member: TeamMemberResponse): void => {
  selectedMember.value = member
  selectedRoleIds.value = member.roles?.map(r => r.id) || []
  roleDialogOpen.value = true
}

const handleSaveRoles = async (): Promise<void> => {
  if (!teamId.value || !selectedMember.value) return

  saveRolesLoading.value = true
  try {
    await teamApi.assignMemberRoles(teamId.value, selectedMember.value.id, selectedRoleIds.value)
    toast.success('角色已分配')
    roleDialogOpen.value = false
    fetchMembers()
  } catch (error) {
    handleApiError(error, '分配角色')
  } finally {
    saveRolesLoading.value = false
  }
}

// ==================== Reset Password ====================
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
  if (!teamId.value || !resetPasswordTargetUser.value) return

  resetPasswordSubmitting.value = true
  try {
    await teamApi.resetMemberPassword(
      teamId.value,
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

// ==================== Remove Member ====================
const handleRemoveMember = async (member: TeamMemberResponse): Promise<void> => {
  const confirmed = await confirmDelete(`成员"${member.name}"`)
  if (!confirmed || !teamId.value) return

  try {
    await teamApi.removeMember(teamId.value, member.id.toString())
    toast.success('成员已移除')
    fetchMembers()
  } catch (error) {
    handleApiError(error, '移除成员')
  }
}

// ==================== Regenerate Invite Code ====================
const handleRegenerateCode = async (): Promise<void> => {
  if (!teamId.value) return

  const confirmed = await confirmDialog(
    '确定要重置邀请码吗？重置后旧邀请码将失效。',
    '重置邀请码'
  )
  if (!confirmed) return

  codeLoading.value = true
  try {
    const response = await teamApi.regenerateInviteCode(teamId.value)
    if (team.value) {
      team.value = { ...team.value, code: response.code }
    }
    toast.success('邀请码已重置')
  } catch (error) {
    handleApiError(error, '重置邀请码')
  } finally {
    codeLoading.value = false
  }
}

// ==================== Lifecycle ====================
watch(() => props.open, (open) => {
  if (open) {
    fetchTeamInfo()
    fetchMembers()
    fetchAvailableRoles()
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

function handleRoleChange(roleId: number, checked: boolean): void {
  if (checked) {
    if (!selectedRoleIds.value.includes(roleId)) {
      selectedRoleIds.value.push(roleId)
    }
  } else {
    selectedRoleIds.value = selectedRoleIds.value.filter(id => id !== roleId)
  }
}
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <SheetHeader>
      <SheetTitle>团队成员</SheetTitle>
      <SheetDescription>管理团队成员与角色分配</SheetDescription>
    </SheetHeader>
    <DetailSheetContent>
      <ScrollArea class="h-full">
        <!-- 团队信息 -->
        <div class="p-4 border-b">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-semibold">{{ team?.name || '团队管理' }}</h3>
              <p class="text-sm text-muted-foreground">邀请码: {{ team?.code }}</p>
            </div>
            <div class="flex items-center gap-2">
              <Button @click="showInviteDialog">
                <UserPlus class="w-4 h-4 mr-2" />
                邀请成员
              </Button>
              <Button variant="outline" :loading="codeLoading" @click="handleRegenerateCode">
                <RefreshCw class="w-4 h-4 mr-2" />
                重置邀请码
              </Button>
            </div>
          </div>
        </div>

        <!-- 搜索栏 -->
        <div class="p-4 border-b">
          <div class="relative">
            <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              v-model="searchText"
              placeholder="搜索成员姓名、邮箱"
              class="pl-10"
            />
          </div>
        </div>

        <!-- 表格区域 -->
        <div class="p-4">
          <DataTable
            :columns="columns"
            :data="filteredMembers"
            :loading="loading"
            :total="pagination.total"
            :page="pagination.page"
            :page-size="pagination.pageSize"
            height="calc(100vh - 400px)"
            empty-title="暂无团队成员"
          >
            <!-- 姓名列 -->
            <template #cell-name="{ row }">
              <div class="flex items-center gap-2">
                <div v-if="row.avatar_url" class="w-8 h-8 rounded-full overflow-hidden">
                  <img :src="row.avatar_url" alt="头像" class="w-full h-full object-cover" />
                </div>
                <div v-else class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-sm font-semibold">
                  {{ row.name?.charAt(0) || 'U' }}
                </div>
                <span class="font-medium">{{ row.name }}</span>
              </div>
            </template>

            <!-- 当前团队列 -->
            <template #cell-current_team="{ row }">
              <Badge :variant="row.current_team ? 'default' : 'secondary'">
                {{ row.current_team ? '是' : '否' }}
              </Badge>
            </template>

            <!-- 加入时间列 -->
            <template #cell-joined_at="{ row }">
              {{ formatDate(row.joined_at) }}
            </template>

            <!-- 角色列 -->
            <template #cell-roles="{ row }">
              <div class="flex items-center gap-1 flex-wrap">
                <Badge
                  v-for="role in row.roles"
                  :key="role.id"
                  variant="outline"
                  class="text-xs"
                >
                  {{ role.name }}
                </Badge>
                <span v-if="!row.roles || row.roles.length === 0" class="text-muted-foreground text-sm">
                  暂无角色
                </span>
              </div>
            </template>

            <!-- 操作列 -->
            <template #cell-actions="{ row }">
              <div class="flex items-center justify-center gap-1">
                <Button
                  v-if="row.id !== currentUserId && isTeamAdmin"
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  @click="showResetPasswordDialog(row)"
                >
                  <Key class="w-3.5 h-3.5 mr-1" />
                  重置密码
                </Button>
                <Button
                  v-if="row.id !== currentUserId && isTeamAdmin"
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2"
                  @click="handleAssignRoles(row)"
                >
                  <Shield class="w-3.5 h-3.5 mr-1" />
                  分配角色
                </Button>
                <Button
                  v-if="row.id !== currentUserId && isTeamAdmin"
                  variant="ghost"
                  size="sm"
                  class="h-8 px-2 text-destructive hover:text-destructive"
                  @click="handleRemoveMember(row)"
                >
                  <Trash2 class="w-3.5 h-3.5 mr-1" />
                  移除
                </Button>
              </div>
            </template>
          </DataTable>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>

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
          <Button variant="outline" @click="resetPasswordDialogOpen = false">取消</Button>
          <Button type="submit" :loading="resetPasswordSubmitting">
            {{ resetPasswordSubmitting ? '提交中...' : '确认重置' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>