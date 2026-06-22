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

        <div class="header">
          <h2>加入已有团队</h2>
          <p>请输入团队邀请码，加入您的团队</p>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          class="join-form"
          @submit.prevent="handleSubmit"
        >
          <el-form-item prop="code">
            <el-input
              v-model="form.code"
              placeholder="请输入邀请码"
              size="large"
              maxlength="20"
              show-word-limit
            />
          </el-form-item>

          <el-button
            type="primary"
            size="large"
            class="submit-btn"
            :loading="loading"
            @click="handleSubmit"
          >
            加入团队
          </el-button>
        </el-form>

        <div class="tip-text">
          <p>邀请码由团队管理员提供，通常为6-8位字母数字组合</p>
        </div>

        <div class="back-link">
          <el-button text @click="goBack">
            <el-icon><ArrowLeft /></el-icon>
            返回上一步
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { showError, showSuccess } from '@/utils/errorMessages'
import { ArrowLeft, SwitchButton } from '@element-plus/icons-vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const teamStore = useTeamStore()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({
  code: ''
})

const rules: FormRules = {
  code: [
    { required: true, message: '请输入邀请码', trigger: 'blur' },
    { min: 4, max: 20, message: '邀请码长度为4-20个字符', trigger: 'blur' }
  ]
}

const handleSubmit = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    await teamStore.joinTeam(form.code)
    showSuccess('加入', '团队')
    router.push('/leads')
  } catch (error: any) {
    console.error('加入团队失败', error)
    showError(error, '加入团队')
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/onboarding')
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

.header {
  text-align: center;
  margin-bottom: $wolf-space-8;
}

.header h2 {
  font-size: 24px;
  color: $wolf-text-primary;
  margin: 0 0 $wolf-space-sm 0;
  font-weight: $wolf-font-weight-semibold;
}

.header p {
  font-size: $wolf-font-size-body;
  color: $wolf-text-secondary;
  margin: 0;
}

.join-form {
  margin-bottom: $wolf-space-md;
}

.submit-btn {
  width: 100%;
  height: 48px;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  border-radius: $wolf-radius-sm;
  margin-top: $wolf-space-md;
}

.tip-text {
  text-align: center;
  margin-bottom: $wolf-space-lg;
}

.tip-text p {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin: 0;
}

.back-link {
  text-align: center;
}

.back-link .el-button {
  color: $wolf-text-secondary;
  font-size: $wolf-font-size-caption;
}
</style>