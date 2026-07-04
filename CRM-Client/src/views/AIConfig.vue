<template>
  <div class="ai-config-container">
    <el-card class="config-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>大模型服务配置</span>
          <el-button type="primary" size="small" class="wolf-btn wolf-btn--primary-sm" @click="handleSave" :loading="saving">
            <template #icon><el-icon><Check /></el-icon></template>
            保存配置
          </el-button>
        </div>
      </template>

      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="120px">
        <el-form-item label="AI 供应商" prop="api_host">
          <el-select v-model="selectedProvider" placeholder="选择 AI 供应商" @change="handleProviderChange">
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="智谱 AI (GLM)" value="zhipu" />
            <el-option label="阿里云通义" value="aliyun" />
            <el-option label="百度文心" value="baidu" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>

        <el-form-item label="接口地址" prop="api_host">
          <el-input v-model="formData.api_host" placeholder="如 https://api.deepseek.com/v1" />
          <div class="form-tip">兼容 OpenAI 格式的 API 基础地址</div>
        </el-form-item>

        <el-form-item label="API Key" prop="api_key">
          <el-input
            v-model="formData.api_key"
            type="password"
            placeholder="输入 API Key"
            show-password
          />
          <div v-if="configInfo?.api_key_masked" class="form-tip">
            当前配置：<span class="masked-key">{{ configInfo.api_key_masked }}</span>
          </div>
        </el-form-item>

        <el-form-item label="模型名称" prop="model_name">
          <el-input v-model="formData.model_name" placeholder="如 deepseek-chat" />
          <div class="form-tip">模型名称，如 deepseek-chat、gpt-4o、glm-4 等</div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="test-card">
      <template #header>
        <div class="card-header">
          <span>连接测试</span>
          <el-button size="small" class="wolf-btn wolf-btn--success-sm" @click="handleTest" :loading="testing">
            <template #icon><el-icon><Connection /></el-icon></template>
            测试连接
          </el-button>
        </div>
      </template>

      <el-form :model="testData" label-width="120px">
        <el-form-item label="测试消息">
          <el-input
            v-model="testData.test_message"
            placeholder="输入测试消息，如：帮我查询线索列表"
          />
        </el-form-item>

        <el-form-item v-if="testResult || streamingContent" label="测试结果">
          <el-alert
            v-if="testResult"
            :type="testResult.success ? 'success' : 'error'"
            :title="testResult.message"
            show-icon
            :closable="false"
          />
          <div v-if="streamingContent" class="ai-response">
            <div class="response-label">AI 回复{{ testing ? '（流式输出中...）' : '' }}：</div>
            <div class="response-content">{{ streamingContent }}</div>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="info-card">
      <template #header>
        <span>配置说明</span>
      </template>
      <div class="info-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="支持的供应商">
            DeepSeek、OpenAI、智谱 AI、阿里云通义、百度文心等兼容 OpenAI 格式的服务
          </el-descriptions-item>
          <el-descriptions-item label="温度参数">固定 0.1（确保输出稳定）</el-descriptions-item>
          <el-descriptions-item label="最大 Tokens">固定 1024</el-descriptions-item>
          <el-descriptions-item label="API Key 安全">加密存储，仅显示前 8 位</el-descriptions-item>
          <el-descriptions-item label="用途">
            用于飞书/钉钉/企业微信机器人对话的意图识别和参数解析
          </el-descriptions-item>
        </el-descriptions>

        <div class="provider-links">
          <h4>各供应商 API 文档：</h4>
          <ul>
            <li><a href="https://platform.deepseek.com/api-docs/" target="_blank">DeepSeek API 文档</a></li>
            <li><a href="https://platform.openai.com/docs/api-reference/chat" target="_blank">OpenAI API 文档</a></li>
            <li><a href="https://open.bigmodel.cn/dev/api" target="_blank">智谱 AI API 文档</a></li>
            <li><a href="https://help.aliyun.com/document_detail/610000.html" target="_blank">阿里云通义 API 文档</a></li>
          </ul>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showError, showSuccess } from '@/utils/errorMessages'
import type { FormInstance, FormRules } from 'element-plus'
import { Check, Connection } from '@element-plus/icons-vue'
import { aiConfigApi, type SSEEvent, type AIConfigResponse } from '@/api/aiConfig'
import { useUserStore } from '@/stores/user'
import { usePageTitle } from '@/composables/usePageTitle'
import { useHeaderStore } from '@/stores/header'

usePageTitle()

const router = useRouter()
const userStore = useUserStore()
const headerStore = useHeaderStore()

onMounted(() => {
  headerStore.setBack(true, '/ai-assistant')
})

onUnmounted(() => {
  headerStore.clear()
})

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const formRef = ref<FormInstance>()
const configInfo = ref<AIConfigResponse | null>(null)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const streamingContent = ref('')  // 流式响应内容

const selectedProvider = ref('custom')

const formData = reactive({
  api_host: '',
  api_key: '',
  model_name: ''
})

const testData = reactive({
  test_message: '帮我查询线索列表'
})

const providerDefaults: Record<string, { api_host: string; model_name: string }> = {
  deepseek: { api_host: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat' },
  openai: { api_host: 'https://api.openai.com/v1', model_name: 'gpt-4o' },
  zhipu: { api_host: 'https://open.bigmodel.cn/api/paas/v4', model_name: 'glm-4' },
  aliyun: { api_host: 'https://dashscope.aliyuncs.com/api/v1', model_name: 'qwen-plus' },
  baidu: { api_host: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1', model_name: 'ernie-4.0-8k' },
  custom: { api_host: '', model_name: '' }
}

const formRules: FormRules = {
  api_host: [
    { required: true, message: '请输入接口地址', trigger: 'blur' },
    { type: 'url', message: '请输入有效的 URL 地址', trigger: 'blur' }
  ],
  api_key: [
    { required: true, message: '请输入 API Key', trigger: 'blur' },
    { min: 8, message: 'API Key 长度至少 8 位', trigger: 'blur' }
  ],
  model_name: [
    { required: true, message: '请输入模型名称', trigger: 'blur' }
  ]
}

const handleProviderChange = (provider: string) => {
  const defaults = providerDefaults[provider]
  if (defaults) {
    formData.api_host = defaults.api_host
    formData.model_name = defaults.model_name
  }
}

const fetchConfig = async () => {
  loading.value = true
  try {
    const response = await aiConfigApi.getConfig()
    configInfo.value = response.data
    if (response.data) {
      formData.api_host = response.data.api_host
      formData.model_name = response.data.model_name
      formData.api_key = ''
    }
  } catch (error: unknown) {
    const err = error as Error
    console.error('[AIConfig] fetchConfig error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '获取 AI 配置')
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    await aiConfigApi.saveConfig({
      api_host: formData.api_host,
      api_key: formData.api_key,
      model_name: formData.model_name
    })
    // ✅ P0: Copywriting - 具体化的成功提示
    showSuccess('保存', 'AI 配置')
    await fetchConfig()
  } catch (error: unknown) {
    const err = error as Error
    console.error('[AIConfig] saveConfig error:', err)
    // ✅ P0: Copywriting - 具体 + 方向性
    showError(error, '保存 AI 配置')
  } finally {
    saving.value = false
  }
}

const handleTest = async () => {
  if (!testData.test_message) {
    // ✅ P0: Copywriting - 具体的提示（不是 generic）
    ElMessage.warning('请输入测试消息内容，验证 AI 连接')
    return
  }

  testing.value = true
  testResult.value = null
  streamingContent.value = ''

  try {
    const token = userStore.token
    if (!token) {
      // ✅ P0: Copywriting - 具体化的错误提示
      showError(new Error('无认证令牌'), '访问 AI 服务')
      testing.value = false
      return
    }

    await aiConfigApi.testConnectionSSE(
      { test_message: testData.test_message },
      (event: SSEEvent) => {
        if (event.event === 'start') {
          // ✅ P0: Copywriting - 具体化的状态提示
          ElMessage.info('正在连接 AI 服务，等待响应...')
        } else if (event.event === 'content') {
          // 流式追加内容
          streamingContent.value += event.content || ''
        } else if (event.event === 'done') {
          testResult.value = {
            success: event.success ?? false,
            message: event.message ?? ''
          }
          // ✅ P0: Copywriting - 具体化的成功提示
          showSuccess('连接测试', 'AI 服务')
          testing.value = false
        } else if (event.event === 'error') {
          testResult.value = {
            success: false,
            message: event.message ?? '连接失败'
          }
          // ✅ P0: Copywriting - 具体化的错误提示
          showError(new Error(event.message || '连接失败'), 'AI 连接测试')
          testing.value = false
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    testResult.value = {
      success: false,
      message: err.message || '连接测试失败'
    }
    console.error('[AIConfig] testConnection error:', err)
    // ✅ P0: Copywriting - 具体化的错误提示
    showError(error, 'AI 连接测试')
    testing.value = false
  }
}

const handleBack = () => {
  router.back()
}

onMounted(() => {
  fetchConfig()
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.ai-config-container {
  padding: 0;
  background: $wolf-bg-page;
  min-height: calc(100vh - 48px);
}

// 页面标题（sticky）
.page-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: $wolf-bg-card;
  border-bottom: 1px solid $wolf-border-default;
  height: $wolf-header-height;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 $wolf-page-padding;
}

.page-header-left {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
}

.back-btn {
  width: 32px !important;
  height: 32px !important;
  padding: 0 !important;
  border-radius: $wolf-radius-md !important;
  background: transparent !important;
  border: none !important;

  &:hover {
    background: $wolf-bg-hover !important;
  }
}

.config-card,
.test-card,
.info-card {
  background: $wolf-bg-card;
  border-radius: $wolf-radius-md;
  box-shadow: $wolf-shadow-card;
  margin-bottom: $wolf-space-md;
  border: none;
}

.config-card :deep(.el-card__header),
.test-card :deep(.el-card__header),
.info-card :deep(.el-card__header) {
  padding: $wolf-card-padding;
  border-bottom: 1px solid $wolf-border-light;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.config-card :deep(.el-card__body),
.test-card :deep(.el-card__body),
.info-card :deep(.el-card__body) {
  padding: $wolf-card-padding;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.form-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-top: $wolf-space-xs;
}

.masked-key {
  color: $wolf-text-secondary;
  font-family: monospace;
}

.ai-response {
  margin-top: $wolf-space-sm;
  padding: $wolf-space-sm;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-md;
}

.response-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-sm;
}

.response-content {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  white-space: pre-wrap;
}

.info-content {
  padding: $wolf-space-md 0;
}

.provider-links {
  margin-top: $wolf-space-lg;
}

.provider-links h4 {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  margin-bottom: $wolf-space-sm;
}

.provider-links ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.provider-links li {
  margin-bottom: $wolf-space-sm;
}

.provider-links a {
  color: $wolf-primary;
  text-decoration: none;
}

.provider-links a:hover {
  text-decoration: underline;
}

.wolf-btn--primary-sm {
  background: $wolf-primary !important;
  border-color: $wolf-primary !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

.wolf-btn--success-sm {
  background: $wolf-success-text !important;
  border-color: $wolf-success-text !important;
  color: $wolf-text-inverse !important;
  font-weight: $wolf-font-weight-medium !important;
}

// 内容区域需要padding
.config-card,
.test-card,
.info-card {
  margin-left: $wolf-page-padding;
  margin-right: $wolf-page-padding;
}

.config-card {
  margin-top: $wolf-page-padding;
}

// 响应式
@media (max-width: 768px) {
  .config-card,
  .test-card,
  .info-card {
    margin-left: $wolf-space-md;
    margin-right: $wolf-space-md;
  }

  .config-card {
    margin-top: $wolf-space-md;
  }
}
</style>