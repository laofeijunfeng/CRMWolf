<template>
  <div class="onboarding-container">
    <div class="logout-btn">
      <el-button text @click="handleLogout">
        <el-icon><SwitchButton /></el-icon>
        退出登录
      </el-button>
    </div>
    <div class="onboarding-card">
      <div class="card-body">
        <div class="logo">
          <img src="/logo.png" alt="CRM Logo" />
          <p>智能客户关系管理系统</p>
        </div>

        <div class="welcome-text">
          <h2>欢迎使用 CRMWolf</h2>
          <p>开始使用前，您需要先创建或加入一个团队</p>
        </div>

        <div class="action-buttons">
          <el-button
            type="primary"
            size="large"
            class="action-btn"
            @click="goToCreateTeam"
          >
            <el-icon><Plus /></el-icon>
            创建新团队
          </el-button>

          <el-button
            size="large"
            class="action-btn join-btn"
            @click="goToJoinTeam"
          >
            <el-icon><Link /></el-icon>
            加入已有团队
          </el-button>
        </div>

        <div class="tip-text">
          <p>创建团队后，您将成为团队管理员，可以邀请团队成员</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Plus, Link, SwitchButton } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const goToCreateTeam = () => {
  router.push('/onboarding/create-team')
}

const goToJoinTeam = () => {
  router.push('/onboarding/join-team')
}

const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.onboarding-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page;
  padding: $wolf-space-lg;
}

.logout-btn {
  position: absolute;
  top: $wolf-space-lg;
  right: $wolf-space-lg;
}

.logout-btn .el-button {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-caption;
}

.onboarding-card {
  width: 100%;
  max-width: 480px;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  box-shadow: $wolf-shadow-card;
  overflow: hidden;
}

.card-body {
  padding: $wolf-space-8 $wolf-space-lg;
}

.logo {
  text-align: center;
  margin-bottom: $wolf-space-8;
}

.logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
  margin-bottom: $wolf-space-md;
}

.logo p {
  font-size: $wolf-font-size-title;
  color: $wolf-text-primary;
  margin: 0;
  font-weight: $wolf-font-weight-semibold;
}

.welcome-text {
  text-align: center;
  margin-bottom: $wolf-space-8;
}

.welcome-text h2 {
  font-size: 24px;
  color: $wolf-text-primary;
  margin: 0 0 $wolf-space-sm 0;
  font-weight: $wolf-font-weight-semibold;
}

.welcome-text p {
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
  margin: 0;
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;
}

.action-btn {
  width: 100%;
  height: 48px;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  border-radius: $wolf-radius-sm;
}

.action-btn.join-btn {
  background: $wolf-bg-hover;
  border: 1px solid $wolf-border-default;
  color: $wolf-text-secondary;
}

.action-btn.join-btn:hover {
  border-color: $wolf-primary;
  color: $wolf-primary;
}

.tip-text {
  text-align: center;
  margin-top: $wolf-space-8;
}

.tip-text p {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin: 0;
}
</style>