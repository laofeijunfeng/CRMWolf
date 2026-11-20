<script setup lang="ts">
import { CircleHelp } from 'lucide-vue-next'
import HoverInfo from './HoverInfo.vue'

// 字段标签行右侧的规则说明：静态提示收进问号，悬停或聚焦时显示；校验错误仍在输入框下方直接展示。
defineProps<{ label: string }>()
</script>

<template>
  <HoverInfo side="top" align="end" content-class="max-w-64 text-caption">
    <template #trigger>
      <button
        type="button"
        class="inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :aria-label="label"
      >
        <CircleHelp class="size-3.5" aria-hidden="true" />
      </button>
    </template>
    <slot />
  </HoverInfo>
</template>
