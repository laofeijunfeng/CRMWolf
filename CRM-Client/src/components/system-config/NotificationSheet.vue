<script setup lang="ts">
/**
 * NotificationSheet.vue - 通知配置管理 Sheet
 *
 * 功能：
 * - 配置飞书群聊通知
 * - 测试通知发送
 * - 显示配置说明
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件
 * - V2 Design Tokens
 * - z-index: Sheet z-[200], Dialog z-[1000]
 */
import { ref, computed, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Save, Send, ExternalLink, Copy, Check, AlertTriangle } from 'lucide-vue-next'
import {
  Sheet,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { DetailSheetContent } from '@/components/ui/detail-sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { handleApiError } from '@/utils/errorHandler'
import { notificationConfigApi, type NotificationConfigResponse, type NotificationConfigUpdate } from '@/api/notificationConfig'

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// ==================== State ====================
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const configInfo = ref<NotificationConfigResponse | null>(null)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const savedUrl = ref('')
const copySuccess = ref(false)

// ==================== Zod Schema ====================
const notificationSchema = toTypedSchema(
  z.object({
    feishu_webhook_enabled: z.boolean().default(false),
    feishu_webhook_url: z.string()
      .refine((_val) => {
        // 如果未启用，不校验
        return true
      }, '请输入 Webhook URL')
      .refine((val) => {
        if (!val) return true
        return val.includes('open.feishu.cn/open-apis/bot/v2/hook')
      }, 'URL 格式应为 https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
      .optional()
      .nullable(),
    notification_group_name: z.string().optional().nullable()
  })
)

// VeeValidate form setup
const { handleSubmit, resetForm, values } = useForm({
  validationSchema: notificationSchema,
  initialValues: {
    feishu_webhook_enabled: false,
    feishu_webhook_url: '',
    notification_group_name: ''
  }
})

// ==================== Computed ====================
const canTest = computed(() => {
  return Boolean(values.feishu_webhook_enabled) &&
         Boolean(values.feishu_webhook_url) &&
         values.feishu_webhook_url === savedUrl.value &&
         isValidWebhookUrl(values.feishu_webhook_url || '')
})

const testDisabledReason = computed(() => {
  if (!values.feishu_webhook_enabled) {
    return '请先开启「启用通知」开关'
  }
  if (!values.feishu_webhook_url) {
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

// ==================== Helper Functions ====================
function isValidWebhookUrl(url: string): boolean {
  if (!url) return false
  try {
    new URL(url)
    return url.includes('open.feishu.cn/open-apis/bot/v2/hook')
  } catch {
    return false
  }
}

async function copyWebhookExample(): Promise<void> {
  try {
    await navigator.clipboard.writeText('https://open.feishu.cn/open-apis/bot/v2/hook/xxx')
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 3000)
    toast.success('示例 URL 已复制到剪贴板')
  } catch {
    toast.warning('复制失败，请手动复制')
  }
}

// ==================== API Methods ====================
const fetchConfig = async (): Promise<void> => {
  loading.value = true
  try {
    const response = await notificationConfigApi.getConfig({ skipErrorNotification: true })
    configInfo.value = response
    if (response) {
      resetForm({
        values: {
          feishu_webhook_enabled: response.feishu_webhook_enabled ?? false,
          feishu_webhook_url: response.feishu_webhook_url ?? '',
          notification_group_name: response.notification_group_name ?? ''
        }
      })
      savedUrl.value = response.feishu_webhook_url ?? ''
    }
  } catch (error) {
    // 404 表示配置不存在，使用默认值
    const err = error as { response?: { status?: number } }
    if (err.response?.status !== 404) {
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
      notification_method: 'webhook'
    }
    if (formValues.feishu_webhook_url) {
      updateData.feishu_webhook_url = formValues.feishu_webhook_url
    }
    if (formValues.feishu_webhook_enabled !== undefined) {
      updateData.feishu_webhook_enabled = formValues.feishu_webhook_enabled
    }
    if (formValues.notification_group_name) {
      updateData.notification_group_name = formValues.notification_group_name
    }
    const response = await notificationConfigApi.updateConfig(updateData)

    configInfo.value = response
    savedUrl.value = formValues.feishu_webhook_url || ''
    toast.success('通知配置保存成功')
    saving.value = false

    // 保存成功后询问是否测试
    if (formValues.feishu_webhook_enabled && formValues.feishu_webhook_url) {
      handleTest()
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
      message: '请求失败，请稍后重试'
    }
    handleApiError(error, '测试通知')
  } finally {
    testing.value = false
  }
}

// ==================== Lifecycle ====================
watch(() => props.open, (open) => {
  if (open) {
    fetchConfig()
  }
})
</script>

<template>
  <Sheet :open="open" @update:open="emit('update:open', $event)">
    <DetailSheetContent>
      <SheetHeader class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">通知配置</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">配置审批流程的飞书群通知</SheetDescription>
      </SheetHeader>
      <ScrollArea class="h-full">
        <div class="p-4 space-y-4">
          <!-- 配置卡片 -->
          <Card>
            <CardHeader>
              <CardTitle class="text-base">飞书群聊通知</CardTitle>
              <CardDescription>配置审批流程提交时的飞书群通知</CardDescription>
            </CardHeader>
            <CardContent>
              <form class="space-y-4" @submit="onSubmit">
                <!-- 启用通知 -->
                <FormField v-slot="{ componentField, value }" name="feishu_webhook_enabled">
                  <FormItem>
                    <div class="flex items-center justify-between">
                      <div class="space-y-0.5">
                        <FormLabel>启用通知</FormLabel>
                        <p class="text-xs text-muted-foreground">
                          开启后，审批流程提交时会自动发送通知到飞书群
                        </p>
                      </div>
                      <FormControl>
                        <Switch
                          :checked="value"
                          @update:checked="(checked: boolean) => {
                            const event = { target: { value: checked } }
                            if (typeof componentField.onChange === 'function') {
                              componentField.onChange(event)
                            }
                          }"
                        />
                      </FormControl>
                    </div>
                  </FormItem>
                </FormField>

                <!-- Webhook URL -->
                <FormField v-slot="{ componentField }" name="feishu_webhook_url">
                  <FormItem>
                    <FormLabel>Webhook URL</FormLabel>
                    <FormControl>
                      <Input
                        v-bind="componentField as unknown as Record<string, unknown>"
                        :disabled="!values.feishu_webhook_enabled"
                        placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
                      />
                    </FormControl>
                    <Alert v-if="!values.feishu_webhook_enabled" variant="default" class="mt-2">
                      <AlertTriangle class="h-4 w-4" />
                      <AlertDescription>
                        请先开启「启用通知」开关
                      </AlertDescription>
                    </Alert>
                    <p v-else class="text-xs text-muted-foreground">
                      从飞书群聊机器人设置中获取
                    </p>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <!-- 通知群名称 -->
                <FormField v-slot="{ componentField }" name="notification_group_name">
                  <FormItem>
                    <FormLabel>通知群名称</FormLabel>
                    <FormControl>
                      <Input
                        v-bind="componentField as unknown as Record<string, unknown>"
                        :disabled="!values.feishu_webhook_enabled"
                        placeholder="如：审批通知群"
                      />
                    </FormControl>
                    <p class="text-xs text-muted-foreground">
                      用于标识通知目标群（可选）
                    </p>
                  </FormItem>
                </FormField>

                <div class="flex justify-end pt-4">
                  <Button type="submit" :loading="saving">
                    <Save class="w-4 h-4 mr-2" />
                    保存配置
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <!-- 测试卡片 -->
          <Card>
            <CardHeader>
              <CardTitle class="text-base">通知测试</CardTitle>
              <CardDescription>发送测试消息验证配置是否正确</CardDescription>
            </CardHeader>
            <CardContent class="space-y-4">
              <!-- 前置条件提示 -->
              <Alert v-if="!canTest" variant="default">
                <AlertTriangle class="h-4 w-4" />
                <AlertDescription>{{ testDisabledReason }}</AlertDescription>
              </Alert>

              <div class="flex justify-end">
                <Button :disabled="!canTest" :loading="testing" @click="handleTest">
                  <Send class="w-4 h-4 mr-2" />
                  {{ testing ? '发送中...' : '测试通知' }}
                </Button>
              </div>

              <!-- 测试结果 -->
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

          <!-- 说明卡片 -->
          <Card>
            <CardHeader>
              <CardTitle class="text-base">配置说明</CardTitle>
              <CardDescription>如何获取飞书群聊机器人 Webhook URL</CardDescription>
            </CardHeader>
            <CardContent class="space-y-4">
              <!-- 步骤引导 -->
              <div class="space-y-4">
                <div class="flex items-start gap-4">
                  <div class="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-semibold shrink-0">
                    1
                  </div>
                  <div class="flex-1">
                    <div class="font-medium text-sm">在飞书群聊中添加机器人</div>
                    <a
                      href="https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN"
                      target="_blank"
                      class="text-primary text-xs hover:underline flex items-center gap-1 mt-1"
                    >
                      查看官方文档
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </div>
                </div>

                <div class="flex items-start gap-4">
                  <div class="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-semibold shrink-0">
                    2
                  </div>
                  <div class="flex-1">
                    <div class="font-medium text-sm">复制 Webhook URL</div>
                    <div
                      class="mt-2 inline-flex items-center gap-2 px-3 py-1.5 bg-muted rounded-md cursor-pointer hover:bg-muted/80 transition-colors"
                      @click="copyWebhookExample"
                    >
                      <code class="text-xs text-muted-foreground">https://open.feishu.cn/open-apis/bot/v2/hook/xxx</code>
                      <Copy v-if="!copySuccess" class="w-3 h-3 text-muted-foreground" />
                      <Check v-else class="w-3 h-3 text-green-500" />
                    </div>
                  </div>
                </div>

                <div class="flex items-start gap-4">
                  <div class="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm font-semibold shrink-0">
                    3
                  </div>
                  <div class="flex-1">
                    <div class="font-medium text-sm">粘贴到上方输入框，点击测试</div>
                    <div class="text-xs text-muted-foreground mt-1">测试成功后保存配置即可</div>
                  </div>
                </div>
              </div>

              <div class="pt-4 border-t">
                <div class="text-sm font-medium mb-2">官方文档：</div>
                <ul class="space-y-2">
                  <li>
                    <a
                      href="https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN"
                      target="_blank"
                      class="text-primary text-sm hover:underline flex items-center gap-1"
                    >
                      飞书群聊机器人配置指南
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </li>
                  <li>
                    <a
                      href="https://open.feishu.cn/document/ukTMukTMukTM/uUjN14yIdjL14iTMykTN"
                      target="_blank"
                      class="text-primary text-sm hover:underline flex items-center gap-1"
                    >
                      如何获取 Webhook URL
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;

.system-config-sheet-header {
  padding: $wolf-space-xl-v2;
  padding-bottom: $wolf-space-lg-v2;
  border-bottom: 1px solid $wolf-border-default-v2;
  background: $wolf-bg-card-v2;
}
</style>
