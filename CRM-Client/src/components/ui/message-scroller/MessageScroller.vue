<script setup lang="ts">
import type { HTMLAttributes, StyleValue } from "vue"
import { nextTick, ref, watch } from "vue"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"

const props = withDefaults(defineProps<{
  class?: HTMLAttributes["class"]
  contentClass?: HTMLAttributes["class"]
  contentStyle?: StyleValue
  itemsCount?: number
}>(), {
  itemsCount: 0,
})

const contentRef = ref<HTMLElement | null>(null)

const scrollToBottom = async (): Promise<void> => {
  await nextTick()
  const content = contentRef.value
  const viewport = content?.closest("[data-reka-scroll-area-viewport]") as HTMLElement | null
  if (viewport) {
    viewport.scrollTop = viewport.scrollHeight
  }
}

watch(() => props.itemsCount, scrollToBottom, { flush: "post" })
watch(() => props.contentStyle, scrollToBottom, { flush: "post" })
</script>

<template>
  <ScrollArea :class="cn('message-scroller h-full min-h-0', props.class)">
    <div
      ref="contentRef"
      :class="cn('flex min-h-full flex-col gap-wolf-md p-wolf-md', props.contentClass)"
      :style="props.contentStyle"
    >
      <slot />
    </div>
  </ScrollArea>
</template>

<style scoped>
.message-scroller {
  overflow: hidden;
}

.message-scroller :deep([data-reka-scroll-area-viewport]) {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
</style>
