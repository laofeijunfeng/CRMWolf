<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { toTypedSchema } from '@vee-validate/zod'
import { ErrorMessage, useForm } from 'vee-validate'
import { toast } from 'vue-sonner'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Skeleton,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/crmwolf'
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form'
import { authApi } from '@/api/auth'
import { changePasswordSchema, type ChangePasswordFormValues } from '@/schemas/account-settings'
import { useUserStore } from '@/stores/user'
import { useHeaderStore } from '@/stores/header'
import { handleApiError } from '@/utils/errorHandler'

const userStore = useUserStore()
const headerStore = useHeaderStore()
const { userInfo } = storeToRefs(userStore)

const isInitialLoad = ref<boolean>(false)
const loadError = ref<boolean>(false)
const avatarFailed = ref<boolean>(false)
const passwordDialogOpen = ref<boolean>(false)
const passwordSubmitting = ref<boolean>(false)
const passwordVisible = reactive<Record<'oldPassword' | 'newPassword' | 'confirmPassword', boolean>>({
  oldPassword: false,
  newPassword: false,
  confirmPassword: false,
})

const { handleSubmit, resetForm } = useForm<ChangePasswordFormValues>({
  validationSchema: toTypedSchema(changePasswordSchema),
  initialValues: {
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  },
})

const displayValue = (value?: string | null): string => value?.trim() || '未设置'
const formatDateTime = (value?: string): string => {
  if (!value || Number.isNaN(Date.parse(value))) return '未设置'
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

const initials = (): string => userInfo.value?.name?.trim().slice(0, 1) || '用'

onMounted(() => {
  headerStore.clear()
  if (userInfo.value === null) void loadUser()
})
</script>

<template>
  <main class="account-settings account-settings--system" aria-label="账户设置">
    <div v-if="isInitialLoad" class="account-settings__cards" aria-label="正在加载账户信息">
      <Card v-for="index in 3" :key="index">
        <CardHeader><Skeleton class="h-6 w-32" /></CardHeader>
        <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /><Skeleton class="h-10 w-full" /></CardContent>
      </Card>
    </div>

    <Alert v-else-if="loadError" variant="destructive">
      <AlertTitle>账户信息加载失败</AlertTitle>
      <AlertDescription class="flex items-center justify-between gap-4">
        请检查网络后重试。
        <Button data-testid="account-retry" variant="outline" @click="loadUser">重试</Button>
      </AlertDescription>
    </Alert>

    <Alert v-else-if="userInfo === null">
      <AlertTitle>暂无账户信息</AlertTitle>
      <AlertDescription>暂时无法显示账户资料，请稍后重试。</AlertDescription>
    </Alert>

    <div v-else class="account-settings__cards">
      <Card>
        <CardHeader><h2>个人信息</h2></CardHeader>
        <CardContent class="account-settings__profile">
          <Avatar class="h-16 w-16">
            <AvatarImage v-if="userInfo.avatar_url && !avatarFailed" :src="userInfo.avatar_url" :alt="`${displayValue(userInfo.name)}的头像`" @error="avatarFailed = true" />
            <AvatarFallback>{{ initials() }}</AvatarFallback>
          </Avatar>
          <dl class="account-settings__details">
            <div><dt>姓名</dt><dd>{{ displayValue(userInfo.name) }}</dd></div>
            <div><dt>邮箱</dt><dd>{{ displayValue(userInfo.email) }}</dd></div>
            <div><dt>手机号</dt><dd>{{ displayValue(userInfo.mobile) }}</dd></div>
            <div><dt>所属区域</dt><dd>{{ displayValue(userInfo.region) }}</dd></div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><h2>账户详情</h2></CardHeader>
        <CardContent>
          <dl class="account-settings__details">
            <div><dt>用户 ID</dt><dd class="flex items-center gap-2 tabular-nums"><span>{{ userInfo.id }}</span><Tooltip><TooltipTrigger as-child><Button type="button" variant="ghost" size="sm" aria-label="复制用户 ID" @click="copyUserId">复制</Button></TooltipTrigger><TooltipContent>复制用户 ID</TooltipContent></Tooltip></dd></div>
            <div><dt>工号</dt><dd>{{ displayValue(userInfo.employee_no) }}</dd></div>
            <div><dt>账户状态</dt><dd><Badge>{{ displayValue(userInfo.status) }}</Badge></dd></div>
            <div><dt>创建时间</dt><dd>{{ formatDateTime(userInfo.created_at) }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatDateTime(userInfo.updated_at) }}</dd></div>
            <div><dt>角色</dt><dd class="flex flex-wrap gap-2"><Badge v-for="role in userInfo.roles" :key="role.id" variant="secondary">{{ role.name }}</Badge><span v-if="!userInfo.roles?.length">未设置</span></dd></div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><h2>安全设置</h2></CardHeader>
        <CardContent class="flex items-center justify-between gap-4">
          <div><Label class="font-medium">登录密码</Label><p class="text-sm text-muted-foreground">定期更新密码有助于保护账户安全。</p></div>
          <Button data-testid="change-password-trigger" @click="passwordDialogOpen = true">修改密码</Button>
        </CardContent>
      </Card>
    </div>

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
  </main>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.account-settings {
  min-height: 100%;
  padding: $wolf-page-padding-v2;
  background: $wolf-bg-page-v2;
  color: $wolf-text-primary-v2;
  font-family: $wolf-font-family-v2;
  font-size: $wolf-font-size-body-v2;
  font-weight: $wolf-font-weight-normal-v2;
  line-height: $wolf-line-height-body-v2;

  &__cards { display: grid; gap: $wolf-card-gap-v2; }
  &__profile { display: flex; gap: $wolf-space-lg-v2; align-items: flex-start; }
  &__details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: $wolf-space-lg-v2; width: 100%; }
  &__details div { min-width: 0; }
  &__details dt { color: $wolf-text-secondary-v2; font-size: 0.875rem; }
  &__details dd { margin: $wolf-space-xs-v2 0 0; overflow-wrap: anywhere; word-break: break-word; }
  &__password-input { display: flex; align-items: center; gap: $wolf-space-sm-v2; }
  &__password-input > :first-child { flex: 1; }

  @media (max-width: $wolf-breakpoint-sm-v2) {
    padding: $wolf-page-padding-mobile-v2;
    &__profile { gap: $wolf-card-padding-mobile-v2; }
    &__details { grid-template-columns: 1fr; gap: $wolf-form-item-gap-mobile-v2; }
    &__password-input :deep(input) { min-height: $wolf-input-height-mobile-v2; padding-inline: $wolf-input-padding-mobile-v2; font-size: $wolf-font-size-body-mobile-v2; }
    &__password-input :deep(button) { min-height: $wolf-button-height-mobile-v2; }
  }
}

@media (prefers-reduced-motion: reduce) {
  .account-settings :deep(button) { transition-property: none; }
}
</style>
