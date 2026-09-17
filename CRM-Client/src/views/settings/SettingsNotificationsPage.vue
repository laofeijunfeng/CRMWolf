<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { AlertTriangle, Check } from 'lucide-vue-next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import ErrorState from '@/components/ErrorState.vue'
import { handleApiError } from '@/utils/errorHandler'
import { notificationConfigApi } from '@/api/notificationConfig'
import type { NotificationConfigResponse, NotificationConfigUpdate } from '@/api/notificationConfig'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { useSettingsUnsavedLeave } from '@/composables/useSettingsUnsavedLeave'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { usePageTitle } from '@/composables/usePageTitle'
import SettingsContent from '@/views/settings/SettingsContent.vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

usePageTitle()

const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { canAccess, permissionsUnavailable } = useSettingsAccess()
const notificationSettings = getSettingsNavigationItem('notifications')

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const loadError = ref(false)
const configInfo = ref<NotificationConfigResponse | null>(null)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const savedUrl = ref('')

const hasAccess = computed(() => notificationSettings !== undefined && canAccess(notificationSettings))
const retryingPermissions = computed(() => permissionStore.loadState === 'loading')

const notificationSchema = toTypedSchema(
  z.object({
    feishu_webhook_enabled: z.boolean().default(false),
    feishu_webhook_url: z.string()
      .refine((_val) => {
        return true
      }, '请输入 Webhook URL')
      .refine((val) => {
        if (!val) return true
        return val.includes('open.feishu.cn/open-apis/bot/v2/hook')
      }, 'URL 格式应为 https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
      .optional()
      .nullable(),
    notification_group_name: z.string().optional().nullable(),
  }),
)

const { handleSubmit, resetForm, setFieldValue, values, meta } = useForm({
  validationSchema: notificationSchema,
  initialValues: {
    feishu_webhook_enabled: false,
    feishu_webhook_url: '',
    notification_group_name: '',
  },
})

const { showLeaveConfirm, confirmLeave, cancelLeave } = useSettingsUnsavedLeave({
  isDirty: (): boolean => meta.value.dirty,
  isSubmitting: (): boolean => saving.value,
})

const handleLeaveDialogOpenChange = (open: boolean): void => {
  if (open) return
  Promise.resolve().then((): void => {
    if (showLeaveConfirm.value) cancelLeave()
  })
}

const canTest = computed(() => {
  return Boolean(values.feishu_webhook_enabled)
    && Boolean(values.feishu_webhook_url)
    && values.feishu_webhook_url === savedUrl.value
    && isValidWebhookUrl(values.feishu_webhook_url || '')
})

const testDisabledReason = computed(() => {
  if (values.feishu_webhook_enabled !== true) {
    return '请先开启「启用通知」开关'
  }
  if (values.feishu_webhook_url === undefined || values.feishu_webhook_url === null || values.feishu_webhook_url === '') {
    return '请先填写 Webhook URL'
  }
  if (values.feishu_webhook_url !== savedUrl.value) {
    return 'URL 已修改，请先保存后再测试'
  }
  if (!isValidWebhookUrl(values.feishu_webhook_url)) {
    return 'Webhook URL 格式不正确'
  }
  return ''
})

function isValidWebhookUrl(url: string): boolean {
  if (!url) return false
  try {
    new URL(url)
    return url.includes('open.feishu.cn/open-apis/bot/v2/hook')
  } catch {
    return false
  }
}

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
    const response = await notificationConfigApi.getConfig({ skipErrorNotification: true })
    configInfo.value = response
    if (response !== null && response !== undefined) {
      resetForm({
        values: {
          feishu_webhook_enabled: response.feishu_webhook_enabled ?? false,
          feishu_webhook_url: response.feishu_webhook_url ?? '',
          notification_group_name: response.notification_group_name ?? '',
        },
      })
      savedUrl.value = response.feishu_webhook_url ?? ''
    }
  } catch (error) {
    const err = error as { response?: { status?: number } }
    if (err.response?.status !== 404) {
      loadError.value = true
      handleApiError(error, '获取通知配置')
    }
  } finally {
    loading.value = false
  }
}

const onSubmit = handleSubmit(async (formValues) => {
  saving.value = true
  try {
    const updateData: NotificationConfigUpdate = {
      notification_method: 'webhook',
    }
    if (formValues.feishu_webhook_url !== undefined && formValues.feishu_webhook_url !== null && formValues.feishu_webhook_url !== '') {
      updateData.feishu_webhook_url = formValues.feishu_webhook_url
    }
    if (formValues.feishu_webhook_enabled !== undefined) {
      updateData.feishu_webhook_enabled = formValues.feishu_webhook_enabled
    }
    if (formValues.notification_group_name !== undefined && formValues.notification_group_name !== null && formValues.notification_group_name !== '') {
      updateData.notification_group_name = formValues.notification_group_name
    }
    const response = await notificationConfigApi.updateConfig(updateData)

    configInfo.value = response
    resetForm({
      values: {
        feishu_webhook_enabled: response.feishu_webhook_enabled ?? false,
        feishu_webhook_url: response.feishu_webhook_url ?? '',
        notification_group_name: response.notification_group_name ?? '',
      },
    })
    savedUrl.value = response.feishu_webhook_url ?? ''
    toast.success('通知配置保存成功')
    saving.value = false

    if (formValues.feishu_webhook_enabled === true && formValues.feishu_webhook_url !== undefined && formValues.feishu_webhook_url !== null && formValues.feishu_webhook_url !== '') {
      void handleTest()
    }
  } catch (error) {
    handleApiError(error, '保存通知配置')
    saving.value = false
  }
})

const handleTest = async (): Promise<void> => {
  testing.value = true
  testResult.value = null

  try {
    const response = await notificationConfigApi.testNotification()
    testResult.value = response

    if (response.success) {
      toast.success('测试消息发送成功')
    }
  } catch (error) {
    testResult.value = {
      success: false,
      message: '请求失败，请稍后重试',
    }
    handleApiError(error, '测试通知')
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  void fetchConfig()
})
</script>

<template>
  <SettingsContent ariaLabel="通知配置" description="审批相关的团队通知通道。这里改的是怎么通知，不是审批流程本身。">
    <ErrorState
      v-if="permissionsUnavailable"
      variant="error"
      title="权限信息暂不可用"
      description="暂时无法确认你的团队设置权限。请重试权限同步，避免在权限不明确时继续操作。"
    >
      <template #action>
        <Button :loading="retryingPermissions" @click="retryPermissions">
          {{ retryingPermissions ? '同步中…' : '重试权限同步' }}
        </Button>
      </template>
    </ErrorState>
    <ErrorState
      v-else-if="!hasAccess"
      variant="forbidden"
      title="暂无访问权限"
      description="你没有访问通知配置的权限，请联系团队所有者或管理员。"
    />
    <template v-else>
      <div v-if="loading" class="flex flex-col gap-4" aria-label="正在加载通知配置">
        <Card>
          <CardHeader><Skeleton class="h-6 w-36" /></CardHeader>
          <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /></CardContent>
        </Card>
      </div>
      <ErrorState
        v-else-if="loadError"
        variant="error"
        title="通知配置加载失败"
        description="请检查网络后重试。"
      >
        <template #action><Button variant="outline" @click="fetchConfig">重试</Button></template>
      </ErrorState>
      <form v-else class="flex flex-col gap-4" @submit="onSubmit">
        <Card>
          <CardHeader>
            <CardTitle>飞书群通知</CardTitle>
            <CardDescription>配置审批流程提交时的飞书群通知</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <FormField v-slot="{ value }" name="feishu_webhook_enabled">
              <FormItem>
                <div class="flex items-center justify-between gap-4">
                  <div class="space-y-0.5">
                    <FormLabel>启用通知</FormLabel>
                    <FormDescription>开启后，审批流程提交时会自动发送通知到飞书群</FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      :model-value="value ?? false"
                      @update:model-value="(checked: boolean) => setFieldValue('feishu_webhook_enabled', checked)"
                    />
                  </FormControl>
                </div>
              </FormItem>
            </FormField>

            <div class="settings-form-grid">
              <FormField v-slot="{ value, handleChange, handleBlur }" name="notification_group_name">
                <FormItem>
                  <FormLabel>群名称</FormLabel>
                  <FormControl>
                    <Input
                      :model-value="value ?? ''"
                      :disabled="!values.feishu_webhook_enabled"
                      placeholder="如：审批通知群"
                      @update:model-value="handleChange"
                      @blur="handleBlur"
                    />
                  </FormControl>
                  <FormDescription>用于标识通知目标群（可选）</FormDescription>
                </FormItem>
              </FormField>

              <FormField v-slot="{ value, handleChange, handleBlur }" name="feishu_webhook_url">
                <FormItem>
                  <FormLabel>Webhook</FormLabel>
                  <FormControl>
                    <Input
                      :model-value="value ?? ''"
                      :disabled="!values.feishu_webhook_enabled"
                      placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
                      @update:model-value="handleChange"
                      @blur="handleBlur"
                    />
                  </FormControl>
                  <FormDescription>
                    {{ values.feishu_webhook_enabled ? '从飞书群聊机器人设置中获取' : '请先开启「启用通知」开关' }}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              </FormField>
            </div>

            <Alert v-if="!canTest" variant="default">
              <AlertTriangle class="h-4 w-4" />
              <AlertDescription>{{ testDisabledReason }}</AlertDescription>
            </Alert>

            <div class="flex justify-end">
              <Button type="button" variant="outline" :disabled="!canTest" :loading="testing" @click="handleTest">
                {{ testing ? '发送中...' : '发送测试' }}
              </Button>
            </div>

            <div v-if="testResult">
              <Alert :variant="testResult.success ? 'default' : 'destructive'">
                <Check v-if="testResult.success" class="h-4 w-4" />
                <AlertTriangle v-else class="h-4 w-4" />
                <AlertDescription>
                  <div v-if="testResult.success">
                    <div class="font-medium">测试消息发送成功</div>
                    <div class="text-xs mt-1">
                      飞书群已收到测试消息，请检查群聊确认。配置生效后，审批流程提交时会自动通知此群。
                    </div>
                  </div>
                  <div v-else>
                    <div class="font-medium">测试消息发送失败</div>
                    <div class="text-xs mt-1">{{ testResult.message }}</div>
                    <div class="text-xs mt-2 text-muted-foreground">
                      可能原因：Webhook URL 不正确或已失效、飞书群聊机器人被移除、网络连接问题
                    </div>
                  </div>
                </AlertDescription>
              </Alert>
            </div>
          </CardContent>
        </Card>

        <div class="settings-form-actions">
          <Button type="submit" :loading="saving">保存配置</Button>
        </div>
      </form>
    </template>
    <AlertDialog :open="showLeaveConfirm" @update:open="handleLeaveDialogOpenChange">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>放弃未保存的更改？</AlertDialogTitle>
          <AlertDialogDescription>
            当前页面有尚未保存的更改。离开后这些内容会丢失。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel @click="cancelLeave">继续编辑</AlertDialogCancel>
          <AlertDialogAction @click="confirmLeave">放弃更改</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </SettingsContent>
</template>
