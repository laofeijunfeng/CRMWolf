<!-- CRM-Client/src/components/ThinkingBubble.vue -->
<template>
  <div class="thinking-bubble">
    <el-icon :size="16" class="thinking-icon">
      <Cpu />
    </el-icon>
    <span class="thinking-text">{{ content }}</span>
  </div>
</template>

<script setup lang="ts">
import { Cpu } from '@element-plus/icons-vue'

interface Props {
  content: string
}

defineProps<Props>()
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.thinking-bubble {
  background: $wolf-bg-ai-message;
  border-radius: $wolf-radius-sm;
  padding: $wolf-space-sm;
  display: flex;
  align-items: flex-start;
  gap: $wolf-space-xs;

  .thinking-icon {
    color: $wolf-primary;
    flex-shrink: 0;
  }

  .thinking-text {
    font-size: $wolf-font-size-auxiliary;
    font-style: italic;
    color: $wolf-text-secondary;
    line-height: $wolf-line-height-body;
  }
}
</style>