<template>
  <div class="login-container min-h-dvh flex items-center justify-center bg-wolf-bg-page px-wolf-lg py-wolf-lg">
    <Card class="login-card w-full max-w-[420px] overflow-hidden">
      <CardContent class="p-wolf-8">
        <!-- Logo Section -->
        <div class="logo text-center mb-wolf-8">
          <img
            src="/logo.png"
            alt="CRM Logo"
            class="w-[64px] h-[64px] object-contain mx-auto mb-wolf-md"
          />
          <h1 class="text-wolf-title font-wolf-semibold text-wolf-text-primary m-0">
            智能客户关系管理系统
          </h1>
        </div>

        <!-- Login/Register Tabs -->
        <Tabs v-model="activeTab" class="login-tabs">
          <TabsList class="w-full mb-wolf-lg p-0">
            <TabsTrigger
              value="login"
              class="flex-1 h-[40px] text-wolf-body font-wolf-medium text-wolf-text-tertiary data-[state=active]:text-wolf-primary data-[state=active]:font-wolf-semibold hover:text-wolf-primary transition-colors duration-wolf-fast"
            >
              登录
            </TabsTrigger>
            <TabsTrigger
              value="register"
              class="flex-1 h-[40px] text-wolf-body font-wolf-medium text-wolf-text-tertiary data-[state=active]:text-wolf-primary data-[state=active]:font-wolf-semibold hover:text-wolf-primary transition-colors duration-wolf-fast"
            >
              注册
            </TabsTrigger>
          </TabsList>

          <!-- Login Tab -->
          <TabsContent value="login" class="tab-content pt-wolf-xs focus:outline-none">
            <Form
              :schema="loginFormSchema"
              @submit="handleLogin"
              class="space-y-wolf-md"
            >
              <FormField v-slot="{ componentField }" name="email">
                <FormItem>
                  <FormControl>
                    <TouchInput
                      v-bind="componentField"
                      label="邮箱"
                      type="email"
                      placeholder="请输入邮箱"
                      autocomplete="email"
                      :disabled="loading"
                      required
                      size="mobile"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              </FormField>

              <FormField v-slot="{ componentField }" name="password">
                <FormItem>
                  <FormControl>
                    <TouchInput
                      v-bind="componentField"
                      label="密码"
                      type="password"
                      placeholder="请输入密码"
                      autocomplete="current-password"
                      :disabled="loading"
                      required
                      show-password-toggle
                      size="mobile"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              </FormField>

              <TouchButton
                type="submit"
                size="touch"
                :loading="loading"
                class="w-full mt-wolf-lg"
              >
                登录
              </TouchButton>
            </Form>
          </TabsContent>

          <!-- Register Tab -->
          <TabsContent value="register" class="tab-content pt-wolf-xs focus:outline-none">
            <Form
              :schema="registerFormSchema"
              @submit="handleRegister"
              class="space-y-wolf-md"
            >
              <FormField v-slot="{ componentField }" name="email">
                <FormItem>
                  <FormControl>
                    <TouchInput
                      v-bind="componentField"
                      label="邮箱"
                      type="email"
                      placeholder="请输入邮箱"
                      autocomplete="email"
                      :disabled="registering"
                      required
                      size="mobile"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              </FormField>

              <FormField v-slot="{ componentField }" name="name">
                <FormItem>
                  <FormControl>
                    <TouchInput
                      v-bind="componentField"
                      label="姓名"
                      type="text"
                      placeholder="请输入姓名"
                      autocomplete="name"
                      :disabled="registering"
                      required
                      size="mobile"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              </FormField>

              <FormField v-slot="{ componentField }" name="password">
                <FormItem>
                  <FormControl>
                    <TouchInput
                      v-bind="componentField"
                      label="密码"
                      type="password"
                      placeholder="请设置密码（6-50位）"
                      autocomplete="new-password"
                      helper-text="密码长度为6-50个字符"
                      :disabled="registering"
                      required
                      show-password-toggle
                      size="mobile"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              </FormField>

              <TouchButton
                type="submit"
                size="touch"
                :loading="registering"
                class="w-full mt-wolf-lg"
              >
                注册
              </TouchButton>
            </Form>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>

    <!-- Toast Container -->
    <Toast position="top-center" :duration="4000" />
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
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'sonner'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { authApi } from '@/api/auth'
import { loginFormSchema, registerFormSchema } from '@/schemas/auth'
import {
  TouchButton,
  TouchInput,
  Form,
  FormField,
  FormItem,
  FormControl,
  FormMessage,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Card,
  CardContent,
  Toast,
} from '@/components/crmwolf'

const router = useRouter()
const userStore = useUserStore()
const teamStore = useTeamStore()

const activeTab = ref('login')
const loading = ref(false)
const registering = ref(false)

/**
 * Handle login form submission
 */
const handleLogin = async (values: Record<string, unknown>) => {
  loading.value = true

  try {
    const res = await authApi.loginWithPassword({
      email: values.email as string,
      password: values.password as string,
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

    // Success feedback (UI/UX Pro Max §8 success-feedback)
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
    // Error feedback (UI/UX Pro Max §8 error-recovery)
    const message = error instanceof Error ? error.message : '登录失败，请重试'
    toast.error('登录失败', { description: message })
  } finally {
    loading.value = false
  }
}

/**
 * Handle register form submission
 */
const handleRegister = async (values: Record<string, unknown>) => {
  registering.value = true

  try {
    const res = await authApi.registerWithPassword({
      email: values.email as string,
      name: values.name as string,
      password: values.password as string,
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

    // Success feedback
    toast.success('注册成功', { description: '正在跳转到团队设置...' })
    router.push('/onboarding')
  } catch (error: unknown) {
    // Error feedback
    const message = error instanceof Error ? error.message : '注册失败，请重试'
    toast.error('注册失败', { description: message })
  } finally {
    registering.value = false
  }
}
</script>

<style scoped>
/* Login page uses Tailwind CSS for all styling */
/* No custom CSS needed - all styles are utility-based */
</style>