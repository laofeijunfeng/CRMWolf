<template>
  <div class="login-container">
    <div class="login-card">
      <div class="card-body">
        <div class="logo">
          <img src="/logo.png" alt="CRM Logo" />
          <p>智能客户关系管理系统</p>
        </div>

        <el-tabs v-model="activeTab" class="login-tabs">
          <el-tab-pane label="登录" name="login">
            <div class="tab-content">
              <el-form :model="loginForm" :rules="loginRules" label-position="top" ref="loginFormRef">
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="loginForm.email" placeholder="请输入邮箱" />
                </el-form-item>
                <el-form-item label="密码" prop="password">
                  <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password />
                </el-form-item>
                <el-button
                  type="primary"
                  size="large"
                  :loading="loading"
                  @click="handleLogin"
                  class="login-button"
                >
                  登录
                </el-button>
              </el-form>
            </div>
          </el-tab-pane>

          <el-tab-pane label="注册" name="register">
            <div class="tab-content">
              <el-form :model="registerForm" :rules="registerRules" label-position="top" ref="registerFormRef">
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="registerForm.email" placeholder="请输入邮箱" />
                </el-form-item>
                <el-form-item label="姓名" prop="name">
                  <el-input v-model="registerForm.name" placeholder="请输入姓名" />
                </el-form-item>
                <el-form-item label="密码" prop="password">
                  <el-input v-model="registerForm.password" type="password" placeholder="请设置密码（6-50位）" show-password />
                </el-form-item>
                <el-button
                  type="primary"
                  size="large"
                  :loading="registering"
                  @click="handleRegister"
                  class="login-button"
                >
                  注册
                </el-button>
              </el-form>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { authApi } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()

const activeTab = ref('login')
const loading = ref(false)
const registering = ref(false)

const loginFormRef = ref()
const registerFormRef = ref()

const loginForm = reactive({
  email: '',
  password: ''
})

const registerForm = reactive({
  email: '',
  name: '',
  password: ''
})

const emailRule = [
  { required: true, message: '请输入邮箱', trigger: 'blur' },
  { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
]

const loginRules = {
  email: emailRule,
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const registerRules = {
  email: emailRule,
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' },
    { min: 1, max: 100, message: '姓名长度为1-100个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 50, message: '密码长度为6-50个字符', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  try {
    await loginFormRef.value?.validate()
  } catch {
    return
  }

  loading.value = true

  try {
    const res = await authApi.loginWithPassword({
      email: loginForm.email,
      password: loginForm.password
    })

    userStore.setToken(res.access_token)
    const user = res.user

    try {
      const roles = await authApi.getUserRoles()
      userStore.setUserInfo({ ...user, roles })
    } catch (roleError) {
      console.warn('获取用户角色失败', roleError)
      userStore.setUserInfo(user)
    }

    ElMessage.success('登录成功')

    try {
      await teamStore.fetchUserTeams()
      if (teamStore.hasTeam()) {
        router.push('/leads')
      } else {
        router.push('/onboarding')
      }
    } catch {
      router.push('/onboarding')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  try {
    await registerFormRef.value?.validate()
  } catch {
    return
  }

  registering.value = true

  try {
    const res = await authApi.registerWithPassword({
      email: registerForm.email,
      name: registerForm.name,
      password: registerForm.password
    })

    userStore.setToken(res.access_token)
    const user = res.user

    try {
      const roles = await authApi.getUserRoles()
      userStore.setUserInfo({ ...user, roles })
    } catch (roleError) {
      console.warn('获取用户角色失败', roleError)
      userStore.setUserInfo(user)
    }

    ElMessage.success('注册成功')
    router.push('/onboarding')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '注册失败')
  } finally {
    registering.value = false
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page;
  padding: $wolf-space-lg;
}

.login-card {
  width: 100%;
  max-width: 420px;
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

.login-tabs :deep(.el-tabs__header) {
  margin-bottom: $wolf-space-lg;
}

.login-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0;
}

.login-tabs :deep(.el-tabs__item) {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-tertiary;
  padding: 0 $wolf-space-lg;
  height: 40px;
  line-height: 40px;
}

.login-tabs :deep(.el-tabs__item:hover) {
  color: $wolf-primary;
}

.login-tabs :deep(.el-tabs__item.is-active) {
  color: $wolf-primary;
  font-weight: $wolf-font-weight-semibold;
}

.login-tabs :deep(.el-tabs__active-bar) {
  height: 2px;
  background-color: $wolf-primary;
  border-radius: 1px;
}

.tab-content {
  padding: $wolf-space-xs 0;
}

.login-button {
  width: 100%;
  height: 44px;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  border-radius: $wolf-radius-sm;
  background: $wolf-primary;
  border-color: $wolf-primary;
}

.login-button:hover {
  background: $wolf-primary-hover;
  border-color: $wolf-primary-hover;
}

:deep(.el-form-item) {
  margin-bottom: $wolf-space-md;
}

:deep(.el-form-item__label) {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-secondary;
  padding-bottom: $wolf-space-xs;
}

:deep(.el-input__wrapper) {
  border-radius: $wolf-radius-sm;
  padding: $wolf-space-sm $wolf-space-md;
}
</style>