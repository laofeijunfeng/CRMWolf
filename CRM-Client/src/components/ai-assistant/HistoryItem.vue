/**
 * AI 助手 - 历史对话项组件
 *
 * 展示单个对话历史记录，包含标题、实体类型标签、时间、删除按钮
 * Signature: Orchestrated deletion animation（精心编排的删除过程）
 */
<template>
  <div
    class="history-item"
    :class="{ active: active, deleting: isDeleting }"
    @click="handleClick"
  >
    <div class="history-item__content">
      <div class="history-item__title">
        {{ title }}
      </div>
      <div class="history-item__meta">
        <span
          v-if="entityType"
          class="history-item__tag"
          :class="tagClass"
        >
          {{ entityLabel }}
        </span>
        <span class="history-item__time">
          {{ formattedTime }}
        </span>
      </div>
    </div>

    <!-- 删除按钮（悬停时显示） -->
    <button
      class="history-item__delete-btn"
      :disabled="isDeleting"
      @click.stop="handleDelete"
      title="删除对话"
    >
      <el-icon><Delete /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PropType } from 'vue'
import { Delete } from '@element-plus/icons-vue'

// ========== Props ==========

const props = defineProps({
  /** 对话 ID */
  id: {
    type: Number,
    required: true
  },
  /** 对话标题 */
  title: {
    type: String,
    required: true
  },
  /** 实体类型 */
  entityType: {
    type: String as PropType<'customer' | 'opportunity' | 'lead' | 'contract' | null>,
    default: null
  },
  /** 创建时间 */
  createdAt: {
    type: String,
    required: true
  },
  /** 是否选中 */
  active: {
    type: Boolean,
    default: false
  }
})

// ========== Emits ==========

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'delete', id: number): void
}>()

// ========== State ==========

/** 是否正在删除（用于动画） */
const isDeleting = ref(false)

// ========== Computed ==========

/** 实体类型中文映射 */
const entityLabelMap: Record<string, string> = {
  customer: '客户',
  opportunity: '商机',
  lead: '线索',
  contract: '合同'
}

/** 实体类型标签文本 */
const entityLabel = computed(() => {
  if (!props.entityType) return ''
  return entityLabelMap[props.entityType] || props.entityType
})

/** 标签样式类 */
const tagClass = computed(() => {
  if (!props.entityType) return ''
  // 根据实体类型返回对应的标签样式
  const tagStyleMap: Record<string, string> = {
    customer: 'history-item__tag--customer',
    opportunity: 'history-item__tag--opportunity',
    lead: 'history-item__tag--lead',
    contract: 'history-item__tag--contract'
  }
  return tagStyleMap[props.entityType] || ''
})

/** 格式化时间（仅显示 HH:mm） */
const formattedTime = computed(() => {
  if (!props.createdAt) return ''
  const date = new Date(props.createdAt)
  // 检查是否为有效日期
  if (isNaN(date.getTime())) return ''
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
})

// ========== Methods ==========

function handleClick(): void {
  if (!isDeleting.value) {
    emit('select', props.id)
  }
}

async function handleDelete(): Promise<void> {
  // ← Signature: Orchestrated deletion animation
  // 1. 触发删除动画（淡出 + 折叠）
  isDeleting.value = true

  // 2. 等待动画完成（300ms）
  await new Promise(resolve => setTimeout(resolve, 300))

  // 3. 触发删除事件（父组件处理实际删除）
  emit('delete', props.id)
}
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

// ==================== Signature: Orchestrated Deletion Animation ====================

// 删除动画：淡出 + 折叠 + 缩小（精心编排的序列）
@keyframes delete-fade-out {
  0% {
    opacity: 1;
    transform: scale(1) translateX(0);
  }
  50% {
    opacity: 0.5;
    transform: scale(0.95) translateX(-8px);  // ← 向左收缩
  }
  100% {
    opacity: 0;
    transform: scale(0.8) translateX(-16px);  // ← 完全收缩
  }
}

// ==================== History Item Base ====================

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $wolf-space-sm $wolf-space-md;
  cursor: pointer;
  border-radius: $wolf-radius-md;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: $wolf-bg-hover;

    .history-item__delete-btn {
      opacity: 1;
    }
  }

  &.active {
    background-color: $wolf-bg-active;
  }

  // ← Signature: 删除状态（正在删除时的动画）
  &.deleting {
    animation: delete-fade-out 0.3s ease-out forwards;
    pointer-events: none;  // ← 防止重复点击
  }

  // 内容区
  .history-item__content {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: $wolf-space-xs;
  }

  // 标题
  .history-item__title {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-text-primary;
    line-height: $wolf-line-height-body;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  // 元信息（标签 + 时间）
  .history-item__meta {
    display: flex;
    align-items: center;
    gap: $wolf-space-xs;
  }

  // 实体类型标签
  .history-item__tag {
    display: inline-flex;
    align-items: center;
    padding: 0 $wolf-space-xs;
    height: $wolf-tag-height;
    font-size: $wolf-tag-font-size;
    font-weight: $wolf-font-weight-normal;
    border-radius: $wolf-tag-radius;
    background-color: $wolf-tag-neutral-bg;
    color: $wolf-tag-neutral-text;

    // 客户标签 - 使用主色
    &--customer {
      background-color: $wolf-primary-light;
      color: $wolf-primary;
    }

    // 商机标签 - 使用成功色
    &--opportunity {
      background-color: $wolf-tag-success-bg;
      color: $wolf-tag-success-text;
    }

    // 线索标签 - 使用警告色
    &--lead {
      background-color: $wolf-tag-warning-bg;
      color: $wolf-tag-warning-text;
    }

    // 合同标签 - 使用中性色
    &--contract {
      background-color: $wolf-tag-neutral-bg;
      color: $wolf-tag-neutral-text;
    }
  }

  // 时间
  .history-item__time {
    // ← Signature: IBM Plex Mono（技术 vernacular）
    font-family: $wolf-font-mono;
    font-size: $wolf-font-size-caption;
    color: $wolf-text-tertiary;
  }

  // 删除按钮
  .history-item__delete-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    margin-left: $wolf-space-sm;
    background-color: transparent;
    border: none;
    border-radius: $wolf-radius-sm;
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s ease;
    color: $wolf-text-tertiary;

    &:hover:not(:disabled) {
      background-color: $wolf-danger-bg;
      color: $wolf-danger-text;
      transform: scale(1.1);  // ← 微妙的放大（hover 微交互）
    }

    &:disabled {
      opacity: 0;
      cursor: not-allowed;
      transform: scale(0.9);  // ← 禁用时缩小
    }

    .el-icon {
      font-size: 14px;
    }
  }
}

// ==================== Reduced Motion ====================
// 尊重用户的减少动画偏好

@media (prefers-reduced-motion: reduce) {
  .history-item.deleting {
    animation: none;
    opacity: 0;
    transform: scale(0.8);
  }

  .history-item__delete-btn:hover {
    transform: none;  // ← 移除 hover 放大
  }
}
</style>