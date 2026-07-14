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
import { ref, reactive, watch } from 'vue'
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
import { aiConfigApi, type AIConfigResponse, type SSEEvent } from '@/api/aiConfig'
import { useUserStore } from '@/stores/user'

// ==================== Props & Emits ====================
interface Props {
  open: boolean
}

type Emits = (e: 'update:open', value: boolean) => void

const props = defineProps<Props>()
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

// ==================== Zod Schema ====================
const aiConfigSchema = toTypedSchema(
  z.object({
    api_host: z.string()
      .min(1, '请输入接口地址')
      .url('请输入有效的 URL 地址'),
    api_key: z.string()
      .min(8, 'API Key 长度至少 8 位'),
    model_name: z.string()
      .min(1, '请输入模型名称')
  })
)

// VeeValidate form setup
const { handleSubmit, resetForm, values } = useForm({
  validationSchema: aiConfigSchema,
  initialValues: {
    api_host: '',
    api_key: '',
    model_name: ''
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
        api_key: values.api_key || '',
        model_name: defaults.model_name
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
          model_name: response.data.model_name
        }
      })
    }
  } catch (error) {
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
      model_name: formValues.model_name
    })
    toast.success('AI 配置保存成功')
    fetchConfig()
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
          streamingContent.value += event.content || ''
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
          toast.error(event.message || 'AI 连接测试失败')
          testing.value = false
        }
      },
      token
    )
  } catch (error) {
    testResult.value = {
      success: false,
      message: '连接测试失败'
    }
    handleApiError(error, 'AI 连接测试')
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
    <SheetHeader>
      <SheetTitle>AI 配置</SheetTitle>
      <SheetDescription>配置大模型服务接口</SheetDescription>
    </SheetHeader>
    <DetailSheetContent>
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
              <CardTitle class="text-base">连接测试</CardTitle>
              <CardDescription>验证 AI 服务是否正常连接</CardDescription>
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
                <Button :loading="testing" @click="handleTest">
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
    </DetailSheetContent>
  </Sheet>
</template>

<style scoped lang="scss">
@use '@/styles/variables-v2.scss' as *;
</style>
