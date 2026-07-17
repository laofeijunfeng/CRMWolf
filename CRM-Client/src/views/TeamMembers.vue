<template>
  <div class="team-members-container">
    <div class="wolf-card header-card">
      <div class="header-content">
        <div class="team-info">
          <h2>{{ team?.name || '团队管理' }}</h2>
          <span class="invite-code">邀请码: {{ team?.code }}</span>
        </div>
        <div class="header-actions">
          <el-button type="primary" class="wolf-btn wolf-btn--primary-sm" @click="showInviteDialog">
            <el-icon><Plus /></el-icon>
            邀请成员
          </el-button>
          <el-button class="wolf-btn wolf-btn--default" @click="handleRegenerateCode" :loading="codeLoading">
            <el-icon><Refresh /></el-icon>
            重置邀请码
          </el-button>
        </div>
      </div>
    </div>

    <div class="wolf-card table-card">
      <div class="wolf-table-wrapper">
        <el-table :data="members" v-loading="loading" class="wolf-table">
          <el-table-column prop="name" label="姓名" min-width="120">
            <template #default="{ row }">
              <div class="member-cell">
                <div v-if="row.avatar_url" class="member-avatar">
                  <img :src="row.avatar_url" alt="头像" />
                </div>
                <span v-else class="member-avatar avatar-text">{{ row.name?.charAt(0) || 'U' }}</span>
                <span class="member-name">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" min-width="180" />
          <el-table-column label="当前团队" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.current_team" class="wolf-tag wolf-tag--success" size="small">是</el-tag>
              <el-tag v-else class="wolf-tag wolf-tag--gray" size="small">否</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="joined_at" label="加入时间" min-width="160">
            <template #default="{ row }">
              {{ formatDate(row.joined_at) }}
            </template>
          </el-table-column>
          <el-table-column label="角色" min-width="150">
            <template #default="{ row }">
              <div class="roles-cell">
                <el-tag v-for="role in row.roles" :key="role.id" class="role-tag wolf-tag wolf-tag--info" size="small">
                  {{ role.name }}
                </el-tag>
                <Empty v-if="!row.roles || row.roles.length === 0" class="no-role min-h-0 border-0 p-0">
                  <EmptyHeader>
                    <EmptyTitle class="text-sm font-normal">暂无角色</EmptyTitle>
                  </EmptyHeader>
                </Empty>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="200">
            <template #default="{ row }">
              <div class="action-buttons">
                <el-button
                  v-if="row.id !== currentUserId && isTeamAdmin"
                  type="text"
                  size="small"
                  class="wolf-btn wolf-btn--text"
                  @click="showResetPasswordDialog(row)"
                >
                  重置密码
                </el-button>
                <el-button
                  v-if="row.id !== currentUserId && isTeamAdmin"
                  type="text"
                  size="small"
                  class="wolf-btn wolf-btn--text"
                  @click="handleAssignRoles(row)"
                >
                  分配角色
                </el-button>
                <el-button
                  v-if="row.id !== currentUserId && isTeamAdmin"
                  type="text"
                  size="small"
                  class="wolf-btn wolf-btn--text-danger"
                  @click="handleRemoveMember(row)"
                >
                  移除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="inviteDialogVisible" title="邀请成员" width="500px" :close-on-click-modal="false">
      <el-form :model="inviteForm" label-width="80px">
        <el-form-item label="邮箱">
          <el-input
            v-model="inviteForm.email"
            placeholder="输入用户邮箱"
            clearable
          >
            <template #append>
              <el-button :loading="searchLoading" @click="handleSearchEmail">
                <el-icon><Search /></el-icon>
                搜索
              </el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>

      <div v-if="searchLoading" class="search-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>搜索中...</span>
      </div>

      <div v-else-if="hasSearched && searchResults.length > 0" class="search-results">
        <div class="results-header">找到以下用户:</div>
        <div v-for="user in searchResults" :key="user.id" class="result-item">
          <div v-if="user.avatar_url" class="result-avatar">
            <img :src="user.avatar_url" alt="头像" />
          </div>
          <span v-else class="result-avatar avatar-text">{{ user.name?.charAt(0) || 'U' }}</span>
          <div class="result-info">
            <span class="result-name">{{ user.name }}</span>
            <span class="result-email">{{ user.email }}</span>
          </div>
          <el-tag v-if="isInTeam(user.id)" type="info" size="small">已在团队中</el-tag>
          <el-button v-else type="primary" size="small" @click="handleInviteUser(user)">邀请</el-button>
        </div>
      </div>

      <div v-else-if="hasSearched && searchResults.length === 0" class="search-empty">
        未找到该用户
      </div>

      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="inviteDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 角色分配对话框 -->
    <el-dialog v-model="roleDialogVisible" title="分配角色" width="500px" :close-on-click-modal="false">
      <div class="role-dialog-content">
        <div class="member-info">
          <span class="member-name">{{ selectedMember?.name }}</span>
          <span class="member-email">{{ selectedMember?.email }}</span>
        </div>
        <el-checkbox-group v-model="selectedRoleIds" class="role-checkbox-group">
          <el-checkbox v-for="role in availableRoles" :key="role.id" :label="role.id">
            {{ role.name }} ({{ role.code }})
          </el-checkbox>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button class="wolf-btn wolf-btn--default" @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" class="wolf-btn wolf-btn--primary" @click="handleSaveRoles" :loading="saveRolesLoading">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog
      v-model="resetPasswordVisible"
      :title="`重置密码 - ${resetPasswordTargetUser?.name || ''}`"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="resetPasswordFormRef"
        :model="resetPasswordForm"
        :rules="resetPasswordRules"
        label-width="80px"
      >
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="resetPasswordForm.newPassword"
            type="password"
            placeholder="请输入新密码（6-50位）"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="resetPasswordForm.confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPasswordVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResetPassword" :loading="resetPasswordLoading">
          确认重置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Refresh, Search, Loading } from '@element-plus/icons-vue'
import {
  Empty,
  EmptyHeader,
  EmptyTitle
} from '@/components/ui/empty'
import { teamApi, type TeamMemberResponse, type TeamResponse, type RoleSimpleResponse } from '@/api/team'
import userApi, { type UserSearchResult } from '@/api/user'
import roleApi, { type RoleResponse } from '@/api/role'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { authApi } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()

const loading = ref(false)
const codeLoading = ref(false)
const searchLoading = ref(false)
const hasSearched = ref(false)
const members = ref<TeamMemberResponse[]>([])
const team = ref<TeamResponse | null>(null)
const searchResults = ref<UserSearchResult[]>([])

const inviteDialogVisible = ref(false)
const inviteForm = reactive({ email: '' })

// 角色分配相关状态
const roleDialogVisible = ref(false)
const selectedMember = ref<TeamMemberResponse | null>(null)
const selectedRoleIds = ref<number[]>([])
const availableRoles = ref<RoleResponse[]>([])
const saveRolesLoading = ref(false)
const currentUserRoles = ref<RoleSimpleResponse[]>([])

const currentUserId = computed(() => userStore.userInfo?.id)
const teamId = computed(() => teamStore.currentTeam?.id)

// 判断当前用户是否为 TEAM_ADMIN
const isTeamAdmin = computed(() => {
  return currentUserRoles.value?.some(r => r.code === 'TEAM_ADMIN') ?? false
})

const formatDate = (dateStr: string) => {
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

const fetchTeamInfo = async () => {
  if (!teamId.value) return
  try {
    const response = await teamApi.getTeamDetail(teamId.value)
    team.value = response
  } catch (error) {
    console.error('获取团队信息失败', error)
  }
}

const fetchMembers = async () => {
  if (!teamId.value) return
  loading.value = true
  try {
    const response = await teamApi.getTeamMembers(teamId.value)
    members.value = response
  } catch (error) {
    console.error('获取成员列表失败', error)
    ElMessage.error('获取成员列表失败')
  } finally {
    loading.value = false
  }
}

const showInviteDialog = () => {
  inviteForm.email = ''
  searchResults.value = []
  hasSearched.value = false
  inviteDialogVisible.value = true
}

const isInTeam = (userId: number) => {
  return members.value.some(m => Number(m.id) === userId)
}

const handleSearchEmail = async () => {
  if (!inviteForm.email || inviteForm.email.trim().length === 0) {
    ElMessage.warning('请输入邮箱')
    return
  }

  searchLoading.value = true
  hasSearched.value = false
  try {
    // 不传 excludeTeamId，获取所有匹配用户，前端自行判断是否已在团队中
    const response = await userApi.searchUsers(inviteForm.email.trim())
    searchResults.value = response
    hasSearched.value = true
  } catch (error) {
    console.error('搜索用户失败', error)
    ElMessage.error('搜索失败，请稍后重试')
    hasSearched.value = true
  } finally {
    searchLoading.value = false
  }
}

const handleInviteUser = async (user: UserSearchResult) => {
  if (!teamId.value) return

  try {
    await teamApi.addMemberDirect(teamId.value, user.id)
    ElMessage.success(`${user.name} 已加入团队`)
    inviteDialogVisible.value = false
    fetchMembers()
  } catch (error: unknown) {
    console.error('邀请失败', error)
    ElMessage.error(error.response?.data?.detail || '邀请失败')
  }
}

const handleRemoveMember = (member: TeamMemberResponse) => {
  if (!teamId.value) return

  const currentTeamId = teamId.value
  ElMessageBox.confirm(
    `确定要移除成员"${member.name}"吗？`,
    '确认移除',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    try {
      await teamApi.removeMember(currentTeamId, member.id.toString())
      ElMessage.success('成员已移除')
      fetchMembers()
    } catch (error: unknown) {
      console.error('移除失败', error)
      ElMessage.error(error.response?.data?.detail || '移除失败')
    }
  }).catch((error: unknown) => {
    console.debug('取消移除成员', error)
  })
}

const handleRegenerateCode = async () => {
  if (!teamId.value || !team.value) return

  codeLoading.value = true
  try {
    const response = await teamApi.regenerateInviteCode(teamId.value)
    team.value = { ...team.value, code: response.code }
    ElMessage.success('邀请码已重置')
  } catch (error: unknown) {
    console.error('重置失败', error)
    ElMessage.error(error.response?.data?.detail || '重置失败')
  } finally {
    codeLoading.value = false
  }
}

// 获取所有可用角色
const fetchAvailableRoles = async () => {
  try {
    const response = await roleApi.getRoles()
    availableRoles.value = response
  } catch (error) {
    console.error('获取角色列表失败', error)
  }
}

// 获取当前用户在当前团队的角色
const fetchCurrentUserRoles = async () => {
  if (!teamId.value) return
  try {
    const response = await authApi.getUserRoles()
    currentUserRoles.value = response || []
  } catch (error) {
    console.error('获取当前用户角色失败', error)
  }
}

// 打开角色分配对话框
const handleAssignRoles = (member: TeamMemberResponse) => {
  selectedMember.value = member
  selectedRoleIds.value = member.roles?.map(r => r.id) || []
  roleDialogVisible.value = true
}

// 保存角色分配
const handleSaveRoles = async () => {
  if (!teamId.value || !selectedMember.value) return

  saveRolesLoading.value = true
  try {
    await teamApi.assignMemberRoles(teamId.value, selectedMember.value.id, selectedRoleIds.value)
    ElMessage.success('角色已分配')
    roleDialogVisible.value = false
    fetchMembers()
  } catch (error: unknown) {
    console.error('分配角色失败', error)
    ElMessage.error(error.response?.data?.detail || '分配角色失败')
  } finally {
    saveRolesLoading.value = false
  }
}

// 重置密码相关状态
const resetPasswordVisible = ref(false)
const resetPasswordLoading = ref(false)
const resetPasswordFormRef = ref<FormInstance>()
const resetPasswordTargetUser = ref<TeamMemberResponse | null>(null)

const resetPasswordForm = reactive({
  newPassword: '',
  confirmPassword: '',
})

const validateResetConfirmPassword = (rule: unknown, value: string, callback: (error?: Error) => void) => {
  if (value !== resetPasswordForm.newPassword) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const resetPasswordRules: FormRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度为6-50个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateResetConfirmPassword, trigger: 'blur' }
  ]
}

const showResetPasswordDialog = (member: TeamMemberResponse) => {
  resetPasswordTargetUser.value = member
  resetPasswordForm.newPassword = ''
  resetPasswordForm.confirmPassword = ''
  resetPasswordVisible.value = true
}

const handleResetPassword = async () => {
  const valid = await resetPasswordFormRef.value?.validate().catch(() => false)
  if (!valid || !resetPasswordTargetUser.value || !teamId.value) return

  resetPasswordLoading.value = true
  try {
    await teamApi.resetMemberPassword(
      teamId.value,
      resetPasswordTargetUser.value.id,
      { new_password: resetPasswordForm.newPassword }
    )
    ElMessage.success(`已重置 ${resetPasswordTargetUser.value.name} 的密码`)
    resetPasswordVisible.value = false
  } catch (error: unknown) {
    console.error('重置密码失败', error)
    ElMessage.error(error.response?.data?.detail || '重置密码失败')
  } finally {
    resetPasswordLoading.value = false
  }
}

onMounted(async () => {
  // 确保团队数据已加载
  if (!teamStore.currentTeam) {
    try {
      await teamStore.fetchUserTeams()
    } catch (error) {
      console.error('获取团队信息失败', error)
      ElMessage.warning('请先加入团队')
      router.push('/settings')
      return
    }
  }

  if (!teamId.value) {
    ElMessage.warning('请先加入团队')
    router.push('/settings')
    return
  }
  fetchTeamInfo()
  fetchMembers()
  fetchAvailableRoles()
  fetchCurrentUserRoles()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.team-members-container {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

.wolf-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  margin-bottom: $wolf-space-md;
}

.header-card {
  padding: $wolf-space-md;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.team-info h2 {
  font-size: $wolf-font-size-title;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin: 0 0 4px 0;
}

.invite-code {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.header-actions {
  display: flex;
  gap: $wolf-space-sm;
}

.table-card {
  padding: $wolf-space-md;
}

.wolf-table-wrapper {
  border-radius: $wolf-radius-md;
  overflow-x: auto;
}

.wolf-table :deep(.el-table__header th) {
  background-color: $wolf-bg-hover !important;
  color: $wolf-text-secondary;
  font-weight: $wolf-font-weight-medium;
  font-size: $wolf-font-size-auxiliary;
  padding: 12px $wolf-space-md;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row td) {
  padding: 12px $wolf-space-md;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  border-bottom: 1px solid $wolf-border-light;
}

.wolf-table :deep(.el-table__row:hover td) {
  background-color: $wolf-bg-hover !important;
}

.member-cell {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.member-avatar {
  width: 32px;
  height: 32px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.avatar-text {
  font-size: 14px;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-inverse;
}

.member-name {
  font-weight: $wolf-font-weight-medium;
}

.wolf-tag {
  border-radius: $wolf-radius-sm !important;
  padding: 2px 8px !important;
  font-size: $wolf-font-size-caption !important;
  font-weight: $wolf-font-weight-medium !important;
  height: auto !important;
  line-height: 1.5 !important;
  border-width: 1px !important;
}

.wolf-tag--success {
  background-color: $wolf-success-bg !important;
  border-color: $wolf-success-border !important;
  color: $wolf-success-text !important;
}

.wolf-tag--gray {
  background-color: $wolf-purple-bg !important;
  border-color: $wolf-purple-border !important;
  color: $wolf-purple !important;
}

.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

.wolf-btn--default {
  background: $wolf-bg-card !important;
  border: 1px solid $wolf-border-default !important;
  color: $wolf-text-secondary !important;
}

.wolf-btn--text-danger {
  color: $wolf-danger-text !important;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.wolf-btn--text {
  color: $wolf-text-link !important;
}

.roles-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.role-tag {
  margin: 2px;
}

.no-role {
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
}

// 角色分配对话框
.role-dialog-content {
  .member-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: $wolf-space-md;
    padding-bottom: $wolf-space-md;
    border-bottom: 1px solid $wolf-border-light;

    .member-name {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-medium;
      color: $wolf-text-primary;
    }

    .member-email {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
    }
  }

  .role-checkbox-group {
    display: flex;
    flex-direction: column;
    gap: $wolf-space-sm;
  }
}

.search-loading,
.search-empty {
  padding: $wolf-space-md;
  text-align: center;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-caption;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-sm;
}

.search-results {
  margin-top: $wolf-space-md;
}

.results-header {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-secondary;
  margin-bottom: $wolf-space-sm;
}

.result-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-sm $wolf-space-md;
  border-radius: $wolf-radius-sm;
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: $wolf-space-xs;

  &:hover {
    background: $wolf-bg-hover;
  }
}

.result-avatar {
  width: 36px;
  height: 36px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-size: 16px;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-inverse;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.result-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.result-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
}

.result-email {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

@media (max-width: 768px) {
  .header-content {
    flex-direction: column;
    gap: $wolf-space-md;
    align-items: flex-start;
  }
  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
