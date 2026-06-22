/**
 * AI 助手 - 输入区组件
 *
 * 消息输入框 + 发送按钮
 */
<template>
  <div class="chat-input">
    <div class="chat-input__wrapper">
      <textarea
        ref="inputRef"
        class="chat-input__textarea"
        :value="message"
        :disabled="disabled"
        :placeholder="placeholder"
        rows="1"
        @input="handleInput"
        @keydown.enter="handleEnter"
      />
      <button
        class="chat-input__send-btn"
        :disabled="disabled || !hasContent"
        @click="handleSend"
      >
        发送
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

// ========== Props ==========

const props = defineProps({
  /** 禁用状态 */
  disabled: {
    type: Boolean,
    default: false
  },
  /** placeholder */
  placeholder: {
    type: String,
    default: '有什么我可以帮助你的？'
  }
})

// ========== Emits ==========

const emit = defineEmits<{
  (e: 'send', message: string): void
}>()

// ========== State ==========

/** 输入内容 */
const message = ref('')

/** textarea ref */
const inputRef = ref<HTMLTextAreaElement | null>(null)

// ========== Computed ==========

/** 是否有内容 */
const hasContent = computed(() => {
  return message.value.trim().length > 0
})

// ========== Methods ==========

/** 输入事件 */
function handleInput(event: Event): void {
  const target = event.target as HTMLTextAreaElement
  message.value = target.value

  // 自动调整高度
  nextTick(() => {
    adjustHeight()
  })
}

/** Enter 键发送 */
function handleEnter(event: KeyboardEvent): void {
  if (event.shiftKey) return // Shift+Enter 换行

  event.preventDefault()
  handleSend()
}

/** 发送消息 */
function handleSend(): void {
  const content = message.value.trim()
  if (!content || props.disabled) return

  emit('send', content)
  message.value = ''

  // 重置高度
  nextTick(() => {
    resetHeight()
  })
}

/** 自动调整 textarea 高度 */
function adjustHeight(): void {
  const textarea = inputRef.value
  if (!textarea) return

  textarea.style.height = 'auto'
  const newHeight = Math.min(textarea.scrollHeight, 120)
  textarea.style.height = `${newHeight}px`
}

/** 重置 textarea 高度 */
function resetHeight(): void {
  const textarea = inputRef.value
  if (!textarea) return

  textarea.style.height = 'auto'
}
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.chat-input {
  width: 100%;
  max-width: 800px;

  .chat-input__wrapper {
    display: flex;
    align-items: flex-end;
    gap: $wolf-space-sm;
    padding: $wolf-space-sm;
    background-color: $wolf-bg-hover;
    border: 1px solid $wolf-border-default;
    border-radius: $wolf-radius-lg;
    transition: border-color 0.2s ease;

    &:focus-within {
      border-color: $wolf-primary;
    }
  }

  .chat-input__textarea {
    flex: 1;
    min-height: 28px;
    max-height: 120px;
    padding: $wolf-space-sm $wolf-space-md;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-text-primary;
    background-color: transparent;
    border: none;
    outline: none;
    resize: none;
    line-height: $wolf-line-height-body;

    &::placeholder {
      color: $wolf-text-placeholder;
    }

    &:disabled {
      color: $wolf-text-disabled;
      cursor: not-allowed;
    }
  }

  .chat-input__send-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: $wolf-button-height-md;
    padding: $wolf-button-padding-md;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-text-inverse;
    background-color: $wolf-primary;
    border: none;
    border-radius: $wolf-radius-sm;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      background-color: $wolf-primary-hover;
    }

    &:active:not(:disabled) {
      background-color: $wolf-primary-active;
    }

    &:disabled {
      background-color: $wolf-primary-disabled;
      cursor: not-allowed;
    }
  }
}
</style>