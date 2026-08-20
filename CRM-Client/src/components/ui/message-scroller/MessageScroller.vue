<script setup lang="ts">
import type { HTMLAttributes, StyleValue } from "vue"
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"

const props = withDefaults(defineProps<{
  class?: HTMLAttributes["class"]
  contentClass?: HTMLAttributes["class"]
  contentStyle?: StyleValue
  itemsCount?: number
  scrollKey?: number
}>(), {
  itemsCount: 0,
  scrollKey: 0,
})

const contentRef = ref<HTMLElement | null>(null)
const resizeObserver = ref<ResizeObserver | null>(null)
const keepAtBottom = ref(true)

const getViewport = (): HTMLElement | null => {
  const content = contentRef.value
  return content?.closest("[data-reka-scroll-area-viewport]") as HTMLElement | null
}

const isNearBottom = (viewport: HTMLElement): boolean => (
  viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 24
)

const handleViewportScroll = (): void => {
  const viewport = getViewport()
  if (viewport) keepAtBottom.value = isNearBottom(viewport)
}

const scrollToBottom = async (): Promise<void> => {
  await nextTick()
  const viewport = getViewport()
  if (viewport) {
    viewport.scrollTop = viewport.scrollHeight
    keepAtBottom.value = true
  }
}

const observeSizeChanges = (): void => {
  const viewport = getViewport()
  if (viewport === null || typeof ResizeObserver === "undefined") return

  viewport.addEventListener("scroll", handleViewportScroll, { passive: true })
  resizeObserver.value = new ResizeObserver(() => {
    if (keepAtBottom.value) void scrollToBottom()
  })
  resizeObserver.value.observe(viewport)
  if (contentRef.value) resizeObserver.value.observe(contentRef.value)
}

const disposeSizeChanges = (): void => {
  const viewport = getViewport()
  viewport?.removeEventListener("scroll", handleViewportScroll)
  resizeObserver.value?.disconnect()
  resizeObserver.value = null
}

watch(() => props.itemsCount, scrollToBottom, { flush: "post" })
watch(() => props.contentStyle, scrollToBottom, { flush: "post" })
watch(() => props.scrollKey, scrollToBottom, { flush: "post" })
onMounted(async () => {
  await scrollToBottom()
  observeSizeChanges()
})
onBeforeUnmount(disposeSizeChanges)
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
