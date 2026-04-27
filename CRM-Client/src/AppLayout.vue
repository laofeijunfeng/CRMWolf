<template>
  <div class="app-layout">
    <aside class="sidebar">
      <nav class="nav">
        <div class="menu-item" :class="{ active: currentPath === '/leads' || currentPath === '/leads/public' || currentPath === '/leads/my' }" @click="handleMenuClick('/leads')">
          <el-icon class="item-icon"><Flag /></el-icon>
          <span class="item-text">线索管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath === '/customers' }" @click="handleMenuClick('/customers')">
          <el-icon class="item-icon"><OfficeBuilding /></el-icon>
          <span class="item-text">客户管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath === '/opportunities' }" @click="handleMenuClick('/opportunities')">
          <el-icon class="item-icon"><TrendCharts /></el-icon>
          <span class="item-text">商机管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath.startsWith('/contracts') }" @click="handleMenuClick('/contracts')">
          <el-icon class="item-icon"><Document /></el-icon>
          <span class="item-text">合同管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath === '/payments' }" @click="handleMenuClick('/payments')">
          <el-icon class="item-icon"><Money /></el-icon>
          <span class="item-text">回款管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="menu-item" :class="{ active: currentPath.startsWith('/invoices') }" @click="handleMenuClick('/invoices')">
          <el-icon class="item-icon"><Tickets /></el-icon>
          <span class="item-text">发票管理</span>
          <el-icon class="item-arrow"><ArrowRight /></el-icon>
        </div>
      </nav>
      <div class="user-info" @click="handleUserProfile">
        <div class="user-avatar">
          <img v-if="userStore.userInfo?.avatar_url" :src="userStore.userInfo.avatar_url" alt="用户头像" />
          <span v-else class="avatar-placeholder">{{ userStore.userInfo?.name?.charAt(0) || 'U' }}</span>
        </div>
        <div class="user-details">
          <div class="user-name">{{ userStore.userInfo?.name || '未登录' }}</div>
          <div class="user-position">{{ getUserPosition() }}</div>
        </div>
        <el-icon class="item-arrow"><ArrowRight /></el-icon>
      </div>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { Flag, OfficeBuilding, TrendCharts, Document, Money, Tickets, ArrowRight } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const currentPath = computed(() => {
  const path = route.path
  if (path.startsWith('/leads/public')) return '/leads/public'
  if (path.startsWith('/leads/my')) return '/leads/my'
  if (path.startsWith('/leads/reminder')) return '/leads/reminder'
  if (path.startsWith('/leads/') && path.match(/\/leads\/\d+/)) return '/leads'
  if (path.startsWith('/opportunities/') && path.match(/\/opportunities\/\d+/)) return '/opportunities'
  return path
})

const handleMenuClick = (key: string) => {
  router.push(key)
}

const getUserPosition = () => {
  const userRoles = (userStore.userInfo as any)?.roles
  if (!userRoles || !Array.isArray(userRoles) || userRoles.length === 0) {
    return ''
  }

  const roleNames = userRoles.map((r: any) => r.name || r.code).filter(Boolean)
  return roleNames.join('、')
}

const handleUserProfile = () => {
  router.push('/settings')
}

const handleLogout = () => {
  userStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}

onMounted(async () => {
  if (!userStore.isLoggedIn()) {
    router.push('/login')
  } else {
    try {
      if (!userStore.userInfo) {
        await userStore.fetchUserInfo()
      }
      const { usePermissionStore } = await import('@/stores/permissions')
      const permissionStore = usePermissionStore()
      if (!permissionStore.initialized) {
        await permissionStore.fetchPermissions()
      }
    } catch (error) {
      console.error('初始化用户信息和权限失败', error)
    }
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.app-layout {
  display: flex;
  height: 100vh;
  background: $wolf-bg-page;
}

.sidebar {
  width: 200px;
  background: $wolf-bg-sidebar;
  display: flex;
  flex-direction: column;
  padding: 0;
  flex-shrink: 0;
  border-right: 1px solid $wolf-border-default;
}

.nav {
  flex: 1;
  padding: $wolf-space-md $wolf-space-md;
  overflow-y: auto;
}

// 菜单项样式 - 参考 Settings.vue 的 settings-item 样式
.menu-item {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-md;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.2s;
  border-radius: $wolf-radius-sm;
  color: $wolf-text-tertiary;

  &:hover {
    background: $wolf-bg-hover;
  }

  &.active {
    background: $wolf-bg-hover;
    color: $wolf-primary;
  }
}

.item-icon {
  font-size: 18px;
  color: $wolf-text-tertiary;
  flex-shrink: 0;
}

.menu-item.active .item-icon {
  color: $wolf-primary;
}

.item-text {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  flex: 1;
}

.item-arrow {
  font-size: 14px;
  color: $wolf-text-placeholder;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.menu-item:hover .item-arrow,
.menu-item.active .item-arrow {
  opacity: 1;
  color: $wolf-text-tertiary;
}

// 用户信息区域 - 同样采用列表项样式
.user-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-md;
  border-top: 1px solid $wolf-border-default;
  cursor: pointer;
  transition: background 0.2s;
  margin: 0 $wolf-space-md $wolf-space-md;

  &:hover {
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-sm;
  }
}

.user-avatar {
  width: 32px;
  height: 32px;
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

  .avatar-placeholder {
    font-size: 14px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-inverse;
  }
}

.user-details {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-primary;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-position {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.main-content {
  flex: 1;
  overflow: auto;
  padding: 0;
  background: $wolf-bg-page;
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
