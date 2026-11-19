<template>
  <main class="onboarding-container" role="main" aria-label="团队设置引导页面">
    <Button
      variant="ghost"
      size="sm"
      class="logout-btn"
      aria-label="退出登录"
      @click="handleLogout"
    >
      <LogOut class="mr-2 h-4 w-4" aria-hidden="true" />
      退出登录
    </Button>

    <Card class="onboarding-card">
      <CardContent class="card-body">
        <!-- Logo Section - consistent with Login.vue -->
        <div class="logo-section">
          <img
            src="/logo.png"
            alt="CRM Logo"
            class="w-16 h-16 object-contain"
          />
          <h1 class="text-body-strong font-semibold text-foreground">智能客户关系管理系统</h1>
          <p class="welcome-subtitle">欢迎使用 CRMWolf，开始使用前您需要先创建或加入一个团队</p>
        </div>

        <div class="action-buttons" role="group" aria-label="团队操作选项">
          <Button size="lg" class="action-btn" @click="goToCreateTeam">
            <Plus class="mr-2 h-5 w-5" aria-hidden="true" />
            创建新团队
          </Button>

          <Button variant="outline" size="lg" class="action-btn" @click="goToJoinTeam">
            <Link class="mr-2 h-5 w-5" aria-hidden="true" />
            加入已有团队
          </Button>
        </div>

        <p class="tip-text">创建团队后，您将成为团队管理员，可以邀请团队成员</p>
      </CardContent>
    </Card>

    <!-- 退出登录确认对话框 -->
    <AlertDialog v-model:open="showLogoutDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认退出</AlertDialogTitle>
          <AlertDialogDescription>
            确定要退出登录吗？退出后需要重新登录才能继续使用系统。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="confirmLogout">确认退出</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Link, LogOut } from 'lucide-vue-next'
import { Button, Card, CardContent } from '@/components/crmwolf'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useUserStore } from '@/stores/user'
import { createAuthReturnQuery, getSafeAuthReturnPath } from '@/utils/authRecovery'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const showLogoutDialog = ref(false)

const goToCreateTeam = (): void => {
  router.push({ name: 'TeamCreate', query: createAuthReturnQuery(getSafeAuthReturnPath(route.query['redirect'])) })
}

const goToJoinTeam = (): void => {
  router.push({ name: 'TeamJoin', query: createAuthReturnQuery(getSafeAuthReturnPath(route.query['redirect'])) })
}

const handleLogout = (): void => {
  showLogoutDialog.value = true
}

const confirmLogout = (): void => {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped lang="scss">
@use '@/styles/tokens.scss' as *;

.onboarding-container {
  // UI/UX Pro Max: 使用动态视口高度，避免 iOS Safari 地址栏问题
  min-height: min(100vh, 100dvh);
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--card));
  padding: $space-4;
  // UI/UX Pro Max: Safe area 支持
  padding-top: calc($space-4 + var(--safe-top));
  padding-bottom: calc($space-4 + var(--safe-bottom));
  position: relative;
}

.logout-btn {
  position: absolute;
  top: calc($space-4 + var(--safe-top));
  right: $space-4;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  // UI/UX Pro Max: Touch target ≥44px
  min-height: var(--touch-target);
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
}

.card-body {
  padding: $space-8 $space-4;
  display: flex;
  flex-direction: column;
  align-items: center;
}

// Logo section - consistent with Login.vue
.logo-section {
  text-align: center;
  margin-bottom: $space-8;

  img {
    display: block;
    margin-left: auto;
    margin-right: auto;
    margin-bottom: $space-3;
  }

  h1 {
    margin: 0 0 $space-3 0;
  }

  .welcome-subtitle {
    font-size: 14px;
    color: hsl(var(--muted-foreground));
    margin: 0;
  }
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: $space-3;
  width: 100%;
}

.action-btn {
  width: 100%;
  height: var(--control-h-lg); // 48px - UI/UX Pro Max touch target
  font-size: 14px;
  font-weight: 500;
}

.tip-text {
  text-align: center;
  margin-top: $space-8;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

// UI/UX Pro Max: Mobile breakpoint
@media (max-width: $bp-xs) {
  .onboarding-container {
    padding: var(--page-padding);
    padding-top: calc(var(--page-padding) + var(--safe-top));
    padding-bottom: calc(var(--page-padding) + var(--safe-bottom));
  }

  .logout-btn {
    top: calc($space-3 + var(--safe-top));
    right: $space-3;
  }

  .card-body {
    padding: $space-6 $space-3;
  }

  .welcome-text h1 {
    font-size: 18px;
  }
}
</style>