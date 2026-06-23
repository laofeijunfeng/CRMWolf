/**
 * AI 助手 - 欢迎界面组件
 *
 * 显示欢迎信息、快捷操作按钮
 */
<template>
  <div class="welcome-screen">
    <!-- 图标 -->
    <div class="welcome-screen__icon">
      <svg
        width="48"
        height="48"
        viewBox="0 0 48 48"
        fill="none"
      >
        <rect
          x="4"
          y="4"
          width="40"
          height="40"
          rx="12"
          fill="currentColor"
          opacity="0.1"
        />
        <path
          d="M24 12C17.373 12 12 17.373 12 24C12 30.627 17.373 36 24 36C30.627 36 36 30.627 36 24C36 17.373 30.627 12 24 12Z"
          stroke="currentColor"
          stroke-width="2"
          fill="none"
        />
        <circle
          cx="24"
          cy="24"
          r="6"
          fill="currentColor"
          opacity="0.2"
        />
      </svg>
    </div>

    <!-- 标题 -->
    <h2 class="welcome-screen__title">
      有什么我可以帮助你的？
    </h2>

    <!-- 描述 -->
    <p class="welcome-screen__desc">
      描述你想做的操作，我会帮你快速完成
    </p>

    <!-- 快捷操作 -->
    <div class="welcome-screen__actions">
      <button
        v-for="action in quickActions"
        :key="action.key"
        class="welcome-screen__action-btn"
        @click="handleAction(action.key)"
      >
        {{ action.label }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// ========== Emits ==========

const emit = defineEmits<{
  (e: 'quick-action', action: string): void
}>()

// ========== Data ==========

/** 快捷操作列表 - 用户视角命名 */
const quickActions = [
  { key: 'create-customer', label: '新增一位客户' },
  { key: 'create-follow-up', label: '记一次跟进' },
  { key: 'win-opportunity', label: '签下这笔生意' },
  { key: 'query-contract', label: '找一份合同' }
]

// ========== Methods ==========

function handleAction(action: string): void {
  emit('quick-action', action)
}
</script>

<style scoped lang="scss">
@import '@/styles/variables.scss';

.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: $wolf-space-md;
  padding: $wolf-space-lg;

  // 图标
  .welcome-screen__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    border-radius: 32px;
    background-color: $wolf-primary-light;
    color: $wolf-primary;
  }

  // 标题
  .welcome-screen__title {
    font-size: 18px;
    font-weight: $wolf-font-weight-semibold;
    color: $wolf-text-primary;
    margin: 0;
    text-align: center;
  }

  // 描述
  .welcome-screen__desc {
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-text-secondary;
    margin: 0;
    text-align: center;
  }

  // 快捷操作
  .welcome-screen__actions {
    display: flex;
    flex-wrap: wrap;
    gap: $wolf-space-sm;
    justify-content: center;
    margin-top: $wolf-space-md;
  }

  .welcome-screen__action-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: $wolf-button-height-md;
    padding: $wolf-button-padding-md;
    font-size: $wolf-font-size-body;
    font-weight: $wolf-font-weight-normal;
    color: $wolf-btn-text;
    background-color: $wolf-btn-bg;
    border: 1px solid $wolf-border-default;
    border-radius: $wolf-button-radius-sm;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      background-color: $wolf-btn-bg-hover;
      border-color: $wolf-primary;
      color: $wolf-primary;
    }

    &:active {
      background-color: $wolf-btn-bg-active;
    }
  }

  // 响应式 - 小屏 2x2 网格
  @media (max-width: 480px) {
    .welcome-screen__actions {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: $wolf-space-sm;
    }

    .welcome-screen__action-btn {
      width: 100%;
    }
  }
}
</style>