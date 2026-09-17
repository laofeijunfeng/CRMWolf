<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
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
import type { AIConfigResponse, SSEEvent } from '@/api/aiConfig'
import { useUserStore } from '@/stores/user'
import { useTeamStore } from '@/stores/team'
import { usePermissionStore } from '@/stores/permissions'
import { useSettingsAccess } from '@/composables/useSettingsAccess'
import { getSettingsNavigationItem } from '@/settingsNavigation'
import { usePageTitle } from '@/composables/usePageTitle'
import SettingsContent from '@/views/settings/SettingsContent.vue'

usePageTitle()

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

const hasAccess = computed(() => aiSettings !== undefined && canAccess(aiSettings))
const retryingPermissions = computed(() => permissionStore.loadState === 'loading')

const aiConfigSchema = toTypedSchema(
  z.object({
    api_host: z.string()
      .min(1, '请输入接口地址')
      .url('请输入有效的 URL 地址'),
    api_key: z.string()
      .min(8, 'API Key 长度至少 8 位'),
    model_name: z.string()
      .min(1, '请输入模型名称'),
  }),
)

const { handleSubmit, resetForm, values } = useForm({
  validationSchema: aiConfigSchema,
  initialValues: {
    api_host: '',
    api_key: '',
    model_name: '',
  },
})

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
        },
      })
    }
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
    await aiConfigApi.saveConfig({
      api_host: formValues.api_host,
      api_key: formValues.api_key,
      model_name: formValues.model_name,
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
    testResult.value = {
      success: false,
      message: '连接测试失败',
    }
    handleApiError(error, 'AI 连接测试')
    testing.value = false
  }
}

onMounted(() => {
  void fetchConfig()
})
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
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>连接测试</CardTitle>
            <CardDescription>验证 AI 服务是否正常连接</CardDescription>
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
              <Button type="button" variant="outline" :loading="testing" @click="handleTest">
                {{ testing ? '测试中...' : '测试连接' }}
              </Button>
            </div>
            <div v-if="streamingContent || testResult" class="space-y-4">
              <div v-if="testResult">
                <Alert :variant="testResult.success ? 'default' : 'destructive'">
                  <Check v-if="testResult.success" class="h-4 w-4" />
                  <AlertCircle v-else class="h-4 w-4" />
                  <AlertDescription>
                    {{ testResult.success ? '测试成功' : testResult.message }}
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
          <Button type="submit" :loading="saving">保存配置</Button>
        </div>
      </form>
    </template>
  </SettingsContent>
</template>
