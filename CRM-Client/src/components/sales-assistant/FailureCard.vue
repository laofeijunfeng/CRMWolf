<script setup lang="ts">
import type { TaskWaiting } from '@/schemas/assistant-contracts'

/**
 * FailureCard — 场景8：写入被拒/失败。
 * 三要素：结论、原因、出路。客户未找到时给「换个名称重试 / 结束本次记录」。
 */
const props = defineProps<{
  message: string
  waiting: TaskWaiting | null
  replayed?: boolean | undefined
  busy?: boolean | undefined
}>()

const emit = defineEmits<(e: 'retry' | 'abort') => void>()

const isCustomerNotFound = props.waiting?.field === 'customer' || props.message.includes('没有找到客户') || props.message.includes('未找到对应客户')
const isWriteFailure = props.message.includes('拒绝') || isCustomerNotFound
</script>

<template>
  <div class="w-full rounded-wolf-lg border bg-card p-4 shadow-sm">
    <div class="flex items-start gap-3">
      <span class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-wolf-md" :class="isWriteFailure ? 'bg-destructive/15 text-destructive' : 'bg-muted text-muted-foreground'">
        <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>
      </span>
      <div class="min-w-0 flex-1">
        <div class="text-sm font-medium">{{ isCustomerNotFound ? '尚未写入' : isWriteFailure ? '写入未完成' : '遇到问题' }}</div>
        <p class="mt-1 text-sm text-muted-foreground">{{ message }}</p>
        <p v-if="isWriteFailure" class="mt-1.5 text-xs text-muted-foreground">整理稿已保留，处理后可再次确认。</p>
        <div v-if="isCustomerNotFound && !(replayed ?? false)" class="mt-2.5 flex flex-wrap gap-2">
          <button
            type="button"
            class="h-8 rounded-wolf-md bg-primary px-3.5 text-xs font-medium text-primary-foreground hover:bg-primary-hover"
            :disabled="busy ?? false"
            @click="emit('retry')"
          >修改客户名称</button>
          <button
            type="button"
            class="h-8 rounded-wolf-md border px-3.5 text-xs hover:bg-accent"
            :disabled="busy ?? false"
            @click="emit('abort')"
          >结束本次记录</button>
        </div>
      </div>
    </div>
  </div>
</template>
