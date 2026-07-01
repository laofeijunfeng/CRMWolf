<template>
  <div class="settings-page">
    <!-- 用户信息卡片 -->
    <div class="user-card">
      <div class="user-avatar">
        <img v-if="userInfo?.avatar_url" :src="userInfo.avatar_url" alt="头像" />
        <span v-else class="avatar-text">{{ userInfo?.name?.charAt(0) || 'U' }}</span>
      </div>
      <div class="user-info">
        <div class="user-name">{{ userInfo?.name || '未登录' }}</div>
        <div class="user-meta">
          <span :class="['status-tag', getStatusClass(userInfo?.status)]">
            {{ getStatusText(userInfo?.status) }}
          </span>
          <span class="user-email">{{ userInfo?.email || '未填写邮箱' }}</span>
        </div>
      </div>
      <div class="user-actions">
        <el-button size="small" @click="showChangePasswordDialog">
          <el-icon><Key /></el-icon>
          修改密码
        </el-button>
        <el-button size="small" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          退出登录
        </el-button>
      </div>
    </div>

    <!-- 系统管理入口 -->
    <div class="settings-card">
      <div class="card-header">
        <span class="card-title">系统管理</span>
      </div>
      <div class="settings-list">
        <div v-if="canManageRoles" class="settings-item" @click="goToRoles">
          <el-icon class="item-icon"><UserFilled /></el-icon>
          <span class="item-text">角色管理</span>
          <span class="item-desc">配置角色与权限</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div v-if="canManageApprovalFlows" class="settings-item" @click="goToApprovalFlows">
          <el-icon class="item-icon"><Document /></el-icon>
          <span class="item-text">审批流程</span>
          <span class="item-desc">配置审批流程模板</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div v-if="canManageProcurementMethods" class="settings-item" @click="goToProcurementMethods">
          <el-icon class="item-icon"><ShoppingCart /></el-icon>
          <span class="item-text">采购配置</span>
          <span class="item-desc">管理采购方式与阶段</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div v-if="canManageAIConfig" class="settings-item" @click="goToAIConfig">
          <el-icon class="item-icon"><Cpu /></el-icon>
          <span class="item-text">AI 配置</span>
          <span class="item-desc">大模型服务参数设置</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div v-if="canManageApprovalFlows" class="settings-item" @click="goToNotificationConfig">
          <el-icon class="item-icon"><Bell /></el-icon>
          <span class="item-text">通知配置</span>
          <span class="item-desc">配置飞书群聊通知</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div v-if="canManageTeam" class="settings-item" @click="goToTeamMembers">
          <el-icon class="item-icon"><UserFilled /></el-icon>
          <span class="item-text">团队成员</span>
          <span class="item-desc">管理团队成员与邀请</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>

    <!-- 用户详情 -->
    <div class="detail-card">
      <div class="card-header">
        <span class="card-title">账户详情</span>
      </div>
      <div class="detail-grid">
        <div class="detail-item">
          <span class="detail-label">用户 ID</span>
          <span class="detail-value">{{ userInfo?.id || '-' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">邮箱</span>
          <span class="detail-value">{{ userInfo?.email || '-' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">注册时间</span>
          <span class="detail-value">{{ formatDate(userInfo?.created_time) }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">角色</span>
          <div class="role-list">
            <el-skeleton :loading="rolesLoading" animated :rows="1">
              <template #template>
                <el-skeleton-item variant="text" style="width: 80px" />
              </template>
              <template #default>
                <span v-if="userRoles && userRoles.length > 0" class="roles-text">
                  {{ userRoles.map(r => r.name).join('、') }}
                </span>
                <span v-else class="detail-value empty">暂无角色</span>
              </template>
            </el-skeleton>
          </div>
        </div>
      </div>
    </div>

    <!-- 操作记录 -->
    <div class="logs-card">
      <div class="card-header">
        <span class="card-title">我的操作记录</span>
      </div>
      <Timeline
        :logs="myOperationLogs"
        :loading="myOperationsLoading"
        :has-more="myOperationsHasMore"
        :filters="myOperationsFilters"
        :show-filter="false"
        @load-more="handleMyOperationsLoadMore"
        @filter-change="handleMyOperationsFilterChange"
        @reset="handleMyOperationsReset"
      />
    </div>

    <!-- 修改密码对话框 -->
    <el-dialog
      v-model="changePasswordVisible"
      title="修改密码"
      width="400px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="changePasswordFormRef"
        :model="changePasswordForm"
        :rules="changePasswordRules"
        label-width="80px"
      >
        <el-form-item label="旧密码" prop="oldPassword">
          <el-input
            v-model="changePasswordForm.oldPassword"
            type="password"
            placeholder="请输入旧密码"
            show-password
          />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="changePasswordForm.newPassword"
            type="password"
            placeholder="请输入新密码（6-50位）"
            show-password
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="changePasswordForm.confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="changePasswordVisible = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword" :loading="changePasswordLoading">
          确认修改
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { showSuccess } from '@/utils/errorMessages'
import { SwitchButton, User, UserFilled, Document, ShoppingCart, Cpu, ArrowRight, Key, Bell } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { usePermissionStore } from '@/stores/permissions'
import { authApi, type RoleResponse } from '@/api/auth'
import Timeline from '@/components/Timeline/index.vue'
import { useTimeline } from '@/composables/useTimeline'

const router = useRouter()
const userStore = useUserStore()
const permissionStore = usePermissionStore()

const userInfo = computed(() => userStore.userInfo)
const userRoles = ref<RoleResponse[]>([])
const rolesLoading = ref(false)

const canManageUsers = computed(() => permissionStore.hasPermission('user:manage'))
const canManageRoles = computed(() => permissionStore.hasPermission('role:manage'))
const canManageApprovalFlows = computed(() => permissionStore.hasAnyPermission(['approval:flow:create', 'approval:flow:update']))
const canManageProcurementMethods = computed(() => permissionStore.hasPermission('procurement_method:view'))
const canManageAIConfig = computed(() => permissionStore.hasAnyPermission(['system:config', 'ai:manage']))
const canManageTeam = computed(() => userRoles.value?.some(r => r.code === 'TEAM_ADMIN') ?? false)

const goToRoles = () => router.push('/roles')
const goToApprovalFlows = () => router.push('/approval-flows')
const goToProcurementMethods = () => router.push('/procurement-methods')
const goToAIConfig = () => router.push('/ai-config')
const goToTeamMembers = () => router.push('/team-members')
const goToNotificationConfig = () => router.push('/notification-config')

const myTimeline = useTimeline({
  useMyLogs: true,
  pageSize: 20
})

const myOperationLogs = computed(() => myTimeline.logs.value)
const myOperationsLoading = computed(() => myTimeline.loading.value)
const myOperationsHasMore = computed(() => myTimeline.hasMore.value)
const myOperationsFilters = computed(() => myTimeline.filters.value)

const handleMyOperationsLoadMore = () => myTimeline.loadMore()
const handleMyOperationsFilterChange = () => myTimeline.refresh()
const handleMyOperationsReset = () => myTimeline.resetFilters()

const fetchUserRoles = async () => {
  rolesLoading.value = true
  try {
    const response = await authApi.getUserRoles()
    userRoles.value = response || []
  } catch (error) {
    console.error('获取用户角色失败', error)
  } finally {
    rolesLoading.value = false
  }
}

onMounted(() => {
  fetchUserRoles()
  myTimeline.fetchLogs()
})

// 修改密码相关状态
const changePasswordVisible = ref(false)
const changePasswordLoading = ref(false)
const changePasswordFormRef = ref<FormInstance>()

const changePasswordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const validateConfirmPassword = (rule: unknown, value: string, callback: (error?: Error) => void) => {
  if (value !== changePasswordForm.newPassword) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const changePasswordRules: FormRules = {
  oldPassword: [
    { required: true, message: '请输入旧密码', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度为6-50个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const showChangePasswordDialog = () => {
  changePasswordForm.oldPassword = ''
  changePasswordForm.newPassword = ''
  changePasswordForm.confirmPassword = ''
  changePasswordVisible.value = true
}

const handleChangePassword = async () => {
  const valid = await changePasswordFormRef.value?.validate().catch(() => false)
  if (!valid) return

  changePasswordLoading.value = true
  try {
    await authApi.changePassword({
      old_password: changePasswordForm.oldPassword,
      new_password: changePasswordForm.newPassword,
    })
    showSuccess('密码修改成功')
    changePasswordVisible.value = false
  } catch (error: unknown) {
    console.error('修改密码失败', error)
    ElMessage.error('密码修改失败，请检查旧密码是否正确')
  } finally {
    changePasswordLoading.value = false
  }
}

const getStatusText = (status?: string): string => {
  const map: Record<string, string> = {
    'ACTIVE': '正常',
    'INACTIVE': '停用',
    'PENDING': '待激活'
  }
  return map[status || ''] || status || '未知'
}

const getStatusClass = (status?: string): string => {
  const map: Record<string, string> = {
    'ACTIVE': 'status-success',
    'INACTIVE': 'status-default',
    'PENDING': 'status-warning'
  }
  return map[status || ''] || 'status-default'
}

const formatDate = (dateStr?: string): string => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '确认退出', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logout()
    showSuccess('退出登录', '账户')
    router.push('/login')
  }).catch(() => {})
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.settings-page {
  padding: $wolf-page-padding;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 用户信息卡片
.user-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
}

.user-avatar {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  border-radius: $wolf-radius-full;
  overflow: hidden;
  background: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .avatar-text {
    font-size: 20px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-inverse;
  }
}

.user-info {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
  margin-bottom: 4px;
}

.user-meta {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.user-email {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.user-actions {
  flex-shrink: 0;
}

// 状态标签
.status-tag {
  display: inline-flex;
  padding: 2px 6px;
  font-size: $wolf-font-size-caption;
  font-weight: $wolf-font-weight-normal;
  border-radius: $wolf-radius-sm;
}

.status-success {
  background: $wolf-success-bg;
  color: $wolf-success-text;
}

.status-warning {
  background: $wolf-warning-bg;
  color: $wolf-warning-text;
}

.status-default {
  background: $wolf-bg-hover;
  color: $wolf-text-tertiary;
}

// 通用卡片样式
.settings-card,
.detail-card,
.logs-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
  box-shadow: $wolf-shadow-card;
}

.card-header {
  padding: $wolf-space-md;
  border-bottom: 1px solid $wolf-border-light;
}

.card-title {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

// 设置列表
.settings-list {
  padding: 0;
}

.settings-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-md;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid $wolf-border-light;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: $wolf-bg-hover;
  }
}

.item-icon {
  font-size: 18px;
  color: $wolf-text-tertiary;
  flex-shrink: 0;
}

.item-text {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  flex-shrink: 0;
}

.item-desc {
  flex: 1;
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.item-arrow {
  font-size: 14px;
  color: $wolf-text-placeholder;
  flex-shrink: 0;
}

// 详情网格
.detail-grid {
  padding: $wolf-space-md;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-md;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.detail-value {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  font-weight: $wolf-font-weight-medium;

  &.empty {
    color: $wolf-text-placeholder;
  }
}

.roles-text {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
}

.role-list {
  display: flex;
  align-items: center;
}

// 操作记录卡片
.logs-card {
  margin-bottom: 0;
}

.logs-card :deep(.timeline-container) {
  padding: 0;
  background: transparent;
}

// 响应式
@media (max-width: 768px) {
  .settings-page { padding: $wolf-space-md; }
  .user-card { flex-wrap: wrap; }
  .user-info { order: 1; width: 100%; }
  .user-actions { order: 2; width: 100%; margin-top: $wolf-space-sm; }
  .detail-grid { grid-template-columns: 1fr; }
}
</style>