<template>
  <div class="login-container">
    <div class="login-card">
      <div class="card-body">
        <div class="logo">
          <img src="/logo.png" alt="CRM Logo" />
          <p>智能客户关系管理系统</p>
        </div>

        <div class="dev-login-section">
          <h3 class="section-title">开发环境快速登录</h3>
          
          <div class="quick-login-buttons">
            <el-button
              type="primary"
              size="large"
              :loading="loading && currentLogin === 'admin'"
              @click="quickLogin('admin')"
              class="quick-login-btn admin-btn"
            >
              <el-icon><User /></el-icon>
              <span>管理员</span>
            </el-button>
            
            <el-button
              type="success"
              size="large"
              :loading="loading && currentLogin === 'director'"
              @click="quickLogin('director')"
              class="quick-login-btn director-btn"
            >
              <el-icon><Avatar /></el-icon>
              <span>销售总监</span>
            </el-button>
            
            <el-button
              type="warning"
              size="large"
              :loading="loading && currentLogin === 'sales'"
              @click="quickLogin('sales')"
              class="quick-login-btn sales-btn"
            >
              <el-icon><UserFilled /></el-icon>
              <span>销售人员</span>
            </el-button>
            
            <el-button
              type="info"
              size="large"
              :loading="loading && currentLogin === 'finance'"
              @click="quickLogin('finance')"
              class="quick-login-btn finance-btn"
            >
              <el-icon><Money /></el-icon>
              <span>财务人员</span>
            </el-button>
          </div>
        </div>

        <div class="divider">
          <span>或</span>
        </div>

        <el-tabs v-model="activeTab" class="login-tabs">
          <el-tab-pane label="飞书登录" name="feishu">
            <div class="tab-content">
              <el-button
                type="primary"
                size="large"
                :loading="loading"
                @click="handleFeishuLogin"
                class="login-button"
              >
                <el-icon><Connection /></el-icon>
                飞书登录
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane label="模拟登录" name="mock">
            <div class="tab-content">
              <el-form :model="mockForm" :rules="mockFormRules" label-position="top" ref="mockFormRef">
                <el-form-item label="姓名" prop="name">
                  <el-input v-model="mockForm.name" placeholder="请输入姓名" />
                </el-form-item>
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="mockForm.email" placeholder="请输入邮箱" />
                </el-form-item>
                <el-form-item label="手机号" prop="mobile">
                  <el-input v-model="mockForm.mobile" placeholder="请输入手机号" />
                </el-form-item>
                <el-form-item label="地区" prop="region">
                  <el-input v-model="mockForm.region" placeholder="请输入所属地区" />
                </el-form-item>
                <el-button
                  type="primary"
                  size="large"
                  :loading="loading"
                  @click="handleMockLogin"
                  class="login-button"
                >
                  模拟登录
                </el-button>
              </el-form>
            </div>
          </el-tab-pane>
        </el-tabs>

        <div class="tips">
          <p>开发环境 · 快速登录模式</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Avatar, UserFilled, Money, Connection } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const currentLogin = ref('')
const activeTab = ref('feishu')

const mockFormRef = ref()

const mockForm = reactive({
  name: '',
  email: '',
  mobile: '',
  region: ''
})

const mockFormRules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  mobile: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^\+?[1-9]\d{1,14}$/, message: '请输入正确的手机号格式', trigger: 'blur' }
  ],
  region: [{ required: true, message: '请输入地区', trigger: 'blur' }]
}

const QUICK_LOGIN_USERS = {
  admin: {
    name: 'AdminUser',
    email: 'AdminUser@qq.com',
    mobile: '+8613800138000',
    region: '北京',
    feishu_open_id: 'mock_user_id_AdminUser',
    id: 11
  },
  director: {
    name: 'eddie',
    email: 'eddie@crm.com',
    mobile: '+8613800138001',
    region: '华东区',
    feishu_open_id: 'mock_open_id_Eddie',
    id: 9
  },
  sales: {
    name: 'test',
    email: 'test@crm.com',
    mobile: '+8613800138002',
    region: '华东区',
    feishu_open_id: 'member_open_id',
    id: 4
  },
  finance: {
    name: 'Echo',
    email: 'echo@crm.com',
    mobile: '+8615151000000',
    region: '总部',
    feishu_open_id: 'mock_open_id_Echo',
    id: 13
  }
}

const quickLogin = async (type: keyof typeof QUICK_LOGIN_USERS) => {
  loading.value = true
  currentLogin.value = type
  
  try {
    const userData = QUICK_LOGIN_USERS[type]
    
    const res = await authApi.mockLogin({
      name: userData.name,
      email: userData.email,
      mobile: userData.mobile,
      region: userData.region
    }) as any
    
    userStore.setToken(res.access_token)
    
    const userInfo: {
      id: number
      feishu_open_id: string
      name: string
      email: string
      mobile: string
      status: string
      roles: any[]
    } = {
      id: userData.id,
      feishu_open_id: userData.feishu_open_id,
      name: userData.name,
      email: userData.email,
      mobile: userData.mobile,
      status: 'active',
      roles: []
    }
    
    try {
      const roles = await authApi.getUserRoles() as any
      userInfo.roles = roles
    } catch (roleError) {
      console.warn('获取用户角色失败', roleError)
    }
    
    userStore.setUserInfo(userInfo as any)
    
    ElMessage.success(`以${userData.name}身份登录成功`)
    router.push('/leads')
  } catch (error: any) {
    console.error('快速登录失败', error)
    ElMessage.error(error.message || '登录失败，请检查后端服务是否启动')
  } finally {
    loading.value = false
    currentLogin.value = ''
  }
}

const handleFeishuLogin = () => {
  const appId = import.meta.env.VITE_FEISHU_APP_ID || 'cli_test'
  const redirectUri = encodeURIComponent(window.location.origin + '/login/callback')
  const state = 'STATE'
  
  const authUrl = `https://open.feishu.cn/open-apis/authen/v1/authorize?app_id=${appId}&redirect_uri=${redirectUri}&state=${state}`
  
  window.location.href = authUrl
}

const handleMockLogin = async () => {
  try {
    await mockFormRef.value?.validate()
  } catch {
    return
  }
  
  loading.value = true
  
  try {
    const res = await authApi.mockLogin(mockForm) as any
    userStore.setToken(res.access_token)
    
    const user = res.user as any
    
    try {
      const roles = await authApi.getUserRoles()
      user.roles = roles
    } catch (roleError) {
      console.warn('获取用户角色失败', roleError)
      user.roles = []
    }
    
    userStore.setUserInfo(user as any)
    
    ElMessage.success('模拟登录成功')
    router.push('/leads')
  } catch (error: any) {
    console.error('模拟登录失败', error)
    ElMessage.error(error.message || '登录失败，请检查后端服务是否启动')
  } finally {
    loading.value = false
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
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  overflow: hidden;
}

.card-body {
  padding: $wolf-space-lg;
}

.logo {
  text-align: center;
  margin-bottom: $wolf-space-lg;
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

.dev-login-section {
  margin-bottom: $wolf-space-md;
}

.section-title {
  font-size: $wolf-font-size-auxiliary;
  color: $wolf-text-tertiary;
  font-weight: $wolf-font-weight-medium;
  margin-bottom: $wolf-space-md;
  text-align: center;
}

.quick-login-buttons {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $wolf-space-sm;
}

.quick-login-btn {
  height: 48px;
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  border-radius: $wolf-radius-sm;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: $wolf-space-xs;
  background: $wolf-bg-hover;
  border: 1px solid $wolf-border-default;
  color: $wolf-text-secondary;
  transition: all 0.2s ease;
}

.quick-login-btn:hover {
  background: $wolf-bg-hover;
  border-color: $wolf-border-default;
}

.quick-login-btn .el-icon {
  font-size: 18px;
}

.admin-btn {
  background: $wolf-primary;
  border-color: $wolf-primary;
  color: $wolf-text-inverse;
}

.admin-btn:hover {
  background: $wolf-primary-hover;
  border-color: $wolf-primary-hover;
}

.director-btn {
  background: $wolf-success-bg;
  border-color: $wolf-success-border;
  color: $wolf-success-text;
}

.director-btn:hover {
  background: $wolf-success-bg;
}

.sales-btn {
  background: $wolf-warning-bg;
  border-color: $wolf-warning-border;
  color: $wolf-warning-text;
}

.sales-btn:hover {
  background: $wolf-warning-bg;
}

.finance-btn {
  background: $wolf-bg-hover;
  border-color: $wolf-border-default;
  color: $wolf-text-secondary;
}

.finance-btn:hover {
  background: $wolf-bg-hover;
}

.divider {
  display: flex;
  align-items: center;
  margin: $wolf-space-md 0;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: $wolf-border-divider;
}

.divider span {
  padding: 0 $wolf-space-md;
  color: $wolf-text-tertiary;
  font-size: $wolf-font-size-auxiliary;
}

.login-tabs {
  margin-bottom: $wolf-space-md;
}

.login-tabs :deep(.el-tabs__header) {
  margin-bottom: $wolf-space-md;
}

.login-tabs :deep(.el-tabs__item) {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-medium;
  color: $wolf-text-tertiary;
  padding: 0 $wolf-space-md;
  height: 36px;
  line-height: 36px;
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
  min-height: 100px;
}

.login-button {
  width: 100%;
  height: 40px;
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

.tips {
  margin-top: $wolf-space-md;
  padding-top: $wolf-space-md;
  border-top: 1px solid $wolf-border-divider;
  text-align: center;
}

.tips p {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin: 0;
}

@media (max-width: 480px) {
  .card-body {
    padding: $wolf-space-md;
  }

  .quick-login-buttons {
    grid-template-columns: 1fr;
  }

  .quick-login-btn {
    flex-direction: row;
    gap: $wolf-space-sm;
  }
}
</style>
