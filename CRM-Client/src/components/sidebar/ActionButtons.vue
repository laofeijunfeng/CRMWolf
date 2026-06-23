<template>
  <div class="action-buttons-container">
    <!-- 停止操作按钮（EXECUTING 状态） -->
    <el-button
      v-if="showStop"
      type="danger"
      size="small"
      :loading="isStopping"
      @click="handleStop"
      class="action-button stop-button"
    >
      <el-icon><VideoPause /></el-icon>
      停止操作
    </el-button>

    <!-- 新对话按钮（COMPLETED 状态） -->
    <el-button
      v-if="showNewChat"
      type="primary"
      size="small"
      @click="handleNewChat"
      class="action-button new-chat-button"
    >
      <el-icon><ChatDotRound /></el-icon>
      新对话
    </el-button>

    <!-- 撤销按钮（可选，有 undoEndpoint 时显示） -->
    <el-button
      v-if="showUndoValue && undoEndpointValue"
      type="warning"
      size="small"
      plain
      :loading="isUndoing"
      @click="handleUndo"
      class="action-button undo-button"
    >
      <el-icon><RefreshLeft /></el-icon>
      撤销
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { VideoPause, ChatDotRound, RefreshLeft } from '@element-plus/icons-vue'

/**
 * ActionButtons 组件
 *
 * 用于 Sidebar 底部的操作按钮区域：
 * - 停止操作按钮（EXECUTING 状态显示）
 * - 新对话按钮（COMPLETED 状态显示）
 * - 撤销按钮（可选）
 */

// 使用 defineProps 泛型定义类型
const props = defineProps<{
  /** 是否显示停止操作按钮 */
  showStop: boolean
  /** 是否显示新对话按钮 */
  showNewChat: boolean
  /** 是否显示撤销按钮 */
  showUndo?: boolean
  /** 撤销操作的 API endpoint */
  undoEndpoint?: string
  /** 操作 ID（用于撤销） */
  operationId?: number
}>()

// 默认值处理
const showUndoValue = props.showUndo ?? false
const undoEndpointValue = props.undoEndpoint
const operationIdValue = props.operationId

const emit = defineEmits<{
  /** 停止操作事件 */
  (e: 'stop'): void
  /** 新对话事件 */
  (e: 'newChat'): void
  /** 撤销操作事件 */
  (e: 'undo'): void
  /** 撤销成功事件 */
  (e: 'undoSuccess'): void
  /** 撤销失败事件 */
  (e: 'undoFailed', reason: string): void
}>()

// 加载状态
const isStopping = ref(false)
const isUndoing = ref(false)

/**
 * 停止操作
 */
function handleStop() {
  isStopping.value = true
  emit('stop')
  // 状态由父组件管理，这里只负责触发事件
  setTimeout(() => {
    isStopping.value = false
  }, 500)
}

/**
 * 新对话
 */
function handleNewChat() {
  emit('newChat')
}

/**
 * 撤销操作
 */
async function handleUndo() {
  if (!undoEndpointValue || !operationIdValue) {
    emit('undoFailed', '缺少撤销参数')
    return
  }

  isUndoing.value = true

  try {
    const response = await fetch(undoEndpointValue, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        operation_id: operationIdValue
      })
    })

    const result = await response.json()

    if (result.success) {
      emit('undoSuccess')
    } else {
      emit('undoFailed', result.message || '撤销失败')
    }
  } catch (error) {
    const err = error as Error
    emit('undoFailed', err.message || '撤销请求失败')
  } finally {
    isUndoing.value = false
  }
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.action-buttons-container {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: $wolf-space-md;
  padding: $wolf-space-md $wolf-space-lg;
  background: $wolf-bg-card;
  border-radius: $wolf-radius-lg;
  border: 1px solid $wolf-border-light;
  box-shadow: $wolf-shadow-card;
  margin-top: $wolf-space-md;

  .action-button {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 100px;
    padding: $wolf-space-sm $wolf-space-md;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-medium;
    transition: all 0.2s ease;

    .el-icon {
      font-size: 14px;
    }

    &:hover {
      transform: translateY(-1px);
    }
  }

  // 停止按钮样式
  .stop-button {
    background: $wolf-danger-bg;
    color: $wolf-danger-text;
    border-color: $wolf-danger;

    &:hover {
      background: $wolf-danger;
      color: $wolf-bg-card;
    }
  }

  // 新对话按钮样式
  .new-chat-button {
    background: $wolf-primary;
    color: $wolf-bg-card;

    &:hover {
      background: darken($wolf-primary, 5%);
    }
  }

  // 撤销按钮样式
  .undo-button {
    background: $wolf-warning-bg;
    color: $wolf-warning-text;
    border-color: $wolf-warning;

    &:hover {
      background: $wolf-warning;
      color: $wolf-bg-card;
    }
  }
}

// 响应式适配
@media (max-width: 768px) {
  .action-buttons-container {
    padding: $wolf-space-sm $wolf-space-md;

    .action-button {
      min-width: 80px;
      font-size: $wolf-font-size-caption;
    }
  }
}
</style>