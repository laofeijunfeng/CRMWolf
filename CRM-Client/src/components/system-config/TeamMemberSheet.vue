<script setup lang="ts">
/**
 * TeamMemberSheet.vue - 团队成员管理 Sheet
 *
 * 功能：
 * - 展示团队成员列表（ListCard）
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
import { Search, RefreshCw, UserPlus, Key, Shield, Trash2, Loader2, Pencil, Copy } from 'lucide-vue-next'
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
import { ListCard } from '@/components/crmwolf'
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
import {
  teamApi,
  type TeamMemberResponse,
  type TeamResponse
} from '@/api/team'
import userApi, { type UserSearchResult } from '@/api/user'
import roleApi, { type RoleResponse } from '@/api/role'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'

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

// 修改用户名 Dialog
const updateNameDialogOpen = ref(false)
const updateNameTargetUser = ref<TeamMemberResponse | null>(null)
const updateNameSubmitting = ref(false)
const updateNameValue = ref('')
const updateNameError = ref('')

// ==================== Zod Schema ====================
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

// ==================== Computed ====================
const currentUserId = computed(() => String(userStore.userInfo?.id ?? ''))
const teamId = computed(() => teamStore.currentTeam?.id)

const isTeamAdmin = computed(() => {
  // TODO: Get current user roles in current team
  return true // For now, allow all operations
})

const filteredMembers = computed(() => {
  const search = searchText.value.trim().toLowerCase()
  if (search.length === 0) return members.value
  return members.value.filter(member =>
    member.name.toLowerCase().includes(search) ||
    member.email.toLowerCase().includes(search)
  )
})

const inviteLink = computed(() => {
  const code = team.value?.code
  if (code === undefined || code.length === 0) return ''
  return `${window.location.origin}/invite/${code}`
})

const listTitle = computed(() => `成员列表（${filteredMembers.value.length}）`)

// ==================== API Methods ====================
const currentTeamId = (): number | null => teamId.value ?? null

const fetchTeamInfo = async (): Promise<void> => {
  const id = currentTeamId()
  if (id === null) return
  try {
    const response = await teamApi.getTeamDetail(id)
    team.value = response
  } catch (error) {
    handleApiError(error, '获取团队信息')
  }
}

const fetchMembers = async (): Promise<void> => {
  const id = currentTeamId()
  if (id === null) return
  loading.value = true
  try {
    const response = await teamApi.getTeamMembers(id)
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
    fetchMembers()
  } catch (error) {
    handleApiError(error, '邀请成员')
  }
}

// ==================== Role Assignment ====================
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
    fetchMembers()
  } catch (error) {
    handleApiError(error, '分配角色')
  } finally {
    saveRolesLoading.value = false
  }
}

// ==================== Update Member Name ====================
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
    await fetchMembers()
  } catch (error) {
    handleApiError(error, '修改用户名')
  } finally {
    updateNameSubmitting.value = false
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

// ==================== Remove Member ====================
const handleRemoveMember = async (member: TeamMemberResponse): Promise<void> => {
  const confirmed = await confirmDelete(`成员"${member.name}"`)
  const id = currentTeamId()
  if (!confirmed || id === null) return

  try {
    await teamApi.removeMember(id, member.id.toString())
    toast.success('成员已移除')
    fetchMembers()
  } catch (error) {
    handleApiError(error, '移除成员')
  }
}

// ==================== Regenerate Invite Code ====================
const handleRegenerateCode = async (): Promise<void> => {
  const id = currentTeamId()
  if (id === null) return

  const confirmed = await confirmDialog(
    '确定要重置邀请码吗？重置后旧邀请码将失效。',
    '重置邀请码'
  )
  if (!confirmed) return

  codeLoading.value = true
  try {
    const response = await teamApi.regenerateInviteCode(id)
    if (team.value !== null) {
      team.value = { ...team.value, code: response.code }
    }
    toast.success('邀请码已重置')
  } catch (error) {
    handleApiError(error, '重置邀请码')
  } finally {
    codeLoading.value = false
  }
}

const handleCopyInviteLink = async (): Promise<void> => {
  if (inviteLink.value.length === 0) return
  try {
    await navigator.clipboard.writeText(inviteLink.value)
    toast.success('邀请链接已复制')
  } catch {
    toast.warning('复制失败，请手动复制')
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
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent>
      <SheetHeader class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">团队成员</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">管理团队成员与角色分配</SheetDescription>
      </SheetHeader>
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
              <Button variant="outline" :disabled="!inviteLink" @click="handleCopyInviteLink">
                <Copy class="w-4 h-4 mr-2" />
                复制邀请链接
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

        <!-- 列表区域 -->
        <div class="p-4">
          <ListCard
            :title="listTitle"
            :items="filteredMembers"
            :loading="loading"
            empty-text="暂无团队成员"
          >
            <template #itemMain="{ item }">
              <div class="flex items-center gap-3">
                <div v-if="item.avatar_url" class="h-9 w-9 overflow-hidden rounded-full">
                  <img :src="item.avatar_url" alt="头像" class="h-full w-full object-cover" />
                </div>
                <div v-else class="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  {{ item.name?.charAt(0) || 'U' }}
                </div>
                <div class="min-w-0">
                  <div class="font-medium text-wolf-text-primary">{{ item.name }}</div>
                  <div class="mt-1 text-xs text-muted-foreground">
                    {{ item.email }} · {{ formatDate(item.joined_at) }}
                  </div>
                </div>
              </div>
            </template>

            <template #itemBadges="{ item }">
              <Badge :variant="item.current_team ? 'default' : 'secondary'">
                {{ item.current_team ? '当前团队' : '其他团队' }}
              </Badge>
              <Badge
                v-for="role in item.roles"
                :key="role.id"
                variant="outline"
              >
                {{ role.name }}
              </Badge>
              <Badge v-if="!item.roles || item.roles.length === 0" variant="secondary">暂无角色</Badge>
            </template>

            <template #itemActions="{ item }">
              <Button
                v-if="item.id !== currentUserId && isTeamAdmin"
                variant="ghost"
                size="icon"
                title="修改用户名"
                @click="showUpdateNameDialog(item)"
              >
                <Pencil class="h-4 w-4" />
              </Button>
              <Button
                v-if="item.id !== currentUserId && isTeamAdmin"
                variant="ghost"
                size="icon"
                title="重置密码"
                @click="showResetPasswordDialog(item)"
              >
                <Key class="h-4 w-4" />
              </Button>
              <Button
                v-if="item.id !== currentUserId && isTeamAdmin"
                variant="ghost"
                size="icon"
                title="分配角色"
                @click="handleAssignRoles(item)"
              >
                <Shield class="h-4 w-4" />
              </Button>
              <Button
                v-if="item.id !== currentUserId && isTeamAdmin"
                variant="ghost"
                size="icon"
                title="移除"
                class="text-destructive hover:text-destructive"
                @click="handleRemoveMember(item)"
              >
                <Trash2 class="h-4 w-4" />
              </Button>
            </template>
          </ListCard>
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

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
}
</style>
