<template>
  <div class="agent-progress">
    <!-- 执行进度列表 -->
    <div class="progress-list">
      <div
        v-for="item in executionHistory"
        :key="`${item.round}-${item.tool}`"
        class="progress-item"
        :class="{ 'success': item.result?.success, 'error': !item.result?.success }"
      >
        <div class="item-header">
          <span class="round-tag">Round {{ item.round }}</span>
          <span class="tool-name">{{ getToolDisplayName(item.tool) }}</span>
          <el-icon v-if="item.result?.success" class="status-icon success"><SuccessFilled /></el-icon>
          <el-icon v-else class="status-icon error"><CircleCloseFilled /></el-icon>
        </div>
        <div class="item-result">
          {{ item.result?.message || '执行完成' }}
        </div>
      </div>
    </div>

    <!-- 当前轮次指示 -->
    <div v-if="currentRound && !isComplete" class="current-round">
      <el-progress
        :percentage="(currentRound / maxRounds) * 100"
        :format="() => `Round ${currentRound}/${maxRounds}`"
      />
    </div>

    <!-- 等待用户确认 -->
    <div v-if="waitingForUser" class="user-confirmation">
      <div class="question-box">
        <el-icon class="question-icon"><QuestionFilled /></el-icon>
        <span class="question-text">{{ waitingForUser.question }}</span>
      </div>

      <!-- 选项选择 -->
      <div v-if="waitingForUser.options?.length" class="options-list">
        <el-radio-group v-model="selectedOption" class="options-radio">
          <el-radio
            v-for="opt in waitingForUser.options"
            :key="opt"
            :value="opt"
            :label="opt"
            class="option-item"
          >
            {{ opt }}
          </el-radio>
        </el-radio-group>
      </div>

      <!-- 缺失字段输入 -->
      <div v-if="waitingForUser.missing_fields?.length" class="missing-fields">
        <div class="fields-hint">请补充以下信息：</div>
        <el-form :model="fieldValues" class="fields-form">
          <el-form-item
            v-for="field in waitingForUser.missing_fields"
            :key="field"
            :label="getFieldLabel(field)"
          >
            <el-input
              v-model="fieldValues[field]"
              :placeholder="`请输入${getFieldLabel(field)}`"
            />
          </el-form-item>
        </el-form>
      </div>

      <!-- 上下文提示 -->
      <div v-if="waitingForUser.context_hint" class="context-hint">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ waitingForUser.context_hint }}</span>
      </div>

      <!-- 提交按钮 -->
      <div class="confirmation-actions">
        <el-button @click="handleCancel">取消</el-button>
        <el-button
          type="primary"
          :loading="isSubmitting"
          :disabled="!canSubmit"
          @click="handleSubmit"
        >
          提交
        </el-button>
      </div>
    </div>

    <!-- 完成提示 -->
    <div v-if="isComplete" class="complete-message">
      <el-icon class="complete-icon"><SuccessFilled /></el-icon>
      <span>{{ completeMessage }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { SuccessFilled, CircleCloseFilled, QuestionFilled, InfoFilled } from '@element-plus/icons-vue'
import { continueReactWithUserResponse } from '@/api/aiAssistant'

// 类型定义
interface ExecutionHistoryItem {
  round: number
  tool: string
  params?: Record<string, unknown>
  result?: {
    success: boolean
    message?: string
    data?: unknown
  }
}

interface WaitingForUserData {
  question: string
  options?: string[]
  missing_fields?: string[]
  context_hint?: string
  interaction_type?: 'select' | 'input' | 'mixed'
}

// Props
const props = defineProps<{
  sessionId?: string
  executionHistory: ExecutionHistoryItem[]
  currentRound?: number
  maxRounds: number
  waitingForUser?: WaitingForUserData | null
  isComplete?: boolean
  completeMessage?: string
  token?: string
}>()

// Emits
const emit = defineEmits<{
  (e: 'continue', response: string): void
  (e: 'cancel'): void
  (e: 'complete'): void
}>()

// State
const selectedOption = ref<string>('')
const fieldValues = ref<Record<string, string>>({})
const isSubmitting = ref(false)

// Computed
const canSubmit = computed(() => {
  if (props.waitingForUser?.options?.length) {
    return selectedOption.value.length > 0
  }
  if (props.waitingForUser?.missing_fields?.length) {
    return props.waitingForUser.missing_fields.every(
      f => fieldValues.value[f]?.length > 0
    )
  }
  return true
})

// Methods
const getToolDisplayName = (tool: string) => {
  const toolNames: Record<string, string> = {
    'follow_up_customer': '创建跟进记录',
    'create_opportunity': '创建商机',
    'win_opportunity': '标记赢单',
    'lose_opportunity': '标记输单',
    'create_contract': '创建合同',
    'create_payment_plan': '创建回款计划',
    'create_payment_record': '登记回款',
    'create_invoice_application': '申请开票',
    'get_entity_context': '获取上下文',
    'ask_user': '询问用户'
  }
  return toolNames[tool] || tool
}

const getFieldLabel = (field: string) => {
  const fieldLabels: Record<string, string> = {
    'product': '产品名称',
    'amount': '预计金额',
    'user_count': '用户数',
    'subscription_years': '订阅年限',
    'customer_name': '客户名称',
    'opportunity_name': '商机名称',
    'contract_name': '合同名称'
  }
  return fieldLabels[field] || field
}

const handleSubmit = async () => {
  isSubmitting.value = true

  // 构建用户回复
  let response = ''

  if (props.waitingForUser?.options?.length) {
    response = selectedOption.value
  } else if (props.waitingForUser?.missing_fields?.length) {
    response = Object.entries(fieldValues.value)
      .map(([k, v]) => `${getFieldLabel(k)}: ${v}`)
      .join(', ')
  }

  // 调用继续接口
  if (props.sessionId && props.token) {
    try {
      await continueReactWithUserResponse(
        props.sessionId,
        response,
        (event) => {
          // 事件处理（通过 emit 传递给父组件）
          if (event.event === 'tool_result') {
            // 添加到执行历史
            emit('continue', response)
          } else if (event.event === 'waiting_for_user') {
            // 还有问题需要回答
            emit('continue', response)
          } else if (event.event === 'result' || event.event === 'react_complete') {
            emit('complete')
          }
        },
        props.token
      )
    } catch (e) {
      console.error('继续循环失败', e)
    } finally {
      isSubmitting.value = false
    }
  } else {
    emit('continue', response)
    isSubmitting.value = false
  }
}

const handleCancel = () => {
  emit('cancel')
}

// 初始化字段值
watch(() => props.waitingForUser?.missing_fields, (fields) => {
  if (fields) {
    fieldValues.value = {}
    fields.forEach(f => {
      fieldValues.value[f] = ''
    })
  }
}, { immediate: true })

// 重置选项
watch(() => props.waitingForUser?.options, () => {
  selectedOption.value = ''
}, { immediate: true })
</script>

<style scoped lang="scss">
.agent-progress {
  .progress-list {
    max-height: 300px;
    overflow-y: auto;

    .progress-item {
      padding: 12px;
      margin-bottom: 8px;
      border-radius: 8px;
      background: #f5f7fa;

      &.success {
        background: #f0f9eb;
      }

      &.error {
        background: #fef0f0;
      }

      .item-header {
        display: flex;
        align-items: center;
        gap: 8px;

        .round-tag {
          font-size: 12px;
          color: #909399;
        }

        .tool-name {
          font-weight: 500;
        }

        .status-icon {
          margin-left: auto;

          &.success {
            color: #67c23a;
          }

          &.error {
            color: #f56c6c;
          }
        }
      }

      .item-result {
        margin-top: 8px;
        font-size: 14px;
        color: #606266;
      }
    }
  }

  .current-round {
    margin: 16px 0;
  }

  .user-confirmation {
    margin-top: 16px;
    padding: 16px;
    border-radius: 8px;
    background: #fff;
    border: 1px solid #ebeef5;

    .question-box {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;

      .question-icon {
        font-size: 20px;
        color: #409eff;
      }

      .question-text {
        font-size: 16px;
        font-weight: 500;
      }
    }

    .options-list {
      .options-radio {
        display: flex;
        flex-direction: column;
        gap: 12px;

        .option-item {
          margin-right: 0;
        }
      }
    }

    .missing-fields {
      .fields-hint {
        margin-bottom: 12px;
        font-size: 14px;
        color: #606266;
      }

      .fields-form {
        .el-form-item {
          margin-bottom: 16px;
        }
      }
    }

    .context-hint {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 12px;
      padding: 8px 12px;
      background: #f4f4f5;
      border-radius: 4px;
      font-size: 13px;
      color: #909399;
    }

    .confirmation-actions {
      margin-top: 16px;
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
  }

  .complete-message {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 24px;

    .complete-icon {
      font-size: 24px;
      color: #67c23a;
    }
  }
}
</style>