<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { Field, useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Copy } from 'lucide-vue-next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { InputField } from '@/components/crmwolf'
import ErrorState from '@/components/crmwolf/ErrorState.vue'
import { oauthApi } from '@/api/oauth'
import type { OAuthProviderConfigResponse, OAuthProviderConfigUpdate } from '@/api/oauth'
import { handleApiError } from '@/utils/errorHandler'
import { copyToClipboard } from '@/utils/clipboard'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { useRouteLeaveGuard } from '@/composables/useRouteLeaveGuard'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { useHeaderStore } from '@/stores/header'

import { usePageTitle } from '@/composables/usePageTitle'
import SettingsContent from '@/views/settings/SettingsContent.vue'

usePageTitle()
const headerStore = useHeaderStore()


const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { canAccess, permissionsUnavailable } = useSettingsAccess()
const integrationSettings = getSettingsNavigationItem('integrations')

const loading = ref(true)
const saving = ref(false)
const loadError = ref(false)
const config = ref<OAuthProviderConfigResponse | null>(null)

const hasAccess = computed(() => integrationSettings !== undefined && canAccess(integrationSettings))
const retryingPermissions = computed(() => permissionStore.loadState === 'loading')

const callbackUrl = computed(() => `${window.location.origin}/auth/feishu/callback`)

const schema = toTypedSchema(z.object({
  enabled: z.boolean().default(false),
  app_id: z.string().trim().min(1, '请输入 App ID').max(128, 'App ID 不能超过128个字符'),
  app_secret: z.string().trim().max(255, 'App Secret 不能超过255个字符').optional(),
  redirect_uri: z.string().trim().url('请输入有效的重定向 URL').max(500, '重定向 URL 不能超过500个字符'),
}))

const { handleSubmit, resetForm, setFieldValue, values, meta } = useForm({
  validationSchema: schema,
  initialValues: {
    enabled: false,
    app_id: '',
    app_secret: '',
    redirect_uri: callbackUrl.value,
  },
})

useRouteLeaveGuard({
  isDirty: (): boolean => meta.value.dirty,
  isSubmitting: (): boolean => saving.value,
})

const retryPermissions = async (): Promise<void> => {
  await teamStore.retryPermissionSync()
}

const fetchConfig = async (): Promise<void> => {
  if (!hasAccess.value) {
    loading.value = false
    return
  }

  loading.value = true
  loadError.value = false
  try {
    const response = await oauthApi.getFeishuConfig()
    config.value = response
    resetForm({
      values: {
        enabled: response.enabled,
        app_id: response.app_id ?? '',
        app_secret: '',
        redirect_uri: response.redirect_uri ?? callbackUrl.value,
      },
    })
  } catch (error) {
    loadError.value = true
    handleApiError(error, '获取第三方集成配置')
  } finally {
    loading.value = false
  }
}

const onSubmit = handleSubmit(async (formValues) => {
  saving.value = true
  try {
    const payload: OAuthProviderConfigUpdate = {
      enabled: formValues.enabled ?? false,
      app_id: formValues.app_id ?? '',
      redirect_uri: formValues.redirect_uri ?? callbackUrl.value,
      bot_enabled: config.value?.bot_enabled ?? false,
      bot_verification_token: config.value?.bot_verification_token,
      bot_encrypt_key: config.value?.bot_encrypt_key,
      bot_open_id: config.value?.bot_open_id,
    }
    if (formValues.app_secret !== undefined && formValues.app_secret.trim().length > 0) {
      payload.app_secret = formValues.app_secret
    }
    const response = await oauthApi.updateFeishuConfig(payload)
    config.value = response
    resetForm({
      values: {
        enabled: response.enabled,
        app_id: response.app_id ?? '',
        app_secret: '',
        redirect_uri: response.redirect_uri ?? callbackUrl.value,
      },
    })
    toast.success('第三方集成配置已保存')
  } catch (error) {
    handleApiError(error, '保存第三方集成配置')
  } finally {
    saving.value = false
  }
})

const copyCallbackUrl = async (): Promise<void> => {
  await copyToClipboard(values.redirect_uri ?? callbackUrl.value, '重定向 URL')
}

onMounted(() => {
  headerStore.clear()
})

watch(hasAccess, (ok) => {
  if (ok) void fetchConfig()
}, { immediate: true })

</script>

<template>
  <SettingsContent ariaLabel="第三方集成" description="当前团队的飞书应用配置。和个人账户里的飞书绑定分开。">
    <ErrorState
      v-if="permissionsUnavailable"
      variant="error"
      title="权限信息暂不可用"
      description="暂时无法确认你的团队设置权限。请重试权限同步，避免在权限不明确时继续操作。"
    >
      <template #action>
        <Button :loading="retryingPermissions" @click="retryPermissions">
          重试权限同步
        </Button>
      </template>
    </ErrorState>
    <ErrorState
      v-else-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问第三方集成的权限，请联系团队所有者或管理员。"
    />
    <template v-else>
      <div v-if="loading" class="flex flex-col gap-4" aria-label="正在加载第三方集成">
        <Card v-for="index in 2" :key="index">
          <CardHeader><Skeleton class="h-6 w-36" /></CardHeader>
          <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /></CardContent>
        </Card>
      </div>
      <ErrorState
        v-else-if="loadError"
        variant="error"
        title="第三方集成加载失败"
        description="请检查网络后重试。"
      >
        <template #action><Button variant="outline" @click="fetchConfig">重试</Button></template>
      </ErrorState>
      <form v-else class="flex flex-col gap-4" @submit.prevent="onSubmit">
        <Card>
          <CardHeader>
            <CardTitle>飞书应用</CardTitle>
            <CardDescription>当前配置只对本团队生效，用于飞书登录。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <Field v-slot="{ value }" name="enabled">
              <div class="flex items-center justify-between gap-4">
                <div class="space-y-0.5">
                  <Label for="feishu-enabled">启用飞书登录</Label>
                  <p id="feishu-enabled-description" class="text-caption text-muted-foreground">
                    启用后，团队邀请链接将使用飞书登录。
                  </p>
                </div>
                <Switch
                  id="feishu-enabled"
                  aria-describedby="feishu-enabled-description"
                  :model-value="(value as boolean) ?? false"
                  :disabled="loading || saving"
                  @update:model-value="(checked: boolean) => setFieldValue('enabled', checked)"
                />
              </div>
            </Field>

            <div class="flex flex-col gap-4">
              <Field v-slot="{ value, handleChange, handleBlur, errorMessage }" name="app_id">
                <InputField
                  id="feishu-app-id"
                  label="App ID"
                  :model-value="value as string"
                  :disabled="loading || saving"
                  autocomplete="off"
                  :error="errorMessage ?? ''"
                  @update:model-value="handleChange"
                  @blur="handleBlur"
                />
              </Field>

              <Field v-slot="{ value, handleChange, handleBlur, errorMessage }" name="app_secret">
                <InputField
                  id="feishu-app-secret"
                  label="App Secret"
                  :model-value="value as string"
                  :placeholder="config?.app_secret_configured ? '已配置，留空则不修改' : '请输入 App Secret'"
                  :disabled="loading || saving"
                  type="password"
                  autocomplete="new-password"
                  helper-text="已配置时留空保存表示保持原密钥。"
                  :error="errorMessage ?? ''"
                  @update:model-value="handleChange"
                  @blur="handleBlur"
                />
              </Field>

              <Field v-slot="{ value, handleChange, handleBlur, errorMessage }" name="redirect_uri">
                <div class="grid gap-1">
                  <Label for="feishu-redirect-uri" class="text-caption font-medium text-foreground">重定向 URL</Label>
                  <div class="flex items-start gap-2">
                    <Input
                      id="feishu-redirect-uri"
                      class="flex-1"
                      :model-value="value as string"
                      :disabled="loading || saving"
                      :aria-invalid="Boolean(errorMessage)"
                      :aria-describedby="errorMessage ? 'feishu-redirect-uri-error' : undefined"
                      @update:model-value="handleChange"
                      @blur="handleBlur"
                    />
                    <Button type="button" variant="outline" size="icon" aria-label="复制重定向 URL" @click="copyCallbackUrl">
                      <Copy class="h-4 w-4" />
                    </Button>
                  </div>
                  <p v-if="errorMessage" id="feishu-redirect-uri-error" class="text-caption text-destructive" role="alert">
                    {{ errorMessage }}
                  </p>
                </div>
              </Field>
            </div>
          </CardContent>
        </Card>

        <div class="settings-form-actions">
          <Button type="submit" :disabled="loading || saving">
            {{ saving ? '正在保存...' : '保存配置' }}
          </Button>
        </div>
      </form>
    </template>
  </SettingsContent>
</template>
