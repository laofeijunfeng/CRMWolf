<template>
  <el-dialog
    v-model="visible"
    title="AI 快速跟进"
    width="500px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <!-- 第一阶段：输入 -->
    <div v-if="stage === 'input'" class="input-stage">
      <div class="entity-info">
        <span class="entity-type">{{ todoTypeDisplay }}</span>
        <span class="entity-name">{{ entityName }}</span>
      </div>

      <el-input
        v-model="userInput"
        type="textarea"
        :rows="3"
        placeholder="请描述本次跟进情况，例如：电话沟通了，客户对方案感兴趣，下周三再跟进确认报价"
        :disabled="loading"
      />

      <div class="input-actions">
        <el-button @click="handleCancel">取消</el-button>
        <el-button type="primary" @click="handleParse" :loading="loading">
          解析
        </el-button>
      </div>
    </div>

    <!-- 第二阶段：确认 -->
    <div v-if="stage === 'confirm'" class="confirm-stage">
      <div class="parse-result">
        <div class="result-header">AI 解析结果</div>

        <!-- 跟进记录 -->
        <div v-if="followUpContent" class="result-section">
          <div class="section-title">跟进记录</div>
          <div class="result-item">
            <span class="item-label">内容：</span>
            <span class="item-value">{{ followUpContent }}</span>
          </div>
          <div class="result-item">
            <span class="item-label">方式：</span>
            <span class="item-value">{{ followUpMethod }}</span>
          </div>
        </div>

        <!-- 下次跟进 -->
        <div v-if="nextFollowTime" class="result-section">
          <div class="section-title">下次跟进</div>
          <div class="result-item">
            <span class="item-label">时间：</span>
            <span class="item-value">{{ nextFollowTime }}</span>
          </div>
          <div v-if="nextAction" class="result-item">
            <span class="item-label">动作：</span>
            <span class="item-value">{{ nextAction }}</span>
          </div>
        </div>
      </div>

      <div class="ai-reply">{{ replyText }}</div>

      <div class="confirm-actions">
        <el-button @click="handleBack">返回修改</el-button>
        <el-button type="primary" @click="handleExecute" :loading="loading">
          确认执行
        </el-button>
      </div>
    </div>

    <!-- 第三阶段：结果 -->
    <div v-if="stage === 'result'" class="result-stage">
      <el-result
        :icon="executeSuccess ? 'success' : 'error'"
        :title="executeSuccess ? '跟进完成' : '跟进失败'"
        :sub-title="executeMessage"
      />

      <div class="result-actions">
        <el-button type="primary" @click="handleClose">关闭</el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { calendarApi, type ParsedAction } from '@/api/calendar'

interface Props {
  modelValue: boolean
  todoType: string
  todoId: number
  entityName: string
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'refresh'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const stage = ref<'input' | 'confirm' | 'result'>('input')
const userInput = ref('')
const loading = ref(false)

// 解析结果
const parsedActions = ref<ParsedAction[]>([])
const replyText = ref('')
const followUpContent = ref('')
const followUpMethod = ref('')
const nextFollowTime = ref('')
const nextAction = ref('')

// 执行结果
const executeSuccess = ref(false)
const executeMessage = ref('')

const todoTypeDisplay = computed(() => {
  const typeMap: Record<string, string> = {
    lead_follow_up: '线索',
    customer_follow_up: '客户',
    opportunity: '商机',
    payment_plan: '回款'
  }
  return typeMap[props.todoType] || props.todoType
})

// 重置状态
watch(visible, (val) => {
  if (val) {
    stage.value = 'input'
    userInput.value = ''
    parsedActions.value = []
    replyText.value = ''
    followUpContent.value = ''
    followUpMethod.value = ''
    nextFollowTime.value = ''
    nextAction.value = ''
    executeSuccess.value = false
    executeMessage.value = ''
  }
})

const handleCancel = () => {
  visible.value = false
}

const handleParse = async () => {
  if (!userInput.value.trim()) {
    ElMessage.warning('请输入跟进内容')
    return
  }

  loading.value = true
  try {
    const response = await calendarApi.parseFollowUp({
      todo_type: props.todoType,
      todo_id: props.todoId,
      user_input: userInput.value
    })

    parsedActions.value = response.actions
    replyText.value = response.reply_text

    // 检查是否暂不支持
    if (response.actions.length === 0) {
      ElMessage.warning(response.reply_text)
      stage.value = 'result'
      executeSuccess.value = false
      executeMessage.value = response.reply_text
      return
    }

    // 提取显示信息
    const followUpAction = response.actions.find(a => a.action === 'follow_up')
    if (followUpAction) {
      followUpContent.value = followUpAction.params.content || ''
      followUpMethod.value = followUpAction.params.method || '电话'
    }

    const nextFollowAction = response.actions.find(a => a.action === 'set_next_follow')
    if (nextFollowAction) {
      nextFollowTime.value = nextFollowAction.params.next_follow_time || ''
      nextAction.value = nextFollowAction.params.next_action || ''
    }

    stage.value = 'confirm'
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '解析失败')
  } finally {
    loading.value = false
  }
}

const handleBack = () => {
  stage.value = 'input'
}

const handleExecute = async () => {
  loading.value = true
  try {
    const response = await calendarApi.executeFollowUp({
      actions: parsedActions.value
    })

    executeSuccess.value = response.success
    executeMessage.value = response.message
    stage.value = 'result'

    if (response.success) {
      emit('refresh')
    }
  } catch (error: any) {
    executeSuccess.value = false
    executeMessage.value = error.response?.data?.detail || '执行失败'
    stage.value = 'result'
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  visible.value = false
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.entity-info {
  display: flex;
  align-items: center;
  gap: $wolf-space-sm;
  margin-bottom: $wolf-space-md;

  .entity-type {
    padding: 2px 8px;
    background: $wolf-primary-light;
    color: $wolf-primary;
    border-radius: $wolf-radius-sm;
    font-size: $wolf-font-size-caption;
  }

  .entity-name {
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-primary;
  }
}

.input-stage,
.confirm-stage,
.result-stage {
  padding: $wolf-space-md 0;
}

.input-actions,
.confirm-actions,
.result-actions {
  display: flex;
  justify-content: flex-end;
  gap: $wolf-space-sm;
  margin-top: $wolf-space-md;
}

.parse-result {
  background: $wolf-bg-elevated;
  border-radius: $wolf-radius-md;
  padding: $wolf-space-md;

  .result-header {
    font-weight: $wolf-font-weight-medium;
    color: $wolf-text-primary;
    margin-bottom: $wolf-space-md;
  }

  .result-section {
    margin-bottom: $wolf-space-md;

    .section-title {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-secondary;
      margin-bottom: $wolf-space-sm;
    }
  }

  .result-item {
    display: flex;
    align-items: flex-start;
    margin-bottom: $wolf-space-xs;

    .item-label {
      color: $wolf-text-tertiary;
      min-width: 50px;
    }

    .item-value {
      color: $wolf-text-primary;
    }
  }
}

.ai-reply {
  margin-top: $wolf-space-md;
  padding: $wolf-space-md;
  background: $wolf-primary-light;
  border-radius: $wolf-radius-md;
  color: $wolf-primary;
  font-size: $wolf-font-size-body;
}
</style>