<script setup lang="ts">
import type { Component, HTMLAttributes } from 'vue'

import { cn } from '@/lib/utils'

type BannerTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

interface Props {
  /** 与 [data-tone] 的取值一致；底色与语气色由它派生。 */
  tone?: BannerTone
  /** 左侧语气图标，颜色继承反馈条的语气色。 */
  icon?: Component | undefined
  title?: string | null | undefined
  /** 需要立刻引起注意时用 alert，其余用 status。 */
  role?: 'alert' | 'status' | undefined
  class?: HTMLAttributes['class'] | undefined
}

const props = withDefaults(defineProps<Props>(), {
  tone: 'neutral',
  icon: undefined,
  title: null,
  role: undefined,
  class: undefined,
})
</script>

<template>
  <div
    :data-tone="tone"
    :role="role"
    :class="cn('flex min-w-0 items-start gap-space-2 rounded-md px-space-3 py-space-2', props.class)"
  >
    <span v-if="icon" class="flex h-[var(--line-height-body)] shrink-0 items-center" aria-hidden="true">
      <component :is="icon" class="size-icon-sm" />
    </span>
    <div class="grid min-w-0 flex-1 gap-space-1">
      <p v-if="title" class="m-0 text-body font-medium text-foreground">{{ title }}</p>
      <slot />
    </div>
    <div v-if="$slots['actions']" class="flex shrink-0 items-center gap-space-2 self-center text-foreground">
      <slot name="actions" />
    </div>
  </div>
</template>
