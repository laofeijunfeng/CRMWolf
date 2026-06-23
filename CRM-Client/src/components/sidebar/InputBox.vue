<template>
  <div class="input-box-container">
    <!-- 实体信息卡片（可选显示） -->
    <div class="entity-card" v-if="entityName">
      <el-icon class="entity-icon"><Cpu /></el-icon>
      <div class="entity-info">
        <span class="entity-name">{{ entityName }}</span>
        <span class="entity-type">{{ entityTypeText }}</span>
      </div>
    </div>

    <!-- 输入框主体 -->
    <div class="input-box-wrapper" :class="{ focused: isFocused, hasValue: inputValue.length > 0 }">
      <!-- 输入区域 -->
      <div class="input-area">
        <el-input
          v-model="inputValue"
          type="textarea"
          :rows="textareaRows"
          :placeholder="computedPlaceholder"
          :disabled="isLoading"
          @focus="handleFocus"
          @blur="handleBlur"
          @input="handleInputChange"
          @keydown="handleKeyDown"
          class="main-input"
          resize="none"
        />
      </div>

      <!-- 动态提示区（聚焦且无输入时显示） -->
      <Transition name="fade">
        <div class="input-hints" v-if="showHints">
          <div class="hint-title">试试这些操作：</div>
          <div class="hint-items">
            <button
              v-for="(hint, index) in dynamicHints"
              :key="index"
              class="hint-item"
              @click="insertHint(hint.command)"
            >
              <span class="hint-command">{{ hint.command }}</span>
              <span class="hint-desc">{{ hint.description }}</span>
            </button>
          </div>
        </div>
      </Transition>

      <!-- 操作按钮区 -->
      <div class="input-actions">
        <!-- 发送按钮 -->
        <el-button
          type="primary"
          :loading="isLoading"
          :disabled="!canSubmit"
          @click="handleSubmit"
          class="send-button"
        >
          <el-icon v-if="!isLoading"><Promotion /></el-icon>
          <span>{{ isLoading ? '发送中' : '发送' }}</span>
        </el-button>
      </div>
    </div>

    <!-- 快捷指令提示（底部） -->
    <div class="quick-hints-footer" v-if="!isFocused && !inputValue">
      <span class="footer-label">快捷操作：</span>
      <button
        v-for="cmd in quickCommands"
        :key="cmd.command"
        class="footer-hint"
        @click="insertHint(cmd.command)"
      >
        {{ cmd.command }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Cpu, Promotion } from '@element-plus/icons-vue'

/**
 * InputBox 组件
 *
 * 参考 ChatGPT 设计的主输入框组件：
 * - 居中布局，最大宽度 800px
 * - 聚焦时显示动态提示
 * - 符合 Design Token 规范
 */

const props = withDefaults(defineProps<{
  /** 实体名称（显示在卡片中） */
  entityName?: string
  /** 实体类型文本 */
  entityTypeText?: string
  /** Placeholder 文本 */
  placeholder?: string
  /** 是否加载中 */
  isLoading?: boolean
  /** 快捷指令列表 */
  quickCommands?: Array<{ command: string; description: string }>
  /** 动态提示列表 */
  hints?: Array<{ command: string; description: string }>
}>(), {
  entityName: '',
  entityTypeText: '',
  placeholder: '有什么我可以帮助你的？',
  isLoading: false,
  quickCommands: () => [
    { command: '/赢单', description: '标记商机赢单' },
    { command: '/跟进', description: '跟进客户' },
    { command: '/查合同', description: '查询合同' }
  ],
  hints: () => [
    { command: '创建客户张三，电话13812345678', description: '创建客户' },
    { command: '跟进客户，微信沟通产品需求', description: '跟进记录' },
    { command: '标记商机赢单，成交金额50万', description: '商机赢单' }
  ]
})

const emit = defineEmits<{
  /** 提交事件 */
  (e: 'submit', value: string): void
  /** 输入变化事件 */
  (e: 'inputChange', value: string): void
  /** 聚焦事件 */
  (e: 'focus'): void
  /** 失焦事件 */
  (e: 'blur'): void
}>()

// 状态
const inputValue = ref('')
const isFocused = ref(false)
const textareaRows = computed(() => {
  // 动态调整行数（有内容时增加）
  if (inputValue.value.length > 50) return 3
  if (inputValue.value.length > 20) return 2
  return 1
})

// 计算属性
const computedPlaceholder = computed(() => {
  return inputValue.value ? '' : props.placeholder
})

const canSubmit = computed(() => {
  return inputValue.value.trim().length > 0 && !props.isLoading
})

const showHints = computed(() => {
  return isFocused.value && inputValue.value.length === 0
})

const dynamicHints = computed(() => {
  return props.hints
})

// 方法
function handleFocus() {
  isFocused.value = true
  emit('focus')
}

function handleBlur() {
  isFocused.value = false
  emit('blur')
}

function handleInputChange(value: string) {
  emit('inputChange', value)
}

function handleKeyDown(event: KeyboardEvent) {
  // Enter 发送（非组合输入时）
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    handleSubmit()
  }
}

function handleSubmit() {
  if (!canSubmit.value) return
  emit('submit', inputValue.value.trim())
}

function insertHint(command: string) {
  inputValue.value = command + ' '
  isFocused.value = true
}

// 暴露方法供外部使用
defineExpose({
  clear: () => {
    inputValue.value = ''
  },
  focus: () => {
    isFocused.value = true
  },
  getValue: () => inputValue.value
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.input-box-container {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: $wolf-space-md;

  // ========== 实体信息卡片 ==========

  .entity-card {
    display: flex;
    align-items: center;
    gap: $wolf-space-sm;
    padding: $wolf-space-sm $wolf-space-md;
    background: $wolf-bg-card;
    border-radius: $wolf-radius-lg;
    border: 1px solid $wolf-border-light;
    box-shadow: $wolf-shadow-card;

    .entity-icon {
      font-size: 20px;
      color: $wolf-primary;
    }

    .entity-info {
      flex: 1;
      display: flex;
      align-items: center;
      gap: $wolf-space-sm;

      .entity-name {
        font-size: $wolf-font-size-body;
        font-weight: $wolf-font-weight-medium;
        color: $wolf-text-primary;
      }

      .entity-type {
        font-size: $wolf-font-size-caption;
        color: $wolf-text-tertiary;
        padding: 2px 8px;
        background: $wolf-bg-hover;
        border-radius: $wolf-radius-sm;
      }
    }
  }

  // ========== 输入框主体 ==========

  .input-box-wrapper {
    background: $wolf-bg-card;
    border-radius: $wolf-radius-xl;
    border: 1px solid $wolf-border-light;
    box-shadow: $wolf-shadow-card;
    padding: $wolf-space-md $wolf-space-lg;
    transition: all 0.3s ease;

    &:hover {
      border-color: $wolf-border-hover;
    }

    &.focused {
      border-color: $wolf-primary;
      box-shadow: 0 0 0 3px rgba($wolf-primary, 0.1), $wolf-shadow-card;
    }

    &.hasValue {
      background: $wolf-input-bg-active;
    }

    // ========== 输入区域 ==========

    .input-area {
      .main-input {
        :deep(.el-textarea__inner) {
          background: transparent;
          border: none;
          border-radius: $wolf-radius-lg;
          padding: 0;
          font-size: $wolf-font-size-body;
          color: $wolf-text-primary;
          line-height: 1.5;
          resize: none;
          min-height: 24px;
          box-shadow: none;

          &:focus {
            box-shadow: none;
          }

          &::placeholder {
            color: $wolf-text-placeholder;
            text-align: center;
          }
        }
      }
    }

    // ========== 动态提示区 ==========

    .input-hints {
      margin-top: $wolf-space-md;
      padding: $wolf-space-md;
      background: $wolf-bg-hover;
      border-radius: $wolf-radius-md;
      border: 1px solid $wolf-border-light;

      .hint-title {
        font-size: $wolf-font-size-caption;
        color: $wolf-text-tertiary;
        margin-bottom: $wolf-space-sm;
        text-align: center;
      }

      .hint-items {
        display: flex;
        flex-wrap: wrap;
        gap: $wolf-space-sm;
        justify-content: center;

        .hint-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: $wolf-space-sm $wolf-space-md;
          background: $wolf-bg-card;
          border-radius: $wolf-radius-md;
          border: 1px solid $wolf-border-light;
          cursor: pointer;
          transition: all 0.2s ease;
          text-align: left;
          min-width: 120px;

          &:hover {
            border-color: $wolf-primary;
            background: $wolf-primary-light;
          }

          .hint-command {
            font-size: $wolf-font-size-caption;
            color: $wolf-primary;
            font-weight: $wolf-font-weight-medium;
          }

          .hint-desc {
            font-size: $wolf-font-size-auxiliary;
            color: $wolf-text-tertiary;
          }
        }
      }
    }

    // ========== 操作按钮区 ==========

    .input-actions {
      display: flex;
      justify-content: flex-end;
      margin-top: $wolf-space-md;

      .send-button {
        display: flex;
        align-items: center;
        gap: 4px;
        padding: $wolf-space-sm $wolf-space-lg;
        font-size: $wolf-font-size-body;
        font-weight: $wolf-font-weight-medium;

        .el-icon {
          font-size: 14px;
        }
      }
    }
  }

  // ========== 快捷指令提示（底部） ==========

  .quick-hints-footer {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: $wolf-space-sm;

    .footer-label {
      font-size: $wolf-font-size-caption;
      color: $wolf-text-tertiary;
    }

    .footer-hint {
      font-size: $wolf-font-size-caption;
      color: $wolf-primary;
      padding: 2px 8px;
      background: $wolf-primary-light;
      border-radius: $wolf-radius-sm;
      cursor: pointer;
      transition: all 0.2s ease;
      border: none;

      &:hover {
        background: $wolf-primary;
        color: $wolf-bg-card;
      }
    }
  }
}

// ========== 过渡动画 ==========

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

// ========== 响应式适配 ==========

// 大屏（≥1200px）：居中布局，最大宽度 800px
@media (min-width: 1200px) {
  .input-box-container {
    max-width: 800px;

    .input-box-wrapper {
      padding: $wolf-space-lg $wolf-space-8;  // 24px 32px

      .input-hints {
        .hint-items {
          .hint-item {
            min-width: 140px;
          }
        }
      }
    }
  }
}

// 中屏（768px-1199px）：全宽布局
@media (max-width: 1199px) and (min-width: 768px) {
  .input-box-container {
    max-width: 100%;
    padding: $wolf-space-md;

    .entity-card {
      max-width: 600px;
      margin: 0 auto;
    }

    .input-box-wrapper {
      max-width: 600px;
      margin: 0 auto;
    }

    .quick-hints-footer {
      max-width: 600px;
      margin: 0 auto;
    }
  }
}

// 小屏（<768px）：紧凑布局
@media (max-width: 767px) {
  .input-box-container {
    max-width: 100%;
    padding: $wolf-space-sm;

    .entity-card {
      padding: $wolf-space-xs $wolf-space-sm;

      .entity-info {
        .entity-name {
          font-size: $wolf-font-size-caption;
        }
      }
    }

    .input-box-wrapper {
      padding: $wolf-space-sm $wolf-space-md;
      border-radius: $wolf-radius-lg;

      .input-hints {
        padding: $wolf-space-sm;

        .hint-items {
          .hint-item {
            min-width: 100px;
            padding: $wolf-space-xs $wolf-space-sm;

            .hint-command {
              font-size: $wolf-font-size-auxiliary;
            }

            .hint-desc {
              font-size: 10px;
            }
          }
        }
      }
    }

    .quick-hints-footer {
      flex-wrap: wrap;

      .footer-hint {
        font-size: $wolf-font-size-auxiliary;
        padding: 2px 6px;
      }
    }
  }
}

// 超小屏（<480px）：极简布局
@media (max-width: 479px) {
  .input-box-container {
    padding: $wolf-space-xs;

    .entity-card {
      display: none; // 超小屏隐藏实体卡片，节省空间
    }

    .input-box-wrapper {
      padding: $wolf-space-sm;
      border-radius: $wolf-radius-md;

      .input-hints {
        display: none; // 超小屏隐藏动态提示
      }
    }

    .quick-hints-footer {
      display: none; // 超小屏隐藏快捷指令
    }
  }
}
</style>