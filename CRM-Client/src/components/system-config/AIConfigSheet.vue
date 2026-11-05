<script setup lang="ts">
/**
 * AIConfigSheet.vue - AI 配置管理 Sheet
 *
 * 功能：
 * - 配置 AI 供应商信息
 * - 测试 AI 连接（SSE 流式响应）
 * - 显示配置说明
 *
 * 基于 MASTER.md §6.6 布局架构：
 * - 使用 shadcn-vue Sheet 组件
 * - V2 Design Tokens
 * - z-index: Sheet z-[200], Dialog z-[1000]
 */
import { ref, reactive, computed, watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Save, Play, ExternalLink, AlertCircle, Check } from 'lucide-vue-next'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { handleApiError } from '@/utils/errorHandler'
import { aiConfigApi, type AIConfigResponse, type SSEEvent, type AssistantCapabilityResult, type AssistantVerificationStage } from '@/api/aiConfig'
import { useUserStore } from '@/stores/user'

// ==================== Props & Emits ====================
interface Props {
  open?: boolean
  active?: boolean
  embedded?: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = withDefaults(defineProps<Props>(), {
  open: false,
  active: false,
  embedded: false,
})
const embedded = computed(() => props.embedded)
const active = computed(() => embedded.value ? props.active : props.open)
const emit = defineEmits<Emits>()
const userStore = useUserStore()

// ==================== State ====================
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
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
const assistantStageLabels: Record<AssistantVerificationStage, string> = {
  CONFIGURATION: '配置检查', ROOT_DECISION: '根决策', MEETING_STREAM: '会议流式结构化',
  QUALITY_STREAM: '质量流式评估',
  SAVE_VERIFICATION: '保存验证结果', COMPLETE: '全部完成',
}
const assistantReady = computed(() => !hasUnsavedChanges.value && configInfo.value?.assistant_verification_state === 'VERIFIED')

// ==================== Zod Schema ====================
const aiConfigSchema = toTypedSchema(
  z.object({
    api_host: z.string()
      .min(1, '请输入接口地址')
      .url('请输入有效的 URL 地址'),
    api_key: z.union([z.literal(''), z.string().min(8, 'API Key 长度至少 8 位')]),
    model_name: z.string()
      .min(1, '请输入模型名称'),
    structured_output_mode: z.enum(['json_object', 'json_schema'])
  })
)

// VeeValidate form setup
const { handleSubmit, resetForm, values } = useForm({
  validationSchema: aiConfigSchema,
  initialValues: {
    api_host: '',
    api_key: '',
    model_name: '',
    structured_output_mode: 'json_object' as const
  }
})

const testData = reactive({
  test_message: '帮我查询线索列表'
})

// Provider defaults
const providerDefaults: Record<string, { api_host: string; model_name: string }> = {
  deepseek: { api_host: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  openai: { api_host: 'https://api.openai.com/v1', model_name: 'gpt-4o' },
  zhipu: { api_host: 'https://open.bigmodel.cn/api/paas/v4', model_name: 'glm-4' },
  aliyun: { api_host: 'https://dashscope.aliyuncs.com/api/v1', model_name: 'qwen-plus' },
  baidu: { api_host: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1', model_name: 'ernie-4.0-8k' },
  custom: { api_host: '', model_name: '' }
}

// ==================== Provider Change ====================
const handleProviderChange = (provider: unknown): void => {
  const providerStr = String(provider)
  const defaults = providerDefaults[providerStr]
  if (defaults) {
    resetForm({
      values: {
        api_host: defaults.api_host,
        api_key: values.api_key ?? '',
        model_name: defaults.model_name,
        structured_output_mode: values.structured_output_mode ?? 'json_object'
      }
    })
  }
}

// ==================== API Methods ====================
const fetchConfig = async (): Promise<void> => {
  loading.value = true
  try {
    const response = await aiConfigApi.getConfig()
    configInfo.value = response.data
    if (response.data) {
      resetForm({
        values: {
          api_host: response.data.api_host,
          api_key: '',
          model_name: response.data.model_name,
          structured_output_mode: response.data.structured_output_mode
        }
      })
    }
    savedForm.value = formSnapshot()
  } catch (error) {
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
      structured_output_mode: formValues.structured_output_mode
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
            message: event.message ?? ''
          }
          toast.success('AI 服务连接成功')
          testing.value = false
        } else if (event.event === 'error') {
          testResult.value = {
            success: false,
            message: event.message ?? '连接失败'
          }
          toast.error(event.message ?? 'AI 连接测试失败')
          testing.value = false
        }
      },
      token
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

// ==================== Lifecycle ====================
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
    // Reload persisted protocol and readiness only while the user's form is unchanged.
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
watch(active, (isActive) => {
  if (isActive) {
    fetchConfig()
  }
}, { immediate: true })
</script>

<template>
  <component
    :is="embedded ? 'div' : Sheet"
    :open="embedded ? undefined : open"
    @update:open="emit('update:open', $event)"
  >
    <component :is="embedded ? 'div' : DetailSheetContent">
      <SheetHeader v-if="!embedded" class="system-config-sheet-header">
        <SheetTitle class="text-base font-semibold text-wolf-text-primary">AI 配置</SheetTitle>
        <SheetDescription class="text-sm text-wolf-text-secondary">配置大模型服务接口</SheetDescription>
      </SheetHeader>
      <ScrollArea class="h-full">
        <div class="p-4 space-y-4">
          <!-- 配置卡片 -->
          <Card>
            <CardHeader>
              <CardTitle class="text-base">大模型服务配置</CardTitle>
              <CardDescription>配置 AI 供应商的接口地址和密钥</CardDescription>
            </CardHeader>
            <CardContent>
              <form class="space-y-4" @submit="onSubmit">
                <!-- AI 供应商 -->
                <div class="space-y-2">
                  <label class="text-sm font-medium">AI 供应商</label>
                  <Select v-model="selectedProvider" @update:model-value="handleProviderChange">
                    <SelectTrigger>
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

                <!-- 接口地址 -->
                <FormField v-slot="{ componentField }" name="api_host">
                  <FormItem>
                    <FormLabel>接口地址 <span class="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input
                        v-bind="componentField as unknown as Record<string, unknown>"
                        placeholder="如 https://api.deepseek.com/v1"
                      />
                    </FormControl>
                    <p class="text-xs text-muted-foreground">兼容 OpenAI 格式的 API 基础地址</p>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <!-- API Key -->
                <FormField v-slot="{ componentField }" name="api_key">
                  <FormItem>
                    <FormLabel>API Key <span class="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input
                        v-bind="componentField as unknown as Record<string, unknown>"
                        type="password"
                        placeholder="输入 API Key"
                      />
                    </FormControl>
                    <p v-if="configInfo?.api_key_masked" class="text-xs text-muted-foreground">
                      当前配置：<span class="font-mono">{{ configInfo.api_key_masked }}</span>
                    </p>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <!-- 模型名称 -->
                <FormField v-slot="{ componentField }" name="model_name">
                  <FormItem>
                    <FormLabel>模型名称 <span class="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input
                        v-bind="componentField as unknown as Record<string, unknown>"
                        placeholder="如 deepseek-chat"
                      />
                    </FormControl>
                    <p class="text-xs text-muted-foreground">模型名称，如 deepseek-chat、gpt-4o、glm-4 等</p>
                    <FormMessage />
                  </FormItem>
                </FormField>

                <FormField v-slot="{ value, handleChange }" name="structured_output_mode">
                  <FormItem>
                    <FormLabel>结构化输出协议</FormLabel>
                    <Select :model-value="value" @update:model-value="handleChange">
                      <FormControl>
                        <SelectTrigger class="min-h-11"><SelectValue /></SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="json_object">JSON 对象（本地完整校验）</SelectItem>
                        <SelectItem value="json_schema">JSON Schema（严格协议）</SelectItem>
                      </SelectContent>
                    </Select>
                    <p class="text-xs text-muted-foreground">能力验证优先检查严格协议，仅在服务明确不支持时检查 JSON 对象协议。</p>
                    <FormMessage />
                  </FormItem>
                </FormField>
                <div class="flex justify-end pt-4">
                  <Button type="submit" class="min-h-11" :loading="saving" :disabled="verifyingAssistant || testing">
                    <Save class="w-4 h-4 mr-2" />
                    保存配置
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle class="text-base">销售助手能力验证</CardTitle>
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
                <Button class="min-h-11" :loading="verifyingAssistant" :disabled="!configInfo || hasUnsavedChanges || saving || testing" @click="handleAssistantVerification">
                  <Play class="mr-2 size-4" />
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
          <!-- 测试卡片 -->
          <Card>
            <CardHeader>
              <CardTitle class="text-base">连接测试</CardTitle>
              <CardDescription>普通连接成功只代表服务可连接，不代表销售助手已就绪。</CardDescription>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="space-y-2">
                <label class="text-sm font-medium">测试消息</label>
                <Input
                  v-model="testData.test_message"
                  placeholder="输入测试消息，如：帮我查询线索列表"
                />
              </div>

              <div class="flex justify-end">
                <Button class="min-h-11" :loading="testing" :disabled="hasUnsavedChanges || saving || verifyingAssistant" @click="handleTest">
                  <Play class="w-4 h-4 mr-2" />
                  {{ testing ? '测试中...' : '测试连接' }}
                </Button>
              </div>

              <!-- AI 响应 -->
              <div v-if="streamingContent || testResult" class="space-y-4">
                <div v-if="testResult" class="rounded-lg">
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

          <!-- 说明卡片 -->
          <Card>
            <CardHeader>
              <CardTitle class="text-base">配置说明</CardTitle>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span class="text-muted-foreground">支持的供应商：</span>
                  <span>DeepSeek、OpenAI、智谱 AI、阿里云通义、百度文心等</span>
                </div>
                <div>
                  <span class="text-muted-foreground">温度参数：</span>
                  <span>固定 0.1（确保输出稳定）</span>
                </div>
                <div>
                  <span class="text-muted-foreground">最大 Tokens：</span>
                  <span>固定 1024</span>
                </div>
                <div>
                  <span class="text-muted-foreground">API Key 安全：</span>
                  <span>加密存储，仅显示前 8 位</span>
                </div>
              </div>

              <div class="pt-4 border-t">
                <div class="text-sm font-medium mb-2">各供应商 API 文档：</div>
                <ul class="space-y-2">
                  <li>
                    <a
                      href="https://platform.deepseek.com/api-docs/"
                      target="_blank"
                      class="text-primary text-sm hover:underline flex items-center gap-1"
                    >
                      DeepSeek API 文档
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </li>
                  <li>
                    <a
                      href="https://platform.openai.com/docs/api-reference/chat"
                      target="_blank"
                      class="text-primary text-sm hover:underline flex items-center gap-1"
                    >
                      OpenAI API 文档
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </li>
                  <li>
                    <a
                      href="https://open.bigmodel.cn/dev/api"
                      target="_blank"
                      class="text-primary text-sm hover:underline flex items-center gap-1"
                    >
                      智谱 AI API 文档
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </li>
                  <li>
                    <a
                      href="https://help.aliyun.com/document_detail/610000.html"
                      target="_blank"
                      class="text-primary text-sm hover:underline flex items-center gap-1"
                    >
                      阿里云通义 API 文档
                      <ExternalLink class="w-3 h-3" />
                    </a>
                  </li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </component>
  </component>
</template>

<style scoped>
.system-config-sheet-header {
  padding: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card));
}
</style>
