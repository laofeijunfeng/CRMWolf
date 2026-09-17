<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { toTypedSchema } from '@vee-validate/zod'
import { ErrorMessage, useForm } from 'vee-validate'
import { toast } from 'vue-sonner'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataViewStatePanel,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Skeleton,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/crmwolf'
import { CardTitle } from '@/components/ui/card'
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form'
import { authApi } from '@/api/auth'
import { oauthApi, type OAuthBindingStatusResponse } from '@/api/oauth'
import { changePasswordSchema, type ChangePasswordFormValues } from '@/schemas/account-settings'
import { useUserStore } from '@/stores/user'
import { useRoute } from 'vue-router'
import { useHeaderStore } from '@/stores/header'
import { handleApiError } from '@/utils/errorHandler'
import { rememberOAuthReturnPath } from '@/utils/authRecovery'
import { Link2, Loader2, Unlink } from 'lucide-vue-next'
import SettingsContent from '@/views/settings/SettingsContent.vue'

const userStore = useUserStore()
const route = useRoute()
const headerStore = useHeaderStore()
const { userInfo } = storeToRefs(userStore)

const isInitialLoad = ref<boolean>(userInfo.value === null)
const loadError = ref<boolean>(false)
const avatarFailed = ref<boolean>(false)
const passwordDialogOpen = ref<boolean>(false)
const passwordSubmitting = ref<boolean>(false)
const oauthLoading = ref<boolean>(true)
const oauthSubmitting = ref<boolean>(false)
const feishuBinding = ref<OAuthBindingStatusResponse | null>(null)
const passwordVisible = reactive<Record<'oldPassword' | 'newPassword' | 'confirmPassword', boolean>>({
  oldPassword: false,
  newPassword: false,
  confirmPassword: false,
})
const userRoles = computed(() => userInfo.value?.roles ?? [])
const avatarUrl = computed(() => {
  const url = userInfo.value?.avatar_url?.trim()
  return url !== undefined && url.length > 0 ? url : ''
})

const { handleSubmit, resetForm } = useForm<ChangePasswordFormValues>({
  validationSchema: toTypedSchema(changePasswordSchema),
  initialValues: {
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  },
})

const displayValue = (value?: string | null): string => {
  const trimmed = value?.trim()
  return trimmed !== undefined && trimmed.length > 0 ? trimmed : '未设置'
}
const formatDateTime = (value?: string | null): string => {
  if (value === undefined || value === null || value.trim().length === 0 || Number.isNaN(Date.parse(value))) return '未设置'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

const loadUser = async (): Promise<void> => {
  isInitialLoad.value = true
  loadError.value = false
  try {
    await userStore.fetchUserInfo()
  } catch (error: unknown) {
    loadError.value = true
    handleApiError(error, '获取账户信息')
  } finally {
    isInitialLoad.value = false
  }
}

const loadFeishuBinding = async (): Promise<void> => {
  oauthLoading.value = true
  try {
    feishuBinding.value = await oauthApi.getFeishuBindingStatus()
  } catch {
    feishuBinding.value = null
  } finally {
    oauthLoading.value = false
  }
}

const resetPasswordVisibility = (): void => {
  passwordVisible.oldPassword = false
  passwordVisible.newPassword = false
  passwordVisible.confirmPassword = false
}

const closePasswordDialog = (): void => {
  resetForm()
  resetPasswordVisibility()
  passwordDialogOpen.value = false
}

const handlePasswordDialogOpenChange = (open: boolean): void => {
  if (open) {
    passwordDialogOpen.value = true
    return
  }
  closePasswordDialog()
}

const focusFirstInvalidField = async (): Promise<void> => {
  await nextTick()
  const firstInvalid = document.querySelector<HTMLInputElement>('input[aria-invalid="true"]')
  firstInvalid?.focus()
}

const submitPassword = handleSubmit(async (values): Promise<void> => {
  passwordSubmitting.value = true
  try {
    await authApi.changePassword({ old_password: values.oldPassword, new_password: values.newPassword })
    resetForm()
    passwordDialogOpen.value = false
    toast.success('密码修改成功')
  } catch (error: unknown) {
    handleApiError(error, '修改密码')
  } finally {
    passwordSubmitting.value = false
  }
}, focusFirstInvalidField)

const copyUserId = async (): Promise<void> => {
  try {
    await navigator.clipboard.writeText(String(userInfo.value?.id ?? ''))
    toast.success('用户 ID 已复制')
  } catch (error: unknown) {
    handleApiError(error, '复制用户 ID')
  }
}

const bindFeishu = async (): Promise<void> => {
  oauthSubmitting.value = true
  try {
    const response = await oauthApi.getFeishuBindUrl()
    // The provider returns to a fresh callback route. Persist the current
    // settings context so binding never drops the user at a fixed page.
    rememberOAuthReturnPath(route.fullPath)
    window.location.href = response.auth_url
  } catch (error: unknown) {
    oauthSubmitting.value = false
    handleApiError(error, '绑定飞书账号')
  }
}

const unbindFeishu = async (): Promise<void> => {
  oauthSubmitting.value = true
  try {
    const response = await oauthApi.unbindFeishu()
    toast.success(response.message)
    await loadFeishuBinding()
  } catch (error: unknown) {
    handleApiError(error, '解绑飞书账号')
  } finally {
    oauthSubmitting.value = false
  }
}

const initials = (): string => {
  const name = userInfo.value?.name?.trim()
  return name !== undefined && name.length > 0 ? name.slice(0, 1) : '用'
}

onMounted(() => {
  headerStore.clear()
  if (userInfo.value === null) void loadUser()
  void loadFeishuBinding()
})
</script>

<template>
  <SettingsContent ariaLabel="账户设置" description="个人资料和登录安全。飞书个人绑定与团队级飞书应用配置不是同一件事。" class="account-settings">
    <DataViewStatePanel
      :state="isInitialLoad ? 'loading' : loadError ? 'error' : userInfo === null ? 'empty' : 'ready'"
      error-title="账户信息加载失败"
      error-description="请检查网络后重试。"
      empty-title="暂无账户信息"
      empty-description="暂时无法显示账户资料，请稍后重试。"
      class="account-settings__state"
      @retry="loadUser"
    >
      <template #loading>
        <div class="account-settings__cards" aria-label="正在加载账户信息">
          <Card v-for="index in 2" :key="index">
            <CardHeader><Skeleton class="h-6 w-32" /></CardHeader>
            <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /><Skeleton class="h-10 w-full" /></CardContent>
          </Card>
        </div>
      </template>

      <template #error-action>
        <Button data-testid="account-retry" variant="outline" @click="loadUser">重试</Button>
      </template>

      <template #default>
        <div v-if="userInfo" class="account-settings__cards">
      <Card>
        <CardHeader>
          <CardTitle>个人信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="account-settings__profile">
            <Avatar class="h-16 w-16">
              <AvatarImage v-if="avatarUrl.length > 0 && !avatarFailed" :src="avatarUrl" :alt="`${displayValue(userInfo.name)}的头像`" @error="avatarFailed = true" />
              <AvatarFallback>{{ initials() }}</AvatarFallback>
            </Avatar>
            <div>
              <div class="font-medium">{{ displayValue(userInfo.name) }}</div>
              <p class="text-sm text-muted-foreground">{{ displayValue(userInfo.email) }}</p>
            </div>
          </div>
          <dl class="settings-dl">
            <dt>姓名</dt><dd>{{ displayValue(userInfo.name) }}</dd>
            <dt>邮箱</dt><dd>{{ displayValue(userInfo.email) }}</dd>
            <dt>手机号</dt><dd>{{ displayValue(userInfo.mobile) }}</dd>
            <dt>所属区域</dt><dd>{{ displayValue(userInfo.region) }}</dd>
            <dt>工号</dt><dd>{{ displayValue(userInfo.employee_no) }}</dd>
            <dt>账户状态</dt><dd><Badge>{{ displayValue(userInfo.status) }}</Badge></dd>
            <dt>用户 ID</dt>
            <dd class="flex items-center gap-2 tabular-nums">
              <span>{{ userInfo.id }}</span>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button type="button" variant="ghost" size="sm" aria-label="复制用户 ID" @click="copyUserId">复制</Button>
                </TooltipTrigger>
                <TooltipContent>复制用户 ID</TooltipContent>
              </Tooltip>
            </dd>
            <dt>角色</dt>
            <dd class="flex flex-wrap gap-2">
              <Badge v-for="role in userRoles" :key="role.id" variant="secondary">{{ role.name }}</Badge>
              <span v-if="userRoles.length === 0">未设置</span>
            </dd>
            <dt>创建时间</dt><dd>{{ formatDateTime(userInfo.created_at) }}</dd>
            <dt>更新时间</dt><dd>{{ formatDateTime(userInfo.updated_at) }}</dd>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>安全与授权</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="settings-setting-row">
            <div>
              <div class="font-medium">登录密码</div>
              <p class="text-sm text-muted-foreground">定期更新密码有助于保护账户安全。</p>
            </div>
            <Button data-testid="change-password-trigger" variant="outline" @click="passwordDialogOpen = true">修改密码</Button>
          </div>
          <div v-if="oauthLoading || feishuBinding?.enabled" class="settings-setting-row">
            <div>
              <div class="font-medium">飞书账号</div>
              <p class="text-sm text-muted-foreground">
                <span v-if="oauthLoading">正在加载授权状态</span>
                <span v-else-if="feishuBinding?.bound === true">已绑定 {{ displayValue(feishuBinding.name ?? feishuBinding.email) }}</span>
                <span v-else>当前未绑定飞书账号</span>
                。这是个人绑定，不是团队应用配置
              </p>
            </div>
            <Button
              v-if="!oauthLoading && feishuBinding?.bound === true"
              variant="outline"
              :disabled="oauthSubmitting"
              @click="unbindFeishu"
            >
              <Loader2 v-if="oauthSubmitting" class="mr-2 h-4 w-4 animate-spin" />
              <Unlink v-else class="mr-2 h-4 w-4" />
              解绑
            </Button>
            <Button
              v-else-if="!oauthLoading"
              :disabled="oauthSubmitting"
              @click="bindFeishu"
            >
              <Loader2 v-if="oauthSubmitting" class="mr-2 h-4 w-4 animate-spin" />
              <Link2 v-else class="mr-2 h-4 w-4" />
              绑定飞书
            </Button>
          </div>
        </CardContent>
      </Card>
        </div>
      </template>
    </DataViewStatePanel>

    <Dialog :open="passwordDialogOpen" @update:open="handlePasswordDialogOpenChange">
      <DialogContent>
        <DialogHeader><DialogTitle>修改密码</DialogTitle></DialogHeader>
        <form class="space-y-4" @submit.prevent="submitPassword">
          <FormField v-slot="{ value, handleChange, handleBlur }" name="oldPassword">
            <FormItem>
              <FormLabel>当前密码</FormLabel>
              <div class="account-settings__password-input">
                <FormControl><Input :model-value="value" name="oldPassword" :type="passwordVisible.oldPassword ? 'text' : 'password'" autocomplete="current-password" @update:model-value="handleChange" @blur="handleBlur" /></FormControl>
                <Tooltip><TooltipTrigger as-child><Button type="button" variant="ghost" size="icon" :aria-label="passwordVisible.oldPassword ? '隐藏当前密码' : '显示当前密码'" @click="passwordVisible.oldPassword = !passwordVisible.oldPassword">{{ passwordVisible.oldPassword ? '隐藏' : '显示' }}</Button></TooltipTrigger><TooltipContent>{{ passwordVisible.oldPassword ? '隐藏密码' : '显示密码' }}</TooltipContent></Tooltip>
              </div>
              <ErrorMessage v-slot="{ message }" as="div" name="oldPassword">
                <p v-if="message" role="alert" class="text-sm font-medium text-destructive">{{ message }}</p>
              </ErrorMessage>
            </FormItem>
          </FormField>

          <FormField v-slot="{ value, handleChange, handleBlur }" name="newPassword">
            <FormItem>
              <FormLabel>新密码</FormLabel>
              <div class="account-settings__password-input">
                <FormControl><Input :model-value="value" name="newPassword" :type="passwordVisible.newPassword ? 'text' : 'password'" autocomplete="new-password" @update:model-value="handleChange" @blur="handleBlur" /></FormControl>
                <Tooltip><TooltipTrigger as-child><Button type="button" variant="ghost" size="icon" :aria-label="passwordVisible.newPassword ? '隐藏新密码' : '显示新密码'" @click="passwordVisible.newPassword = !passwordVisible.newPassword">{{ passwordVisible.newPassword ? '隐藏' : '显示' }}</Button></TooltipTrigger><TooltipContent>{{ passwordVisible.newPassword ? '隐藏密码' : '显示密码' }}</TooltipContent></Tooltip>
              </div>
              <FormDescription>密码长度为 6–50 个字符。</FormDescription>
              <ErrorMessage v-slot="{ message }" as="div" name="newPassword">
                <p v-if="message" role="alert" class="text-sm font-medium text-destructive">{{ message }}</p>
              </ErrorMessage>
            </FormItem>
          </FormField>

          <FormField v-slot="{ value, handleChange, handleBlur }" name="confirmPassword">
            <FormItem>
              <FormLabel>确认新密码</FormLabel>
              <div class="account-settings__password-input">
                <FormControl><Input :model-value="value" name="confirmPassword" :type="passwordVisible.confirmPassword ? 'text' : 'password'" autocomplete="new-password" @update:model-value="handleChange" @blur="handleBlur" /></FormControl>
                <Tooltip><TooltipTrigger as-child><Button type="button" variant="ghost" size="icon" :aria-label="passwordVisible.confirmPassword ? '隐藏确认密码' : '显示确认密码'" @click="passwordVisible.confirmPassword = !passwordVisible.confirmPassword">{{ passwordVisible.confirmPassword ? '隐藏' : '显示' }}</Button></TooltipTrigger><TooltipContent>{{ passwordVisible.confirmPassword ? '隐藏密码' : '显示密码' }}</TooltipContent></Tooltip>
              </div>
              <ErrorMessage v-slot="{ message }" as="div" name="confirmPassword">
                <p v-if="message" role="alert" class="text-sm font-medium text-destructive">{{ message }}</p>
              </ErrorMessage>
            </FormItem>
          </FormField>

          <DialogFooter>
            <Button type="button" variant="outline" :disabled="passwordSubmitting" @click="closePasswordDialog">取消</Button>
            <Button type="submit" :disabled="passwordSubmitting">{{ passwordSubmitting ? '正在保存…' : '保存密码' }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </SettingsContent>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.account-settings {
  &__cards { display: grid; gap: $wolf-card-gap-v2; }
  &__profile { display: flex; gap: $wolf-space-lg-v2; align-items: flex-start; }
  &__password-input { display: flex; align-items: center; gap: $wolf-space-sm-v2; }
  &__password-input > :first-child { flex: 1; }

  @media (max-width: $wolf-breakpoint-sm-v2) {
    &__profile { gap: $wolf-card-padding-mobile-v2; }
    &__password-input :deep(input) { min-height: $wolf-input-height-mobile-v2; padding-inline: $wolf-input-padding-mobile-v2; font-size: $wolf-font-size-body-mobile-v2; }
    &__password-input :deep(button) { min-height: $wolf-button-height-mobile-v2; }
  }
}

@media (prefers-reduced-motion: reduce) {
  .account-settings :deep(button) { transition-property: none; }
}
</style>
