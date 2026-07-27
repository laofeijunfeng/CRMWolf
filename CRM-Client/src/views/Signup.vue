<template>
  <main class="auth-page">
    <div class="auth-page__shell">
      <div class="auth-page__brand">
        <img src="/logo.png" alt="CRM Logo" class="auth-page__logo" />
        <div class="auth-page__name">智能客户关系管理系统</div>
      </div>

      <Card class="auth-card">
        <CardHeader class="auth-card__header">
          <CardTitle class="auth-card__title">创建账号</CardTitle>
          <CardDescription>注册后继续完成团队设置</CardDescription>
        </CardHeader>
        <CardContent>
          <form class="auth-form" @submit.prevent="handleRegister">
            <div class="auth-form__field">
              <Label for="signup-email">邮箱</Label>
              <Input
                id="signup-email"
                v-model="registerForm.email"
                type="email"
                placeholder="name@example.com"
                autocomplete="email"
                required
                :disabled="registering"
                :aria-invalid="registerErrors.email.length > 0"
                aria-describedby="signup-email-error"
              />
              <p v-if="registerErrors.email" id="signup-email-error" class="auth-form__error">
                {{ registerErrors.email }}
              </p>
            </div>

            <div class="auth-form__field">
              <Label for="signup-name">姓名</Label>
              <Input
                id="signup-name"
                v-model="registerForm.name"
                type="text"
                placeholder="请输入姓名"
                autocomplete="name"
                required
                :disabled="registering"
                :aria-invalid="registerErrors.name.length > 0"
                aria-describedby="signup-name-error"
              />
              <p v-if="registerErrors.name" id="signup-name-error" class="auth-form__error">
                {{ registerErrors.name }}
              </p>
            </div>

            <div class="auth-form__field">
              <Label for="signup-password">密码</Label>
              <Input
                id="signup-password"
                v-model="registerForm.password"
                type="password"
                placeholder="请设置密码"
                autocomplete="new-password"
                required
                :disabled="registering"
                :aria-invalid="registerErrors.password.length > 0"
                aria-describedby="signup-password-hint signup-password-error"
              />
              <p id="signup-password-hint" class="auth-form__hint">密码长度为 6-50 个字符</p>
              <p v-if="registerErrors.password" id="signup-password-error" class="auth-form__error">
                {{ registerErrors.password }}
              </p>
            </div>

            <Button type="submit" class="w-full" :disabled="registering">
              <Loader2 v-if="registering" class="h-4 w-4 animate-spin" aria-hidden="true" />
              创建账号
            </Button>
          </form>

          <p class="auth-card__switch">
            已有账号？
            <RouterLink to="/login">登录</RouterLink>
          </p>
        </CardContent>
      </Card>
    </div>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import { authApi } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { registerFormSchema } from '@/schemas/auth'
import { useUserStore } from '@/stores/user'
import { handleApiError } from '@/utils/errorHandler'
import { logger } from '@/utils/logger'

const router = useRouter()
const userStore = useUserStore()

const registering = ref(false)
const registerForm = reactive({
  email: '',
  name: '',
  password: '',
})
const registerErrors = reactive({
  email: '',
  name: '',
  password: '',
})

function validateRegisterForm(): boolean {
  registerErrors.email = ''
  registerErrors.name = ''
  registerErrors.password = ''

  const result = registerFormSchema.safeParse(registerForm)
  if (!result.success) {
    for (const error of result.error.errors) {
      const field = error.path[0] as keyof typeof registerErrors
      if (field in registerErrors) registerErrors[field] = error.message
    }
    return false
  }
  return true
}

async function handleRegister(): Promise<void> {
  if (!validateRegisterForm()) return

  registering.value = true
  try {
    const res = await authApi.registerWithPassword({
      email: registerForm.email,
      name: registerForm.name,
      password: registerForm.password,
    })

    userStore.setToken(res.access_token)
    const user = res.user

    try {
      const roles = await authApi.getUserRoles()
      userStore.setUserInfo({ ...user, roles })
    } catch (roleError) {
      logger.warn('[Signup]', '获取用户角色失败', { error: roleError })
      userStore.setUserInfo(user)
    }

    toast.success('注册成功', { description: '正在跳转到团队设置...' })
    void router.push('/onboarding')
  } catch (error: unknown) {
    handleApiError(error, '注册', {
      exists: {
        title: '邮箱已注册',
        description: '该邮箱已被使用，请更换邮箱或登录',
      },
      email: {
        title: '邮箱已注册',
        description: '该邮箱已被使用，请更换邮箱或登录',
      },
      password: {
        title: '密码不符合要求',
        description: '密码长度需为 6-50 个字符，请重新设置',
      },
    })
  } finally {
    registering.value = false
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.auth-page {
  display: flex;
  min-height: 100dvh;
  align-items: center;
  justify-content: center;
  background: $wolf-bg-page-v2;
  padding: $wolf-space-xl-v2;
}

.auth-page__shell {
  display: grid;
  width: 100%;
  max-width: 420px;
  gap: $wolf-space-lg-v2;
}

.auth-page__brand {
  display: grid;
  justify-items: center;
  gap: $wolf-space-sm-v2;
  color: $wolf-text-primary-v2;
  font-size: $wolf-font-size-title-v2;
  font-weight: $wolf-font-weight-semibold-v2;
}

.auth-page__logo {
  width: 48px;
  height: 48px;
  object-fit: contain;
}

.auth-card {
  width: 100%;
  box-shadow: none;
}

.auth-card__header {
  text-align: center;
}

.auth-card__title {
  font-size: $wolf-font-size-title-v2;
}

.auth-form {
  display: grid;
  gap: $wolf-space-md-v2;
}

.auth-form__field {
  display: grid;
  gap: $wolf-space-sm-v2;
}

.auth-form__hint {
  margin: -2px 0 0;
  color: $wolf-text-tertiary-v2;
  font-size: $wolf-font-size-caption-v2;
}

.auth-form__error {
  margin: 0;
  color: $wolf-danger-text-v2;
  font-size: $wolf-font-size-caption-v2;
}

.auth-card__switch {
  margin: $wolf-space-lg-v2 0 0;
  text-align: center;
  color: $wolf-text-secondary-v2;
  font-size: $wolf-font-size-auxiliary-v2;

  a {
    color: $wolf-text-link-v2;
    font-weight: $wolf-font-weight-medium-v2;
    text-decoration: none;

    &:hover {
      color: $wolf-text-link-hover-v2;
      text-decoration: underline;
    }
  }
}

@media (max-width: 767px) {
  .auth-page {
    padding: $wolf-page-padding-mobile-v2;
  }
}
</style>
