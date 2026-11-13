<script setup lang="ts">
import { copyToClipboard } from '@/utils/clipboard'

interface Props {
  /** 被复制并展示的值 */
  value: string
  /** 项名，用于提示「已复制<项名>」和无障碍名称 */
  label: string
  /** 是否使用等宽字体（编号、ID、URL 默认等宽） */
  mono?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mono: true,
})

const handleClick = (): void => {
  void copyToClipboard(props.value, props.label)
}
</script>

<template>
  <button
    type="button"
    :class="[
      'copyable-text -mx-0.5 inline cursor-pointer rounded-sm px-0.5 text-left text-[hsl(var(--primary))] underline decoration-primary/40 decoration-dashed decoration-1 underline-offset-4 transition-colors [overflow-wrap:anywhere] hover:bg-primary/10 hover:decoration-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      { 'font-mono': props.mono },
    ]"
    :aria-label="`复制${props.label} ${props.value}`"
    :title="`点击复制${props.label}`"
    @click.stop="handleClick"
  >
    {{ props.value }}
  </button>
</template>
