<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { nextTick, ref, watch } from "vue"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"

const props = withDefaults(defineProps<{
  class?: HTMLAttributes["class"]
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
</script>

<template>
  <ScrollArea :class="cn('h-full min-h-0', props.class)">
    <div ref="contentRef" class="flex min-h-full flex-col gap-wolf-md p-wolf-md">
      <slot />
    </div>
  </ScrollArea>
</template>
