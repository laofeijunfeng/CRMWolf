<template>
  <div class="workflow-progress">
    <!-- 流程标题 -->
    <div v-if="workflowName" class="workflow-header">
      <span class="workflow-icon">📋</span>
      <span class="workflow-title">{{ workflowName }}</span>
      <span class="workflow-status" :class="statusClass">{{ statusText }}</span>
    </div>

    <!-- 步骤进度列表 -->
    <div class="steps-container">
      <div
        v-for="(step, index) in steps"
        :key="step.step_id"
        class="step-item"
        :class="{
          'step-completed': step.success,
          'step-current': step.step_id === currentStepId && !step.success,
          'step-error': step.error,
          'step-waiting': step.waiting
        }"
      >
        <!-- 步骤图标 -->
        <div class="step-icon">
          <span v-if="step.success">✓</span>
          <span v-else-if="step.error">✗</span>
          <span v-else-if="step.waiting">⏳</span>
          <span v-else-if="step.step_id === currentStepId">○</span>
          <span v-else>-</span>
        </div>

        <!-- 步骤内容 -->
        <div class="step-content">
          <div class="step-description">{{ step.description }}</div>
          <div v-if="step.message" class="step-message" :class="{ 'error-message': step.error }">
            {{ step.message }}
          </div>
        </div>
      </div>
    </div>

    <!-- 用户选择界面 -->
    <div v-if="waitingForUser" class="user-interaction">
      <div class="question-box">
        <div class="question-icon">💬</div>
        <div class="question-text">{{ pendingQuestion }}</div>
      </div>

      <!-- 选项列表 -->
      <div v-if="pendingOptions && pendingOptions.length > 0" class="options-list">
        <div
          v-for="(option, index) in pendingOptions"
          :key="index"
          class="option-item"
          :class="{ 'option-selected': selectedOption === option }"
          @click="selectOption(option)"
        >
          <span class="option-radio">{{ selectedOption === option ? '●' : '○' }}</span>
          <span class="option-text">{{ option }}</span>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <button
          class="btn-confirm"
          :disabled="!selectedOption && pendingOptions?.length > 0"
          @click="confirmChoice"
        >
          确认
        </button>
        <button class="btn-cancel" @click="cancelWorkflow">取消</button>
      </div>
    </div>

    <!-- 完成状态 -->
    <div v-if="workflowComplete" class="workflow-complete">
      <div class="complete-icon">🎉</div>
      <div class="complete-message">{{ completeMessage }}</div>
      <div v-if="executionSummary" class="execution-summary">
        <div v-for="step in executionSummary.completed_steps" :key="step" class="summary-item">
          ✓ {{ step }}
        </div>
      </div>
    </div>

    <!-- 错误状态 -->
    <div v-if="workflowError" class="workflow-error">
      <div class="error-icon">❌</div>
      <div class="error-message">{{ errorMessage }}</div>
      <div v-if="rollbackPerformed" class="rollback-info">
        已回滚到上一节点
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { WorkflowEvent } from '@/api/workflow'

// Props
const props = defineProps<{
  sessionId?: string
}>()

// Emits
const emit = defineEmits<{
  (e: 'continue', sessionId: string, userResponse: string): void
  (e: 'cancel', sessionId: string): void
  (e: 'complete', summary: any): void
  (e: 'error', message: string): void
}>()

// State
const workflowName = ref<string>('')
const workflowId = ref<string>('')
const sessionId = ref<string>('')
const currentStepId = ref<string>('')
const statusClass = ref<string>('')
const statusText = ref<string>('')

const steps = ref<Array<{
  step_id: string
  description: string
  success?: boolean
  error?: boolean
  waiting?: boolean
  message?: string
}>>([])

const waitingForUser = ref<boolean>(false)
const pendingQuestion = ref<string>('')
const pendingOptions = ref<string[]>([])
const pendingMetadata = ref<any>(null)
const selectedOption = ref<string>('')

const workflowComplete = ref<boolean>(false)
const completeMessage = ref<string>('')
const executionSummary = ref<any>(null)

const workflowError = ref<boolean>(false)
const errorMessage = ref<string>('')
const rollbackPerformed = ref<boolean>(false)

// Methods
function handleEvent(event: WorkflowEvent) {
  switch (event.event) {
    case 'workflow_start':
      workflowId.value = event.data.workflow_id || ''
      workflowName.value = event.data.workflow_name || ''
      sessionId.value = event.data.session_id || ''
      statusClass.value = 'status-running'
      statusText.value = '执行中'
      steps.value = []
      break

    case 'step_start':
      currentStepId.value = event.data.step_id || ''
      const stepType = event.data.step_type || ''
      const description = event.data.description || stepType

      // 添加新步骤
      steps.value.push({
        step_id: currentStepId.value,
        description,
        waiting: stepType === 'ask_user'
      })
      break

    case 'step_result':
      const lastStep = steps.value.find(s => s.step_id === event.data.step_id)
      if (lastStep) {
        lastStep.success = event.data.success
        lastStep.error = !event.data.success
        lastStep.message = event.data.success
          ? event.data.message
          : event.data.error
      }
      break

    case 'waiting_for_user':
      waitingForUser.value = true
      pendingQuestion.value = event.data.question || ''
      pendingOptions.value = event.data.options || []
      pendingMetadata.value = event.data.metadata
      selectedOption.value = ''
      break

    case 'workflow_complete':
      workflowComplete.value = true
      completeMessage.value = event.data.message || '流程执行完成'
      executionSummary.value = event.data.execution_summary
      statusClass.value = 'status-complete'
      statusText.value = '已完成'
      waitingForUser.value = false
      emit('complete', executionSummary.value)
      break

    case 'workflow_error':
      workflowError.value = true
      errorMessage.value = event.data.message || '流程执行失败'
      rollbackPerformed.value = event.data.rollback || false
      statusClass.value = 'status-error'
      statusText.value = '错误'
      waitingForUser.value = false
      emit('error', errorMessage.value)
      break

    case 'rollback':
      rollbackPerformed.value = true
      errorMessage.value = `已回滚: ${event.data.reason}`
      break
  }
}

function selectOption(option: string) {
  selectedOption.value = option
}

function confirmChoice() {
  if (!selectedOption.value && pendingOptions.value.length > 0) {
    return
  }

  const response = selectedOption.value || '确认'
  emit('continue', sessionId.value, response)
  waitingForUser.value = false
}

function cancelWorkflow() {
  emit('cancel', sessionId.value)
  waitingForUser.value = false
}

// Expose handleEvent for parent component
defineExpose({
  handleEvent,
  sessionId
})
</script>

<style scoped>
.workflow-progress {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.workflow-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.workflow-icon {
  font-size: 20px;
}

.workflow-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.workflow-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  margin-left: auto;
}

.status-running {
  background: #ecf5ff;
  color: #409eff;
}

.status-complete {
  background: #f0f9eb;
  color: #67c23a;
}

.status-error {
  background: #fef0f0;
  color: #f56c6c;
}

.steps-container {
  margin-bottom: 16px;
}

.step-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  margin-bottom: 8px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.step-completed {
  background: #f0f9eb;
  border-color: #67c23a;
}

.step-current {
  background: #ecf5ff;
  border-color: #409eff;
}

.step-error {
  background: #fef0f0;
  border-color: #f56c6c;
}

.step-waiting {
  background: #fdf6ec;
  border-color: #e6a23c;
}

.step-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #606266;
}

.step-completed .step-icon {
  color: #67c23a;
}

.step-error .step-icon {
  color: #f56c6c;
}

.step-waiting .step-icon {
  color: #e6a23c;
}

.step-content {
  flex: 1;
}

.step-description {
  font-size: 14px;
  color: #303133;
}

.step-message {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.error-message {
  color: #f56c6c;
}

.user-interaction {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  border: 2px solid #409eff;
}

.question-box {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.question-icon {
  font-size: 24px;
}

.question-text {
  font-size: 16px;
  font-weight: 500;
  color: #303133;
  flex: 1;
}

.options-list {
  margin-bottom: 16px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  margin-bottom: 8px;
  background: #f5f7fa;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
}

.option-item:hover {
  background: #ecf5ff;
}

.option-selected {
  background: #ecf5ff;
  border-color: #409eff;
}

.option-radio {
  font-size: 16px;
  color: #909399;
}

.option-selected .option-radio {
  color: #409eff;
}

.option-text {
  font-size: 14px;
  color: #303133;
}

.action-buttons {
  display: flex;
  gap: 12px;
}

.btn-confirm,
.btn-cancel {
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-confirm {
  background: #409eff;
  color: #fff;
  border: none;
}

.btn-confirm:disabled {
  background: #c0c4cc;
  cursor: not-allowed;
}

.btn-cancel {
  background: #f5f7fa;
  color: #606266;
  border: 1px solid #dcdfe6;
}

.workflow-complete {
  text-align: center;
  padding: 24px;
}

.complete-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.complete-message {
  font-size: 16px;
  font-weight: 500;
  color: #67c23a;
  margin-bottom: 16px;
}

.execution-summary {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
}

.summary-item {
  font-size: 14px;
  color: #606266;
  margin-bottom: 4px;
}

.workflow-error {
  text-align: center;
  padding: 24px;
}

.error-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.error-message {
  font-size: 16px;
  font-weight: 500;
  color: #f56c6c;
}

.rollback-info {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}
</style>