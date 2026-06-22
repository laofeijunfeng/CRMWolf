/**
 * AI 助手 - 对话气泡组件
 *
 * Signature Element: 不对称圆角 + AI 专属字体 + 智能边线
 *
 * 设计原则：
 * - 用户气泡：左下角直角 + 左侧蓝色边线 + primary-light 背景
 * - AI 气泡：右下角直角 + IBM Plex Mono 字体 + 微蓝背景 + 智能边线（← Signature）
 * - 流式响应：打字机光标 + 逐字符显现
 */
<template>
  <div
    class="chat-bubble"
    :class="[bubbleClass, { 'chat-bubble--streaming': isStreaming }]"
  >
    <!-- 用户气泡（右侧）- Signature: 左下角直角 + 左侧边线 -->
    <template v-if="role === 'user'">
      <div class="chat-bubble__content">
        <p class="chat-bubble__text">
          {{ content }}
        </p>
      </div>
      <div class="chat-bubble__avatar">
        <el-icon class="chat-bubble__avatar-icon"><User /></el-icon>
      </div>
      <span class="chat-bubble__time">{{ formattedTime }}</span>
    </template>

    <!-- AI 气泡（左侧）- Signature: 右下角直角 + 思考图标 + 呼吸动画 -->
    <template v-else>
      <!-- ← Signature: AI 思考图标 -->
      <div class="chat-bubble__ai-icon" :class="{ 'chat-bubble__ai-icon--active': isStreaming }">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <!-- 简化的脑图图标（不是 emoji） -->
          <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5" fill="none"/>
          <path d="M10 2 Q14 10 10 18 Q6 10 10 2" stroke="currentColor" stroke-width="1.5" fill="none"/>
          <circle cx="10" cy="10" r="3" fill="currentColor" opacity="0.3"/>
        </svg>
      </div>

      <div class="chat-bubble__content">
        <MarkdownContent :content="content" />
        <!-- 流式响应时的打字机光标 -->
        <span v-if="isStreaming" class="chat-bubble__cursor"></span>
        <!-- 内嵌预览卡片插槽 -->
        <slot name="preview-card" />
      </div>

      <span class="chat-bubble__time">{{ formattedTime }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import { User } from '@element-plus/icons-vue'
import MarkdownContent from './MarkdownContent.vue'

// ========== Props ==========

const props = defineProps({
  /** 角色：user 或 assistant */
  role: {
    type: String as PropType<'user' | 'assistant'>,
    required: true
  },
  /** 消息内容 */
  content: {
    type: String,
    required: true
  },
  /** 时间戳 */
  timestamp: {
    type: String,
    required: true
  },
  /** 是否正在流式输出（仅 AI 消息） */
  isStreaming: {
    type: Boolean,
    default: false
  }
})

// ========== Computed ==========

/** 气泡样式类 */
const bubbleClass = computed(() => {
  return props.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--assistant'
})

/** 格式化时间（仅显示 HH:mm） */
const formattedTime = computed(() => {
  const date = new Date(props.timestamp)
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
})
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

// ==================== Signature: Animation ====================

// 页面加载淡入动画（所有消息出现时）
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// AI 思考图标的呼吸动画（ambient atmosphere）
@keyframes pulse-subtle {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}

// 打字机光标闪烁动画（流式响应的视觉提示）
@keyframes blink {
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
}

// ← Signature: AI 思考图标在流式响应时的快速脉冲（思考中的状态）
@keyframes pulse-active {
  0%, 100% {
    opacity: 0.8;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);  // ← 更明显的放大（表示活跃思考）
  }
}

// ==================== Chat Bubble Base ====================

.chat-bubble {
  display: flex;
  align-items: flex-end;
  gap: $wolf-space-sm;
  max-width: 80%;

  // ← Signature: 消息出现时的淡入动画
  animation: fadeIn 0.3s ease-out;

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  // ========== 用户气泡（右侧）- Signature: 左下角直角 + 左侧边线 ==========

  &--user {
    flex-direction: row-reverse;
    margin-left: auto;

    .chat-bubble__content {
      // ← Signature: Primary-light 背景 + 不对称圆角（左下角直角）
      background-color: rgba($wolf-primary, 0.08);
      color: $wolf-primary;
      border-radius: $wolf-radius-lg $wolf-radius-lg $wolf-radius-sm $wolf-radius-lg;

      // ← Signature: 左侧 2px 蓝色边线（不是整个边框）
      border-left: 2px solid $wolf-primary;
      padding-left: $wolf-space-md - 2px; // 补偿边线宽度

      // ← 微妙反馈：悬停时边线加深
      transition: border-left-color 0.2s ease;

      &:hover {
        border-left-color: $wolf-primary-hover;
      }
    }

    .chat-bubble__avatar {
      background-color: $wolf-bg-active;
      color: $wolf-text-secondary;
    }

    .chat-bubble__time {
      text-align: right;
    }
  }

  // ========== AI 气泡（左侧）- Signature: 右下角直角 + 思考图标 ==========

  &--assistant {
    flex-direction: row;
    margin-right: auto;

    // ← Signature: AI 思考图标（不是 emoji，自定义 SVG）
    .chat-bubble__ai-icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      color: $wolf-primary;
      flex-shrink: 0;

      // ← Signature: Ambient animation（呼吸效果）
      animation: pulse-subtle 2s ease-in-out infinite;

      // ← Signature: 流式响应时：快速脉冲动画（思考中的状态）
      &--active {
        animation: pulse-active 1s ease-in-out infinite;  // ← 加快频率 + 更明显
        color: $wolf-primary-hover;
      }

      svg {
        width: 20px;
        height: 20px;
      }
    }

    .chat-bubble__content {
      // ← Signature: 微蓝背景（暗示智能）+ 不对称圆角（右下角直角）+ 智能边线
      background-color: $wolf-bg-ai-message;  // ← 微蓝调，不是模板暖灰
      color: $wolf-text-primary;
      border-radius: $wolf-radius-lg $wolf-radius-lg $wolf-radius-lg $wolf-radius-sm;
      padding: $wolf-space-sm $wolf-space-md;

      // ← Signature: 左侧 2px 智能边线（微蓝渐变）
      border-left: 2px solid rgba($wolf-primary, 0.3);
    }

    .chat-bubble__time {
      text-align: left;
    }
  }

  // ========== 流式响应状态 ==========

  &--streaming {
    .chat-bubble__content {
      // 流式响应时的视觉提示
      position: relative;
    }

    // ← Signature: 打字机光标（不是闪烁的点）
    .chat-bubble__cursor {
      display: inline-block;
      width: 2px;
      height: 18px;
      background-color: $wolf-primary;
      margin-left: 2px;
      vertical-align: middle;
      animation: blink 0.8s infinite;
    }
  }

  // ========== 内容区 ==========

  .chat-bubble__content {
    display: flex;
    flex-direction: column;
    padding: $wolf-space-sm $wolf-space-md;
    min-width: 60px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);  // 极轻阴影（符合设计规范）
  }

  .chat-bubble__text {
    // ← 用户消息：系统字体
    font-family: $wolf-font-family;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    line-height: $wolf-line-height-body;
    margin: 0;
    word-break: break-word;
    white-space: pre-wrap;
  }

  // ← Signature: AI 消息使用技术字体
  .chat-bubble--assistant .chat-bubble__text {
    font-family: $wolf-font-mono;  // ← AI 用 IBM Plex Mono
  }

  // ========== 用户头像 ==========

  .chat-bubble__avatar {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .chat-bubble__avatar-icon {
    font-size: 18px;
  }

  // ========== 时间 ==========

  .chat-bubble__time {
    // ← Signature: IBM Plex Mono（技术 vernacular）
    font-family: $wolf-font-mono;
    font-size: $wolf-font-size-caption;
    color: $wolf-text-placeholder;
    flex-shrink: 0;
    min-width: 40px;
  }
}

// ==================== Reduced Motion ====================
// 尊重用户的减少动画偏好

@media (prefers-reduced-motion: reduce) {
  .chat-bubble {
    animation: none;
  }

  .chat-bubble__ai-icon {
    animation: none;
    opacity: 1;
  }

  .chat-bubble__cursor {
    animation: none;
    opacity: 0.7;
  }
}
</style>