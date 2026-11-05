<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { AlertCircle, Check } from 'lucide-vue-next'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import ErrorState from '@/components/ErrorState.vue'
import { handleApiError } from '@/utils/errorHandler'
import { aiConfigApi } from '@/api/aiConfig'
import type { AIConfigResponse, SSEEvent, AssistantCapabilityResult, AssistantVerificationStage } from '@/api/aiConfig'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { useSettingsUnsavedLeave } from '@/composables/useSettingsUnsavedLeave'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { useHeaderStore } from '@/stores/header'

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
const headerStore = useHeaderStore()


const userStore = useUserStore()
const teamStore = useTeamStore()
const permissionStore = usePermissionStore()
const { canAccess, permissionsUnavailable } = useSettingsAccess()
const aiSettings = getSettingsNavigationItem('ai')

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const loadError = ref(false)
const configInfo = ref<AIConfigResponse | null>(null)
const streamingContent = ref('')
const testResult = ref<{ success: boolean; message: string } | null>(null)
const selectedProvider = ref('custom')
const verifyingAssistant = ref(false)
const assistantResult = ref<AssistantCapabilityResult | null>(null)
let configurationRevision = 0
const savedForm = ref('')
const formSnapshot = (): string => JSON.stringify([values.api_host, values.api_key, values.model_name, values.structured_output_mode])
const hasUnsavedChanges = computed(() => formSnapshot() !== savedForm.value)
const assistantReady = computed(() => !hasUnsavedChanges.value && configInfo.value?.assistant_verification_state === 'VERIFIED')
const assistantStageLabels: Record<AssistantVerificationStage, string> = {
  CONFIGURATION: '配置检查', ROOT_DECISION: '根决策', MEETING_STREAM: '会议流式结构化',
  QUALITY_STREAM: '质量流式评估',
  SAVE_VERIFICATION: '保存验证结果', COMPLETE: '全部完成',
}

const hasAccess = computed(() => aiSettings !== undefined && canAccess(aiSettings))
const retryingPermissions = computed(() => permissionStore.loadState === 'loading')

const aiConfigSchema = toTypedSchema(
  z.object({
    api_host: z.string()
      .min(1, '请输入接口地址')
      .url('请输入有效的 URL 地址'),
    api_key: z.union([
      z.literal(''),
      z.string().min(8, 'API Key 长度至少 8 位'),
    ]),
    model_name: z.string()
      .min(1, '请输入模型名称'),
    structured_output_mode: z.enum(['json_object', 'json_schema']),
  }),
)

const { handleSubmit, resetForm, values, meta } = useForm({
  validationSchema: aiConfigSchema,
  initialValues: {
    api_host: '',
    api_key: '',
    model_name: '',
    structured_output_mode: 'json_object' as const,
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

const testData = reactive({
  test_message: '帮我查询线索列表',
})

const providerDefaults: Record<string, { api_host: string; model_name: string }> = {
  deepseek: { api_host: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  openai: { api_host: 'https://api.openai.com/v1', model_name: 'gpt-4o' },
  zhipu: { api_host: 'https://open.bigmodel.cn/api/paas/v4', model_name: 'glm-4' },
  aliyun: { api_host: 'https://dashscope.aliyuncs.com/api/v1', model_name: 'qwen-plus' },
  baidu: { api_host: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1', model_name: 'ernie-4.0-8k' },
  custom: { api_host: '', model_name: '' },
}

const retryPermissions = async (): Promise<void> => {
  await teamStore.retryPermissionSync()
}

const handleProviderChange = (provider: string | number | bigint | Record<string, unknown> | null): void => {
  if (typeof provider !== 'string') return
  const defaults = providerDefaults[provider]
  if (defaults === undefined) return
  resetForm({
    values: {
      api_host: defaults.api_host,
      api_key: values.api_key ?? '',
      model_name: defaults.model_name,
      structured_output_mode: values.structured_output_mode ?? 'json_object',
    },
  })
}

const fetchConfig = async (): Promise<void> => {
  if (!hasAccess.value) {
    loading.value = false
    return
  }

  loading.value = true
  loadError.value = false
  try {
    const response = await aiConfigApi.getConfig()
    configInfo.value = response.data
    if (response.data) {
      resetForm({
        values: {
          api_host: response.data.api_host,
          api_key: '',
          model_name: response.data.model_name,
          structured_output_mode: response.data.structured_output_mode,
        },
      })
    }
    savedForm.value = formSnapshot()
  } catch (error) {
    loadError.value = true
    handleApiError(error, '获取 AI 配置')
  } finally {
    loading.value = false
  }
}

const onSubmit = handleSubmit(async (formValues) => {
  saving.value = true
  try {
    if (!configInfo.value && !formValues.api_key) {
      toast.warning('首次配置必须提供 API Key')
      return
    }
    await aiConfigApi.saveConfig({
      api_host: formValues.api_host,
      api_key: formValues.api_key,
      model_name: formValues.model_name,
      structured_output_mode: formValues.structured_output_mode,
    })
    toast.success('AI 配置保存成功')
    await fetchConfig()
  } catch (error) {
    handleApiError(error, '保存 AI 配置')
  } finally {
    saving.value = false
  }
})

const handleTest = async (): Promise<void> => {
  if (!testData.test_message) {
    toast.warning('请输入测试消息内容')
    return
  }

  if (hasUnsavedChanges.value) {
    toast.warning('请先保存配置后再测试')
    return
  }
  const revision = configurationRevision
  testing.value = true
  testResult.value = null
  streamingContent.value = ''

  try {
    const token = userStore.token
    if (!token) {
      toast.error('无认证令牌')
      testing.value = false
      return
    }

    await aiConfigApi.testConnectionSSE(
      { test_message: testData.test_message },
      (event: SSEEvent) => {
        if (revision !== configurationRevision) return
        if (event.event === 'start') {
          toast.info('正在连接 AI 服务...')
        } else if (event.event === 'content') {
          streamingContent.value += event.content ?? ''
        } else if (event.event === 'done') {
          testResult.value = {
            success: event.success ?? false,
            message: event.message ?? '',
          }
          toast.success('AI 服务连接成功')
          testing.value = false
        } else if (event.event === 'error') {
          testResult.value = {
            success: false,
            message: event.message ?? '连接失败',
          }
          toast.error(event.message ?? 'AI 连接测试失败')
          testing.value = false
        }
      },
      token,
    )
  } catch (error) {
    if (revision === configurationRevision) {
      testResult.value = { success: false, message: '连接测试失败' }
      handleApiError(error, 'AI 连接测试')
    }
  } finally {
    testing.value = false
  }
}

watch(() => [values.api_host, values.api_key, values.model_name, values.structured_output_mode], () => {
  configurationRevision += 1
  testResult.value = null
  streamingContent.value = ''
  assistantResult.value = null
}, { flush: 'sync' })

const handleAssistantVerification = async (): Promise<void> => {
  if (!configInfo.value || hasUnsavedChanges.value) return
  const revision = configurationRevision
  verifyingAssistant.value = true
  assistantResult.value = null
  configInfo.value = { ...configInfo.value, assistant_verification_state: 'UNVERIFIED', assistant_verified_at: null }
  try {
    const result = await aiConfigApi.testAssistantCapability()
    if (revision !== configurationRevision) return
    const config = await aiConfigApi.getConfig()
    if (revision !== configurationRevision) return
    configInfo.value = config.data
    if (config.data) {
      resetForm({ values: {
        api_host: config.data.api_host, api_key: '', model_name: config.data.model_name,
        structured_output_mode: config.data.structured_output_mode,
      } })
      savedForm.value = formSnapshot()
    }
    assistantResult.value = result
    if (result.success) toast.success('销售助手能力验证通过')
  } catch (error) {
    if (revision === configurationRevision) handleApiError(error, '销售助手能力验证')
  } finally {
    verifyingAssistant.value = false
  }
}
onMounted(() => {
  headerStore.clear()
})

watch(hasAccess, (ok) => {
  if (ok) void fetchConfig()
}, { immediate: true })

</script>

<template>
  <SettingsContent ariaLabel="AI 配置" description="配置当前团队使用的大模型接口。密钥不明文回显，空值保存表示保持原密钥。">
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
      description="你没有访问 AI 配置的权限，请联系团队所有者或管理员。"
    />
    <template v-else>
      <div v-if="loading" class="flex flex-col gap-4" aria-label="正在加载 AI 配置">
        <Card v-for="index in 2" :key="index">
          <CardHeader><Skeleton class="h-6 w-36" /></CardHeader>
          <CardContent class="space-y-3"><Skeleton class="h-10 w-full" /></CardContent>
        </Card>
      </div>
      <ErrorState
        v-else-if="loadError"
        variant="error"
        title="AI 配置加载失败"
        description="请检查网络后重试。"
      >
        <template #action><Button variant="outline" @click="fetchConfig">重试</Button></template>
      </ErrorState>
      <form v-else class="flex flex-col gap-4" @submit="onSubmit">
        <Card>
          <CardHeader>
            <CardTitle>服务配置</CardTitle>
            <CardDescription>配置 AI 供应商的接口地址和密钥</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="settings-form-grid">
              <div class="space-y-2">
                <Label for="ai-provider">供应商</Label>
                <Select v-model="selectedProvider" @update:model-value="handleProviderChange">
                  <SelectTrigger id="ai-provider">
                    <SelectValue placeholder="选择 AI 供应商" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="deepseek">DeepSeek</SelectItem>
                    <SelectItem value="openai">OpenAI</SelectItem>
                    <SelectItem value="zhipu">智谱 AI (GLM)</SelectItem>
                    <SelectItem value="aliyun">阿里云通义</SelectItem>
                    <SelectItem value="baidu">百度文心</SelectItem>
                    <SelectItem value="custom">自定义</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <FormField v-slot="{ value, handleChange, handleBlur }" name="model_name">
                <FormItem>
                  <FormLabel>模型名称 <span class="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input
                      :model-value="value"
                      placeholder="如 deepseek-chat"
                      @update:model-value="handleChange"
                      @blur="handleBlur"
                    />
                  </FormControl>
                  <FormDescription>模型名称，如 deepseek-chat、gpt-4o、glm-4 等</FormDescription>
                  <FormMessage />
                </FormItem>
              </FormField>

              <FormField v-slot="{ value, handleChange, handleBlur }" name="api_host">
                <FormItem class="settings-form-grid-full">
                  <FormLabel>接口地址 <span class="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input
                      :model-value="value"
                      placeholder="如 https://api.deepseek.com/v1"
                      @update:model-value="handleChange"
                      @blur="handleBlur"
                    />
                  </FormControl>
                  <FormDescription>兼容 OpenAI 格式的 API 基础地址</FormDescription>
                  <FormMessage />
                </FormItem>
              </FormField>

              <FormField v-slot="{ value, handleChange, handleBlur }" name="api_key">
                <FormItem class="settings-form-grid-full">
                  <FormLabel>API Key <span class="text-destructive">*</span></FormLabel>
                  <FormControl>
                    <Input
                      :model-value="value"
                      type="password"
                      placeholder="输入 API Key"
                      autocomplete="new-password"
                      @update:model-value="handleChange"
                      @blur="handleBlur"
                    />
                  </FormControl>
                  <FormDescription v-if="configInfo?.api_key_masked">
                    当前配置：<span class="font-mono">{{ configInfo.api_key_masked }}</span>
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              </FormField>
              <FormField v-slot="{ value, handleChange }" name="structured_output_mode">
                <FormItem class="settings-form-grid-full">
                  <FormLabel>结构化输出协议</FormLabel>
                  <Select :model-value="value" @update:model-value="handleChange">
                    <FormControl><SelectTrigger class="min-h-11"><SelectValue /></SelectTrigger></FormControl>
                    <SelectContent>
                      <SelectItem value="json_object">JSON 对象（本地完整校验）</SelectItem>
                      <SelectItem value="json_schema">JSON Schema（严格协议）</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>能力验证优先检查严格协议，仅在服务明确不支持时检查 JSON 对象协议。</FormDescription>
                  <FormMessage />
                </FormItem>
              </FormField>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>销售助手能力验证</CardTitle>
            <CardDescription>使用固定无害样例验证根决策、完整会议流式输出与质量评估；不会写入 CRM。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="text-sm" aria-live="polite">
              <p>{{ assistantReady ? '当前已保存配置：销售助手能力已验证' : '当前配置尚未通过销售助手能力验证' }}</p>
              <p v-if="configInfo" class="mt-1 text-xs text-muted-foreground">
                当前协议：{{ configInfo.structured_output_mode }}
                <span v-if="assistantReady && configInfo.assistant_verified_at"> · 验证时间：{{ configInfo.assistant_verified_at }}</span>
              </p>
              <p v-if="hasUnsavedChanges" class="mt-1 text-xs text-muted-foreground">配置已修改，请先保存，再验证已保存配置。</p>
            </div>
            <div class="flex justify-end">
              <Button type="button" class="min-h-11" :loading="verifyingAssistant" :disabled="!configInfo || hasUnsavedChanges || saving || testing" @click="handleAssistantVerification">
                {{ verifyingAssistant ? '验证中…' : '验证销售助手能力' }}
              </Button>
            </div>
            <div v-if="assistantResult" role="status" aria-live="polite">
              <Alert :variant="assistantResult.success ? 'default' : 'destructive'">
                <Check v-if="assistantResult.success" class="size-4" />
                <AlertCircle v-else class="size-4" />
                <AlertDescription>
                  <p>{{ assistantResult.message }}</p>
                  <p class="mt-1 text-xs">阶段：{{ assistantStageLabels[assistantResult.stage] }}<span v-if="assistantResult.code"> · {{ assistantResult.code }}</span><span v-if="assistantResult.output_mode"> · {{ assistantResult.output_mode }}</span></p>
                </AlertDescription>
              </Alert>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>连接测试</CardTitle>
            <CardDescription>普通连接成功只代表服务可连接，不代表销售助手已就绪。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <Label for="ai-test-message">测试消息</Label>
              <Input
                id="ai-test-message"
                v-model="testData.test_message"
                placeholder="输入测试消息，如：帮我查询线索列表"
              />
            </div>
            <div class="flex justify-end">
              <Button type="button" variant="outline" class="min-h-11" :loading="testing" :disabled="hasUnsavedChanges || saving || verifyingAssistant" @click="handleTest">
                {{ testing ? '测试中...' : '测试连接' }}
              </Button>
            </div>
            <div v-if="streamingContent || testResult" class="space-y-4">
              <div v-if="testResult">
                <Alert :variant="testResult.success ? 'default' : 'destructive'">
                  <Check v-if="testResult.success" class="h-4 w-4" />
                  <AlertCircle v-else class="h-4 w-4" />
                  <AlertDescription>
                    {{ testResult.success ? '普通连接成功；请另行验证销售助手能力' : testResult.message }}
                  </AlertDescription>
                </Alert>
              </div>
              <div v-if="streamingContent" class="p-4 rounded-lg bg-muted">
                <div class="text-xs text-muted-foreground mb-2">
                  AI 回复{{ testing ? '（流式输出中...）' : '' }}：
                </div>
                <div class="text-sm whitespace-pre-wrap">{{ streamingContent }}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <div class="settings-form-actions">
          <Button type="submit" class="min-h-11" :loading="saving" :disabled="verifyingAssistant || testing">保存配置</Button>
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
