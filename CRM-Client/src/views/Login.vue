<template>
  <div class="login-container min-h-dvh flex items-center justify-center bg-wolf-bg-page px-wolf-lg py-wolf-lg">
    <Card class="login-card w-full max-w-[420px] overflow-hidden">
      <CardContent class="p-wolf-lg pt-wolf-xl">
        <!-- Logo Section (UI/UX Pro Max §5: Visual Hierarchy, Whitespace Balance) -->
        <div class="logo-section flex flex-col items-center justify-center mb-wolf-xl">
          <!-- Logo -->
          <img
            src="/logo.png"
            alt="CRM Logo"
            class="w-16 h-16 object-contain mb-wolf-md"
            style="display: block; margin-left: auto; margin-right: auto;"
          />
          <!-- System Title -->
          <h1 class="text-wolf-title font-wolf-semibold text-wolf-text-primary text-center m-0 mb-wolf-md">
            智能客户关系管理系统
          </h1>
        </div>

        <!-- Login/Register Tabs -->
        <Tabs v-model="activeTab" class="login-tabs">
          <TabsList class="w-full mb-wolf-md p-1 bg-wolf-bg-muted rounded-wolf-lg">
            <TabsTrigger
              value="login"
              class="flex-1 h-[40px] text-wolf-body font-wolf-medium text-wolf-text-tertiary data-[state=active]:bg-wolf-bg-card data-[state=active]:text-wolf-primary data-[state=active]:font-wolf-semibold data-[state=active]:shadow-sm hover:text-wolf-primary transition-all duration-wolf-fast rounded-wolf"
            >
              登录
            </TabsTrigger>
            <TabsTrigger
              value="register"
              class="flex-1 h-[40px] text-wolf-body font-wolf-medium text-wolf-text-tertiary data-[state=active]:bg-wolf-bg-card data-[state=active]:text-wolf-primary data-[state=active]:font-wolf-semibold data-[state=active]:shadow-sm hover:text-wolf-primary transition-all duration-wolf-fast rounded-wolf"
            >
              注册
            </TabsTrigger>
          </TabsList>

          <!-- UI/UX Pro Max §7: Animation - Tab content fade transition -->
          <Transition name="fade" mode="out-in">
            <TabsContent v-if="activeTab === 'login'" value="login">
              <form class="space-y-wolf-md" @submit.prevent="handleLogin">
              <TouchInput
                v-model="loginForm.email"
                label="邮箱"
                type="email"
                placeholder="请输入邮箱"
                autocomplete="email"
                :disabled="loading"
                :error="loginErrors.email"
                required
                size="mobile"
              />

              <TouchInput
                v-model="loginForm.password"
                label="密码"
                type="password"
                placeholder="请输入密码"
                autocomplete="current-password"
                :disabled="loading"
                :error="loginErrors.password"
                required
                show-password-toggle
                size="mobile"
              />

              <Button
                type="submit"
                size="lg"
                :disabled="loading"
                class="w-full mt-wolf-lg"
              >
                <Loader2 v-if="loading" class="w-4 h-4 mr-2 animate-spin" />
                登录
              </Button>
            </form>
          </TabsContent>

            <TabsContent v-else value="register">
              <form class="space-y-wolf-md" @submit.prevent="handleRegister">
              <TouchInput
                v-model="registerForm.email"
                label="邮箱"
                type="email"
                placeholder="请输入邮箱"
                autocomplete="email"
                :disabled="registering"
                :error="registerErrors.email"
                required
                size="mobile"
              />

              <TouchInput
                v-model="registerForm.name"
                label="姓名"
                type="text"
                placeholder="请输入姓名"
                autocomplete="name"
                :disabled="registering"
                :error="registerErrors.name"
                required
                size="mobile"
              />

              <TouchInput
                v-model="registerForm.password"
                label="密码"
                type="password"
                placeholder="请设置密码（6-50位）"
                autocomplete="new-password"
                helper-text="密码长度为6-50个字符"
                :disabled="registering"
                :error="registerErrors.password"
                required
                show-password-toggle
                size="mobile"
              />

              <Button
                type="submit"
                size="lg"
                :disabled="registering"
                class="w-full mt-wolf-lg"
              >
                <Loader2 v-if="registering" class="w-4 h-4 mr-2 animate-spin" />
                注册
              </Button>
            </form>
          </TabsContent>
          </Transition>
        </Tabs>
      </CardContent>
    </Card>
  </div>
</template>

<script setup lang="ts">
/**
 * Login Page
 * UI/UX Pro Max compliant authentication UI
 *
 * Features:
 * - Visible labels (never placeholder-only) - §8 input-labels
 * - Error message below field - §8 error-placement
 * - Helper text for password - §8 input-helper-text
 * - Required field indicator (*) - §8 required-indicators
 * - Semantic input type (email) - §8 input-type-keyboard
 * - Password toggle - §8 password-toggle
 * - Autocomplete support - §8 autofill-support
 * - Loading state on button - §8 loading-buttons
 * - Toast notification - §8 success-feedback, §8 toast-dismiss
 * - Touch-friendly inputs (44px) - §2 touch-target-size
 * - Focus ring visible (2px) - §1 focus-states
 * - Keyboard navigation (Enter submit) - §1 keyboard-nav
 * - Error clarity + recovery - §8 error-clarity, §8 error-recovery
 * - Specific error messages by type - §8 error-feedback
 */
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { authApi } from '@/api/auth'
import { loginFormSchema, registerFormSchema } from '@/schemas/auth'
import { handleApiError } from '@/utils/errorHandler'
import {
  Button,
  TouchInput,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Card,
  CardContent,
} from '@/components/crmwolf'
import { Loader2 } from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()

const activeTab = ref('login')
const loading = ref(false)
const registering = ref(false)

// Login form state
const loginForm = reactive({
  email: '',
  password: '',
})

const loginErrors = reactive({
  email: '',
  password: '',
})

// Register form state
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

/**
 * Validate login form
 */
function validateLoginForm(): boolean {
  loginErrors.email = ''
  loginErrors.password = ''

  const result = loginFormSchema.safeParse(loginForm)
  if (!result.success) {
    for (const error of result.error.errors) {
      const field = error.path[0] as keyof typeof loginErrors
      if (field in loginErrors) {
        loginErrors[field] = error.message
      }
    }
    return false
  }
  return true
}

/**
 * Validate register form
 */
function validateRegisterForm(): boolean {
  registerErrors.email = ''
  registerErrors.name = ''
  registerErrors.password = ''

  const result = registerFormSchema.safeParse(registerForm)
  if (!result.success) {
    for (const error of result.error.errors) {
      const field = error.path[0] as keyof typeof registerErrors
      if (field in registerErrors) {
        registerErrors[field] = error.message
      }
    }
    return false
  }
  return true
}

/**
 * Handle login form submission
 */
async function handleLogin(): Promise<void> {
  if (!validateLoginForm()) return

  loading.value = true

  try {
    const res = await authApi.loginWithPassword({
      email: loginForm.email,
      password: loginForm.password,
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

    toast.success('登录成功', { description: '欢迎使用 CRM 系统' })

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
  } catch (error: unknown) {
    // UI/UX Pro Max §8: error-clarity + error-recovery
    // 使用统一错误处理，并根据业务场景提供自定义消息
    handleApiError(error, '登录', {
      password: {
        title: '密码错误',
        description: '密码不正确，请检查输入或尝试重置密码',
      },
      email: {
        title: '邮箱未注册',
        description: '该邮箱尚未注册，请检查邮箱地址或切换到注册',
      },
      invalid: {
        title: '密码错误',
        description: '密码不正确，请检查输入或尝试重置密码',
      },
      'not found': {
        title: '邮箱未注册',
        description: '该邮箱尚未注册，请检查邮箱地址或切换到注册',
      },
    })
  } finally {
    loading.value = false
  }
}

/**
 * Handle register form submission
 */
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
      console.warn('获取用户角色失败', roleError)
      userStore.setUserInfo(user)
    }

    toast.success('注册成功', { description: '正在跳转到团队设置...' })
    router.push('/onboarding')
  } catch (error: unknown) {
    // UI/UX Pro Max §8: error-clarity + error-recovery
    // 使用统一错误处理，并根据业务场景提供自定义消息
    handleApiError(error, '注册', {
      exists: {
        title: '邮箱已注册',
        description: '该邮箱已被使用，请更换邮箱或切换到登录',
      },
      email: {
        title: '邮箱已注册',
        description: '该邮箱已被使用，请更换邮箱或切换到登录',
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

<style scoped>
/* UI/UX Pro Max §7: Animation - Tab content fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease-out;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Reduced motion support (UI/UX Pro Max §7) */
@media (prefers-reduced-motion: reduce) {
  .fade-enter-active,
  .fade-leave-active {
    transition: none;
  }
}
</style>

<style scoped>
/* Login page uses Tailwind CSS for all styling */
/* No custom CSS needed - all styles are utility-based */
</style>