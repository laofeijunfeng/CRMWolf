<template>
  <div class="empty-state">
    <!-- Cpu 图标（替代 Document） -->
    <el-icon :size="24" class="empty-icon">
      <Cpu />
    </el-icon>

    <!-- 温暖文案 -->
    <span class="welcome-text">AI 准备就绪，等待你的指令</span>

    <!-- 首次提示气泡（首次访问时显示） -->
    <div v-if="showFirstTimeTip" class="first-time-tip">
      <div class="tip-content">
        <span class="tip-icon">💡</span>
        <p>输入指令后，AI 的执行过程会在这里实时展示</p>
      </div>
      <button class="dismiss-button" @click="handleDismiss">
        知道了
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Cpu } from '@element-plus/icons-vue'

const showFirstTimeTip = ref(false)

onMounted(() => {
  // 检查 localStorage 是否已看过
  const hasSeen = localStorage.getItem('hasSeenExecutionLogTip')
  showFirstTimeTip.value = !hasSeen
})

const handleDismiss = () => {
  // 标记已看过
  localStorage.setItem('hasSeenExecutionLogTip', 'true')
  showFirstTimeTip.value = false
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: $wolf-space-lg;
  gap: $wolf-space-md;

  .empty-icon {
    color: $wolf-primary;
  }

  .welcome-text {
    font-size: $wolf-font-size-body;
    color: $wolf-text-secondary;
    font-weight: 500;
  }

  .first-time-tip {
    background: $wolf-bg-ai-message;
    border-radius: $wolf-radius-md;
    padding: $wolf-space-md;
    display: flex;
    flex-direction: column;
    gap: $wolf-space-sm;
    max-width: 400px;

    .tip-content {
      display: flex;
      align-items: start;
      gap: $wolf-space-sm;

      .tip-icon {
        font-size: 16px;
      }

      p {
        margin: 0;
        font-size: $wolf-font-size-auxiliary;
        color: $wolf-text-secondary;
      }
    }

    .dismiss-button {
      align-self: flex-end;
      padding: $wolf-space-xs $wolf-space-sm;
      background: $wolf-primary;
      color: $wolf-text-inverse;
      border: none;
      border-radius: $wolf-radius-sm;
      cursor: pointer;
      font-size: $wolf-font-size-caption;
      transition: background 0.2s;

      &:hover {
        background: $wolf-primary-hover;
      }

      &:focus-visible {
        outline: 2px solid $wolf-primary;
        outline-offset: 2px;
      }
    }
  }
}
</style>