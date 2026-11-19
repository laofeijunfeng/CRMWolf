<script setup lang="ts">
/**
 * ActionOptionCard — 带说明的整卡操作按钮，用于弹窗内的下一步选择。
 *
 * 每张卡片是一个独立动作（不是单选项）；loading 时显示旋转图标并设置 aria-busy。
 */
import type { Component } from 'vue'
import { computed } from 'vue'
import { ArrowRight, Loader2 } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  title: string
  description: string
  icon: Component
  variant?: 'primary' | 'default'
  loading?: boolean
  disabled?: boolean
}>(), {
  variant: 'default',
  loading: false,
  disabled: false,
})

const isPrimary = computed(() => props.variant === 'primary')
</script>

<template>
  <button
    type="button"
    :class="cn(
      'flex w-full items-center gap-3 rounded-md border px-3 py-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60',
      isPrimary ? 'bg-primary text-primary-foreground hover:bg-primary/90' : 'bg-background hover:bg-muted/60',
    )"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
  >
    <span
      :class="cn(
        'flex size-9 shrink-0 items-center justify-center rounded-md',
        isPrimary ? 'bg-primary-foreground/15' : 'bg-muted text-muted-foreground',
      )"
    >
      <Loader2 v-if="loading" class="size-4 animate-spin" aria-hidden="true" />
      <component :is="icon" v-else class="size-4" aria-hidden="true" />
    </span>
    <span class="min-w-0 flex-1">
      <span :class="cn('block text-sm font-medium', isPrimary ? '' : 'text-foreground')">{{ title }}</span>
      <span :class="cn('block text-xs', isPrimary ? 'text-primary-foreground/80' : 'text-muted-foreground')">{{ description }}</span>
    </span>
    <ArrowRight :class="cn('size-4 shrink-0', isPrimary ? 'opacity-80' : 'text-muted-foreground')" aria-hidden="true" />
  </button>
</template>
