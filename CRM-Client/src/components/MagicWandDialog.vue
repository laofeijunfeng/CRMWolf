<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="500px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- Stage 1: Input -->
    <div v-if="stage === 'input'" class="stage-input">
      <div class="entity-info">
        <div class="entity-avatar">{{ entityName?.charAt(0) || '?' }}</div>
        <div class="entity-meta">
          <div class="entity-name">{{ entityName }}</div>
          <div class="entity-type">{{ getEntityTypeText(entityType) }}</div>
        </div>
      </div>

      <div class="input-tip">描述你想对这个{{ getEntityTypeText(entityType) }}做的操作，AI 会帮你完成</div>

      <el-input
        v-model="userInput"
        type="textarea"
        :rows="3"
        placeholder="例如：标记为重点客户、修改状态为成交、退回公海..."
        :disabled="isLoading"
      />

      <div class="input-actions">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="isLoading" @click="handleSend">发送</el-button>
      </div>
    </div>

    <!-- Stage 2: Clarification -->
    <div v-if="stage === 'clarify'" class="stage-clarify">
      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <el-input
        v-model="userInput"
        type="textarea"
        :rows="2"
        placeholder="补充信息..."
        :disabled="isLoading"
      />

      <div class="input-actions">
        <el-button @click="stage = 'input'">返回</el-button>
        <el-button type="primary" :loading="isLoading" @click="handleSend">继续</el-button>
      </div>
    </div>

    <!-- Stage 3: Preview -->
    <div v-if="stage === 'preview'" class="stage-preview">
      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <div class="action-preview">
        <div class="preview-header">即将执行的操作：</div>
        <div class="preview-item">
          <span class="preview-label">工具:</span>
          <span class="preview-value">{{ previewAction?.tool }}</span>
        </div>
        <div v-if="previewAction?.params" class="preview-params">
          <div class="preview-label">参数:</div>
          <pre class="params-json">{{ JSON.stringify(previewAction.params, null, 2) }}</pre>
        </div>
      </div>

      <div class="input-actions">
        <el-button @click="stage = 'input'">返回修改</el-button>
        <el-button type="primary" :loading="isExecuting" @click="handleExecute">确认执行</el-button>
      </div>
    </div>

    <!-- Stage 3.5: Preview with Form (missing params) -->
    <div v-if="stage === 'preview-form'" class="stage-preview-form">
      <div class="ai-reply">
        <div class="reply-icon">🤖</div>
        <div class="reply-content">{{ replyText }}</div>
      </div>

      <div class="form-section">
        <DynamicParamForm
          :param-definitions="paramDefinitions"
          :initial-values="formInitialValues"
          :missing-params="missingParams.length > 0 ? missingParams : undefined"
          :loading="isExecuting"
          submit-text="确认执行"
          @submit="handleFormSubmit"
          @cancel="stage = 'input'"
        />
      </div>
    </div>

    <!-- Stage 3.5: Customer Follow-up Preview -->
    <div v-if="stage === 'preview-followup'" class="stage-preview-followup">
      <div v-if="thinkingContent" class="thinking-section">
        <div class="thinking-header">AI 思考过程</div>
        <div class="thinking-content">{{ thinkingContent }}</div>
      </div>

      <div class="followup-preview">
        <div class="preview-header">解析完成，即将创建跟进记录：</div>

        <div class="preview-item">
          <span class="preview-label">跟进内容：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.content || '无' }}</span>
        </div>
        <div class="preview-item">
          <span class="preview-label">跟进方式：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.method || '其他' }}</span>
        </div>
        <div v-if="customerFollowUpInfo?.next_action" class="preview-item">
          <span class="preview-label">下一步动作：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.next_action }}</span>
        </div>
        <div v-if="customerFollowUpInfo?.next_follow_time" class="preview-item">
          <span class="preview-label">下次跟进时间：</span>
          <span class="preview-value">{{ customerFollowUpInfo?.next_follow_time }}</span>
        </div>
      </div>

      <div class="input-actions">
        <el-button @click="stage = 'input'">返回修改</el-button>
        <el-button type="primary" :loading="isExecuting" @click="handleExecute">确认创建</el-button>
      </div>
    </div>

    <!-- Stage 4: Result -->
    <div v-if="stage === 'result'" class="stage-result">
      <el-result
        :icon="success ? 'success' : 'error'"
        :title="success ? '操作成功' : '操作失败'"
        :sub-title="resultMessage"
      >
        <template #extra>
          <el-button type="primary" @click="handleClose">关闭</el-button>
          <el-button v-if="success" @click="resetDialog">继续操作</el-button>
        </template>
      </el-result>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { aiAssistantApi, type AIAssistantSSEEvent } from '@/api/aiAssistant'
import { customerAiApi, type CustomerAIParseSSEEvent, type CustomerAIFollowUpInfo } from '@/api/customerAI'
import { useUserStore } from '@/stores/user'
import DynamicParamForm from '@/components/DynamicParamForm.vue'

interface ParamDefinition {
  label: string
  type: 'text' | 'number' | 'date' | 'select' | 'textarea'
  required: boolean
  placeholder: string
  default_value?: string
  options?: Array<{ value: string; label: string }>
}

interface Props {
  modelValue: boolean
  entityType: 'lead' | 'customer' | 'opportunity' | 'contract'
  entityId: number
  entityName: string
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const userStore = useUserStore()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const dialogTitle = computed(() => `✨ AI 操作 - ${getEntityTypeText(props.entityType)}`)

const stage = ref<'input' | 'clarify' | 'preview' | 'preview-form' | 'preview-followup' | 'result'>('input')
const userInput = ref('')
const isLoading = ref(false)
const isExecuting = ref(false)
const replyText = ref('')
const previewAction = ref<{ tool: string; params: Record<string, unknown> } | null>(null)
const success = ref(false)
const resultMessage = ref('')
const sessionId = ref('')
const lastParsedEvent = ref<AIAssistantSSEEvent | null>(null)

// Customer follow-up specific state
const customerFollowUpInfo = ref<CustomerAIFollowUpInfo | null>(null)
const thinkingContent = ref('')

// Dynamic form state
const paramDefinitions = ref<Record<string, ParamDefinition>>({})
const missingParams = ref<string[]>([])

// Computed for optional props
const formInitialValues = computed(() => previewAction.value?.params)

watch(visible, (val) => {
  if (val) {
    resetDialog()
    sessionId.value = `mw_${Date.now()}_${props.entityId}`
  }
})

function getEntityTypeText(type: string): string {
  const map: Record<string, string> = {
    lead: '线索',
    customer: '客户',
    opportunity: '商机',
    contract: '合同'
  }
  return map[type] || type
}

function buildContextMessage(content: string): string {
  // Build message with entity context
  const contextPrefix = `[当前操作对象：${getEntityTypeText(props.entityType)} "${props.entityName}"（ID: ${props.entityId}）]\n`
  return contextPrefix + content
}

async function handleSend() {
  console.log('[MagicWand] handleSend called, userInput:', userInput.value)
  if (!userInput.value.trim()) {
    ElMessage.warning('请输入操作描述')
    return
  }

  isLoading.value = true
  replyText.value = ''
  thinkingContent.value = ''

  const token = userStore.token || localStorage.getItem('token') || ''
  console.log('[MagicWand] token:', token ? 'exists' : 'empty')

  // All entity types use generic AI assistant for intent parsing
  const message = buildContextMessage(userInput.value)
  console.log('[MagicWand] message:', message)

  try {
    console.log('[MagicWand] Starting SSE request...')
    await aiAssistantApi.chatSSE(
      { content: message },
      (event: AIAssistantSSEEvent) => {
        console.log('[MagicWand] SSE event received:', event)
        handleSSEEvent(event)
      },
      token
    )
    console.log('[MagicWand] SSE request completed')
  } catch (error: unknown) {
    const err = error as Error
    console.error('[MagicWand] SSE error:', err)
    ElMessage.error(err.message || '请求失败')
    stage.value = 'input'
  } finally {
    isLoading.value = false
  }
}

async function handleCustomerFollowUp(token: string) {
  try {
    await customerAiApi.parseSSE(
      {
        content: userInput.value,
        customer_id: props.entityId,
        customer_name: props.entityName
      },
      (event: CustomerAIParseSSEEvent) => {
        switch (event.event) {
          case 'status':
            replyText.value = event.message || ''
            break
          case 'content':
            thinkingContent.value += event.content || ''
            break
          case 'parsed':
            if (event.follow_up_info) {
              customerFollowUpInfo.value = event.follow_up_info
              stage.value = 'preview-followup'
            } else {
              success.value = false
              resultMessage.value = '未能解析出跟进信息'
              stage.value = 'result'
            }
            break
          case 'error':
            success.value = false
            resultMessage.value = event.message || '解析失败'
            stage.value = 'result'
            break
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '请求失败')
    stage.value = 'input'
  } finally {
    isLoading.value = false
  }
}

function handleSSEEvent(event: AIAssistantSSEEvent) {
  switch (event.event) {
    case 'status':
      replyText.value = event.message || ''
      break

    case 'content':
      replyText.value += event.content || ''
      break

    case 'parsed':
      lastParsedEvent.value = event
      if (event.tool) {
        // Has matched tool
        previewAction.value = {
          tool: event.tool,
          params: event.params || {}
        }
        replyText.value = event.reply_text || ''

        // Check if need user confirmation
        stage.value = 'preview'
      } else if (event.reply_text) {
        // Need clarification
        replyText.value = event.reply_text
        stage.value = 'clarify'
      }
      break

    case 'result':
      // 后端返回 message 字段表示成功
      if (event.message) {
        success.value = true
        resultMessage.value = event.message
        stage.value = 'result'
        emit('refresh')
      } else if (event.success === false) {
        success.value = false
        resultMessage.value = event.message || event.reply_text || '操作失败'
        stage.value = 'result'
      } else {
        // 有 message 或 data 就视为成功
        success.value = true
        resultMessage.value = event.message || '操作已完成'
        stage.value = 'result'
        emit('refresh')
      }
      break

    case 'error':
      success.value = false
      resultMessage.value = event.message || '发生错误'
      stage.value = 'result'
      break
  }
}

async function handleExecute() {
  // Customer follow-up confirmation
  if (stage.value === 'preview-followup' && customerFollowUpInfo.value) {
    await handleCustomerFollowUpCreate()
    return
  }

  // Generic skill/action confirmation
  if (!previewAction.value) {
    ElMessage.warning('没有可执行的操作')
    return
  }

  isExecuting.value = true

  const token = userStore.token || localStorage.getItem('token') || ''

  try {
    await aiAssistantApi.chatSSE(
      {
        content: '确认执行',
        tool: previewAction.value.tool,
        params: previewAction.value.params
      },
      (event: AIAssistantSSEEvent) => {
        if (event.event === 'result' || event.event === 'error') {
          handleSSEEvent(event)
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '执行失败')
    success.value = false
    resultMessage.value = err.message || '执行失败'
    stage.value = 'result'
  } finally {
    isExecuting.value = false
  }
}

async function handleCustomerFollowUpCreate() {
  isExecuting.value = true

  try {
    await customerAiApi.create({
      customer_id: props.entityId,
      customer_name: props.entityName,
      content: customerFollowUpInfo.value?.content || userInput.value,
      method: customerFollowUpInfo.value?.method ?? undefined,
      next_action: customerFollowUpInfo.value?.next_action ?? undefined,
      next_follow_time: customerFollowUpInfo.value?.next_follow_time ?? undefined
    })

    success.value = true
    resultMessage.value = '跟进记录已创建'
    stage.value = 'result'
    emit('refresh')
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '创建失败')
    success.value = false
    resultMessage.value = err.message || '创建失败'
    stage.value = 'result'
  } finally {
    isExecuting.value = false
  }
}

async function handleFormSubmit(values: Record<string, unknown>) {
  if (!previewAction.value) {
    ElMessage.warning('没有可执行的操作')
    return
  }

  isExecuting.value = true

  // Merge form values with existing params
  const mergedParams = {
    ...previewAction.value.params,
    ...values
  }

  const token = userStore.token || localStorage.getItem('token') || ''

  try {
    await aiAssistantApi.chatSSE(
      {
        content: '确认执行',
        tool: previewAction.value.tool,
        params: mergedParams
      },
      (event: AIAssistantSSEEvent) => {
        if (event.event === 'result' || event.event === 'error') {
          handleSSEEvent(event)
        }
      },
      token
    )
  } catch (error: unknown) {
    const err = error as Error
    ElMessage.error(err.message || '执行失败')
    success.value = false
    resultMessage.value = err.message || '执行失败'
    stage.value = 'result'
  } finally {
    isExecuting.value = false
  }
}

function resetDialog() {
  stage.value = 'input'
  userInput.value = ''
  replyText.value = ''
  previewAction.value = null
  success.value = false
  resultMessage.value = ''
  isLoading.value = false
  isExecuting.value = false
  customerFollowUpInfo.value = null
  thinkingContent.value = ''
  paramDefinitions.value = {}
  missingParams.value = []
}

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.stage-input,
.stage-clarify,
.stage-preview,
.stage-result {
  padding: $wolf-space-sm 0;
}

.stage-preview-form {
  padding: $wolf-space-sm 0;

  .ai-reply {
    display: flex;
    gap: $wolf-space-sm;
    padding: $wolf-space-md;
    background: $wolf-bg-hover;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;
  }

  .reply-icon {
    font-size: 20px;
  }

  .reply-content {
    flex: 1;
    font-size: $wolf-font-size-body;
    color: $wolf-text-primary;
    line-height: 1.5;
  }

  .form-section {
    margin-top: $wolf-space-md;
  }
}

.entity-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.entity-avatar {
  width: 40px;
  height: 40px;
  border-radius: $wolf-radius-full;
  background: $wolf-primary-light;
  color: $wolf-primary;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: $wolf-font-weight-semibold;
}

.entity-meta {
  flex: 1;
}

.entity-name {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-text-primary;
}

.entity-type {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
}

.input-tip {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  margin-bottom: $wolf-space-sm;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-xs;
  margin-top: $wolf-space-md;
}

.ai-reply {
  display: flex;
  gap: $wolf-space-sm;
  padding: $wolf-space-md;
  background: $wolf-bg-hover;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.reply-icon {
  font-size: 20px;
}

.reply-content {
  flex: 1;
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  line-height: 1.5;
}

.action-preview {
  padding: $wolf-space-md;
  background: $wolf-warning-bg;
  border-radius: $wolf-radius-md;
  margin-bottom: $wolf-space-md;
}

.preview-header {
  font-size: $wolf-font-size-body;
  font-weight: $wolf-font-weight-semibold;
  color: $wolf-warning-text;
  margin-bottom: $wolf-space-sm;
}

.preview-item {
  display: flex;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-xs;
}

.preview-label {
  font-size: $wolf-font-size-caption;
  color: $wolf-text-tertiary;
  min-width: 60px;
}

.preview-value {
  font-size: $wolf-font-size-body;
  color: $wolf-text-primary;
  font-weight: $wolf-font-weight-medium;
}

.preview-params {
  margin-top: $wolf-space-sm;
}

.params-json {
  font-size: $wolf-font-size-caption;
  background: $wolf-bg-card;
  padding: $wolf-space-sm;
  border-radius: $wolf-radius-sm;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
}

.stage-preview-followup {
  padding: $wolf-space-sm 0;

  .thinking-section {
    margin-bottom: $wolf-space-md;

    .thinking-header {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      margin-bottom: $wolf-space-sm;
    }

    .thinking-content {
      padding: $wolf-space-md;
      background: $wolf-bg-hover;
      border-radius: $wolf-radius-sm;
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
      white-space: pre-wrap;
      max-height: 150px;
      overflow-y: auto;
    }
  }

  .followup-preview {
    padding: $wolf-space-md;
    background: $wolf-success-bg;
    border-radius: $wolf-radius-md;
    margin-bottom: $wolf-space-md;

    .preview-header {
      font-size: $wolf-font-size-body;
      font-weight: $wolf-font-weight-semibold;
      color: $wolf-success-text;
      margin-bottom: $wolf-space-sm;
    }

    .preview-item {
      display: flex;
      gap: $wolf-space-sm;
      margin-bottom: $wolf-space-xs;

      .preview-label {
        font-size: $wolf-font-size-caption;
        color: $wolf-text-tertiary;
        min-width: 80px;
      }

      .preview-value {
        font-size: $wolf-font-size-body;
        color: $wolf-text-primary;
        font-weight: $wolf-font-weight-medium;
      }
    }
  }
}
</style>